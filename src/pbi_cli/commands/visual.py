"""pbi visual — add and list visuals on report pages."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table
from pbi_cli.intelligence.layout_engine import VISUAL_SIZES

console = Console(legacy_windows=False)
# Visual types the CLI accepts → internal Power BI visual type
VISUAL_TYPE_MAP: dict[str, str] = {
    # ── Core ──────────────────────────────────────────────────────────────
    "card": "card",
    "kpi": "kpiVisual",
    "multirow": "multiRowCard",
    # ── Bar / Column ───────────────────────────────────────────────────────
    "bar": "barChart",
    "column": "columnChart",
    "stackedbar": "stackedBarChart",
    "stackedcolumn": "stackedColumnChart",
    "100percentbar": "hundredPercentStackedBarChart",
    "100percentcolumn": "hundredPercentStackedColumnChart",
    # ── Line / Area ────────────────────────────────────────────────────────
    "line": "lineChart",
    "area": "areaChart",
    "stackedarea": "stackedAreaChart",
    # ── Combo ─────────────────────────────────────────────────────────────
    "combo": "lineClusteredColumnComboChart",
    # ── Scatter / Bubble ───────────────────────────────────────────────────
    "scatter": "scatterChart",
    "bubble": "scatterChart",
    # ── Pie / Donut ────────────────────────────────────────────────────────
    "pie": "pieChart",
    "donut": "donutChart",
    # ── Other charts ───────────────────────────────────────────────────────
    "gauge": "gauge",
    "waterfall": "waterfallChart",
    "funnel": "funnel",
    "ribbon": "ribbonChart",
    "treemap": "treemap",
    # ── Matrix / Table ─────────────────────────────────────────────────────
    "table": "tableEx",
    "matrix": "pivotTable",
    # ── Slicer ─────────────────────────────────────────────────────────────
    "slicer": "slicer",
    # ── Map ────────────────────────────────────────────────────────────────
    "map": "map",
    "filledmap": "filledMap",
    "azuremap": "azureMap",
    # ── AI / Smart ─────────────────────────────────────────────────────────
    "decomptree": "decompositionTreeVisual",
    "keyinfluencers": "keyDrivers",
    "smartnarrative": "narrativeVisual",
    "qanda": "qnaVisual",
}

AGG_MAP: dict[str, int] = {
    "sum": 0,
    "avg": 1,
    "min": 2,
    "max": 3,
    "count": 4,
    "none": -1,
}


@click.group()
def visual() -> None:
    """Add, list, and configure visuals on report pages."""


@visual.command("list")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
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


@visual.command("get")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.pass_context
def visual_get(ctx: click.Context, pbip: str, page: str, visual_name: str) -> None:
    """Introspect a visual: type, position, field bindings, formatting, filters.

    The read-side counterpart to add/rebind/format — useful for auditing,
    idempotent edits, and understanding an existing report.

    \b
    Example:
      pbi visual get --pbip MyReport --page "Sales" --name abc123 --json
    """
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        info = b.visual_get(page, visual_name)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if info is None:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)
    output_json_or_table(info, ctx, title=f"Visual {visual_name}")


@visual.command("add")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name to add the visual to.")
@click.option(
    "--type",
    "vtype",
    type=click.Choice(list(VISUAL_TYPE_MAP.keys())),
    required=True,
    help="Visual type.",
)
@click.option("--table", required=True, help="Power BI table name (e.g. Financials).")
@click.option("--value", required=True, help="Measure or column name for the main value/Y axis.")
@click.option("--category", default=None, help="Category column for X axis / bars (charts only).")
@click.option("--measure", is_flag=True, help="Treat --value as an explicit DAX measure.")
@click.option(
    "--agg",
    default="sum",
    type=click.Choice(list(AGG_MAP.keys())),
    help="Aggregation for column values (ignored when --measure).",
)
@click.option(
    "--extra-columns",
    default="",
    help="Comma-separated extra columns/rows for table, matrix, multirow visuals.",
)
@click.option("--series", default=None, help="Series/legend field (scatter, ribbon).")
@click.option("--size", default=None, help="Bubble size field (scatter only).")
@click.option("--title", default="", help="Visual title text.")
@click.option("--x", default=None, type=int, help="Canvas X position (auto if omitted).")
@click.option("--y", default=None, type=int, help="Canvas Y position (auto if omitted).")
@click.option("--width", default=None, type=int, help="Width in pixels.")
@click.option("--height", default=None, type=int, help="Height in pixels.")
@click.pass_context
def visual_add(
    ctx: click.Context,
    pbip: str,
    page: str,
    vtype: str,
    table: str,
    value: str,
    category: str | None,
    measure: bool,
    agg: str,
    extra_columns: str,
    series: str | None,
    size: str | None,
    title: str,
    x: int | None,
    y: int | None,
    width: int | None,
    height: int | None,
) -> None:
    """Add a visual to a report page in a .pbip project."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.intelligence.visual_builder import (
        FieldDef,
        VisualSpec,
        build_bar_chart,
        build_card,
        build_column_chart,
        build_decomposition_tree,
        build_donut_chart,
        build_funnel,
        build_gauge,
        build_key_influencers,
        build_line_chart,
        build_matrix,
        build_multi_row_card,
        build_pie_chart,
        build_qna,
        build_ribbon_chart,
        build_scatter_chart,
        build_slicer,
        build_smart_narrative,
        build_table,
        build_treemap,
        build_waterfall,
    )

    if dry_run_echo(
        ctx,
        f"add {vtype} visual to page '{page}'",
        f"table={table} value={value} category={category}",
    ):
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
    elif vtype in ("decomptree", "keyinfluencers"):
        if not category:
            raise click.UsageError(
                f"--category is required for {vtype} (the Explain-by dimension); "
                "use --extra-columns to add more."
            )
        explain = [FieldDef(entity=table, property=category, agg=None)]
        if extra_columns:
            for col_name in extra_columns.split(","):
                col_name = col_name.strip()
                if col_name:
                    explain.append(FieldDef(entity=table, property=col_name, agg=None))
        builder = build_decomposition_tree if vtype == "decomptree" else build_key_influencers
        body = builder(value_field, explain)
    elif vtype == "smartnarrative":
        body = build_smart_narrative()
    elif vtype == "qanda":
        body = build_qna()
    else:
        raise click.UsageError(f"Unsupported visual type: {vtype}")

    # Auto-position: find next available slot on the page
    b = PbirBackend(pbip)
    if x is None or y is None:
        x, y = _next_position(b, page, width or default_w, height or default_h)

    spec = VisualSpec(
        visual_type=pbi_type,
        visual_body=body,
        x=x,
        y=y,
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
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.pass_context
def visual_delete(ctx: click.Context, pbip: str, page: str, visual_name: str) -> None:
    """Remove a visual from a report page."""
    if dry_run_echo(ctx, f"delete visual '{visual_name}' from page '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    b.visual_delete(page, visual_name)
    console.print(f"[green]Deleted[/green] visual '{visual_name}' from '{page}'.")


@visual.command("update")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option("--x", type=int, default=None, help="New x position.")
@click.option("--y", type=int, default=None, help="New y position.")
@click.option("--z", type=int, default=None, help="New z (stacking) order.")
@click.option("--width", type=int, default=None, help="New width.")
@click.option("--height", type=int, default=None, help="New height.")
@click.option("--tab-order", type=int, default=None, help="New tab order.")
@click.option("--title", default=None, help="New visual title text.")
@click.pass_context
def visual_update(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    x: int | None,
    y: int | None,
    z: int | None,
    width: int | None,
    height: int | None,
    tab_order: int | None,
    title: str | None,
) -> None:
    """Patch an existing visual's position and/or title in place.

    Only the options you pass are changed; query bindings and formatting are
    preserved. To rebind fields, delete the visual and re-add it.

    \b
    Example — move and retitle:
      pbi visual update --pbip MyReport --page "Sales" --name abc123 \\
        --x 40 --y 40 --width 480 --title "Revenue by Region"
    """
    if all(v is None for v in (x, y, z, width, height, tab_order, title)):
        raise click.UsageError("Pass at least one property to change (e.g. --x, --title).")
    if dry_run_echo(ctx, f"update visual '{visual_name}' on page '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    ok = b.visual_update(
        page,
        visual_name,
        x=x,
        y=y,
        z=z,
        width=width,
        height=height,
        tab_order=tab_order,
        title=title,
    )
    if ok:
        console.print(f"[green]Updated[/green] visual '{visual_name}' on '{page}'.")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


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
            "Playwright not installed. Run: pip install pbi-cli-tool[viz] && playwright install chromium"  # noqa: E501
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


def _next_position(backend: Any, page: str, w: int, h: int) -> tuple[int, int]:
    """Find the next free position on the page using simple row-packing."""
    GUTTER = 16
    CANVAS_W = 1280

    existing = backend.visual_list(page)
    if not existing:
        return GUTTER, GUTTER

    # Find bottom-right of all existing visuals
    max_y = max((v["y"] + v["height"] for v in existing), default=0)

    # Try to fit on the same row
    rightmost = max((v["x"] + v["width"] for v in existing), default=0)
    candidate_x = rightmost + GUTTER

    if candidate_x + w <= CANVAS_W:
        # Find the max y of visuals in the same row region
        row_y = min(
            (v["y"] for v in existing if v["x"] + v["width"] + GUTTER == candidate_x),
            default=GUTTER,
        )
        return candidate_x, row_y

    # Start a new row
    return GUTTER, max_y + GUTTER


def _parse_rules(rules: tuple[str, ...]) -> list[tuple]:
    """Parse rule strings into tuples.

    'OP:THRESHOLD:VALUE'        -> (op, threshold, value)
    'between:LOW:HIGH:VALUE'    -> ('between', low, high, value)

    VALUE is a hex colour (for colour rules) or an icon name (for icon rules).
    """
    parsed: list[tuple] = []
    for raw in rules:
        parts = [p.strip() for p in raw.split(":")]
        if parts and parts[0] == "between":
            if len(parts) != 4:
                raise click.UsageError(
                    f"Invalid --rule '{raw}'. Expected 'between:LOW:HIGH:VALUE'."
                )
            try:
                low, high = float(parts[1]), float(parts[2])
            except ValueError:
                raise click.UsageError(f"Invalid numbers in rule '{raw}'.")
            parsed.append(("between", low, high, parts[3]))
            continue
        if len(parts) != 3:
            raise click.UsageError(
                f"Invalid --rule '{raw}'. Expected 'OP:THRESHOLD:VALUE' or "
                "'between:LOW:HIGH:VALUE'."
            )
        op, threshold, value = parts
        try:
            num = float(threshold)
        except ValueError:
            raise click.UsageError(f"Invalid threshold '{threshold}' in rule '{raw}'.")
        parsed.append((op, num, value))
    return parsed


# ── Conditional Formatting ─────────────────────────────────────────────────────


@visual.command("format")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--visual", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option(
    "--type",
    "fmt_type",
    type=click.Choice(["color-scale", "data-bar", "rules", "icons"]),
    required=True,
    help="Conditional formatting type.",
)
@click.option("--table", required=True, help="Table name containing the measure.")
@click.option("--measure", required=True, help="Measure name to apply formatting to.")
@click.option(
    "--rule",
    "rules",
    multiple=True,
    help="Rule for --type rules, as 'OP:THRESHOLD:#HEX' (e.g. '>=:1000000:#00FF00'). "
    "Repeatable; evaluated top-to-bottom, first match wins.",
)
@click.option(
    "--target",
    type=click.Choice(["fill", "text"]),
    default="fill",
    show_default=True,
    help="What --type rules colours: cell fill (backColor) or text (fontColor).",
)
@click.option(
    "--low-color", default="#FF0000", show_default=True, help="Low value color (color-scale)."
)
@click.option(
    "--mid-color",
    default="#FFFF00",
    show_default=True,
    help="Mid value color (color-scale, omit to skip).",
)
@click.option(
    "--high-color", default="#00FF00", show_default=True, help="High value color (color-scale)."
)
@click.option(
    "--positive-color",
    default="#118DFF",
    show_default=True,
    help="Positive value color (data-bar).",
)
@click.option(
    "--negative-color",
    default="#FC4E2A",
    show_default=True,
    help="Negative value color (data-bar).",
)
@click.pass_context
def visual_format(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    fmt_type: str,
    table: str,
    measure: str,
    rules: tuple[str, ...],
    target: str,
    low_color: str,
    mid_color: str,
    high_color: str,
    positive_color: str,
    negative_color: str,
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

    \b
    Rule-based example (text colour by threshold, first match wins):
      pbi visual format --pbip MyReport --page "Sales" --visual abc123 \\
        --type rules --target text --table financials --measure Profit \\
        --rule ">=:100000:#107C10" --rule ">=:0:#D83B01" --rule "<:0:#A4262C"
    """
    if dry_run_echo(
        ctx,
        f"apply {fmt_type} conditional format to '{measure}' in visual '{visual_name}'",
    ):
        return

    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)

    if fmt_type == "rules":
        if not rules:
            raise click.UsageError("--type rules requires at least one --rule OP:THRESHOLD:#HEX.")
        parsed = _parse_rules(rules)
        found = b.visual_format_rules(
            page,
            visual_name,
            table,
            measure,
            parsed,
            target="fontColor" if target == "text" else "backColor",
        )
    elif fmt_type == "icons":
        # No --rule => Desktop's default 3-band percent icon set.
        parsed_icons = _parse_rules(rules) if rules else None
        found = b.visual_format_icons(page, visual_name, table, measure, rules=parsed_icons)
    elif fmt_type == "color-scale":
        found = b.visual_format_color_scale(
            page,
            visual_name,
            table,
            measure,
            low_color=low_color,
            mid_color=mid_color if mid_color else None,
            high_color=high_color,
        )
    else:  # data-bar
        found = b.visual_format_data_bar(
            page,
            visual_name,
            table,
            measure,
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


# ── Visual interactions & slicer sync ───────────────────────────────────────────


@visual.command("interaction")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--source", required=True, help="Source visual name (the one being clicked).")
@click.option("--target", required=True, help="Target visual name (the one that reacts).")
@click.option(
    "--type",
    "interaction_type",
    type=click.Choice(["Default", "DataFilter", "HighlightFilter", "NoFilter"]),
    required=True,
    help="How the source filters the target. NoFilter = no cross-filtering.",
)
@click.pass_context
def visual_interaction(
    ctx: click.Context,
    pbip: str,
    page: str,
    source: str,
    target: str,
    interaction_type: str,
) -> None:
    """Set how one visual cross-filters another on a page (PBIR GA only).

    \b
    Example — stop a slicer from filtering a KPI card:
      pbi visual interaction --pbip MyReport --page "Sales" \\
        --source slicer_abc --target card_xyz --type NoFilter
    """
    if dry_run_echo(
        ctx, f"set interaction {source} -> {target} = {interaction_type} on '{page}'"
    ):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        b.set_visual_interaction(page, source, target, interaction_type)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print(
        f"[green]Interaction set:[/green] {source} → {target} = {interaction_type} on '{page}'"
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")


@visual.command("sync-slicer")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name containing the slicer.")
@click.option("--name", "visual_name", required=True, help="Slicer visual name.")
@click.option("--group", required=True, help="Sync group name; slicers sharing it stay in sync.")
@click.option(
    "--no-field-changes",
    is_flag=True,
    default=False,
    help="Do not sync when the slicer field changes.",
)
@click.option(
    "--no-filter-changes",
    is_flag=True,
    default=False,
    help="Do not sync when the slicer selection changes.",
)
@click.pass_context
def visual_sync_slicer(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    group: str,
    no_field_changes: bool,
    no_filter_changes: bool,
) -> None:
    """Add a slicer to a named sync group so it stays in sync across pages (PBIR GA).

    Run this on each slicer that should be synced, passing the same --group.

    \b
    Example:
      pbi visual sync-slicer --pbip MyReport --page "Sales" --name slicer_abc --group "Region"
    """
    if dry_run_echo(ctx, f"sync slicer '{visual_name}' into group '{group}' on '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.set_slicer_sync(
            page,
            visual_name,
            group,
            field_changes=not no_field_changes,
            filter_changes=not no_filter_changes,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        console.print(f"[green]Slicer synced:[/green] '{visual_name}' → group '{group}'")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


# ── Field rebinding ──────────────────────────────────────────────────────────────


@visual.command("set-field")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option("--role", required=True, help="Visual role slot, e.g. Category, Y, Values, Rows.")
@click.option("--table", required=True, help="Table (entity) of the field to bind.")
@click.option("--field", required=True, help="Column or measure name to bind.")
@click.option("--measure", "is_measure", is_flag=True, help="The field is an explicit DAX measure.")
@click.option(
    "--agg",
    type=click.Choice(["sum", "avg", "min", "max", "count", "none"]),
    default="sum",
    show_default=True,
    help="Aggregation for a column ('none' = no aggregation).",
)
@click.option("--append", is_flag=True, help="Append to the role instead of replacing it.")
@click.pass_context
def visual_set_field(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    role: str,
    table: str,
    field: str,
    is_measure: bool,
    agg: str,
    append: bool,
) -> None:
    """Rebind which field a visual role uses (rewrites the query projection).

    \b
    Example — swap a chart's value from Sales to Profit:
      pbi visual set-field --pbip MyReport --page "Sales" --name abc123 \\
        --role Y --table financials --field Profit
    """
    if dry_run_echo(ctx, f"set {role} = {table}[{field}] on visual '{visual_name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    agg_val = AGG_MAP[agg]
    b = PbirBackend(pbip)
    try:
        ok = b.visual_set_field(
            page,
            visual_name,
            role,
            table,
            field,
            is_measure=is_measure,
            agg=None if agg_val < 0 else agg_val,
            replace=not append,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        console.print(
            f"[green]Bound[/green] {role} = {table}[{field}] on visual '{visual_name}'."
        )
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


# ── Non-data elements: textbox, buttons, navigators ─────────────────────────────


@visual.command("add-element")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name to add the element to.")
@click.option(
    "--type",
    "element_type",
    type=click.Choice(["textbox", "button", "page-nav", "bookmark-nav"]),
    required=True,
    help="Element type.",
)
@click.option("--text", default=None, help="Text content (textbox) or label (button).")
@click.option("--shape", default="blank", show_default=True, help="Button shape (button only).")
@click.option("--x", type=int, default=16, show_default=True)
@click.option("--y", type=int, default=16, show_default=True)
@click.option("--width", type=int, default=300, show_default=True)
@click.option("--height", type=int, default=80, show_default=True)
@click.pass_context
def visual_add_element(
    ctx: click.Context,
    pbip: str,
    page: str,
    element_type: str,
    text: str | None,
    shape: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Add a non-data element (textbox, button, page/bookmark navigator) to a page.

    \b
    Examples:
      pbi visual add-element --pbip R --page "Sales" --type textbox --text "Q4 Review"
      pbi visual add-element --pbip R --page "Sales" --type page-nav --width 800 --height 60
    """
    if dry_run_echo(ctx, f"add {element_type} element to page '{page}'"):
        return
    from pbi_cli.intelligence.visual_builder import (
        VisualSpec,
        build_action_button,
        build_bookmark_navigator,
        build_page_navigator,
        build_textbox,
    )

    if element_type == "textbox":
        body = build_textbox(text or "")
    elif element_type == "button":
        body = build_action_button(shape=shape, text=text)
    elif element_type == "page-nav":
        body = build_page_navigator()
    else:
        body = build_bookmark_navigator()

    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    spec = VisualSpec(
        visual_type=body["visualType"],
        visual_body=body,
        x=x,
        y=y,
        width=width,
        height=height,
    )
    result = b.visual_add(page, spec)
    console.print(
        f"[green]Added[/green] {element_type} '{result['name']}' to page '{page}'."
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


@visual.command("reference-line")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Cartesian chart visual name.")
@click.option("--value", type=float, required=True, help="Constant Y value for the line.")
@click.option("--label", default="Target", show_default=True, help="Line label.")
@click.option("--color", default="#E81123", show_default=True, help="Line colour (hex).")
@click.option(
    "--style",
    type=click.Choice(["solid", "dashed", "dotted"]),
    default="dashed",
    show_default=True,
)
@click.option("--no-label", is_flag=True, help="Hide the line's data label.")
@click.pass_context
def visual_reference_line(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    value: float,
    label: str,
    color: str,
    style: str,
    no_label: bool,
) -> None:
    """Add a constant Y reference (target) line to a cartesian chart.

    \b
    Example — a 1,000,000 sales target line:
      pbi visual reference-line --pbip R --page "Sales" --name bar1 \\
        --value 1000000 --label "Target" --color "#E81123"
    """
    if dry_run_echo(ctx, f"add reference line at {value} on visual '{visual_name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.visual_add_reference_line(
            page, visual_name, value, name=label, color=color, style=style,
            show_label=not no_label,
        )
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        console.print(f"[green]Reference line added:[/green] {label} @ {value} on '{visual_name}'.")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


@visual.command("action")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Button/shape visual name.")
@click.option(
    "--type",
    "action_type",
    type=click.Choice(["Back", "PageNavigation", "Bookmark", "Drill", "QnA", "WebUrl"]),
    required=True,
    help="Action type.",
)
@click.option(
    "--target",
    default=None,
    help="Target: page (PageNavigation), bookmark (Bookmark), or URL (WebUrl).",
)
@click.pass_context
def visual_action(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    action_type: str,
    target: str | None,
) -> None:
    """Wire a navigation/action onto a button so it actually does something.

    A button added with `add-element` has no action until you set one here.

    \b
    Examples:
      pbi visual action --pbip R --page "Home" --name btn1 --type PageNavigation --target "Detail"
      pbi visual action --pbip R --page "Home" --name btn2 --type Bookmark --target "Q4 View"
      pbi visual action --pbip R --page "Home" --name back1 --type Back
    """
    if dry_run_echo(ctx, f"set {action_type} action on visual '{visual_name}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.visual_set_action(page, visual_name, action_type, target=target)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        tgt = f" → {target}" if target else ""
        console.print(f"[green]Action set:[/green] {action_type}{tgt} on '{visual_name}'.")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


# ── Clone & move ────────────────────────────────────────────────────────────────


@visual.command("clone")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Source page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name to clone.")
@click.option("--to-page", default=None, help="Target page (default: same page, offset).")
@click.option("--dx", type=int, default=24, show_default=True, help="X offset when cloning in place.")  # noqa: E501
@click.option("--dy", type=int, default=24, show_default=True, help="Y offset when cloning in place.")  # noqa: E501
@click.pass_context
def visual_clone(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    to_page: str | None,
    dx: int,
    dy: int,
) -> None:
    """Clone a visual under a fresh id — on the same page (offset) or another page.

    Preserves bindings, formatting and conditional formatting. The clone never
    inherits group membership.

    \b
    Example:
      pbi visual clone --pbip R --page "Sales" --name abc123 --to-page "EMEA"
    """
    if dry_run_echo(ctx, f"clone visual '{visual_name}' from '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        result = b.visual_clone(page, visual_name, target_page=to_page, dx=dx, dy=dy)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if not result:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)
    console.print(
        f"[green]Cloned[/green] '{visual_name}' → '{result['name']}' on page '{result['page']}'."
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


@visual.command("move")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Source page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name to move.")
@click.option("--to-page", required=True, help="Target page display name.")
@click.pass_context
def visual_move(
    ctx: click.Context, pbip: str, page: str, visual_name: str, to_page: str
) -> None:
    """Move a visual to another page, keeping its id.

    Drops group membership and removes now-dangling visual interactions on the
    source page.

    \b
    Example:
      pbi visual move --pbip R --page "Sales" --name abc123 --to-page "Detail"
    """
    if dry_run_echo(ctx, f"move visual '{visual_name}' from '{page}' to '{to_page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        result = b.visual_move(page, visual_name, to_page)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if not result:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Moved[/green] '{visual_name}' to page '{to_page}'.")
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


# ── Visual groups & mobile layout ───────────────────────────────────────────────


@visual.command("group")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option(
    "--member",
    "members",
    multiple=True,
    required=True,
    help="Visual name to include in the group (repeatable; at least two).",
)
@click.option("--name", "display_name", default=None, help="Group display name.")
@click.pass_context
def visual_group(
    ctx: click.Context,
    pbip: str,
    page: str,
    members: tuple,
    display_name,
) -> None:
    """Group existing visuals on a page so they move/resize together.

    
    Example:
      pbi visual group --pbip R --page "Sales" --member card_a --member card_b --name "KPIs"
    """
    if dry_run_echo(ctx, f"group {len(members)} visuals on page '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        result = b.visual_group_add(page, list(members), display_name=display_name)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print(
        f"[green]Grouped[/green] {len(result['members'])} visuals "
        f"as '{result['displayName']}' (id: {result['name']})."
    )
    console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")


@visual.command("mobile")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name.")
@click.option("--x", type=int, required=True, help="X on the mobile canvas (320 wide).")
@click.option("--y", type=int, required=True, help="Y on the mobile canvas.")
@click.option("--width", type=int, required=True, help="Width on the mobile canvas.")
@click.option("--height", type=int, required=True, help="Height on the mobile canvas.")
@click.pass_context
def visual_mobile(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Place a visual on the phone (mobile) layout canvas.

    The mobile canvas is 320 units wide. Writes a mobile.json beside the visual.

    
    Example:
      pbi visual mobile --pbip R --page "Sales" --name card_a --x 0 --y 0 --width 320 --height 120
    """
    if dry_run_echo(ctx, f"set mobile layout for visual '{visual_name}' on '{page}'"):
        return
    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.visual_set_mobile(page, visual_name, x, y, width, height)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        console.print(f"[green]Mobile layout set[/green] for '{visual_name}' on '{page}'.")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see it.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


# ── Multi-role rebind & generic formatting ──────────────────────────────────────


def _parse_bind(spec: str):
    """Parse a 'ROLE/TABLE/FIELD[/KIND]' bind spec into (role, FieldDef).

    KIND is one of: col, sum, avg, min, max, count, measure (default: sum).
    """
    from pbi_cli.intelligence.visual_builder import FieldDef

    parts = spec.split("/")
    if len(parts) < 3:
        raise click.UsageError(
            f"--bind '{spec}' must be ROLE/TABLE/FIELD[/KIND] (e.g. 'Y/financials/Sales/sum')."
        )
    role, table, fieldname = parts[0], parts[1], parts[2]
    kind = parts[3].lower() if len(parts) > 3 else "sum"
    if not (role and table and fieldname):
        raise click.UsageError(f"--bind '{spec}' has an empty ROLE, TABLE or FIELD.")
    if kind == "measure":
        fd = FieldDef(entity=table, property=fieldname, is_measure=True)
    elif kind == "col":
        fd = FieldDef(entity=table, property=fieldname, agg=None)
    elif kind in AGG_MAP and AGG_MAP[kind] >= 0:
        fd = FieldDef(entity=table, property=fieldname, agg=AGG_MAP[kind])
    else:
        raise click.UsageError(
            f"--bind '{spec}' has unknown KIND '{kind}'; use col/sum/avg/min/max/count/measure."
        )
    return role, fd


@visual.command("rebind")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option(
    "--bind",
    "binds",
    multiple=True,
    required=True,
    help="Role binding 'ROLE/TABLE/FIELD[/KIND]' (repeatable). "
    "KIND: col, sum, avg, min, max, count, measure (default sum). "
    "Repeat the same ROLE to put multiple fields in one slot.",
)
@click.option(
    "--clear-unlisted",
    is_flag=True,
    help="Remove every role not given here (full atomic rebind).",
)
@click.pass_context
def visual_rebind(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    binds: tuple[str, ...],
    clear_unlisted: bool,
) -> None:
    """Rebind several role slots of a visual at once, in a single atomic write.

    Unlike ``set-field`` (one role), this rewrites multiple roles together and
    preserves the visual's position, title and formatting. With --clear-unlisted
    the visual ends up bound to exactly what you pass — the safe in-place
    equivalent of delete + re-add.

    \b
    Example — turn a chart into Country/Sales+Profit:
      pbi visual rebind --pbip R --page "Sales" --name abc123 \\
        --bind "Category/financials/Country/col" \\
        --bind "Y/financials/Sales/sum" --bind "Y/financials/Profit/sum" \\
        --clear-unlisted
    """
    if dry_run_echo(ctx, f"rebind {len(binds)} role binding(s) on visual '{visual_name}'"):
        return

    bindings: dict[str, list] = {}
    for spec in binds:
        role, fd = _parse_bind(spec)
        bindings.setdefault(role, []).append(fd)

    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.visual_rebind(page, visual_name, bindings, clear_unlisted=clear_unlisted)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        roles = ", ".join(bindings)
        console.print(f"[green]Rebound[/green] roles [{roles}] on visual '{visual_name}'.")
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)


@visual.command("set-format")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page display name.")
@click.option("--name", "visual_name", required=True, help="Visual name (from pbi visual list).")
@click.option(
    "--object",
    "object_name",
    required=True,
    help="Formatting object, e.g. title, background, legend, dataLabels, categoryAxis.",
)
@click.option("--property", "property_name", required=True, help="Property on the object.")
@click.option("--value", required=True, help="Value to set.")
@click.option(
    "--type",
    "value_type",
    type=click.Choice(["auto", "text", "number", "bool", "color"]),
    default="auto",
    show_default=True,
    help="How to interpret --value.",
)
@click.option(
    "--container",
    "container_level",
    is_flag=True,
    help="Target visualContainerObjects (title/background/border/header) instead "
    "of the type-specific objects.",
)
@click.pass_context
def visual_set_format(
    ctx: click.Context,
    pbip: str,
    page: str,
    visual_name: str,
    object_name: str,
    property_name: str,
    value: str,
    value_type: str,
    container_level: bool,
) -> None:
    """Set any formatting-object property on a visual (general formatting writer).

    Goes beyond conditional formatting: turn data labels on, set a legend
    position, recolour the background, change an axis title, and so on.

    \b
    Examples:
      pbi visual set-format --pbip R --page "Sales" --name abc --container \\
        --object title --property show --value true --type bool
      pbi visual set-format --pbip R --page "Sales" --name abc \\
        --object legend --property position --value Top
      pbi visual set-format --pbip R --page "Sales" --name abc --container \\
        --object background --property color --value "#F5F5F5" --type color
    """
    if dry_run_echo(
        ctx, f"set {object_name}.{property_name}={value} on visual '{visual_name}'"
    ):
        return

    # Coerce the string --value to the right Python type for 'auto'/typed writes.
    coerced: object = value
    if value_type == "number":
        coerced = float(value)
    elif value_type == "bool":
        coerced = value.strip().lower() in ("true", "1", "yes", "on")

    from pbi_cli.backends.pbir_backend import PbirBackend

    b = PbirBackend(pbip)
    try:
        ok = b.visual_set_format(
            page,
            visual_name,
            object_name,
            property_name,
            coerced,
            value_type=value_type,
            container_level=container_level,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    if ok:
        console.print(
            f"[green]Format set:[/green] {object_name}.{property_name} = {value} "
            f"on visual '{visual_name}'."
        )
        console.print("[yellow]Tip:[/yellow] Reload the report in Power BI Desktop to see changes.")
    else:
        console.print(f"[red]Visual '{visual_name}' not found on page '{page}'.[/red]")
        raise SystemExit(1)
