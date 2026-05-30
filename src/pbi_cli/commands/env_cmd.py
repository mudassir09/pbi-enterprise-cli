"""pbi env — environment and workspace management."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

_CONNECTIONS_FILE = Path.home() / ".pbi-cli" / "connections.json"
_CONFIG_FILE = Path("pbi.config.toml")


def _load_connections() -> dict:
    if not _CONNECTIONS_FILE.exists():
        return {"default": None, "connections": {}}
    return json.loads(_CONNECTIONS_FILE.read_text(encoding="utf-8"))


def _save_connections(data: dict) -> None:
    _CONNECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONNECTIONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_project_config() -> dict:
    """Load pbi.config.toml from the current directory if present."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            console.print("[yellow]tomllib not available — cannot read pbi.config.toml[/yellow]")
            return {}
    return tomllib.loads(_CONFIG_FILE.read_text(encoding="utf-8"))


@click.group("env")
def env_cmd() -> None:
    """Manage named workspace connections and environment promotion."""


@env_cmd.command("list")
def env_list() -> None:
    """List all configured named connections."""
    data = _load_connections()
    conns = data.get("connections", {})
    default = data.get("default")
    if not conns:
        console.print("[yellow]No connections configured.[/yellow]")
        console.print("Add one with: pbi connections add")
        return

    table = Table(title="Named Connections")
    table.add_column("Name")
    table.add_column("Backend", justify="center")
    table.add_column("Default", justify="center")
    table.add_column("Details")
    for name, cfg in conns.items():
        is_default = "[green]✓[/green]" if name == default else ""
        backend = cfg.get("backend", "desktop")
        details = cfg.get("xmla_endpoint", cfg.get("description", ""))
        table.add_row(name, backend, is_default, details)
    console.print(table)

    cfg_data = _load_project_config()
    if "environments" in cfg_data:
        console.print("\n[cyan]Project environments (pbi.config.toml):[/cyan]")
        for env, conn in cfg_data["environments"].items():
            console.print(f"  {env} → {conn}")


@env_cmd.command("use")
@click.argument("name")
def env_use(name: str) -> None:
    """Set the default named connection."""
    data = _load_connections()
    if name not in data.get("connections", {}):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        console.print("Run 'pbi env list' to see available connections.")
        raise SystemExit(1)
    data["default"] = name
    _save_connections(data)
    console.print(f"[green]Default connection set to:[/green] {name}")


@env_cmd.command("diff")
@click.argument("source_env")
@click.argument("target_env")
@click.pass_context
def env_diff(ctx: click.Context, source_env: str, target_env: str) -> None:
    """Compare the model schema between two named connections.

    \b
    Example:
      pbi env diff fabric-dev fabric-prod
    """
    data = _load_connections()
    conns = data.get("connections", {})
    for env in (source_env, target_env):
        if env not in conns:
            console.print(f"[red]Connection '{env}' not found.[/red]")
            raise SystemExit(1)

    console.print(f"[cyan]Comparing:[/cyan] {source_env} → {target_env}")
    console.print(
        "[yellow]XMLA diff requires a live XMLA connection.[/yellow]\n"
        "Use 'pbi deploy diff --snapshot <path>' for local snapshot comparison."
    )


@env_cmd.command("promote")
@click.argument("source_env")
@click.argument("target_env")
@click.option("--confirm", is_flag=True, required=True, help="Confirm promotion (required).")
@click.pass_context
def env_promote(ctx: click.Context, source_env: str, target_env: str, confirm: bool) -> None:
    """Push the model from SOURCE_ENV to TARGET_ENV.

    \b
    This is a destructive operation — it overwrites the target model.
    Requires --confirm flag to prevent accidental promotion.

    \b
    Example:
      pbi env promote fabric-dev fabric-prod --confirm
    """
    data = _load_connections()
    conns = data.get("connections", {})
    for env in (source_env, target_env):
        if env not in conns:
            console.print(f"[red]Connection '{env}' not found.[/red]")
            raise SystemExit(1)

    console.print(f"[cyan]Promoting:[/cyan] {source_env} → {target_env}")
    console.print(
        "[yellow]XMLA promotion requires a live XMLA backend.[/yellow]\n"
        "Ensure both connections have 'backend': 'xmla' and valid auth configured.\n"
        "Run 'pbi deploy snapshot' + 'pbi deploy push' for manual promotion."
    )
