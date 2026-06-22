"""pbi report — manage pages and scaffold full reports in .pbip projects."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console(legacy_windows=False)


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


@report.command("page-duplicate")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name of the page to duplicate.")
@click.option("--new-name", default=None, help="Display name for the copy (default: '<name> (copy)').")  # noqa: E501
@click.pass_context
def report_page_duplicate(ctx: click.Context, pbip: str, name: str, new_name: str | None) -> None:
    """Duplicate a page and all its visuals under a fresh, independent id.

    Visual ids are regenerated and internal references (groups, visual
    interactions) are remapped, so the copy never aliases the original.

    \b
    Example:
      pbi report page-duplicate --pbip MyReport --name "Sales" --new-name "Sales (EMEA)"
    """
    if dry_run_echo(ctx, f"duplicate page '{name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        result = b.page_duplicate(name, new_display_name=new_name)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print(
        f"[green]Page duplicated:[/green] '{result['displayName']}' "
        f"({result['visuals']} visual(s), id: {result['name']})"
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


# ── Scaffold ───────────────────────────────────────────────────────────────────


@report.command("scaffold")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option(
    "--model",
    default="financials",
    help="Semantic model table name containing the data (default: financials).",
)
@click.option("--pages", default=3, show_default=True, help="Number of pages to create (1-3).")
@click.option("--replace", is_flag=True, help="Delete existing pages before scaffolding.")
@click.pass_context
def report_scaffold(ctx: click.Context, pbip: str, model: str, pages: int, replace: bool) -> None:
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
        AGG_SUM,
        FieldDef,
        VisualSpec,
        build_bar_chart,
        build_card,
        build_line_chart,
        build_multi_row_card,
        build_slicer,
        build_table,
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
    SLIM_W = 580
    SLICER_W = 200
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
            ("Sales", field("Sales"), "Total Sales"),
            ("Profit", field("Profit"), "Total Profit"),
            ("Units", field("Units Sold"), "Units Sold"),
            ("COGS", field("COGS"), "Total COGS"),
        ]
        for i, (_, value_field, title) in enumerate(cards):
            add(
                PAGE,
                VisualSpec(
                    visual_type="card",
                    visual_body=build_card(value_field),
                    x=GUTTER + i * (CARD_W + GUTTER),
                    y=GUTTER,
                    width=CARD_W,
                    height=CARD_H,
                    title=title,
                ),
            )

        y2 = GUTTER + CARD_H + GUTTER
        # Sales by Country bar
        add(
            PAGE,
            VisualSpec(
                visual_type="barChart",
                visual_body=build_bar_chart(col("Country"), field("Sales")),
                x=GUTTER,
                y=y2,
                width=CHART_W,
                height=CHART_H,
                title="Sales by Country",
            ),
        )
        # Year slicer
        add(
            PAGE,
            VisualSpec(
                visual_type="slicer",
                visual_body=build_slicer(col("Year")),
                x=GUTTER + CHART_W + GUTTER,
                y=y2,
                width=SLICER_W,
                height=CHART_H,
                title="Year",
            ),
        )
        # Sales by Month line
        add(
            PAGE,
            VisualSpec(
                visual_type="lineChart",
                visual_body=build_line_chart(col("Month Name"), field("Sales")),
                x=GUTTER + CHART_W + GUTTER + SLICER_W + GUTTER,
                y=y2,
                width=SLIM_W,
                height=CHART_H,
            ),
        )
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

        add(
            PAGE,
            VisualSpec(
                visual_type="barChart",
                visual_body=build_bar_chart(col("Segment"), field("Sales")),
                x=GUTTER,
                y=GUTTER,
                width=CHART_W,
                height=CHART_H,
                title="Sales by Segment",
            ),
        )
        add(
            PAGE,
            VisualSpec(
                visual_type="barChart",
                visual_body=build_bar_chart(col("Product"), field("Sales")),
                x=GUTTER + CHART_W + GUTTER,
                y=GUTTER,
                width=CHART_W,
                height=CHART_H,
                title="Sales by Product",
            ),
        )

        # Summary table
        table_cols = [
            col("Segment"),
            col("Country"),
            col("Product"),
            field("Sales"),
            field("Profit"),
            FieldDef(entity=model, property="Units Sold", agg=AGG_SUM),
        ]
        from pbi_cli.intelligence.visual_builder import build_table

        add(
            PAGE,
            VisualSpec(
                visual_type="tableEx",
                visual_body=build_table(table_cols),
                x=GUTTER,
                y=GUTTER + CHART_H + GUTTER,
                width=TABLE_W,
                height=TABLE_H,
            ),
        )
        console.print("  [green]OK[/green] 3 visuals")

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

        add(
            PAGE,
            VisualSpec(
                visual_type="barChart",
                visual_body=build_bar_chart(col("Country"), field("Profit")),
                x=GUTTER,
                y=GUTTER,
                width=CHART_W,
                height=CHART_H,
                title="Profit by Country",
            ),
        )
        add(
            PAGE,
            VisualSpec(
                visual_type="barChart",
                visual_body=build_bar_chart(col("Segment"), field("Profit")),
                x=GUTTER + CHART_W + GUTTER,
                y=GUTTER,
                width=CHART_W,
                height=CHART_H,
                title="Profit by Segment",
            ),
        )

        y2 = GUTTER + CHART_H + GUTTER
        summary_fields = [
            field("Sales"),
            field("Profit"),
            field("COGS"),
            FieldDef(entity=model, property="Gross Sales", agg=AGG_SUM),
        ]
        from pbi_cli.intelligence.visual_builder import build_multi_row_card

        add(
            PAGE,
            VisualSpec(
                visual_type="multiRowCard",
                visual_body=build_multi_row_card(summary_fields),
                x=GUTTER,
                y=y2,
                width=CHART_W,
                height=200,
                title="P&L Summary",
            ),
        )
        add(
            PAGE,
            VisualSpec(
                visual_type="lineChart",
                visual_body=build_line_chart(col("Month Name"), field("Profit")),
                x=GUTTER + CHART_W + GUTTER,
                y=y2,
                width=CHART_W,
                height=CHART_H,
            ),
        )
        console.print("  [green]OK[/green] 4 visuals")

    console.print("\n[bold green]Report scaffold complete![/bold green]")
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
@click.option(
    "--hidden-visual",
    "hidden_visuals",
    multiple=True,
    help="Visual name to record as hidden in this bookmark (repeatable). "
    "Builds show/hide storytelling bookmarks.",
)
@click.option(
    "--no-capture",
    is_flag=True,
    default=False,
    help="Write an empty bookmark skeleton instead of capturing the page's visuals.",
)
@click.pass_context
def report_bookmark_add(
    ctx: click.Context,
    pbip: str,
    name: str,
    page: str | None,
    hidden_visuals: tuple[str, ...],
    no_capture: bool,
) -> None:
    """Add a named bookmark to a .pbip report.

    By default the bookmark captures the visuals on the target page, so it
    survives reopening in Desktop. Use --hidden-visual to record specific
    visuals as hidden (for show/hide bookmarks).

    \b
    Examples:
      pbi report bookmark-add --pbip MyReport --name "Q4 View" --page "Sales"
      pbi report bookmark-add --pbip MyReport --name "Detail hidden" --page "Sales" \\
        --hidden-visual detail_table_abc --hidden-visual notes_xyz
    """
    if dry_run_echo(ctx, f"add bookmark '{name}'" + (f" on page '{page}'" if page else "")):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    result = b.bookmark_add(
        name,
        page=page,
        hidden_visuals=list(hidden_visuals) or None,
        capture=not no_capture,
    )
    console.print(f"[green]Bookmark added:[/green] '{name}'  (id: {result['name']})")
    if page:
        console.print(f"  Linked to page: {page}")
    captured = result.get("options", {}).get("targetVisualNames", [])
    if not no_capture and captured:
        console.print(f"  Captured {len(captured)} visual(s)" + (
            f", {len(hidden_visuals)} hidden" if hidden_visuals else ""
        ))
    console.print(
        "[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to refine the captured state."
    )


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
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name of the bookmark.")
@click.option(
    "--visible",
    is_flag=True,
    default=True,
    help="Set bookmark visible in the selection pane (default).",
)
@click.option(
    "--hidden", is_flag=True, default=False, help="Hide bookmark from the selection pane."
)
@click.pass_context
def report_bookmark_set_visibility(
    ctx: click.Context, pbip: str, name: str, visible: bool, hidden: bool
) -> None:
    """Show or hide a bookmark in the Power BI bookmark selection pane."""
    if dry_run_echo(ctx, f"set visibility of bookmark '{name}'"):
        return
    import json as _json

    from pbi_cli.backends.pbir_backend import PbirBackend

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
@click.option(
    "--table",
    required=True,
    help="Source entity table (e.g. 'financials') for the drillthrough field.",
)
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
    console.print(
        "[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see the drillthrough option."  # noqa: E501
    )


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
    console.print(
        "[yellow]Tip:[/yellow] Assign this tooltip to a visual in Power BI Desktop via Format > Tooltip > Page."  # noqa: E501
    )


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


# ── Report intelligence: lint, field usage, diff, accessibility ───────────────


@report.command("lint")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option(
    "--fail-on", default="never", show_default=True,
    type=click.Choice(["error", "warning", "info", "never"]),
    help="Exit 3 when findings at or above this severity exist (CI gate).",
)
@click.pass_context
def report_lint(ctx: click.Context, pbip: str, fail_on: str) -> None:
    """Lint the report layer: visual density, hidden visuals, alt text, overlaps."""
    from pbi_cli.pbir_analysis import lint_report, load_report

    violations = lint_report(load_report(pbip))
    output_json_or_table(violations, ctx, title="Report Lint")
    if not violations and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No report lint findings.[/green]")
    rank = {"error": 3, "warning": 2, "info": 1, "never": 99}
    worst = max((rank.get(v["severity"], 0) for v in violations), default=0)
    if worst >= rank[fail_on]:
        raise SystemExit(3)


@report.command("validate")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option(
    "--fail-on", default="error", show_default=True,
    type=click.Choice(["error", "warning", "info", "never"]),
    help="Exit 3 when findings at or above this severity exist (CI gate).",
)
@click.pass_context
def report_validate(ctx: click.Context, pbip: str, fail_on: str) -> None:
    """Validate PBIR files: schema drift, structural invariants, referential integrity.

    Encodes the runtime-validator rules Power BI Desktop enforces at reload
    (e.g. no $schema inside an embedded filterConfig) plus cross-file reference
    checks (pageOrder, bookmark items, parentGroupName, visualInteractions).
    Runs offline — no Desktop required. Exit 3 if findings reach --fail-on.
    """
    from pbi_cli.pbir_validate import validate_report

    try:
        findings = validate_report(pbip)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc

    output_json_or_table(findings, ctx, title="PBIR Validation")
    quiet_json = bool(ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")))
    if not findings and not quiet_json:
        console.print("[green]PBIR is valid — no findings.[/green]")
    rank = {"error": 3, "warning": 2, "info": 1, "never": 99}
    worst = max((rank.get(f["severity"], 0) for f in findings), default=0)
    if worst >= rank[fail_on]:
        raise SystemExit(3)


@report.command("field-usage")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--unused-only", is_flag=True, help="Print only unused columns/measures.")
@click.pass_context
def report_field_usage(ctx: click.Context, pbip: str, unused_only: bool) -> None:
    """Cross-reference model fields with report visuals: find unused columns/measures.

    Model metadata comes from the active backend — use `--backend file --path <pbip>`
    to analyze a PBIP repo with no Desktop at all.
    """
    from pbi_cli.commands._shared import get_backend
    from pbi_cli.pbir_analysis import field_usage, load_report

    backend = get_backend(ctx)
    usage = field_usage(load_report(pbip), backend.column_list(), backend.measure_list())
    if unused_only:
        usage = {"unused_columns": usage["unused_columns"],
                 "unused_measures": usage["unused_measures"]}
    output_json_or_table(usage, ctx, title="Field Usage")
    if not (ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml"))):
        n = len(usage.get("unused_columns", [])) + len(usage.get("unused_measures", []))
        console.print(f"\n[bold]{n} unused field(s)[/bold] — candidates for removal.")


@report.command("diff")
@click.argument("old_path", type=click.Path(exists=True))
@click.argument("new_path", type=click.Path(exists=True))
@click.pass_context
def report_diff(ctx: click.Context, old_path: str, new_path: str) -> None:
    """Human-readable visual-level diff between two report versions.

    Compare a PR branch against main:
      git worktree add /tmp/main main && pbi report diff /tmp/main/MyReport . 
    """
    from pbi_cli.pbir_analysis import diff_reports, load_report

    result = diff_reports(load_report(old_path), load_report(new_path))
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table(result, ctx)
        return
    if not result["has_changes"]:
        console.print("[green]No report changes.[/green]")
        return
    output_json_or_table(result["changes"], ctx, title="Report Changes")
    console.print(f"\n[bold]{len(result['changes'])} change(s)[/bold]")


@report.command("a11y")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option(
    "--fail-on", default="never", show_default=True,
    type=click.Choice(["error", "warning", "info", "never"]),
)
@click.pass_context
def report_a11y(ctx: click.Context, pbip: str, fail_on: str) -> None:
    """Accessibility audit: alt text, visible titles, explicit tab order."""
    from pbi_cli.pbir_analysis import a11y_check, load_report

    findings = a11y_check(load_report(pbip))
    output_json_or_table(findings, ctx, title="Accessibility Audit")
    if not findings and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No accessibility findings.[/green]")
    rank = {"error": 3, "warning": 2, "info": 1, "never": 99}
    worst = max((rank.get(v["severity"], 0) for v in findings), default=0)
    if worst >= rank[fail_on]:
        raise SystemExit(3)


# ── Report-level measures ────────────────────────────────────────────────────────


@report.command("measure-add")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--table", required=True, help="Target table (entity) in the semantic model.")
@click.option("--name", required=True, help="Measure name.")
@click.option("--expression", required=True, help="DAX expression.")
@click.option("--format-string", default=None, help="Optional format string, e.g. '0.0%'.")
@click.option(
    "--data-type",
    default="Double",
    show_default=True,
    type=click.Choice(["Double", "Integer", "Text", "Boolean", "DateTime", "Decimal"]),
    help="Measure data type (required by the schema).",
)
@click.pass_context
def report_measure_add(
    ctx: click.Context,
    pbip: str,
    table: str,
    name: str,
    expression: str,
    format_string: str | None,
    data_type: str,
) -> None:
    """Add a report-level measure (stored in reportExtensions.json).

    \b
    Example:
      pbi report measure-add --pbip MyReport --table financials \
        --name "Margin %" --expression "DIVIDE(SUM(financials[Profit]),SUM(financials[Sales]))" \
        --format-string "0.0%"
    """
    if dry_run_echo(ctx, f"add report-level measure '{name}' on table '{table}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        b.report_measure_add(
            table, name, expression, format_string=format_string, data_type=data_type
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print(f"[green]Report-level measure added:[/green] {table}[{name}]")
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


@report.command("measure-list")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.pass_context
def report_measure_list(ctx: click.Context, pbip: str) -> None:
    """List report-level measures defined in reportExtensions.json."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.commands._shared import output_json_or_table

    b = PbirBackend(pbip)
    measures = b.report_measure_list()
    if not measures:
        console.print("[yellow]No report-level measures.[/yellow]")
        return
    output_json_or_table(measures, ctx, title="Report-level Measures")


# ── Bookmark groups ──────────────────────────────────────────────────────────────


@report.command("bookmark-group-add")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--name", required=True, help="Display name for the group.")
@click.option(
    "--member",
    "members",
    multiple=True,
    required=True,
    help="Display name of a bookmark to include (repeatable).",
)
@click.pass_context
def report_bookmark_group_add(
    ctx: click.Context, pbip: str, name: str, members: tuple[str, ...]
) -> None:
    """Group existing bookmarks under a named bookmark group.

    \b
    Example:
      pbi report bookmark-group-add --pbip MyReport --name "Story" \
        --member "Intro" --member "Detail"
    """
    if dry_run_echo(ctx, f"create bookmark group '{name}' with {len(members)} member(s)"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        result = b.bookmark_group_add(name, list(members))
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print(
        f"[green]Bookmark group created:[/green] '{name}' "
        f"({len(result['members'])} member(s))"
    )
