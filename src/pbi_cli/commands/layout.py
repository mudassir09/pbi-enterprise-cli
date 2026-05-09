"""pbi layout — auto-layout engine commands (Epic C)."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()


@click.group()
def layout() -> None:
    """Auto-position visuals using the shelf-packing layout engine."""


@layout.command("auto")
@click.option("--pbip", required=True, help="Path to the .pbip project folder or file.")
@click.option("--page", required=True, help="Page name to layout.")
@click.option("--canvas-width", default=1280, show_default=True)
@click.option("--canvas-height", default=720, show_default=True)
@click.pass_context
def layout_auto(ctx: click.Context, pbip: str, page: str, canvas_width: int, canvas_height: int) -> None:
    """Load all visuals from a PBIR page, classify them, and repack onto the canvas."""
    from pbi_cli.intelligence.layout_engine import LayoutEngine
    from pbi_cli.backends.pbir_backend import PbirBackend

    console.print(f"[cyan]Auto-layout:[/cyan] page '{page}' ({canvas_width}x{canvas_height})")
    pbir = PbirBackend(pbip)
    visuals = pbir.visual_list(page)

    if not visuals:
        console.print(f"[yellow]No visuals found on page '{page}'.[/yellow]")
        return

    console.print(f"[dim]Found {len(visuals)} visuals — classifying and packing...[/dim]")
    engine = LayoutEngine(canvas_width=canvas_width, canvas_height=canvas_height)
    positions = engine.pack(visuals)

    if dry_run_echo(ctx, f"apply {len(positions)} visual positions to page '{page}'"):
        output_json_or_table(positions, ctx, title="Visual Layout (dry run)")
        return

    # Write positions back to PBIR files
    from pbi_cli.intelligence.visual_builder import VisualSpec
    from pbi_cli._audit import write_audit_entry
    for pos in positions:
        vd = pbir._ga_visuals_dir(page)  # type: ignore[attr-defined]
        if vd is None:
            continue
        for vdir in vd.iterdir():
            if not vdir.is_dir():
                continue
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            import json
            data = json.loads(vj.read_text(encoding="utf-8"))
            if data.get("name") == pos["name"]:
                data.setdefault("position", {}).update({
                    "x": pos["x"], "y": pos["y"],
                    "width": pos["width"], "height": pos["height"],
                })
                vj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    write_audit_entry("layout auto", extra={"page": page, "visuals_repositioned": len(positions)})
    console.print(f"[green]Repositioned[/green] {len(positions)} visuals on page '{page}'")
    output_json_or_table(positions, ctx, title="Visual Layout")


@layout.command("template")
@click.option("--name", required=True, type=click.Choice(["executive-dashboard", "operational-monitor", "financial-report", "drill-through-detail"]))
@click.option("--page", required=True, help="Page name.")
@click.pass_context
def layout_template(ctx: click.Context, name: str, page: str) -> None:
    """Apply a named layout template to a page."""
    templates = {
        "executive-dashboard": ["KPI Strip (top 15%)", "Main Chart (center 60%)", "Table (bottom 25%)", "Slicer Rail (right 20%)"],
        "operational-monitor": ["KPI Strip", "Real-time Chart", "Alert Table"],
        "financial-report": ["Header", "YTD KPIs", "Trend Chart", "Variance Table"],
        "drill-through-detail": ["Filter Panel", "Detail Table", "Supporting Chart"],
    }
    console.print(f"[cyan]Template:[/cyan] {name} -> page '{page}'")
    for zone in templates[name]:
        console.print(f"  [dim]Zone:[/dim] {zone}")
