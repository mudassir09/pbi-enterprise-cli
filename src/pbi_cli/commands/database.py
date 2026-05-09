"""pbi database — TMDL export/import commands."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend

console = Console()


@click.group()
def database() -> None:
    """Export and import TMDL snapshots."""


@database.command("export-tmdl")
@click.argument("path")
@click.pass_context
def export_tmdl(ctx: click.Context, path: str) -> None:
    """Export the current model as TMDL files to a directory."""
    if dry_run_echo(ctx, f"export TMDL to {path}"):
        return
    backend = get_backend(ctx)
    backend.tmdl_export(path)
    console.print(f"[green]TMDL exported to:[/green] {path}")


@database.command("import-tmdl")
@click.argument("path")
@click.pass_context
def import_tmdl(ctx: click.Context, path: str) -> None:
    """Import TMDL files from a directory into the connected model."""
    if dry_run_echo(ctx, f"import TMDL from {path}"):
        return
    backend = get_backend(ctx)
    backend.tmdl_import(path)
    console.print(f"[green]TMDL imported from:[/green] {path}")
