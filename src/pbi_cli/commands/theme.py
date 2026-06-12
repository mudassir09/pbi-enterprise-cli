"""pbi theme — theme generation and validation commands (Epic C)."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console(legacy_windows=False)


@click.group()
def theme() -> None:
    """Generate and validate Power BI themes with WCAG accessibility compliance."""


@theme.command("generate")
@click.option("--brand-color", required=True, help="Primary brand hex colour (e.g. #0078D4).")
@click.option(
    "--style", type=click.Choice(["corporate", "modern", "minimal", "dark"]), default="corporate"
)
@click.option("--output", default="theme.json", help="Output theme JSON file.")
@click.pass_context
def theme_generate(ctx: click.Context, brand_color: str, style: str, output: str) -> None:
    """Generate a complete Power BI theme JSON from a brand colour with WCAG compliance."""
    from pbi_cli.intelligence.theme_generator import ThemeGenerator

    console.print(f"[cyan]Generating {style} theme from:[/cyan] {brand_color}")
    gen = ThemeGenerator()
    theme_json = gen.generate(brand_color=brand_color, style=style)
    validation = gen.validate_wcag(theme_json)

    if not validation["passes"]:
        console.print(
            f"[yellow]WCAG issues:[/yellow] {len(validation['failures'])} contrast failures — auto-fixing..."  # noqa: E501
        )
        theme_json = gen.fix_contrast(theme_json, validation["failures"])

    if dry_run_echo(ctx, f"write theme to {output}"):
        return

    Path(output).write_text(json.dumps(theme_json, indent=2), encoding="utf-8")
    console.print(f"[green]Theme written to:[/green] {output}")


@theme.command("validate")
@click.argument("theme_file", type=click.Path(exists=True))
@click.pass_context
def theme_validate(ctx: click.Context, theme_file: str) -> None:
    """Check a theme JSON for WCAG AA contrast compliance."""
    from pbi_cli.intelligence.theme_generator import ThemeGenerator

    theme_json = json.loads(Path(theme_file).read_text(encoding="utf-8"))
    gen = ThemeGenerator()
    result = gen.validate_wcag(theme_json)
    output_json_or_table(result, ctx, title="WCAG Validation")
