"""pbi deploy — deployment pipeline commands (Epic E)."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()


@click.group()
def deploy() -> None:
    """Deploy and promote models via XMLA: push, diff, promote, snapshot."""


@deploy.command("push")
@click.option("--workspace", required=True, help="Target workspace name.")
@click.option("--xmla", default=None, help="XMLA endpoint URL (overrides config).")
@click.pass_context
def deploy_push(ctx: click.Context, workspace: str, xmla: str | None) -> None:
    """Export TMDL and deploy to a workspace via XMLA with transaction safety.

    \b
    Prerequisites:
      pip install pbi-cli-tool[server]
      Set XMLA endpoint in ~/.pbi-cli/config.toml:
        [xmla]
        endpoint = "powerbi://api.powerbi.com/v1.0/myorg/MyWorkspace"

    \b
    Example:
      pbi deploy push --workspace "Production"
    """
    console.print(f"[cyan]Deploying to:[/cyan] {workspace}")
    if dry_run_echo(ctx, f"push model to workspace '{workspace}' via XMLA"):
        return

    endpoint = xmla or _get_xmla_endpoint()
    if not endpoint:
        console.print(
            "[yellow]XMLA endpoint not configured.[/yellow]\n"
            "Set it in [bold]~/.pbi-cli/config.toml[/bold]:\n"
            "  [xmla]\n"
            "  endpoint = \"powerbi://api.powerbi.com/v1.0/myorg/MyWorkspace\""
        )
        console.print("\n[yellow]XMLA backend required (v6.0). Install pbi-cli-tool[server].[/yellow]")
        return

    console.print(f"  Endpoint: {endpoint}")
    console.print("[yellow]XMLA push not yet implemented — endpoint resolved.[/yellow]")
    console.print("Use 'pbi deploy snapshot' to save a local snapshot first.")


@deploy.command("diff")
@click.option("--workspace", default=None, help="Workspace to compare against (XMLA).")
@click.option("--snapshot", default=None, help="Local TMDL snapshot directory to compare against.")
@click.pass_context
def deploy_diff(ctx: click.Context, workspace: str | None, snapshot: str | None) -> None:
    """Compare local model against deployed model or a local snapshot.

    \b
    Examples:
      pbi deploy diff --snapshot ./snapshots/2025-01-01
      pbi deploy diff --workspace "Staging"
    """
    if snapshot:
        # Use local model_diff (already implemented in TOM backend)
        backend = get_backend(ctx)
        result = backend.model_diff(snapshot_path=snapshot)
        if not result.get("has_changes"):
            console.print("[green]No changes detected[/green] — model matches snapshot.")
            return
        output_json_or_table(result, ctx, title="Model Diff vs Snapshot")
        console.print(
            f"[yellow]Changes:[/yellow] "
            f"{len(result['added'])} added, "
            f"{len(result['removed'])} removed, "
            f"{len(result['changed'])} modified"
        )
    elif workspace:
        console.print(f"[cyan]Diffing against workspace:[/cyan] {workspace}")
        endpoint = _get_xmla_endpoint()
        if not endpoint:
            console.print("[yellow]XMLA endpoint not configured — cannot diff against workspace.[/yellow]")
            console.print("Use --snapshot to diff against a local TMDL snapshot instead.")
            return
        console.print("[yellow]XMLA diff not yet implemented (XMLA backend required).[/yellow]")
        console.print("Tip: Use 'pbi deploy snapshot' to capture a baseline, then 'pbi deploy diff --snapshot'.")
    else:
        raise click.UsageError("Provide --snapshot or --workspace.")


@deploy.command("snapshot")
@click.option(
    "--output",
    default=None,
    help="Output directory for the TMDL snapshot (default: ./snapshots/<timestamp>).",
)
@click.pass_context
def deploy_snapshot(ctx: click.Context, output: str | None) -> None:
    """Export the current model as a TMDL snapshot to a local directory.

    Snapshots can be compared with 'pbi deploy diff --snapshot' or 'pbi model diff --snapshot'.

    \b
    Example:
      pbi deploy snapshot --output ./snapshots/before-refactor
    """
    import datetime
    from pathlib import Path

    if output is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(Path(".") / "snapshots" / ts)

    out_path = Path(output)
    if dry_run_echo(ctx, f"export TMDL snapshot to '{out_path}'"):
        return

    backend = get_backend(ctx)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        result = backend.tmdl_export(str(out_path))
        file_count = len(list(out_path.rglob("*.tmdl")))
        console.print(f"[green]Snapshot saved:[/green] {out_path}")
        console.print(f"  Files: {file_count} .tmdl file(s)")
        console.print(f"\nCompare later with:")
        console.print(f"  pbi deploy diff --snapshot {out_path}")
        console.print(f"  pbi model diff --snapshot {out_path}")
    except Exception as e:
        console.print(f"[red]Snapshot failed:[/red] {e}")
        console.print("Ensure Power BI Desktop is running with the model open.")
        raise SystemExit(1)


@deploy.command("promote")
@click.option("--from", "from_workspace", required=True, help="Source workspace.")
@click.option("--to", "to_workspace", required=True, help="Target workspace.")
@click.pass_context
def deploy_promote(ctx: click.Context, from_workspace: str, to_workspace: str) -> None:
    """Parameterised promotion: swap connections, update partitions, deploy.

    \b
    Example:
      pbi deploy promote --from Staging --to Production
    """
    console.print(f"[cyan]Promoting:[/cyan] {from_workspace} -> {to_workspace}")
    if dry_run_echo(ctx, f"promote model from '{from_workspace}' to '{to_workspace}'"):
        return

    endpoint = _get_xmla_endpoint()
    if not endpoint:
        console.print(
            "[yellow]XMLA endpoint not configured.[/yellow]\n"
            "Set it in [bold]~/.pbi-cli/config.toml[/bold]:\n"
            "  [xmla]\n"
            "  endpoint = \"powerbi://api.powerbi.com/v1.0/myorg/MyWorkspace\""
        )
    console.print("[yellow]Promotion (XMLA backend required — v6.0).[/yellow]")
    console.print("Steps that will run when XMLA is connected:")
    console.print("  1. Export TMDL from source workspace")
    console.print("  2. Swap connection strings (dev -> prod data sources)")
    console.print("  3. Update partition queries")
    console.print("  4. Deploy to target workspace via XMLA transaction")


def _get_xmla_endpoint() -> str | None:
    """Read XMLA endpoint from ~/.pbi-cli/config.toml if available."""
    try:
        from pathlib import Path
        config_path = Path.home() / ".pbi-cli" / "config.toml"
        if not config_path.exists():
            return None
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                return None
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        return data.get("xmla", {}).get("endpoint")
    except Exception:
        return None
