"""pbi dax — DAX query, validate, and test commands."""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console()


@click.group()
def dax() -> None:
    """Execute, validate, and unit-test DAX expressions."""


@dax.command("query")
@click.argument("expression")
@click.pass_context
def dax_query(ctx: click.Context, expression: str) -> None:
    """Execute a DAX query and return results."""
    backend = get_backend(ctx)
    results = backend.dax_query(expression)
    output_json_or_table(results, ctx, title="DAX Results")


@dax.command("validate")
@click.argument("expression")
@click.pass_context
def dax_validate(ctx: click.Context, expression: str) -> None:
    """Validate a DAX expression syntax without executing."""
    backend = get_backend(ctx)
    result = backend.dax_validate(expression)
    if result.get("valid"):
        console.print("[green]Valid DAX expression.[/green]")
    else:
        console.print(f"[red]Invalid:[/red] {result.get('error', 'Unknown error')}")


@dax.command("test")
@click.option(
    "--suite", required=True, type=click.Path(exists=True), help="Path to YAML test suite."
)
@click.pass_context
def dax_test(ctx: click.Context, suite: str) -> None:
    """Run DAX unit tests from a YAML fixture file."""
    import math

    data = yaml.safe_load(Path(suite).read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    console.print(f"[cyan]Running suite:[/cyan] {suite} ({len(tests)} tests)\n")
    backend = get_backend(ctx)
    passed = 0
    failed = 0

    for test in tests:
        name = test["name"]
        dax_expr = test.get("dax", "").strip()
        asserts = test.get("assert", [])
        try:
            rows = backend.dax_query(dax_expr)
        except Exception as exc:
            console.print(f"  [red]FAIL[/red] {name}")
            console.print(f"       Query error: {exc}")
            failed += 1
            continue

        test_failed = False
        fail_reasons: list[str] = []

        for assertion in asserts:
            # row_count: exact number of rows
            if "row_count" in assertion:
                expected_count = assertion["row_count"]
                if len(rows) != expected_count:
                    fail_reasons.append(f"row_count: expected {expected_count}, got {len(rows)}")
                    test_failed = True

            # min_rows
            if "min_rows" in assertion:
                if len(rows) < assertion["min_rows"]:
                    fail_reasons.append(
                        f"min_rows: expected >= {assertion['min_rows']}, got {len(rows)}"
                    )
                    test_failed = True

            # max_rows
            if "max_rows" in assertion:
                if len(rows) > assertion["max_rows"]:
                    fail_reasons.append(
                        f"max_rows: expected <= {assertion['max_rows']}, got {len(rows)}"
                    )
                    test_failed = True

            col = assertion.get("column")
            row_idx = assertion.get("row", 0)

            if col and rows:
                # Get column values (rows is list of dicts)
                col_values = [r.get(col) for r in rows if col in r]

                # not_blank
                if assertion.get("not_blank"):
                    blanks = [
                        v
                        for v in col_values
                        if v is None or (isinstance(v, float) and math.isnan(v))
                    ]
                    if blanks:
                        fail_reasons.append(
                            f"not_blank: column '{col}' has {len(blanks)} blank values"
                        )
                        test_failed = True

                # all_rows_between
                if "all_rows_between" in assertion:
                    lo, hi = assertion["all_rows_between"]
                    out_of_range = [
                        v
                        for v in col_values
                        if v is not None and not math.isnan(float(v)) and not (lo <= float(v) <= hi)
                    ]
                    if out_of_range:
                        fail_reasons.append(
                            f"all_rows_between [{lo},{hi}]: {len(out_of_range)} values out of range"
                        )
                        test_failed = True

                # expected: value at specific row
                if "expected" in assertion and row_idx < len(rows):
                    actual = rows[row_idx].get(col)
                    expected = assertion["expected"]
                    tolerance = assertion.get("tolerance", 0)
                    if actual is None:
                        fail_reasons.append(f"expected {expected} in '{col}'[{row_idx}], got None")
                        test_failed = True
                    elif tolerance:
                        tol_abs = abs(expected) * tolerance if tolerance < 1 else tolerance
                        if abs(float(actual) - expected) > tol_abs:
                            fail_reasons.append(
                                f"expected {expected} ± {tol_abs} in '{col}'[{row_idx}], got {actual}"  # noqa: E501
                            )
                            test_failed = True
                    elif actual != expected:
                        fail_reasons.append(
                            f"expected {expected!r} in '{col}'[{row_idx}], got {actual!r}"
                        )
                        test_failed = True

                # expected_string
                if "expected_string" in assertion and row_idx < len(rows):
                    actual = rows[row_idx].get(col)
                    if str(actual) != assertion["expected_string"]:
                        fail_reasons.append(
                            f"expected '{assertion['expected_string']}' in '{col}'[{row_idx}], got '{actual}'"  # noqa: E501
                        )
                        test_failed = True

        if test_failed:
            console.print(f"  [red]FAIL[/red] {name}")
            for reason in fail_reasons:
                console.print(f"       {reason}")
            failed += 1
        else:
            console.print(f"  [green]PASS[/green] {name}")
            passed += 1

    console.print(f"\n[bold]{passed} passed, {failed} failed[/bold] out of {len(tests)} tests")
    if failed:
        raise SystemExit(1)
