"""pbi report — manage pages and scaffold full reports in .pbip projects."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console()


@click.group()
def report() -> None:
    """Manage report pages and scaffold complete reports from .pbip projects."""


# ── Pages ──────────────────────────────────────────────────────────────────────

@report.command("pages")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.pass_context
def report_pages(ctx: click.Context, pbip: str) -> None:
    """List all pages in a .pbip report."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    pages = b.page_list()
    if not pages:
        console.print("[yellow]No pages found.[/yellow]")
        return
    output_json_or_table(pages, ctx, title="Report Pages")


@report.command("page-add")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name for the new page.")
@click.pass_context
def report_page_add(ctx: click.Context, pbip: str, name: str) -> None:
    """Add a blank page to a .pbip report."""
    if dry_run_echo(ctx, f"add page '{name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    result = b.page_add(name)
    console.print(f"[green]Page added:[/green] '{name}'  (id: {result['name']})")


@report.command("page-delete")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name of the page to delete.")
@click.pass_context
def report_page_delete(ctx: click.Context, pbip: str, name: str) -> None:
    """Delete a page from a .pbip report."""
    if dry_run_echo(ctx, f"delete page '{name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.page_delete(name)
    console.print(f"[green]Deleted[/green] page '{name}'.")


@report.command("clear-page")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name to clear.")
@click.pass_context
def report_clear_page(ctx: click.Context, pbip: str, page: str) -> None:
    """Remove all visuals from a page."""
    if dry_run_echo(ctx, f"clear all visuals on page '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.page_clear(page)
    console.print(f"[green]Cleared[/green] all visuals on '{page}'.")


# ── Scaffold ───────────────────────────────────────────────────────────────────

@report.command("scaffold")
@click.option("--pbip",    required=True, help="Path to the .pbip project folder or file.")
@click.option("--model",   default="financials",
              help="Semantic model table name containing the data (default: financials).")
@click.option("--pages",   default=3, show_default=True, help="Number of pages to create (1-3).")
@click.option("--replace", is_flag=True, help="Delete existing pages before scaffolding.")
@click.pass_context
def report_scaffold(
    ctx: click.Context, pbip: str, model: str, pages: int, replace: bool
) -> None:
    """Scaffold a complete multi-page report in a .pbip project.

    Creates up to 3 pages with pre-built visuals tailored for the
    Financials sample model (or any model with Sales/Profit columns).

    \b
    Prerequisites:
      1. Open your .pbix in Power BI Desktop
      2. File → Save as → Power BI project (.pbip)
      3. Run this command pointing at the saved .pbip folder
      4. Power BI Desktop will prompt to reload — click Reload

    \b
    Example:
      pbi report scaffold --pbip "C:/Users/Me/Reports/Financials.pbip"
    """
    if dry_run_echo(ctx, f"scaffold {pages}-page report in '{pbip}'", f"model table: {model}"):
        return

    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.intelligence.visual_builder import (
        FieldDef, VisualSpec,
        build_card, build_bar_chart, build_column_chart,
        build_line_chart, build_slicer, build_table, build_multi_row_card,
        AGG_SUM, AGG_COUNT,
    )

    b = PbirBackend(pbip)
    console.print(f"[cyan]PBIP format:[/cyan] {b.format}")
    console.print(f"[cyan]Report dir:[/cyan] {b.report_dir}")

    if replace:
        for p in b.page_list():
            b.page_delete(p["displayName"])
        console.print("[yellow]Existing pages cleared.[/yellow]")

    # ── Helpers ──────────────────────────────────────────────────────────────
    def field(prop: str, is_measure: bool = False, agg: int | None = AGG_SUM) -> FieldDef:
        return FieldDef(entity=model, property=prop, is_measure=is_measure, agg=agg)

    def col(prop: str) -> FieldDef:
        """Plain column, no aggregation."""
        return FieldDef(entity=model, property=prop, is_measure=False, agg=None)

    def add(page_name: str, spec: VisualSpec) -> None:
        b.visual_add(page_name, spec)

    GUTTER = 16
    CARD_W, CARD_H = 280, 120
    CHART_W, CHART_H = 600, 360
    SLIM_W, SLIM_H = 580, 360
    SLICER_W, SLICER_H = 200, 360
    TABLE_W, TABLE_H = 1248, 300

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 — Executive Summary
    # Layout:
    #   Row 1 (y=16):  [Card Sales][Card Profit][Card Units][Card Margin]
    #   Row 2 (y=152): [Bar Sales by Country (600)][Slicer Year (200)][Line Sales by Month (600)]
    # ════════════════════════════════════════════════════════════════════════
    if pages >= 1:
        PAGE = "Executive Summary"
        console.print(f"\n[bold]Page 1:[/bold] {PAGE}")
        b.page_add(PAGE)

        # Row 1: KPI cards
        cards = [
            ("Sales",  field("Sales"),           "Total Sales"),
            ("Profit", field("Profit"),          "Total Profit"),
            ("Units",  field("Units Sold"),      "Units Sold"),
            ("COGS",   field("COGS"),            "Total COGS"),
        ]
        for i, (_, value_field, title) in enumerate(cards):
            add(PAGE, VisualSpec(
                visual_type="card",
                visual_body=build_card(value_field),
                x=GUTTER + i * (CARD_W + GUTTER),
                y=GUTTER,
                width=CARD_W, height=CARD_H,
                title=title,
            ))

        y2 = GUTTER + CARD_H + GUTTER
        # Sales by Country bar
        add(PAGE, VisualSpec(
            visual_type="barChart",
            visual_body=build_bar_chart(col("Country"), field("Sales")),
            x=GUTTER, y=y2,
            width=CHART_W, height=CHART_H,
            title="Sales by Country",
        ))
        # Year slicer
        add(PAGE, VisualSpec(
            visual_type="slicer",
            visual_body=build_slicer(col("Year")),
            x=GUTTER + CHART_W + GUTTER, y=y2,
            width=SLICER_W, height=CHART_H,
            title="Year",
        ))
        # Sales by Month line
        add(PAGE, VisualSpec(
            visual_type="lineChart",
            visual_body=build_line_chart(col("Month Name"), field("Sales")),
            x=GUTTER + CHART_W + GUTTER + SLICER_W + GUTTER, y=y2,
            width=SLIM_W, height=CHART_H,
        ))
        console.print(f"  [green]OK[/green] {len(cards) + 3} visuals")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — Sales Analysis
    # Layout:
    #   Row 1: [Bar Segment (600)] [Bar Product (600)]
    #   Row 2: [Table: Segment/Country/Product/Sales/Profit (full width)]
    # ════════════════════════════════════════════════════════════════════════
    if pages >= 2:
        PAGE = "Sales Analysis"
        console.print(f"\n[bold]Page 2:[/bold] {PAGE}")
        b.page_add(PAGE)

        add(PAGE, VisualSpec(
            visual_type="barChart",
            visual_body=build_bar_chart(col("Segment"), field("Sales")),
            x=GUTTER, y=GUTTER,
            width=CHART_W, height=CHART_H,
            title="Sales by Segment",
        ))
        add(PAGE, VisualSpec(
            visual_type="barChart",
            visual_body=build_bar_chart(col("Product"), field("Sales")),
            x=GUTTER + CHART_W + GUTTER, y=GUTTER,
            width=CHART_W, height=CHART_H,
            title="Sales by Product",
        ))

        # Summary table
        table_cols = [
            col("Segment"), col("Country"), col("Product"),
            field("Sales"), field("Profit"),
            FieldDef(entity=model, property="Units Sold", agg=AGG_SUM),
        ]
        from pbi_cli.intelligence.visual_builder import build_table
        add(PAGE, VisualSpec(
            visual_type="tableEx",
            visual_body=build_table(table_cols),
            x=GUTTER,
            y=GUTTER + CHART_H + GUTTER,
            width=TABLE_W, height=TABLE_H,
        ))
        console.print(f"  [green]OK[/green] 3 visuals")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 — Profit Analysis
    # Layout:
    #   Row 1: [Bar Profit by Country (600)] [Bar Profit by Segment (600)]
    #   Row 2: [Multi-row card: Sales/Profit/COGS/Units] [Line Profit by Month]
    # ════════════════════════════════════════════════════════════════════════
    if pages >= 3:
        PAGE = "Profit Analysis"
        console.print(f"\n[bold]Page 3:[/bold] {PAGE}")
        b.page_add(PAGE)

        add(PAGE, VisualSpec(
            visual_type="barChart",
            visual_body=build_bar_chart(col("Country"), field("Profit")),
            x=GUTTER, y=GUTTER,
            width=CHART_W, height=CHART_H,
            title="Profit by Country",
        ))
        add(PAGE, VisualSpec(
            visual_type="barChart",
            visual_body=build_bar_chart(col("Segment"), field("Profit")),
            x=GUTTER + CHART_W + GUTTER, y=GUTTER,
            width=CHART_W, height=CHART_H,
            title="Profit by Segment",
        ))

        y2 = GUTTER + CHART_H + GUTTER
        summary_fields = [
            field("Sales"), field("Profit"), field("COGS"),
            FieldDef(entity=model, property="Gross Sales", agg=AGG_SUM),
        ]
        from pbi_cli.intelligence.visual_builder import build_multi_row_card
        add(PAGE, VisualSpec(
            visual_type="multiRowCard",
            visual_body=build_multi_row_card(summary_fields),
            x=GUTTER, y=y2,
            width=CHART_W, height=200,
            title="P&L Summary",
        ))
        add(PAGE, VisualSpec(
            visual_type="lineChart",
            visual_body=build_line_chart(col("Month Name"), field("Profit")),
            x=GUTTER + CHART_W + GUTTER, y=y2,
            width=CHART_W, height=CHART_H,
        ))
        console.print(f"  [green]OK[/green] 4 visuals")

    console.print(f"\n[bold green]Report scaffold complete![/bold green]")
    console.print(
        "\n[cyan]Next step:[/cyan] In Power BI Desktop, click [bold]Reload[/bold] "
        "when prompted, or close and re-open the .pbip file."
    )
    console.print(
        "If Power BI Desktop doesn't prompt automatically, press [bold]Ctrl+Z[/bold] "
        "then [bold]Ctrl+Y[/bold] to trigger a refresh."
    )


# ── Bookmarks ──────────────────────────────────────────────────────────────────

@report.command("bookmark-list")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.pass_context
def report_bookmark_list(ctx: click.Context, pbip: str) -> None:
    """List all bookmarks in a .pbip report."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    bookmarks = b.bookmark_list()
    if not bookmarks:
        console.print("[yellow]No bookmarks found.[/yellow]")
        return
    output_json_or_table(bookmarks, ctx, title="Report Bookmarks")


@report.command("bookmark-add")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name for the bookmark.")
@click.option("--page", default=None, help="Page to associate with the bookmark.")
@click.pass_context
def report_bookmark_add(ctx: click.Context, pbip: str, name: str, page: str | None) -> None:
    """Add a named bookmark to a .pbip report.

    The bookmark captures the current report state when reloaded in Power BI Desktop.

    \b
    Example:
      pbi report bookmark-add --pbip MyReport --name "Q4 View" --page "Sales"
    """
    if dry_run_echo(ctx, f"add bookmark '{name}'" + (f" on page '{page}'" if page else "")):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    result = b.bookmark_add(name, page=page)
    console.print(f"[green]Bookmark added:[/green] '{name}'  (id: {result['name']})")
    if page:
        console.print(f"  Linked to page: {page}")
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to capture visual state.")


@report.command("bookmark-delete")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name of the bookmark to delete.")
@click.pass_context
def report_bookmark_delete(ctx: click.Context, pbip: str, name: str) -> None:
    """Delete a bookmark from a .pbip report."""
    if dry_run_echo(ctx, f"delete bookmark '{name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    deleted = b.bookmark_delete(name)
    if deleted:
        console.print(f"[green]Deleted[/green] bookmark '{name}'.")
    else:
        console.print(f"[yellow]Bookmark '{name}' not found.[/yellow]")



@report.command("bookmark-get")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name of the bookmark.")
@click.pass_context
def report_bookmark_get(ctx: click.Context, pbip: str, name: str) -> None:
    """Get full details of a single bookmark by display name."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.commands._shared import output_json_or_table
    b = PbirBackend(pbip)
    bookmarks = b.bookmark_list()
    match = next((bm for bm in bookmarks if bm.get("displayName") == name), None)
    if not match:
        console.print(f"[red]Bookmark '{name}' not found.[/red]")
        raise SystemExit(1)
    output_json_or_table(match, ctx, title=f"Bookmark: {name}")


@report.command("bookmark-set-visibility")
@click.option("--pbip",    required=True, help="Path to the .pbip project folder or file.")
@click.option("--name",    required=True, help="Display name of the bookmark.")
@click.option("--visible", is_flag=True, default=True, help="Set bookmark visible in the selection pane (default).")
@click.option("--hidden",  is_flag=True, default=False, help="Hide bookmark from the selection pane.")
@click.pass_context
def report_bookmark_set_visibility(
    ctx: click.Context, pbip: str, name: str, visible: bool, hidden: bool
) -> None:
    """Show or hide a bookmark in the Power BI bookmark selection pane."""
    if dry_run_echo(ctx, f"set visibility of bookmark '{name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    import json as _json
    b = PbirBackend(pbip)
    bdir = b._ga_bookmarks_dir()
    for entry in bdir.iterdir():
        if not entry.is_file() or not entry.name.endswith(".bookmark.json"):
            continue
        data = _json.loads(entry.read_text(encoding="utf-8"))
        if data.get("displayName") == name:
            data.setdefault("options", {})["isHidden"] = hidden
            entry.write_text(_json.dumps(data, indent=2), encoding="utf-8")
            state = "hidden" if hidden else "visible"
            console.print(f"[green]Bookmark '{name}' is now {state}.[/green]")
            return
    console.print(f"[red]Bookmark '{name}' not found.[/red]")
    raise SystemExit(1)


# ── Drillthrough & Tooltip ─────────────────────────────────────────────────────

@report.command("drillthrough-setup")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page name to convert to a drillthrough page.")
@click.option("--table", required=True, help="Source entity table (e.g. 'financials') for the drillthrough field.")
@click.pass_context
def report_drillthrough_setup(ctx: click.Context, pbip: str, page: str, table: str) -> None:
    """Convert a report page into a drillthrough destination.

    Users can right-click a data point and drill through to this page,
    automatically filtered to the selected context.

    \b
    Example:
      pbi report drillthrough-setup --pbip MyReport --page "Product Detail" --table financials
    """
    if dry_run_echo(ctx, f"set page '{page}' as Drillthrough (source: {table})"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.page_set_type(page, "Drillthrough", drillthrough_table=table)
    console.print(f"[green]Drillthrough enabled:[/green] '{page}' is now a drillthrough page.")
    console.print(f"  Source entity: [cyan]{table}[/cyan]")
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see the drillthrough option.")


@report.command("tooltip-setup")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page name to convert to a tooltip page.")
@click.pass_context
def report_tooltip_setup(ctx: click.Context, pbip: str, page: str) -> None:
    """Convert a report page into a custom report tooltip.

    Other visuals can then use this page as a hover tooltip.

    \b
    Example:
      pbi report tooltip-setup --pbip MyReport --page "Sales Tooltip"
    """
    if dry_run_echo(ctx, f"set page '{page}' as ReportTooltip"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.page_set_type(page, "ReportTooltip")
    console.print(f"[green]Tooltip page enabled:[/green] '{page}' is now a report tooltip page.")
    console.print("[yellow]Tip:[/yellow] Assign this tooltip to a visual in Power BI Desktop via Format > Tooltip > Page.")


@report.command("page-type-reset")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page name to reset to a normal report page.")
@click.pass_context
def report_page_type_reset(ctx: click.Context, pbip: str, page: str) -> None:
    """Reset a drillthrough or tooltip page back to a normal report page."""
    if dry_run_echo(ctx, f"reset page '{page}' to Normal type"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.page_set_type(page, "Normal")
    console.print(f"[green]Page reset:[/green] '{page}' is now a normal report page.")
