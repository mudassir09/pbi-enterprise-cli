"""Shared utilities for command implementations."""

from __future__ import annotations

import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console(legacy_windows=False)


def get_backend(ctx: click.Context) -> Any:
    """Get or create the backend from context, auto-connecting if needed."""
    from pbi_cli.backends.mock_backend import MockTomBackend
    from pbi_cli.backends.tom_backend import TomBackend
    from pbi_cli.backends.xmla_backend import XmlaBackend

    obj = ctx.obj or {}
    backend_name = obj.get("backend", "desktop")

    if "_backend_instance" not in obj:
        if backend_name == "mock":
            b: Any = MockTomBackend()
            b.connect()
        elif backend_name == "file":
            from pbi_cli.backends.file_backend import FileBackend

            try:
                b = FileBackend(path=obj.get("path"))
            except FileNotFoundError as exc:
                console.print(f"[red]{exc}[/red]")
                raise click.Abort()
            b.connect()
        elif backend_name == "rest":
            from pbi_cli.backends.rest_backend import RestBackend

            b = RestBackend()
            try:
                b.connect()
            except ConnectionError as exc:
                console.print(f"[red]{exc}[/red]")
                raise click.Abort()
        elif backend_name == "fabric":
            import os

            from pbi_cli.backends.fabric_backend import FabricDefinitionBackend
            from pbi_cli.fabric_api import FabricApiError

            ws = obj.get("workspace") or os.environ.get("PBI_FABRIC_WORKSPACE")
            ds = obj.get("dataset") or os.environ.get("PBI_FABRIC_DATASET")
            if not (ws and ds):
                console.print(
                    "[red]The fabric backend needs a workspace and a semantic-model id.[/red]"
                )
                console.print(
                    "Pass [bold]--workspace <id> --dataset <id>[/bold] "
                    "(or set PBI_FABRIC_WORKSPACE / PBI_FABRIC_DATASET)."
                )
                raise click.Abort()
            try:
                b = FabricDefinitionBackend(ws, ds)
                b.connect()
            except (ConnectionError, FabricApiError, ValueError) as exc:
                console.print(f"[red]{exc}[/red]")
                raise click.Abort()
        elif backend_name == "xmla":
            b = XmlaBackend()
        else:
            b = TomBackend()
        obj["_backend_instance"] = b
        ctx.obj = obj

    backend = obj["_backend_instance"]

    # Auto-connect desktop backend on first use
    if backend_name == "desktop" and not backend.is_connected():
        try:
            backend.connect(port=obj.get("port"))
        except Exception as exc:
            console.print(f"[red]Connection failed:[/red] {exc}")
            raise click.Abort()

    return backend


def output_json_or_table(data: Any, ctx: click.Context, title: str = "") -> None:
    """Print data as JSON, YAML, or Rich table depending on --json/--yaml flag."""
    if ctx.obj and ctx.obj.get("output_json"):
        click.echo(json.dumps(data, indent=2, default=str))
        return

    if ctx.obj and ctx.obj.get("output_yaml"):
        import yaml  # already a core dep
        click.echo(yaml.dump(data, allow_unicode=True, sort_keys=False).rstrip())
        return

    if isinstance(data, list) and data:
        table = Table(title=title, show_header=True)
        for key in data[0].keys():
            table.add_column(str(key))
        for row in data:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)
    elif isinstance(data, dict):
        for k, v in data.items():
            console.print(f"  [bold]{k}[/bold]: {v}")
    else:
        console.print(data)


def dry_run_echo(ctx: click.Context, action: str, detail: str = "") -> bool:
    """Print a dry-run notice. Returns True if in dry-run mode."""
    if ctx.obj and ctx.obj.get("dry_run"):
        console.print(f"[yellow][DRY RUN][/yellow] Would {action}")
        if detail:
            console.print(f"  {detail}")
        return True
    return False


def snapshot_before_write(ctx: click.Context) -> None:
    """Capture a model snapshot before a write operation (used by pbi undo)."""
    try:
        backend = ctx.obj.get("_backend_instance") if ctx.obj else None
        if backend is None or not backend.is_connected():
            return
        from pbi_cli._snapshot import capture_snapshot

        capture_snapshot(backend)
    except Exception:
        pass  # Never let snapshot failure block a write
