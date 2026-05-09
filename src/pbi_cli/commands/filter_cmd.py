"""pbi filter — add relative-date, TopN, and basic filters to report pages."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console()


@click.group("filter")
def filter_cmd() -> None:
    """Add and manage filters on report pages (relative-date, TopN, basic value)."""


def _page_json_path(pbip: str, page: str) -> Path:
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    pages = b.page_list()
    match = next((p for p in pages if p["displayName"] == page), None)
    if not match:
        raise click.ClickException(f"Page '{page}' not found.")
    report_dir = b._report_dir  # type: ignore[attr-defined]
    pages_dir = report_dir / "definition" / "pages"
    for page_dir in pages_dir.iterdir():
        pj = page_dir / "page.json"
        if pj.exists():
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("displayName") == page or data.get("name") == match["name"]:
                return pj
    raise click.ClickException(f"page.json not found for page '{page}'.")


def _append_filter(page_json: Path, filter_obj: dict) -> None:
    data = json.loads(page_json.read_text(encoding="utf-8"))
    filters = data.setdefault("filters", [])
    filters.append(filter_obj)
    page_json.write_text(json.dumps(data, indent=2), encoding="utf-8")


@filter_cmd.command("list")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.pass_context
def filter_list(ctx: click.Context, pbip: str, page: str) -> None:
    """List all filters applied to a report page."""
    pj = _page_json_path(pbip, page)
    data = json.loads(pj.read_text(encoding="utf-8"))
    filters = data.get("filters", [])
    if not filters:
        console.print(f"[yellow]No filters on page '{page}'.[/yellow]")
        return
    output_json_or_table(filters, ctx, title=f"Filters on '{page}'")


@filter_cmd.command("add-relative-date")
@click.option("--pbip", required=True)
@click.option("--page", required=True, help="Page to apply filter to.")
@click.option("--table", required=True, help="Table containing the date column.")
@click.option("--column", required=True, help="Date column name.")
@click.option("--last", type=int, required=True, help="Number of time units (e.g. 30).")
@click.option("--unit", type=click.Choice(["Days", "Weeks", "Months", "Quarters", "Years"]),
              default="Days", show_default=True)
@click.pass_context
def filter_add_relative_date(
    ctx: click.Context,
    pbip: str, page: str,
    table: str, column: str,
    last: int, unit: str,
) -> None:
    """Add a relative-date filter to a page (e.g. 'last 30 days').

    \b
    Example:
      pbi filter add-relative-date --pbip MyReport --page "Sales" \\
        --table Calendar --column Date --last 30 --unit Days
    """
    if dry_run_echo(ctx, f"add relative-date filter: last {last} {unit} on {table}[{column}]"):
        return

    filter_obj = {
        "type": "RelativeDate",
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "operator": "InTheLast",
        "timeUnitsCount": last,
        "timeUnitType": unit,
    }

    pj = _page_json_path(pbip, page)
    _append_filter(pj, filter_obj)
    console.print(f"[green]Filter added:[/green] last {last} {unit} on {table}[{column}] -> page '{page}'")


@filter_cmd.command("add-topn")
@click.option("--pbip", required=True)
@click.option("--page", required=True, help="Page to apply filter to.")
@click.option("--table", required=True, help="Table containing the category field.")
@click.option("--column", required=True, help="Column to filter (e.g. Product).")
@click.option("--n", type=int, required=True, help="Number of top items to keep.")
@click.option("--by-table", required=True, help="Table containing the measure to order by.")
@click.option("--by-measure", required=True, help="Measure name to order by (e.g. Total Sales).")
@click.option("--direction", type=click.Choice(["Top", "Bottom"]), default="Top", show_default=True)
@click.pass_context
def filter_add_topn(
    ctx: click.Context,
    pbip: str, page: str,
    table: str, column: str,
    n: int,
    by_table: str, by_measure: str,
    direction: str,
) -> None:
    """Add a TopN filter to keep only the top (or bottom) N items by a measure.

    \b
    Example:
      pbi filter add-topn --pbip MyReport --page "Sales" \\
        --table Products --column Product --n 10 \\
        --by-table Sales --by-measure "Total Sales"
    """
    if dry_run_echo(ctx, f"add TopN filter: {direction} {n} {table}[{column}] by {by_measure}"):
        return

    operator = "TopCount" if direction == "Top" else "BottomCount"
    filter_obj = {
        "type": "TopN",
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "operator": operator,
        "itemCount": {"Literal": {"Value": str(n)}},
        "orderByField": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": by_table}},
                "Property": by_measure,
            }
        },
    }

    pj = _page_json_path(pbip, page)
    _append_filter(pj, filter_obj)
    console.print(f"[green]Filter added:[/green] {direction} {n} {table}[{column}] by '{by_measure}' -> page '{page}'")


@filter_cmd.command("add-value")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.option("--table", required=True)
@click.option("--column", required=True)
@click.option("--values", required=True, help="Comma-separated list of values to include.")
@click.pass_context
def filter_add_value(
    ctx: click.Context,
    pbip: str, page: str,
    table: str, column: str,
    values: str,
) -> None:
    """Add a basic value-in filter to a page.

    \b
    Example:
      pbi filter add-value --pbip MyReport --page "Sales" \\
        --table financials --column Segment --values "Enterprise,Government"
    """
    if dry_run_echo(ctx, f"add value filter: {table}[{column}] in [{values}]"):
        return

    value_list = [v.strip() for v in values.split(",") if v.strip()]
    filter_conditions = [
        {"operator": "Is", "value": {"Literal": {"Value": f"'{v}'"}}}
        for v in value_list
    ]

    filter_obj = {
        "type": "BasicFilter",
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "operator": "In",
        "values": filter_conditions,
    }

    pj = _page_json_path(pbip, page)
    _append_filter(pj, filter_obj)
    console.print(f"[green]Filter added:[/green] {table}[{column}] in {value_list} -> page '{page}'")


@filter_cmd.command("clear")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.pass_context
def filter_clear(ctx: click.Context, pbip: str, page: str) -> None:
    """Remove all filters from a report page."""
    if dry_run_echo(ctx, f"clear all filters from page '{page}'"):
        return
    pj = _page_json_path(pbip, page)
    data = json.loads(pj.read_text(encoding="utf-8"))
    count = len(data.get("filters", []))
    data["filters"] = []
    pj.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[green]Cleared[/green] {count} filter(s) from page '{page}'.")
