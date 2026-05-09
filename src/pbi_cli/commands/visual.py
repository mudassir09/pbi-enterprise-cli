"""pbi visual — add and list visuals on report pages."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table
from pbi_cli.intelligence.layout_engine import VISUAL_SIZES

console = Console()
# Visual types the CLI accepts → internal Power BI visual type
VISUAL_TYPE_MAP: dict[str, str] = {
    "card":      "card",
    "bar":       "barChart",
    "column":    "columnChart",
    "line":      "lineChart",
    "table":     "tableEx",
    "slicer":    "slicer",
    "multirow":  "multiRowCard",
    "scatter":   "scatterChart",
    "gauge":     "gauge",
    "donut":     "donutChart",
    "pie":       "pieChart",
    "treemap":   "treemap",
    "funnel":    "funnel",
    "waterfall": "waterfallChart",
    "matrix":    "pivotTable",
    "ribbon":    "ribbonChart",
}

AGG_MAP: dict[str, int] = {
    "sum": 0, "avg": 1, "min": 2, "max": 3, "count": 4, "none": -1,
}


@click.group()
def visual() -> None:
    """Add, list, and configure visuals on report pages."""


@visual.command("list")
@click.option("--pbip",   required=True, help="Path to the .pbip project folder or file.")
@click.option("--page",   required=True, help="Page display name.")
@click.pass_context
def visual_list(ctx: click.Context, pbip: str, page: str) -> None:
    """List all visuals on a report page."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    visuals = b.visual_list(page)
    if not visuals:
        console.print(f"[yellow]No visuals found on page '{page}'.[/yellow]")
        return
    output_json_or_table(visuals, ctx, title=f"Visuals on '{page}'")


@visual.command("add")
@click.option("--pbip",   required=True, help="Path to the .pbip project folder or file.")
@click.option("--page",   required=True, help="Page display name to add the visual to.")
@click.option(
    "--type", "vtype",
    type=click.Choice(list(VISUAL_TYPE_MAP.keys())),
    required=True,
    help="Visual type.",
)
@click.option("--table",    required=True,  help="Power BI table name (e.g. Financials).")
@click.option("--value",    required=True,  help="Measure or column name for the main value/Y axis.")
@click.option("--category", default=None,   help="Category column for X axis / bars (charts only).")
@click.option("--measure",  is_flag=True,   help="Treat --value as an explicit DAX measure.")
@click.option("--agg",      default="sum",  type=click.Choice(list(AGG_MAP.keys())),
              help="Aggregation for column values (ignored when --measure).")
@click.option("--extra-columns", default="", help="Comma-separated extra columns/rows for table, matrix, multirow visuals.")
@click.option("--series",   default=None,   help="Series/legend field (scatter, ribbon).")
@click.option("--size",     default=None,   help="Bubble size field (scatter only).")
@click.option("--title",    default="",     help="Visual title text.")
@click.option("--x",        default=None, type=int, help="Canvas X position (auto if omitted).")
@click.option("--y",        default=None, type=int, help="Canvas Y position (auto if omitted).")
@click.option("--width",    default=None, type=int, help="Width in pixels.")
@click.option("--height",   default=None, type=int, help="Height in pixels.")
@click.pass_context
def visual_add(
    ctx: click.Context,
    pbip: str, page: str, vtype: str,
    table: str, value: str, category: str | None,
    measure: bool, agg: str,
    extra_columns: str,
    series: str | None,
    size: str | None,
    title: str,
    x: int | None, y: int | None,
    width: int | None, height: int | None,
) -> None:
    """Add a visual to a report page in a .pbip project."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.intelligence.visual_builder import (
        FieldDef, VisualSpec,
        build_card, build_bar_chart, build_column_chart,
        build_line_chart, build_slicer, build_table, build_multi_row_card,
        build_scatter_chart, build_gauge, build_donut_chart, build_pie_chart,
        build_treemap, build_funnel, build_waterfall, build_matrix, build_ribbon_chart,
        AGG_SUM,
    )

    if dry_run_echo(ctx, f"add {vtype} visual to page '{page}'",
                    f"table={table} value={value} category={category}"):
        return

    agg_func: int | None = None if (measure or agg == "none") else AGG_MAP.get(agg, 0)
    value_field = FieldDef(entity=table, property=value, is_measure=measure, agg=agg_func)

    pbi_type = VISUAL_TYPE_MAP[vtype]
    default_w, default_h = VISUAL_SIZES.get(vtype, (300, 200))

    if vtype == "card":
        body = build_card(value_field)
    elif vtype == "bar":
        if not category:
            raise click.UsageError("--category is required for bar visuals.")
        cat_field = FieldDef(entity=table, property=category, is_measure=False, agg=None)
        body = build_bar_chart(cat_field, value_field)
    elif vtype == "column":
        if not category:
            raise click.UsageError("--category is required for column visuals.")
        cat_field = FieldDef(entity=table, property=category, is_measure=False, agg=None)
        body = build_column_chart(cat_field, value_field)
    elif vtype == "line":
        if not category:
            raise click.UsageError("--category is required for line visuals.")
        cat_field = FieldDef(entity=table, property=category, is_measure=False, agg=None)
        body = build_line_chart(cat_field, value_field)
    elif vtype == "slicer":
        body = build_slicer(FieldDef(entity=table, property=value, is_measure=False, agg=None))
    elif vtype == "table":
        cols = [value_field]
        if extra_columns:
            for col_name in extra_columns.split(","):
                col_name = col_name.strip()
                if col_name:
                    cols.append(FieldDef(entity=table, property=col_name, agg=agg_func))
        body = build_table(cols)
    elif vtype == "multirow":
        fields = [value_field]
        if extra_columns:
            for col_name in extra_columns.split(","):
                col_name = col_name.strip()
                if col_name:
                    fields.append(FieldDef(entity=table, property=col_name, agg=agg_func))
        body = build_multi_row_card(fields)
    elif vtype == "scatter":
        if not category:
            raise click.UsageError("--category is required for scatter (X axis).")
        x_field = FieldDef(entity=table, property=category, is_measure=False, agg=agg_func)
        size_field = FieldDef(entity=table, property=size, agg=agg_func) if size else None
        series_field = FieldDef(entity=table, property=series, agg=None) if series else None
        body = build_scatter_chart(x_field, value_field, details=series_field, size=size_field)
    elif vtype == "gauge":
        target_field = FieldDef(entity=table, property=series, agg=agg_func) if series else None
        body = build_gauge(value_field, target=target_field)
    elif vtype == "donut":
        if not category:
            raise click.UsageError("--category is required for donut chart.")
        cat_field = FieldDef(entity=table, property=category, agg=None)
        body = build_donut_chart(cat_field, value_field)
    elif vtype == "pie":
        if not category:
            raise click.UsageError("--category is required for pie chart.")
        cat_field = FieldDef(entity=table, property=category, agg=None)
        body = build_pie_chart(cat_field, value_field)
    elif vtype == "treemap":
        if not category:
            raise click.UsageError("--category is required for treemap (group field).")
        group_field = FieldDef(entity=table, property=category, agg=None)
        body = build_treemap(group_field, value_field)
    elif vtype == "funnel":
        if not category:
            raise click.UsageError("--category is required for funnel chart.")
        cat_field = FieldDef(entity=table, property=category, agg=None)
        body = build_funnel(cat_field, value_field)
    elif vtype == "waterfall":
        if not category:
            raise click.UsageError("--category is required for waterfall chart.")
        cat_field = FieldDef(entity=table, property=category, agg=None)
        breakdown_field = FieldDef(entity=table, property=series, agg=None) if series else None
        body = build_waterfall(cat_field, value_field, breakdown=breakdown_field)
    elif vtype == "matrix":
        if not category:
            raise click.UsageError("--category is required for matrix (row field).")
        row_field = FieldDef(entity=table, property=category, agg=None)
        col_fields = []
        if extra_columns:
            for col_name in extra_columns.split(","):
                col_name = col_name.strip()
                if col_name:
                    col_fields.append(FieldDef(entity=table, property=col_name, agg=None))
        body = build_matrix([row_field], [value_field], columns=col_fields or None)
    elif vtype == "ribbon":
        if not category:
            raise click.UsageError("--category is required for ribbon chart.")
        cat_field = FieldDef(entity=table, property=category, agg=None)
        series_field = FieldDef(entity=table, property=series, agg=None) if series else None
        body = build_ribbon_chart(cat_field, value_field, series=series_field)
    else:
        raise click.UsageError(f"Unsupported visual type: {vtype}")

    # Auto-position: find next available slot on the page
    b = PbirBackend(pbip)
    if x is None or y is None:
        x, y = _next_position(b, page, width or default_w, height or default_h)

    spec = VisualSpec(
        visual_type=pbi_type,
        visual_body=body,
        x=x, y=y,
        width=width or default_w,
        height=height or default_h,
        title=title,
    )
    result = b.visual_add(page, spec)
    console.print(f"[green]Visual added:[/green] {vtype} -> page '{page}' @ ({x}, {y})")
    console.print(f"  name: {result['name']}")
    if vtype == "slicer":
        console.print(
            "[yellow]Note:[/yellow] slicer defaults to list style. "
            "Edit visual.json and set mode 'Basic' -> 'Dropdown' for a compact filter bar."
        )


@visual.command("delete")
@click.option("--pbip",  required=True, help="Path to the .pbip project folder or file.")
@click.option("--page",  required=True, help="Page display name.")
@click.option("--name",  "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.pass_context
def visual_delete(ctx: click.Context, pbip: str, page: str, visual_name: str) -> None:
    """Remove a visual from a report page."""
    if dry_run_echo(ctx, f"delete visual '{visual_name}' from page '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)
    b.visual_delete(page, visual_name)
    console.print(f"[green]Deleted[/green] visual '{visual_name}' from '{page}'.")


@visual.command("recommend")
@click.option("--measures", required=True, help="Comma-separated measure names.")
@click.pass_context
def visual_recommend(ctx: click.Context, measures: str) -> None:
    """Recommend visual types for a set of measures."""
    from pbi_cli.intelligence.visual_recommender import VisualRecommender
    measure_list = [m.strip() for m in measures.split(",")]
    rec = VisualRecommender()
    recommendations = rec.recommend(measure_list)
    output_json_or_table(recommendations, ctx, title="Visual Recommendations")


@visual.command("screenshot")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name to screenshot.")
@click.option("--output", default=None, help="Output PNG path (default: <page>.png).")
@click.option("--width", default=1280, show_default=True, help="Viewport width.")
@click.option("--height", default=720, show_default=True, help="Viewport height.")
@click.pass_context
def visual_screenshot(
    ctx: click.Context,
    pbip: str,
    page: str,
    output: str | None,
    width: int,
    height: int,
) -> None:
    """Render a report page to PNG via headless Playwright (requires pbi-cli-tool[viz]).

    Power BI Desktop must be running with the report open, and pbi server must
    be started (pbi server start) so the page can be rendered via the REST API.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import]
    except ImportError:
        raise click.ClickException(
            "Playwright not installed. Run: pip install pbi-cli-tool[viz] && playwright install chromium"
        )

    import re
    from pathlib import Path

    out_path = Path(output) if output else Path(re.sub(r"[^\w\-]", "_", page) + ".png")
    console.print(f"[cyan]Screenshotting:[/cyan] page '{page}' → {out_path}")

    server_url = "http://localhost:7788"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page_obj = browser.new_page(viewport={"width": width, "height": height})
        page_obj.goto(f"{server_url}/?page={page}", wait_until="networkidle")
        page_obj.screenshot(path=str(out_path), full_page=False)
        browser.close()

    console.print(f"[green]Screenshot saved:[/green] {out_path}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _next_position(backend: object, page: str, w: int, h: int) -> tuple[int, int]:
    """Find the next free position on the page using simple row-packing."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    GUTTER = 16
    CANVAS_W = 1280

    existing = backend.visual_list(page)
    if not existing:
        return GUTTER, GUTTER

    # Find bottom-right of all existing visuals
    max_x = max((v["x"] + v["width"] for v in existing), default=0)
    max_y = max((v["y"] + v["height"] for v in existing), default=0)

    # Try to fit on the same row
    rightmost = max((v["x"] + v["width"] for v in existing), default=0)
    row_bottom = max(
        (v["y"] + v["height"] for v in existing if v["x"] + v["width"] >= rightmost - w),
        default=GUTTER,
    )
    candidate_x = rightmost + GUTTER

    if candidate_x + w <= CANVAS_W:
        # Find the max y of visuals in the same row region
        row_y = min((v["y"] for v in existing if v["x"] + v["width"] + GUTTER == candidate_x), default=GUTTER)
        return candidate_x, row_y

    # Start a new row
    return GUTTER, max_y + GUTTER


# ── Conditional Formatting ─────────────────────────────────────────────────────

@visual.command("format")
@click.option("--pbip",   required=True, help="Path to the .pbip project folder or file.")
@click.option("--page",   required=True, help="Page display name.")
@click.option("--visual", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option(
    "--type", "fmt_type",
    type=click.Choice(["color-scale", "data-bar"]),
    required=True,
    help="Conditional formatting type.",
)
@click.option("--table",   required=True, help="Table name containing the measure.")
@click.option("--measure", required=True, help="Measure name to apply formatting to.")
@click.option("--low-color",      default="#FF0000", show_default=True, help="Low value color (color-scale).")
@click.option("--mid-color",      default="#FFFF00", show_default=True, help="Mid value color (color-scale, omit to skip).")
@click.option("--high-color",     default="#00FF00", show_default=True, help="High value color (color-scale).")
@click.option("--positive-color", default="#118DFF", show_default=True, help="Positive value color (data-bar).")
@click.option("--negative-color", default="#FC4E2A", show_default=True, help="Negative value color (data-bar).")
@click.pass_context
def visual_format(
    ctx: click.Context,
    pbip: str, page: str, visual_name: str, fmt_type: str,
    table: str, measure: str,
    low_color: str, mid_color: str, high_color: str,
    positive_color: str, negative_color: str,
) -> None:
    """Apply conditional formatting to a measure in a table or matrix visual.

    \b
    Color-scale example (red-yellow-green gradient):
      pbi visual format --pbip MyReport --page "Sales" --visual abc123 \\
        --type color-scale --table financials --measure Sales \\
        --low-color "#FF0000" --mid-color "#FFFF00" --high-color "#00FF00"

    \b
    Data-bar example:
      pbi visual format --pbip MyReport --page "Sales" --visual abc123 \\
        --type data-bar --table financials --measure Profit \\
        --positive-color "#118DFF" --negative-color "#FC4E2A"
    """
    if dry_run_echo(
        ctx,
        f"apply {fmt_type} conditional format to '{measure}' in visual '{visual_name}'",
    ):
        return

    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip)

    if fmt_type == "color-scale":
        found = b.visual_format_color_scale(
            page, visual_name, table, measure,
            low_color=low_color,
            mid_color=mid_color if mid_color else None,
            high_color=high_color,
        )
    else:  # data-bar
        found = b.visual_format_data_bar(
            page, visual_name, table, measure,
            positive_color=positive_color,
            negative_color=negative_color,
        )

    if found:
        console.print(
            f"[green]Conditional format applied:[/green] "
            f"{fmt_type} on {table}[{measure}] in visual '{visual_name}'"
        )
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)
