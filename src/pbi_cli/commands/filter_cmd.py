"""pbi filter — add relative-date, value, and advanced filters to report pages.

Filters are written to the page's ``filterConfig`` object using the official PBIR
filterConfiguration schema (see :mod:`pbi_cli.intelligence.filter_builder`). The
previous flat ``{operator, timeUnitsCount}`` shape did not match any published
PBIR schema and is no longer produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table
from pbi_cli.intelligence import filter_builder as fb

console = Console(legacy_windows=False)


@click.group("filter")
def filter_cmd() -> None:
    """Add and manage page filters (relative-date, value, advanced)."""


def _page_json_path(pbip: str, page: str) -> Path:
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    pages = b.page_list()
    match = next((p for p in pages if p["displayName"] == page), None)
    if not match:
        raise click.ClickException(f"Page '{page}' not found.")
    report_dir = b._report_dir  # type: ignore[attr-defined]
    assert report_dir is not None
    pages_dir = report_dir / "definition" / "pages"
    for page_dir in pages_dir.iterdir():
        pj = page_dir / "page.json"
        if pj.exists():
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("displayName") == page or data.get("name") == match["name"]:
                return pj
    raise click.ClickException(f"page.json not found for page '{page}'.")


def _append_filter(page_json: Path, filter_container: dict) -> None:
    """Append a FilterContainer into the page's ``filterConfig.filters``."""
    data = json.loads(page_json.read_text(encoding="utf-8"))
    data["filterConfig"] = fb.add_filter(data.get("filterConfig"), filter_container)
    page_json.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_filters(page_json: Path) -> list[dict]:
    data = json.loads(page_json.read_text(encoding="utf-8"))
    return data.get("filterConfig", {}).get("filters", [])


@filter_cmd.command("list")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.pass_context
def filter_list(ctx: click.Context, pbip: str, page: str) -> None:
    """List all filters applied to a report page."""
    pj = _page_json_path(pbip, page)
    filters = _read_filters(pj)
    if not filters:
        console.print(f"[yellow]No filters on page '{page}'.[/yellow]")
        return
    # Project to a friendly summary rather than dumping raw FilterDefinition JSON.
    rows = [
        {
            "name": f.get("name", ""),
            "type": f.get("type", ""),
            "field": _describe_field(f.get("field", {})),
            "locked": f.get("isLockedInViewMode", False),
            "hidden": f.get("isHiddenInViewMode", False),
        }
        for f in filters
    ]
    output_json_or_table(rows, ctx, title=f"Filters on '{page}'")


def _describe_field(field: dict) -> str:
    for kind in ("Column", "Measure"):
        node = field.get(kind)
        if node:
            entity = node.get("Expression", {}).get("SourceRef", {}).get("Source", "")
            return f"{entity}.{node.get('Property', '')}" if entity else node.get("Property", "")
    return ""


@filter_cmd.command("add-relative-date")
@click.option("--pbip", required=True)
@click.option("--page", required=True, help="Page to apply filter to.")
@click.option("--table", required=True, help="Table containing the date column.")
@click.option("--column", required=True, help="Date column name.")
@click.option("--last", type=int, required=True, help="Number of time units (e.g. 30).")
@click.option(
    "--unit",
    type=click.Choice(["Days", "Weeks", "Months", "Years"]),
    default="Days",
    show_default=True,
)
@click.option(
    "--exclude-today/--include-today",
    default=False,
    show_default=True,
    help="Exclude the current period from the range.",
)
@click.option("--locked", is_flag=True, help="Lock the filter in view mode.")
@click.option("--hidden", is_flag=True, help="Hide the filter in view mode.")
@click.pass_context
def filter_add_relative_date(
    ctx: click.Context,
    pbip: str,
    page: str,
    table: str,
    column: str,
    last: int,
    unit: str,
    exclude_today: bool,
    locked: bool,
    hidden: bool,
) -> None:
    """Add a relative-date filter to a page (e.g. 'last 30 days').

    \b
    Example:
      pbi filter add-relative-date --pbip MyReport --page "Sales" \\
        --table Calendar --column Date --last 30 --unit Days
    """
    if dry_run_echo(ctx, f"add relative-date filter: last {last} {unit} on {table}[{column}]"):
        return
    fc = fb.build_relative_date_filter(
        table, column, last, unit, include_today=not exclude_today, locked=locked, hidden=hidden
    )
    pj = _page_json_path(pbip, page)
    _append_filter(pj, fc)
    console.print(
        f"[green]Filter added:[/green] last {last} {unit} on {table}[{column}] -> page '{page}'"
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")


@filter_cmd.command("add-value")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.option("--table", required=True)
@click.option("--column", required=True)
@click.option("--values", required=True, help="Comma-separated list of values.")
@click.option("--exclude", is_flag=True, help="Exclude these values instead of including them.")
@click.option("--locked", is_flag=True, help="Lock the filter in view mode.")
@click.option("--hidden", is_flag=True, help="Hide the filter in view mode.")
@click.pass_context
def filter_add_value(
    ctx: click.Context,
    pbip: str,
    page: str,
    table: str,
    column: str,
    values: str,
    exclude: bool,
    locked: bool,
    hidden: bool,
) -> None:
    """Add a categorical (value-in/-out) filter to a page.

    \b
    Example:
      pbi filter add-value --pbip MyReport --page "Sales" \\
        --table financials --column Segment --values "Enterprise,Government"
    """
    value_list = [v.strip() for v in values.split(",") if v.strip()]
    if not value_list:
        raise click.UsageError("--values must contain at least one value.")
    verb = "exclude" if exclude else "include"
    if dry_run_echo(ctx, f"add value filter: {verb} {table}[{column}] in {value_list}"):
        return
    fc = fb.build_value_filter(
        table, column, value_list, exclude=exclude, locked=locked, hidden=hidden
    )
    pj = _page_json_path(pbip, page)
    _append_filter(pj, fc)
    console.print(
        f"[green]Filter added:[/green] {verb} {table}[{column}] in {value_list} -> page '{page}'"
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")


@filter_cmd.command("add-advanced")
@click.option("--pbip", required=True)
@click.option("--page", required=True)
@click.option("--table", required=True)
@click.option("--column", required=True, help="Column or measure to filter.")
@click.option("--measure", "is_measure", is_flag=True, help="Treat --column as a DAX measure.")
@click.option(
    "--condition",
    "conditions",
    multiple=True,
    required=True,
    help="Condition as 'OP:VALUE' (e.g. '>=:1000'). Repeatable, max two.",
)
@click.option(
    "--logic",
    type=click.Choice(["And", "Or"]),
    default="And",
    show_default=True,
    help="How to join two conditions.",
)
@click.option("--locked", is_flag=True, help="Lock the filter in view mode.")
@click.option("--hidden", is_flag=True, help="Hide the filter in view mode.")
@click.pass_context
def filter_add_advanced(
    ctx: click.Context,
    pbip: str,
    page: str,
    table: str,
    column: str,
    is_measure: bool,
    conditions: tuple[str, ...],
    logic: str,
    locked: bool,
    hidden: bool,
) -> None:
    """Add an advanced numeric filter (one or two comparisons) to a page.

    \b
    Example — keep rows where Profit is between 0 and 1,000,000:
      pbi filter add-advanced --pbip MyReport --page "Sales" \\
        --table financials --column Profit \\
        --condition ">=:0" --condition "<=:1000000" --logic And
    """
    parsed: list[tuple[str, float]] = []
    for c in conditions:
        if ":" not in c:
            raise click.UsageError(f"--condition '{c}' must be 'OP:VALUE' (e.g. '>=:1000').")
        op, _, raw = c.partition(":")
        try:
            parsed.append((op.strip(), float(raw)))
        except ValueError as exc:
            raise click.UsageError(f"--condition '{c}' has a non-numeric threshold.") from exc
    if dry_run_echo(ctx, f"add advanced filter on {table}[{column}]: {parsed} ({logic})"):
        return
    try:
        fc = fb.build_advanced_filter(
            table, column, parsed, logic=logic, is_measure=is_measure, locked=locked, hidden=hidden
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    pj = _page_json_path(pbip, page)
    _append_filter(pj, fc)
    console.print(
        f"[green]Filter added:[/green] advanced {table}[{column}] {parsed} -> page '{page}'"
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")


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
    count = len(data.get("filterConfig", {}).get("filters", []))
    if "filterConfig" in data:
        data["filterConfig"]["filters"] = []
    pj.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[green]Cleared[/green] {count} filter(s) from page '{page}'.")
