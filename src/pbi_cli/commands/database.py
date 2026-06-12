"""pbi database — TMDL export/import commands."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend

console = Console(legacy_windows=False)


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


@database.command("diff-tmdl")
@click.argument("snapshot_path", type=click.Path(exists=True))
@click.option("--output", default=None, type=click.Path(), help="Save diff report to a JSON file.")
@click.pass_context
def diff_tmdl(ctx: click.Context, snapshot_path: str, output: str | None) -> None:
    """Compare the live model against a TMDL snapshot directory.

    Reports added, removed, and changed objects (tables, measures, columns,
    relationships) relative to the snapshot.

    \b
    Example:
      pbi database diff-tmdl ./snapshots/2024-01-01/
    """
    import json as _json
    from pathlib import Path

    from pbi_cli.commands._shared import output_json_or_table

    backend = get_backend(ctx)
    diff = backend.model_diff(snapshot_path)

    if output:
        Path(output).write_text(_json.dumps(diff, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Diff saved to:[/green] {output}")
    else:
        if not diff.get("has_changes"):
            console.print("[green]No changes detected[/green] — model matches snapshot.")
        else:
            console.print(
                f"[yellow]Changes detected:[/yellow] {len(diff.get('added', []))} added, "
                f"{len(diff.get('removed', []))} removed, "
                f"{len(diff.get('changed', []))} modified"
            )
            output_json_or_table(diff, ctx, title="TMDL Diff")
