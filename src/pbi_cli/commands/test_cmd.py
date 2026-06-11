"""pbi test — dbt-style declarative tests for semantic models.

Three suite types, all YAML:
  data    — row counts, nulls, uniqueness, accepted values, referential integrity
            (compiled to DAX and executed on the live backend)
  schema  — contract tests: tables/columns/measures must exist with expected types
  rls     — persona matrix: role × DAX expression × expected outcome
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import click
import yaml  # type: ignore[import-untyped]
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console()


@click.group("test")
def test_cmd() -> None:
    """Declarative data, schema-contract, and RLS test suites."""


def _quote_table(table: str) -> str:
    return f"'{table}'" if not re.fullmatch(r"[A-Za-z0-9_]+", table) else table


def _compile_data_test(t: dict[str, Any]) -> tuple[str, str]:
    """Compile one data test to (description, DAX returning a single [result] value).

    A test passes when [result] satisfies the expectation evaluated in Python.
    """
    table = t.get("table", "")
    column = t.get("column", "")
    qt = _quote_table(table)
    ref = f"{qt}[{column}]"

    if "row_count" in t or t.get("type") == "row_count":
        return (f"row count of {table}", f'EVALUATE ROW("result", COUNTROWS({qt}))')
    if t.get("type") == "not_null":
        return (
            f"{ref} has no blanks",
            f'EVALUATE ROW("result", COUNTROWS(FILTER({qt}, ISBLANK({ref}))))',
        )
    if t.get("type") == "unique":
        return (
            f"{ref} is unique",
            f'EVALUATE ROW("result", COUNTROWS({qt}) - DISTINCTCOUNT({ref}))',
        )
    if t.get("type") == "accepted_values":
        values = t.get("values", [])
        value_list = ", ".join(
            f'"{v}"' if isinstance(v, str) else str(v) for v in values
        )
        return (
            f"{ref} within accepted values",
            f'EVALUATE ROW("result", COUNTROWS(FILTER({qt}, NOT {ref} IN {{{value_list}}})))',
        )
    if t.get("type") == "relationship":
        to_table, to_column = t.get("to_table", ""), t.get("to_column", "")
        to_ref = f"{_quote_table(to_table)}[{to_column}]"
        return (
            f"{ref} → {to_ref} integrity",
            f'EVALUATE ROW("result", COUNTROWS(FILTER({qt}, '
            f"NOT {ref} IN VALUES({to_ref}) && NOT ISBLANK({ref}))))",
        )
    if t.get("type") == "expression":
        return (t.get("name", "expression test"), t["dax"])
    raise click.ClickException(f"Unknown data test type: {t}")


def _evaluate_data_test(t: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[bool, str]:
    value = None
    if rows:
        value = next(iter(rows[0].values()))
    if "row_count" in t:
        spec = t["row_count"]
        if isinstance(spec, dict):
            lo, hi = spec.get("min", 0), spec.get("max", float("inf"))
            ok = value is not None and lo <= value <= hi
            return ok, f"rows={value}, expected {lo}..{hi}"
        return value == spec, f"rows={value}, expected {spec}"
    if t.get("type") == "expression":
        expected = t.get("expected", 0)
        return value == expected, f"result={value}, expected {expected}"
    # All violation-count style tests expect 0 (BLANK() counts as 0)
    ok = value in (0, None)
    return ok, f"violations={value or 0}"


@test_cmd.command("data")
@click.option("--suite", required=True, type=click.Path(exists=True),
              help="YAML suite file or directory of suites.")
@click.pass_context
def test_data(ctx: click.Context, suite: str) -> None:
    """Run data quality tests (compiled to DAX): nulls, uniqueness, integrity, counts.

    \b
    Suite format:
      tests:
        - {table: Sales, row_count: {min: 1}}
        - {type: not_null, table: Sales, column: Revenue}
        - {type: unique, table: Customers, column: CustomerKey}
        - {type: accepted_values, table: Products, column: Category, values: [Bikes]}
        - {type: relationship, table: Sales, column: ProductKey,
           to_table: Products, to_column: ProductKey}
        - {type: expression, name: "no negative revenue", expected: 0,
           dax: 'EVALUATE ROW("r", COUNTROWS(FILTER(Sales, Sales[Revenue] < 0)))'}
    """
    backend = get_backend(ctx)
    paths = sorted(Path(suite).glob("*.y*ml")) if Path(suite).is_dir() else [Path(suite)]
    results: list[dict[str, Any]] = []
    for p in paths:
        spec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for t in spec.get("tests", []):
            description, dax_query = _compile_data_test(t)
            name = t.get("name", description)
            try:
                rows = backend.dax_query(dax_query)
                ok, detail = _evaluate_data_test(t, rows)
            except Exception as exc:
                ok, detail = False, f"query error: {exc}"
            results.append({"test": name, "status": "pass" if ok else "fail",
                            "detail": detail, "suite": p.name})

    _report_results(ctx, results, "Data Tests")


@test_cmd.command("schema")
@click.option("--contract", required=True, type=click.Path(exists=True),
              help="YAML schema contract file.")
@click.pass_context
def test_schema(ctx: click.Context, contract: str) -> None:
    """Validate the model against a schema contract (tables, columns, types, measures).

    \b
    Contract format:
      tables:
        Sales:
          columns:
            Revenue: {dataType: decimal}
            ProductKey: {}
          measures: ["Total Revenue"]
        Calendar: {}
    """
    backend = get_backend(ctx)
    spec = yaml.safe_load(Path(contract).read_text(encoding="utf-8")) or {}
    tables = {t["name"] for t in backend.table_list()}
    columns = {(c["table"], c["name"]): c for c in backend.column_list()}
    measures = {(m["table"], m["name"]) for m in backend.measure_list()}

    results: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append({"test": name, "status": "pass" if ok else "fail", "detail": detail})

    for tname, tspec in (spec.get("tables") or {}).items():
        check(f"table {tname} exists", tname in tables)
        if tname not in tables:
            continue
        for cname, cspec in ((tspec or {}).get("columns") or {}).items():
            col = columns.get((tname, cname))
            check(f"column {tname}[{cname}] exists", col is not None)
            expected_type = (cspec or {}).get("dataType")
            if col is not None and expected_type:
                actual = str(col.get("dataType", "")).lower()
                check(
                    f"column {tname}[{cname}] type",
                    actual == expected_type.lower(),
                    f"expected {expected_type}, got {col.get('dataType')}",
                )
        for mname in (tspec or {}).get("measures") or []:
            check(f"measure {tname}[{mname}] exists", (tname, mname) in measures)

    _report_results(ctx, results, "Schema Contract")


@test_cmd.command("rls")
@click.option("--matrix", required=True, type=click.Path(exists=True),
              help="YAML RLS test matrix.")
@click.pass_context
def test_rls(ctx: click.Context, matrix: str) -> None:
    """Run an RLS persona matrix: role × query × expected row count.

    \b
    Matrix format:
      personas:
        - role: Regional
          tests:
            - {dax: "EVALUATE VALUES(Sales[Region])", row_count: 1}
    """
    backend = get_backend(ctx)
    spec = yaml.safe_load(Path(matrix).read_text(encoding="utf-8")) or {}
    known_roles = {r["name"] for r in backend.role_list()} if hasattr(
        backend, "role_list") else set()

    results: list[dict[str, Any]] = []
    for persona in spec.get("personas", []):
        role = persona.get("role", "")
        if known_roles and role not in known_roles:
            results.append({"test": f"role {role} exists", "status": "fail",
                            "detail": f"role not found (model has: {sorted(known_roles)})"})
            continue
        results.append({"test": f"role {role} exists", "status": "pass", "detail": ""})
        for t in persona.get("tests", []):
            name = t.get("name", f"{role}: {t.get('dax', '')[:40]}")
            try:
                outcome = backend.role_test(role, t["dax"])
                actual = outcome.get("rowCount")
                expected = t.get("row_count")
                ok = expected is None or actual == expected
                detail = f"rows={actual}" + ("" if expected is None
                                             else f", expected {expected}")
            except Exception as exc:
                ok, detail = False, f"error: {exc}"
            results.append({"test": name, "status": "pass" if ok else "fail",
                            "detail": detail})

    _report_results(ctx, results, "RLS Matrix")


def _report_results(ctx: click.Context, results: list[dict[str, Any]], title: str) -> None:
    failed = [r for r in results if r["status"] == "fail"]
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table(
            {"summary": {"total": len(results), "passed": len(results) - len(failed),
                         "failed": len(failed)},
             "results": results}, ctx)
    else:
        for r in results:
            mark = "[green]PASS[/green]" if r["status"] == "pass" else "[red]FAIL[/red]"
            console.print(f"  {mark} {r['test']}" + (f" — {r['detail']}" if r["detail"] else ""))
        console.print(f"\n[bold]{len(results) - len(failed)} passed, "
                      f"{len(failed)} failed[/bold]")
    if failed:
        raise SystemExit(1)


@test_cmd.command("seed")
@click.option("--rows", default=100, show_default=True, help="Rows per fact table.")
@click.option("--output", "output_path", default="mock_fixture.json", show_default=True,
              type=click.Path(), help="Where to write the generated fixture.")
@click.option("--seed", "rng_seed", default=42, show_default=True)
@click.pass_context
def test_seed(ctx: click.Context, rows: int, output_path: str, rng_seed: int) -> None:
    """Generate a synthetic mock-backend fixture from the current model's schema.

    Reads the schema from the active backend (file backend works well here) and
    produces a fixture JSON with realistic fake rows for demos and tests.
    """
    import json as _json
    import random

    rng = random.Random(rng_seed)
    backend = get_backend(ctx)
    fixture: dict[str, Any] = {
        "model": backend.model_info() if hasattr(backend, "model_info") else {},
        "tables": backend.table_list(),
        "columns": backend.column_list(),
        "measures": backend.measure_list(),
        "relationships": backend.relationship_list(),
        "rows": {},
    }

    words = ["Alpha", "Beta", "Gamma", "Delta", "Omega", "North", "South", "East", "West"]
    for table in fixture["tables"]:
        tname = table["name"]
        cols = [c for c in fixture["columns"] if c["table"] == tname]
        table_rows = []
        for i in range(rows):
            row: dict[str, Any] = {}
            for c in cols:
                dtype = str(c.get("dataType", "")).lower()
                if "int" in dtype:
                    row[c["name"]] = i + 1 if c["name"].lower().endswith("key") else (
                        rng.randint(1, 1000))
                elif dtype in ("decimal", "double", "currency"):
                    row[c["name"]] = round(rng.uniform(1, 10_000), 2)
                elif "date" in dtype:
                    row[c["name"]] = f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
                else:
                    row[c["name"]] = f"{rng.choice(words)} {i + 1}"
            table_rows.append(row)
        fixture["rows"][tname] = table_rows

    Path(output_path).write_text(_json.dumps(fixture, indent=2), encoding="utf-8")
    console.print(
        f"[green]Fixture written:[/green] {output_path} "
        f"({len(fixture['tables'])} tables × {rows} rows)"
    )
