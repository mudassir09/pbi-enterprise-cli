"""pbi fabric — Microsoft Fabric REST API commands."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console()

_FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
_POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"


def _get_token() -> str:
    """Acquire an access token for Fabric/Power BI REST API."""
    import os

    token = os.environ.get("PBI_REST_BEARER") or os.environ.get("FABRIC_TOKEN")
    if token:
        return token

    # Try MSAL device flow if msal is available
    try:
        import msal  # type: ignore[import-untyped]

        tenant = os.environ.get("AZURE_TENANT_ID", "common")
        client_id = os.environ.get("AZURE_CLIENT_ID", "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
        app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}")
        flow = app.initiate_device_flow(scopes=["https://analysis.windows.net/powerbi/api/.default"])
        console.print(f"\n[cyan]Device flow:[/cyan] {flow['message']}\n")
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            return result["access_token"]
        raise click.ClickException(f"Token acquisition failed: {result.get('error_description')}")
    except ImportError:
        raise click.ClickException(
            "Set PBI_REST_BEARER env var with a valid Bearer token, "
            "or install the [xmla] extra for MSAL device flow: "
            "pip install 'pbi-enterprise-cli[xmla]'"
        )


def _api_get(url: str, token: str) -> Any:
    """Perform an authenticated GET against the Fabric/Power BI REST API."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise click.ClickException(f"API error {exc.code}: {body[:200]}")


def _api_post(url: str, token: str, payload: dict) -> Any:
    """Perform an authenticated POST against the Fabric/Power BI REST API."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode()) if resp.length else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise click.ClickException(f"API error {exc.code}: {body[:200]}")


@click.group("fabric")
def fabric_cmd() -> None:
    """Microsoft Fabric REST API commands — workspaces, capacities, datasets."""


@fabric_cmd.command("workspaces")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--filter", "name_filter", default=None, help="Filter by workspace name (substring).")
def fabric_workspaces(output_json: bool, name_filter: str | None) -> None:
    """List Fabric/Power BI workspaces accessible by the current token.

    \b
    Authentication: set PBI_REST_BEARER env var or use MSAL device flow
    (requires pip install 'pbi-enterprise-cli[xmla]').

    \b
    Examples:
      pbi fabric workspaces
      pbi fabric workspaces --filter "Sales"
      pbi fabric workspaces --json | jq '.[].name'
    """
    token = _get_token()
    data = _api_get(f"{_POWERBI_API_BASE}/groups", token)
    workspaces = data.get("value", [])

    if name_filter:
        workspaces = [w for w in workspaces if name_filter.lower() in w.get("name", "").lower()]

    if output_json:
        click.echo(json.dumps(workspaces, indent=2))
        return

    if not workspaces:
        console.print("[yellow]No workspaces found.[/yellow]")
        return

    table = Table(title=f"Fabric Workspaces ({len(workspaces)})")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("State")
    for w in workspaces:
        table.add_row(
            w.get("id", ""),
            w.get("name", ""),
            w.get("type", ""),
            w.get("state", ""),
        )
    console.print(table)


@fabric_cmd.command("capacities")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
def fabric_capacities(output_json: bool) -> None:
    """List Fabric/Power BI Premium capacities.

    \b
    Requires capacity admin or Power BI admin role.

    \b
    Example:
      pbi fabric capacities --json
    """
    token = _get_token()
    data = _api_get(f"{_POWERBI_API_BASE}/capacities", token)
    capacities = data.get("value", [])

    if output_json:
        click.echo(json.dumps(capacities, indent=2))
        return

    if not capacities:
        console.print("[yellow]No capacities found.[/yellow]")
        return

    table = Table(title=f"Fabric Capacities ({len(capacities)})")
    table.add_column("ID")
    table.add_column("Display Name")
    table.add_column("SKU")
    table.add_column("State")
    table.add_column("Region")
    for c in capacities:
        table.add_row(
            c.get("id", ""),
            c.get("displayName", ""),
            c.get("sku", ""),
            c.get("state", ""),
            c.get("region", ""),
        )
    console.print(table)


@fabric_cmd.command("datasets")
@click.argument("workspace_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--filter", "name_filter", default=None, help="Filter by dataset name.")
def fabric_datasets(workspace_id: str, output_json: bool, name_filter: str | None) -> None:
    """List semantic model datasets in a Fabric workspace.

    \b
    WORKSPACE_ID is the GUID of the workspace (from 'pbi fabric workspaces').

    \b
    Examples:
      pbi fabric datasets <workspace-id>
      pbi fabric datasets <workspace-id> --filter "Sales"
    """
    token = _get_token()
    data = _api_get(f"{_POWERBI_API_BASE}/groups/{workspace_id}/datasets", token)
    datasets = data.get("value", [])

    if name_filter:
        datasets = [d for d in datasets if name_filter.lower() in d.get("name", "").lower()]

    if output_json:
        click.echo(json.dumps(datasets, indent=2))
        return

    if not datasets:
        console.print("[yellow]No datasets found in this workspace.[/yellow]")
        return

    table = Table(title=f"Datasets in workspace {workspace_id[:8]}… ({len(datasets)})")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Configured By")
    table.add_column("IsRefreshable", justify="center")
    for d in datasets:
        table.add_row(
            d.get("id", ""),
            d.get("name", ""),
            d.get("configuredBy", ""),
            "✓" if d.get("isRefreshable") else "–",
        )
    console.print(table)


@fabric_cmd.command("refresh")
@click.argument("workspace_id")
@click.argument("dataset_id")
@click.option("--type", "refresh_type", default="full", show_default=True,
              type=click.Choice(["full", "clearValues", "calculate", "automatic"]),
              help="Refresh type.")
@click.option("--dry-run", is_flag=True, help="Show what would be triggered without executing.")
def fabric_refresh(workspace_id: str, dataset_id: str, refresh_type: str, dry_run: bool) -> None:
    """Trigger a dataset refresh in a Fabric workspace.

    \b
    Examples:
      pbi fabric refresh <workspace-id> <dataset-id>
      pbi fabric refresh <workspace-id> <dataset-id> --type incremental --dry-run
    """
    if dry_run:
        console.print(
            f"[dim]Would trigger[/dim] {refresh_type} refresh "
            f"on dataset {dataset_id[:8]}… in workspace {workspace_id[:8]}…"
        )
        return

    token = _get_token()
    _api_post(
        f"{_POWERBI_API_BASE}/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
        token,
        {"type": refresh_type},
    )
    console.print(
        f"[green]Refresh triggered:[/green] {refresh_type} on dataset {dataset_id[:8]}…"
    )
    console.print(
        "Monitor progress: "
        f"pbi fabric refresh-history {workspace_id} {dataset_id}"
    )


@fabric_cmd.command("lineage")
@click.argument("workspace_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
def fabric_lineage(workspace_id: str, output_json: bool) -> None:
    """Fetch lineage metadata for a Fabric workspace (datasets, dataflows, reports).

    \b
    Example:
      pbi fabric lineage <workspace-id> --json
    """
    token = _get_token()
    # Scanner API — returns upstream/downstream lineage
    data = _api_get(
        f"{_POWERBI_API_BASE}/admin/workspaces/{workspace_id}/scanResult",
        token,
    )

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    workspaces = data.get("workspaces", [])
    if not workspaces:
        console.print("[yellow]No lineage data returned.[/yellow]")
        console.print("Ensure the workspace scan has been triggered first.")
        return

    ws = workspaces[0]
    datasets = ws.get("datasets", [])
    reports = ws.get("reports", [])
    console.print(f"[bold]Workspace:[/bold] {ws.get('name', workspace_id)}")
    console.print(f"  Datasets : {len(datasets)}")
    console.print(f"  Reports  : {len(reports)}")
    for d in datasets[:10]:
        console.print(f"  [cyan]Dataset:[/cyan] {d.get('name')} → "
                      f"{len(d.get('reports', []))} report(s)")
