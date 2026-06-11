"""pbi pquery — Power Query (M) tooling: list, folding analysis, lint."""

from __future__ import annotations

import re
from typing import Any

import click
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console()

# M functions/steps that break query folding against relational sources
_FOLDING_BREAKERS = [
    ("Table.AddIndexColumn", "Index columns are computed locally — move filters before this."),
    ("Table.Buffer", "Buffering materializes the table in memory; nothing folds after it."),
    ("Table.TransformRows", "Row-by-row transformation never folds."),
    ("List.Generate", "Procedural list generation never folds."),
    (r"Table\.AddColumn\(.*each.*Text\.",
     "Text functions in custom columns often break folding."),
    ("Table.Combine", "Appends fold only in limited cases."),
    ("Web.Contents", "Web sources do not fold."),
    ("#table", "Inline tables are constructed locally."),
]

_NATIVE_SOURCES = {
    "Sql.Database": "SQL Server",
    "Sql.Databases": "SQL Server",
    "Fabric.Warehouse": "Fabric Warehouse",
    "Lakehouse.Contents": "Fabric Lakehouse",
    "PostgreSQL.Database": "PostgreSQL",
    "Oracle.Database": "Oracle",
    "Snowflake.Databases": "Snowflake",
    "GoogleBigQuery.Database": "BigQuery",
    "Odbc.DataSource": "ODBC",
    "Databricks.Catalogs": "Databricks",
}

_LOCAL_SOURCES = ["Excel.Workbook", "Csv.Document", "Json.Document", "Folder.Files",
                  "SharePoint.Files", "Web.Contents"]


def _queries_from_backend(backend: Any) -> list[dict[str, str]]:
    """Collect every M query: partition sources + shared expressions."""
    queries: list[dict[str, str]] = []
    for p in backend.partition_list():
        source = p.get("source", "") or ""
        if source:
            queries.append({"name": f"{p['table']} ({p['name']})", "kind": "partition",
                            "m": source})
    if hasattr(backend, "expression_list"):
        for e in backend.expression_list():
            queries.append({"name": e["name"], "kind": "shared expression",
                            "m": e.get("expression", "")})
    return queries


@click.group("pquery")
def pquery_cmd() -> None:
    """Power Query (M): list queries, folding analysis, lint."""


@pquery_cmd.command("list")
@click.pass_context
def pquery_list(ctx: click.Context) -> None:
    """List all M queries (partition sources and shared expressions)."""
    backend = get_backend(ctx)
    queries = _queries_from_backend(backend)
    rows = [{"name": q["name"], "kind": q["kind"],
             "lines": len(q["m"].splitlines())} for q in queries]
    output_json_or_table(rows, ctx, title="Power Query (M) Queries")


@pquery_cmd.command("get")
@click.argument("name")
@click.pass_context
def pquery_get(ctx: click.Context, name: str) -> None:
    """Print the M expression for one query (match by table or expression name)."""
    backend = get_backend(ctx)
    for q in _queries_from_backend(backend):
        if name.lower() in q["name"].lower():
            click.echo(q["m"])
            return
    raise click.ClickException(f"No M query matching '{name}'.")


@pquery_cmd.command("folding-check")
@click.option(
    "--fail-on-breaker", is_flag=True,
    help="Exit 3 when a folding-breaking step follows a foldable native source.",
)
@click.pass_context
def pquery_folding(ctx: click.Context, fail_on_breaker: bool) -> None:
    """Static query-folding analysis: flag steps that stop pushdown to the source."""
    backend = get_backend(ctx)
    findings: list[dict[str, str]] = []
    for q in _queries_from_backend(backend):
        m_text = q["m"]
        source_kind = next(
            (label for fn, label in _NATIVE_SOURCES.items() if fn in m_text), None)
        local = next((s for s in _LOCAL_SOURCES if s in m_text), None)
        if source_kind is None:
            if local:
                findings.append({"query": q["name"], "severity": "info",
                                 "finding": f"{local} is a non-folding source — "
                                            "folding analysis not applicable."})
            continue
        for pattern, why in _FOLDING_BREAKERS:
            if re.search(pattern, m_text):
                step = pattern.split("(")[0].split("\\(")[0].replace("\\", "")
                findings.append({
                    "query": q["name"], "severity": "warning",
                    "finding": f"{step} after a foldable {source_kind} source — {why}",
                })

    output_json_or_table(findings, ctx, title="Query Folding Analysis")
    if not findings and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No folding breakers detected.[/green]")
    if fail_on_breaker and any(f["severity"] == "warning" for f in findings):
        raise SystemExit(3)


@pquery_cmd.command("lint")
@click.pass_context
def pquery_lint(ctx: click.Context) -> None:
    """Lint M queries: hardcoded local paths, embedded credentials, server literals."""
    backend = get_backend(ctx)
    findings: list[dict[str, str]] = []
    for q in _queries_from_backend(backend):
        m_text = q["m"]
        if re.search(r"[A-Za-z]:\\\\|[A-Za-z]:/(?:Users|Temp)", m_text):
            findings.append({"query": q["name"], "rule": "pquery.local-path",
                             "severity": "error",
                             "finding": "Hardcoded local file path — breaks refresh in the "
                                        "service; use a parameter or gateway source."})
        if re.search(r"(?i)password\s*=", m_text):
            findings.append({"query": q["name"], "rule": "pquery.embedded-credentials",
                             "severity": "error",
                             "finding": "Credentials embedded in the connection string."})
        if re.search(r"(?i)(localhost|127\.0\.0\.1)", m_text):
            findings.append({"query": q["name"], "rule": "pquery.localhost-source",
                             "severity": "warning",
                             "finding": "localhost source — unreachable from the service."})
    output_json_or_table(findings, ctx, title="Power Query Lint")
    if not findings and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No Power Query lint findings.[/green]")
    if any(f["severity"] == "error" for f in findings):
        raise SystemExit(3)
