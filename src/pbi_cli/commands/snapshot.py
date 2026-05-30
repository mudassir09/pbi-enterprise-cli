"""pbi snapshot — model snapshot management (create, list, restore, diff)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()

_DEFAULT_SNAPSHOT_DIR = Path(".pbi") / "snapshots"


def _snapshot_dir() -> Path:
    return _DEFAULT_SNAPSHOT_DIR


@click.group("snapshot")
def snapshot_cmd() -> None:
    """Manage TMDL model snapshots for rollback and diffing."""


@snapshot_cmd.command("create")
@click.option(
    "--label",
    default=None,
    help="Human-readable label (default: ISO timestamp).",
)
@click.pass_context
def snapshot_create(ctx: click.Context, label: str | None) -> None:
    """Export the current model as a TMDL snapshot.

    \b
    Snapshots are stored in .pbi/snapshots/<timestamp>/
    and can be restored with 'pbi snapshot restore'.

    \b
    Example:
      pbi snapshot create --label before-refactor
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{ts}_{label}" if label else ts
    out_path = _snapshot_dir() / folder_name

    if dry_run_echo(ctx, f"create snapshot at '{out_path}'"):
        return

    backend = get_backend(ctx)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        backend.tmdl_export(str(out_path))
        file_count = len(list(out_path.rglob("*.tmdl")))

        meta = {"created_at": datetime.datetime.now().isoformat(), "label": label or ts}
        (out_path / ".snapshot-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        console.print(f"[green]Snapshot created:[/green] {out_path}")
        console.print(f"  Files: {file_count} .tmdl file(s)")
        console.print(f"\nRestore with:  pbi snapshot restore {folder_name}")
        console.print(f"Diff with:     pbi snapshot diff {folder_name}")
    except Exception as exc:
        console.print(f"[red]Snapshot failed:[/red] {exc}")
        raise SystemExit(4)


@snapshot_cmd.command("list")
def snapshot_list() -> None:
    """List all snapshots in .pbi/snapshots/."""
    snap_dir = _snapshot_dir()
    if not snap_dir.exists():
        console.print("[yellow]No snapshots found.[/yellow]")
        console.print("Create one with: pbi snapshot create")
        return

    snapshots = sorted(snap_dir.iterdir(), reverse=True)
    table = Table(title="Model Snapshots")
    table.add_column("ID / Folder")
    table.add_column("Created")
    table.add_column("Label")
    table.add_column("Files", justify="right")
    for s in snapshots:
        if not s.is_dir():
            continue
        meta_file = s / ".snapshot-meta.json"
        created = label = ""
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            created = meta.get("created_at", "")
            label = meta.get("label", "")
        files = len(list(s.rglob("*.tmdl")))
        table.add_row(s.name, created, label, str(files))
    console.print(table)


@snapshot_cmd.command("restore")
@click.argument("snapshot_id")
@click.option("--confirm", is_flag=True, help="Confirm restore (required for non-dry-run).")
@click.pass_context
def snapshot_restore(ctx: click.Context, snapshot_id: str, confirm: bool) -> None:
    """Restore the model from a snapshot.

    SNAPSHOT_ID is the folder name shown by 'pbi snapshot list'.

    \b
    Example:
      pbi snapshot restore 20260530_142300_before-refactor --confirm
    """
    snap_path = _snapshot_dir() / snapshot_id
    if not snap_path.exists():
        console.print(f"[red]Snapshot not found:[/red] {snap_path}")
        raise SystemExit(1)

    if dry_run_echo(ctx, f"restore model from snapshot '{snapshot_id}'"):
        return

    if not confirm:
        console.print("[yellow]Add --confirm to apply the restore.[/yellow]")
        console.print("This overwrites the current model state.")
        raise SystemExit(1)

    backend = get_backend(ctx)
    try:
        backend.tmdl_import(str(snap_path))
        console.print(f"[green]Restored from snapshot:[/green] {snapshot_id}")
    except Exception as exc:
        console.print(f"[red]Restore failed:[/red] {exc}")
        raise SystemExit(4)


@snapshot_cmd.command("diff")
@click.argument("snapshot_id")
@click.pass_context
def snapshot_diff(ctx: click.Context, snapshot_id: str) -> None:
    """Show the diff between the current model and a snapshot.

    \b
    Example:
      pbi snapshot diff 20260530_142300_before-refactor
    """
    snap_path = _snapshot_dir() / snapshot_id
    if not snap_path.exists():
        console.print(f"[red]Snapshot not found:[/red] {snap_path}")
        raise SystemExit(1)

    backend = get_backend(ctx)
    result = backend.model_diff(snapshot_path=str(snap_path))
    if not result.get("has_changes"):
        console.print("[green]No changes[/green] — model matches snapshot.")
        return

    added = result.get("added", [])
    removed = result.get("removed", [])
    changed = result.get("changed", [])
    console.print(
        f"[yellow]Changes vs {snapshot_id}:[/yellow] "
        f"[green]+{len(added)}[/green] added, "
        f"[red]-{len(removed)}[/red] removed, "
        f"[yellow]~{len(changed)}[/yellow] modified"
    )
    output_json_or_table(result, ctx, title=f"Diff vs {snapshot_id}")
