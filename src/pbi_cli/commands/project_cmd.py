"""pbi project — scaffold complete, openable PBIP projects from scratch."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo

console = Console(legacy_windows=False)


@click.group()
def project() -> None:
    """Create and manage complete .pbip projects (model + report)."""


@project.command("new")
@click.option("--out", required=True, help="Output directory the project folder is created in.")
@click.option("--name", default="New Report", show_default=True, help="Project / report name.")
@click.option("--table", default="Financials", show_default=True, help="Sample model table name.")
@click.pass_context
def project_new(ctx: click.Context, out: str, name: str, table: str) -> None:
    """Scaffold a complete, openable PBIP (offline model with sample data + report).

    The result opens directly in Power BI Desktop with no data source to connect —
    the model uses entered data. Enable the PBIR preview feature in Desktop first.

    \b
    Example:
      pbi project new --out "C:/Users/Me/Documents" --name "Sales Demo"
    """
    if dry_run_echo(ctx, f"scaffold openable PBIP '{name}' in '{out}'"):
        return
    from pbi_cli.project_scaffold import create_project

    pbip_path = create_project(out, name=name, table=table)
    console.print(f"[green]Project created:[/green] {pbip_path}")
    console.print(
        "[yellow]Tip:[/yellow] Open the .pbip in Power BI Desktop "
        "(PBIR preview feature must be enabled), then click Refresh to load sample data."
    )
