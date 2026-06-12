"""pbi connections — named connection profiles (~/.pbi-cli/connections.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from pbi_cli.commands._shared import output_json_or_table

console = Console(legacy_windows=False)

_CONFIG_PATH = Path.home() / ".pbi-cli" / "connections.json"


def _load() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return {"connections": [], "last": None}


def _save(data: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


@click.group()
def connections() -> None:
    """Manage named Power BI connection profiles (~/.pbi-cli/connections.json)."""


@connections.command("list")
@click.pass_context
def connections_list(ctx: click.Context) -> None:
    """List all saved named connections."""
    data = _load()
    conns = data.get("connections", [])
    if not conns:
        console.print("[yellow]No saved connections.[/yellow]")
        console.print("Use 'pbi connections add' to save one.")
        return
    # Mask secrets
    display = []
    for c in conns:
        row = dict(c)
        if row.get("client_secret"):
            row["client_secret"] = "***"
        display.append(row)
    output_json_or_table(display, ctx, title="Saved Connections")
    if data.get("last"):
        console.print(f"\n[dim]Last used:[/dim] [cyan]{data['last']}[/cyan]")


@connections.command("last")
def connections_last() -> None:
    """Show the most recently used connection name."""
    data = _load()
    last = data.get("last")
    if last:
        console.print(f"[cyan]Last connection:[/cyan] {last}")
    else:
        console.print("[yellow]No connection has been used yet.[/yellow]")


@connections.command("add")
@click.option("--name", required=True, help="Short alias for this connection.")
@click.option(
    "--type",
    "conn_type",
    required=True,
    type=click.Choice(["desktop", "xmla"]),
    help="Connection type.",
)
@click.option("--endpoint", default=None, help="XMLA endpoint URL.")
@click.option("--catalog", default=None, help="Dataset / semantic model name.")
@click.option(
    "--auth",
    default="device_flow",
    type=click.Choice(["device_flow", "service_principal", "token"]),
    help="Auth mode (XMLA only).",
)
@click.option("--client-id", default=None, help="AAD client ID (service_principal).")
@click.option("--client-secret", default=None, help="AAD client secret (service_principal).")
@click.option("--tenant-id", default=None, help="AAD tenant ID (service_principal).")
@click.option("--port", default=None, type=int, help="Desktop local server port.")
def connections_add(
    name: str,
    conn_type: str,
    endpoint: str | None,
    catalog: str | None,
    auth: str,
    client_id: str | None,
    client_secret: str | None,
    tenant_id: str | None,
    port: int | None,
) -> None:
    """Save a named connection profile."""
    data = _load()
    # Remove existing with same name
    data["connections"] = [c for c in data.get("connections", []) if c["name"] != name]
    record: dict[str, Any] = {"name": name, "type": conn_type}
    if conn_type == "xmla":
        if not endpoint:
            raise click.UsageError("--endpoint is required for xmla connections.")
        record.update({"endpoint": endpoint, "catalog": catalog or "", "auth": auth})
        if auth == "service_principal":
            record.update(
                {"client_id": client_id, "client_secret": client_secret, "tenant_id": tenant_id}
            )
    else:
        if port:
            record["port"] = port
    data.setdefault("connections", []).append(record)
    _save(data)
    console.print(f"[green]Connection saved:[/green] '{name}' ({conn_type})")


@connections.command("remove")
@click.argument("name")
def connections_remove(name: str) -> None:
    """Remove a saved connection profile by name."""
    data = _load()
    before = len(data.get("connections", []))
    data["connections"] = [c for c in data.get("connections", []) if c["name"] != name]
    if len(data["connections"]) == before:
        console.print(f"[yellow]Connection '{name}' not found.[/yellow]")
        return
    if data.get("last") == name:
        data["last"] = None
    _save(data)
    console.print(f"[red]Removed[/red] connection '{name}'.")


@connections.command("use")
@click.argument("name")
def connections_use(name: str) -> None:
    """Set a connection as the active default and print its connect command."""
    data = _load()
    conn = next((c for c in data.get("connections", []) if c["name"] == name), None)
    if not conn:
        console.print(f"[red]Connection '{name}' not found.[/red]")
        raise SystemExit(1)
    data["last"] = name
    _save(data)
    console.print(f"[green]Active connection:[/green] {name}")
    if conn["type"] == "xmla":
        console.print(f"  pbi --backend xmla model info  # uses {conn.get('endpoint', '')}")
    else:
        port_flag = f" --port {conn['port']}" if conn.get("port") else ""
        console.print(f"  pbi{port_flag} model info")
