"""pbi dax — DAX query, validate, and test commands."""

from __future__ import annotations

from pathlib import Path

import click
import yaml  # type: ignore[import-untyped]
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console(legacy_windows=False)


@click.group()
def dax() -> None:
    """Execute, validate, and unit-test DAX expressions."""


@dax.command("query")
@click.argument("expression")
@click.pass_context
def dax_query(ctx: click.Context, expression: str) -> None:
    """Execute a DAX query and return results."""
    import time as _time

    from pbi_cli.commands.trace import record_trace_event

    backend = get_backend(ctx)
    record_trace_event("QueryBegin", expression)
    t0 = _time.perf_counter()
    results = backend.dax_query(expression)
    duration_ms = (_time.perf_counter() - t0) * 1000
    record_trace_event("QueryEnd", expression, duration_ms=duration_ms)
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


@dax.command("format")
@click.option("--expression", "-e", default=None, help="Format a single DAX expression.")
@click.option("--measure", "measure_ref", default=None,
              help="Format one measure, referenced as Table[Name].")
@click.option("--all", "format_all", is_flag=True, help="Format every measure in the model.")
@click.option("--write", is_flag=True, help="Persist formatted expressions back to the model.")
@click.option("--check", is_flag=True,
              help="Exit 1 if any measure is not already formatted (CI / pre-commit gate).")
@click.option("--width", default=100, show_default=True, help="Line width before breaking args.")
@click.pass_context
def dax_format(  # noqa: PLR0913
    ctx: click.Context,
    expression: str | None,
    measure_ref: str | None,
    format_all: bool,
    write: bool,
    check: bool,
    width: int,
) -> None:
    """Format DAX (DAX Formatter conventions: uppercase functions, long-line style)."""
    from pbi_cli.dax_tools import format_dax

    if expression:
        click.echo(format_dax(expression, width=width))
        return

    backend = get_backend(ctx)
    measures = backend.measure_list()
    if measure_ref:
        import re as _re

        m = _re.match(r"^(?:'([^']+)'|([^\[]+))\[([^\]]+)\]$", measure_ref)
        if not m:
            raise click.ClickException("Use the form Table[Measure Name].")
        table, name = (m.group(1) or m.group(2)), m.group(3)
        measures = [x for x in measures if x["table"] == table and x["name"] == name]
        if not measures:
            raise click.ClickException(f"Measure {measure_ref} not found.")
    elif not format_all and not check:
        raise click.ClickException("Pass --expression, --measure, --all, or --check.")

    changed: list[dict[str, str]] = []
    for m in measures:
        formatted = format_dax(m.get("expression", ""), width=width)
        if formatted != (m.get("expression") or "").strip():
            changed.append({"table": m["table"], "name": m["name"], "formatted": formatted})

    if check:
        if changed:
            for c in changed:
                console.print(f"[yellow]needs formatting:[/yellow] {c['table']}[{c['name']}]")
            console.print(f"\n[bold]{len(changed)} of {len(measures)} measures need formatting.[/bold]")  # noqa: E501
            raise SystemExit(1)
        console.print(f"[green]All {len(measures)} measures formatted.[/green]")
        return

    for c in changed:
        if write:
            backend.measure_update(c["table"], c["name"], expression=c["formatted"])
            console.print(f"[green]formatted:[/green] {c['table']}[{c['name']}]")
        else:
            console.print(f"\n[bold]{c['table']}[{c['name']}][/bold]")
            click.echo(c["formatted"])
    if not changed:
        console.print("[green]Nothing to format.[/green]")
    elif not write:
        console.print(f"\n[dim]{len(changed)} measure(s) would change — re-run with --write.[/dim]")


@dax.command("lint")
@click.option("--expression", "-e", default=None, help="Lint a single DAX expression.")
@click.option(
    "--fail-on",
    type=click.Choice(["error", "warning", "info", "never"]),
    default="never",
    show_default=True,
    help="Exit 3 when violations at or above this severity exist (CI gate).",
)
@click.pass_context
def dax_lint(ctx: click.Context, expression: str | None, fail_on: str) -> None:
    """Static DAX analysis: DIVIDE, EARLIER, volatile functions, filter anti-patterns."""
    from pbi_cli.dax_tools import lint_expression, lint_measures

    if expression:
        violations = lint_expression("<expression>", expression)
    else:
        backend = get_backend(ctx)
        violations = lint_measures(backend.measure_list())

    output_json_or_table(violations, ctx, title="DAX Lint")
    if not violations and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No DAX lint violations.[/green]")

    rank = {"error": 3, "warning": 2, "info": 1, "never": 99}
    worst = max((rank.get(v["severity"], 0) for v in violations), default=0)
    if worst >= rank[fail_on]:
        raise SystemExit(3)


@dax.command("coverage")
@click.option(
    "--suite", "suites", multiple=True, type=click.Path(exists=True),
    help="YAML suite file or directory (repeatable). Default: ./tests/measures",
)
@click.pass_context
def dax_coverage(ctx: click.Context, suites: tuple[str, ...]) -> None:
    """Report which measures are covered by YAML test suites and which are not."""
    import re as _re

    paths: list[Path] = []
    for s in suites or (["tests/measures"] if Path("tests/measures").exists() else []):
        p = Path(s)
        paths.extend(sorted(p.glob("*.y*ml")) if p.is_dir() else [p])
    if not paths:
        raise click.ClickException("No suite files found — pass --suite.")

    referenced: set[str] = set()
    for p in paths:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for test in data.get("tests", []):
            ref = test.get("measure", "")
            m = _re.match(r"^(?:'[^']+'|[^\[]+)\[([^\]]+)\]$", ref)
            if m:
                referenced.add(m.group(1))
            for token in _re.findall(r"\[([^\]]+)\]", test.get("dax", "")):
                referenced.add(token)

    backend = get_backend(ctx)
    measures = backend.measure_list()
    covered = [m for m in measures if m["name"] in referenced]
    untested = [m for m in measures if m["name"] not in referenced]
    pct = round(100 * len(covered) / len(measures)) if measures else 100

    result = {
        "measures": len(measures),
        "covered": len(covered),
        "coverage_pct": pct,
        "untested": [f"{m['table']}[{m['name']}]" for m in untested],
    }
    output_json_or_table(result, ctx, title="DAX Test Coverage")
