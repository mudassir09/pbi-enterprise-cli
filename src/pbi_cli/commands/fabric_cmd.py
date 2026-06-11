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


# ---------------------------------------------------------------------------
# Fabric platform expansion: items, workspaces, git, pipelines, OneLake,
# capacity operations, jobs, dataflows, Direct Lake diagnostics.
# These use the shared pbi_cli.fabric_api client (token + REST helpers).
# ---------------------------------------------------------------------------

import base64 as _b64  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from pbi_cli import fabric_api as _fab  # noqa: E402
from pbi_cli.commands._shared import output_json_or_table as _out  # noqa: E402


def _folder_to_parts(folder: _Path) -> list[dict]:
    """Encode every file under a folder as Fabric item-definition parts."""
    parts: list[dict] = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            parts.append({
                "path": f.relative_to(folder).as_posix(),
                "payload": _b64.b64encode(f.read_bytes()).decode(),
                "payloadType": "InlineBase64",
            })
    return parts


def _parts_to_folder(parts: list[dict], folder: _Path) -> list[str]:
    written = []
    for part in parts:
        target = folder / part["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_b64.b64decode(part["payload"]))
        written.append(part["path"])
    return written


# --- Items: full CRUD via the Item Definition API ---


@fabric_cmd.group("item")
def fabric_item() -> None:
    """Fabric items: list, get, create, update — any item type, any OS."""


@fabric_item.command("list")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id.")
@click.option("--type", "item_type", default=None,
              help="Filter by type, e.g. SemanticModel, Report, Notebook, Lakehouse.")
@click.pass_context
def item_list(ctx: click.Context, workspace_id: str, item_type: str | None) -> None:
    """List items in a workspace."""
    token = _fab.get_token()
    url = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items"
    if item_type:
        url += f"?type={item_type}"
    items = _fab.get_paged(url, token)
    rows = [{"id": i.get("id", ""), "name": i.get("displayName", ""),
             "type": i.get("type", ""), "description": i.get("description", "")}
            for i in items]
    _out(rows, ctx, title="Fabric Items")


@fabric_item.command("get")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True, help="Item id.")
@click.option("--output", "output_dir", default=None, type=click.Path(),
              help="Download the item definition parts into this folder.")
@click.option("--format", "definition_format", default=None,
              help="Definition format, e.g. TMDL for semantic models, PBIR for reports.")
@click.pass_context
def item_get(ctx: click.Context, workspace_id: str, item_id: str,
             output_dir: str | None, definition_format: str | None) -> None:
    """Get an item; with --output, download its full definition (TMDL/PBIR/etc)."""
    token = _fab.get_token()
    base = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
    item = _fab.get(base, token)
    if not output_dir:
        _out(item, ctx, title="Fabric Item")
        return
    url = f"{base}/getDefinition"
    if definition_format:
        url += f"?format={definition_format}"
    result = _fab.poll_lro(_fab.post(url, token, payload={}), token)
    parts = (result.get("definition") or {}).get("parts", [])
    written = _parts_to_folder(parts, _Path(output_dir))
    console.print(f"[green]{len(written)} definition part(s) written to {output_dir}[/green]")


@fabric_item.command("create")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--name", "display_name", required=True)
@click.option("--type", "item_type", required=True,
              help="SemanticModel, Report, Notebook, Lakehouse, DataPipeline, ...")
@click.option("--definition", "definition_dir", default=None, type=click.Path(exists=True),
              help="Folder of definition parts to upload (e.g. a .SemanticModel folder).")
@click.option("--description", default=None)
@click.pass_context
def item_create(ctx: click.Context, workspace_id: str, display_name: str,
                item_type: str, definition_dir: str | None, description: str | None) -> None:
    """Create a Fabric item — deploy semantic models and reports from any OS, no XMLA."""
    token = _fab.get_token()
    payload: dict = {"displayName": display_name, "type": item_type}
    if description:
        payload["description"] = description
    if definition_dir:
        payload["definition"] = {"parts": _folder_to_parts(_Path(definition_dir))}
    result = _fab.poll_lro(
        _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items", token,
                  payload=payload),
        token,
    )
    _out(result, ctx, title="Item Created")


@fabric_item.command("update")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True)
@click.option("--definition", "definition_dir", required=True, type=click.Path(exists=True),
              help="Folder of definition parts to upload.")
@click.pass_context
def item_update(ctx: click.Context, workspace_id: str, item_id: str, definition_dir: str) -> None:
    """Replace an item's definition (updateDefinition LRO)."""
    token = _fab.get_token()
    url = (f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
           "/updateDefinition?updateMetadata=true")
    payload = {"definition": {"parts": _folder_to_parts(_Path(definition_dir))}}
    result = _fab.poll_lro(_fab.post(url, token, payload=payload), token)
    _out(result if isinstance(result, dict) else {"status": "Succeeded"}, ctx,
         title="Item Updated")


@fabric_item.command("delete")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation.")
@click.pass_context
def item_delete(ctx: click.Context, workspace_id: str, item_id: str, yes: bool) -> None:
    """Delete a Fabric item."""
    if not yes:
        click.confirm(f"Delete item {item_id}?", abort=True)
    token = _fab.get_token()
    _fab.delete(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}", token)
    console.print(f"[green]Deleted item {item_id}.[/green]")


# --- Workspace management ---


@fabric_cmd.group("workspace")
def fabric_workspace() -> None:
    """Workspace management: create, capacity assignment, role assignments."""


@fabric_workspace.command("create")
@click.option("--name", required=True)
@click.option("--capacity", "capacity_id", default=None, help="Capacity id to assign.")
@click.option("--description", default=None)
@click.pass_context
def workspace_create(ctx: click.Context, name: str, capacity_id: str | None,
                     description: str | None) -> None:
    """Create a workspace (optionally on a capacity)."""
    token = _fab.get_token()
    payload: dict = {"displayName": name}
    if description:
        payload["description"] = description
    if capacity_id:
        payload["capacityId"] = capacity_id
    result = _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces", token, payload=payload)
    _out(result, ctx, title="Workspace Created")


@fabric_workspace.command("assign-capacity")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--capacity", "capacity_id", required=True)
@click.pass_context
def workspace_assign(ctx: click.Context, workspace_id: str, capacity_id: str) -> None:
    """Assign a workspace to a capacity."""
    token = _fab.get_token()
    _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/assignToCapacity",
              token, payload={"capacityId": capacity_id})
    console.print(f"[green]Workspace {workspace_id} assigned to capacity {capacity_id}.[/green]")


@fabric_workspace.command("users")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--add", "add_principal", default=None,
              help="Principal id (user object id / group id / SP id) to add.")
@click.option("--role", default="Member",
              type=click.Choice(["Admin", "Member", "Contributor", "Viewer"]),
              show_default=True)
@click.option("--principal-type", default="User",
              type=click.Choice(["User", "Group", "ServicePrincipal"]), show_default=True)
@click.pass_context
def workspace_users(ctx: click.Context, workspace_id: str, add_principal: str | None,
                    role: str, principal_type: str) -> None:
    """List role assignments, or add one with --add."""
    token = _fab.get_token()
    base = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/roleAssignments"
    if add_principal:
        _fab.post(base, token, payload={
            "principal": {"id": add_principal, "type": principal_type},
            "role": role,
        })
        console.print(f"[green]Added {add_principal} as {role}.[/green]")
        return
    assignments = _fab.get_paged(base, token)
    rows = [{"principal": a.get("principal", {}).get("displayName")
             or a.get("principal", {}).get("id", ""),
             "type": a.get("principal", {}).get("type", ""),
             "role": a.get("role", "")} for a in assignments]
    _out(rows, ctx, title="Role Assignments")


# --- Git integration ---


@fabric_cmd.group("git")
def fabric_git() -> None:
    """Workspace git integration: status, commit to git, update from git."""


@fabric_git.command("status")
@click.option("--workspace", "workspace_id", required=True)
@click.pass_context
def git_status(ctx: click.Context, workspace_id: str) -> None:
    """Show git sync status for a workspace."""
    token = _fab.get_token()
    result = _fab.get(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/git/status", token)
    changes = result.get("changes", [])
    rows = [{"item": c.get("itemMetadata", {}).get("displayName", ""),
             "type": c.get("itemMetadata", {}).get("itemType", ""),
             "workspaceChange": c.get("workspaceChange", ""),
             "remoteChange": c.get("remoteChange", "")} for c in changes]
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        _out(result, ctx)
        return
    console.print(f"[bold]Remote commit:[/bold] {result.get('remoteCommitHash', '')[:12]}  "
                  f"[bold]Workspace head:[/bold] {result.get('workspaceHead', '')[:12]}")
    _out(rows or [{"item": "(none)", "type": "", "workspaceChange": "", "remoteChange": ""}],
         ctx, title="Pending Changes")


@fabric_git.command("commit")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--message", "-m", required=True, help="Commit message.")
@click.pass_context
def git_commit(ctx: click.Context, workspace_id: str, message: str) -> None:
    """Commit all workspace changes to the connected git branch."""
    token = _fab.get_token()
    status = _fab.get(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/git/status", token)
    result = _fab.poll_lro(
        _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/git/commitToGit", token,
                  payload={"mode": "All", "comment": message,
                           "workspaceHead": status.get("workspaceHead")}),
        token,
    )
    console.print("[green]Committed workspace to git.[/green]")
    if isinstance(result, dict) and result.get("status"):
        _out(result, ctx, title="Commit")


@fabric_git.command("update")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--allow-override", is_flag=True,
              help="Allow remote to override workspace changes (PreferRemote).")
@click.pass_context
def git_update(ctx: click.Context, workspace_id: str, allow_override: bool) -> None:
    """Update the workspace from the connected git branch."""
    token = _fab.get_token()
    status = _fab.get(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/git/status", token)
    payload = {
        "remoteCommitHash": status.get("remoteCommitHash"),
        "workspaceHead": status.get("workspaceHead"),
        "conflictResolution": {
            "conflictResolutionType": "Workspace",
            "conflictResolutionPolicy": "PreferRemote" if allow_override else "PreferWorkspace",
        },
        "options": {"allowOverrideItems": allow_override},
    }
    _fab.poll_lro(
        _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/git/updateFromGit",
                  token, payload=payload),
        token,
    )
    console.print("[green]Workspace updated from git.[/green]")


# --- Deployment pipelines ---


@fabric_cmd.group("pipeline")
def fabric_pipeline() -> None:
    """Fabric deployment pipelines: list stages, deploy stage to stage."""


@fabric_pipeline.command("list")
@click.pass_context
def pipeline_list(ctx: click.Context) -> None:
    """List deployment pipelines you can access."""
    token = _fab.get_token()
    pipelines = _fab.get_paged(f"{_fab.FABRIC_API_BASE}/deploymentPipelines", token)
    rows = [{"id": p.get("id", ""), "name": p.get("displayName", ""),
             "description": p.get("description", "")} for p in pipelines]
    _out(rows, ctx, title="Deployment Pipelines")


@fabric_pipeline.command("stages")
@click.option("--pipeline", "pipeline_id", required=True)
@click.pass_context
def pipeline_stages(ctx: click.Context, pipeline_id: str) -> None:
    """List the stages of a deployment pipeline."""
    token = _fab.get_token()
    stages = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/deploymentPipelines/{pipeline_id}/stages", token)
    rows = [{"id": s.get("id", ""), "name": s.get("displayName", ""),
             "order": s.get("order", ""), "workspaceId": s.get("workspaceId", "")}
            for s in stages]
    _out(rows, ctx, title="Pipeline Stages")


@fabric_pipeline.command("deploy")
@click.option("--pipeline", "pipeline_id", required=True)
@click.option("--from", "source_stage", required=True, help="Source stage name or id.")
@click.option("--to", "target_stage", required=True, help="Target stage name or id.")
@click.option("--note", default="Deployed by pbi-enterprise-cli")
@click.pass_context
def pipeline_deploy(ctx: click.Context, pipeline_id: str, source_stage: str,
                    target_stage: str, note: str) -> None:
    """Deploy all items from one stage to another."""
    token = _fab.get_token()
    stages = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/deploymentPipelines/{pipeline_id}/stages", token)

    def _resolve(ref: str) -> str:
        for s in stages:
            if ref in (s.get("id"), s.get("displayName")):
                return s["id"]
        raise click.ClickException(f"Stage '{ref}' not found in pipeline.")

    payload = {
        "sourceStageId": _resolve(source_stage),
        "targetStageId": _resolve(target_stage),
        "note": note,
    }
    result = _fab.poll_lro(
        _fab.post(f"{_fab.FABRIC_API_BASE}/deploymentPipelines/{pipeline_id}/deploy",
                  token, payload=payload),
        token,
    )
    console.print(f"[green]Deployed {source_stage} → {target_stage}.[/green]")
    if isinstance(result, dict) and result.get("status"):
        _out(result, ctx, title="Deployment")


# --- OneLake ---


@fabric_cmd.group("onelake")
def fabric_onelake() -> None:
    """OneLake files: list, download, upload, shortcuts (ADLS DFS API)."""


@fabric_onelake.command("ls")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id or name.")
@click.option("--path", "dir_path", default="", help="Directory, e.g. MyLakehouse.Lakehouse/Files.")
@click.option("--recursive", is_flag=True)
@click.pass_context
def onelake_ls(ctx: click.Context, workspace_id: str, dir_path: str, recursive: bool) -> None:
    """List files and folders in OneLake."""
    token = _fab.get_token()
    url = (f"{_fab.ONELAKE_DFS_BASE}/{workspace_id}?resource=filesystem"
           f"&recursive={str(recursive).lower()}")
    if dir_path:
        url += f"&directory={dir_path}"
    result = _fab.get(url, token)
    rows = [{"name": p.get("name", ""),
             "dir": "yes" if p.get("isDirectory") in (True, "true") else "",
             "bytes": p.get("contentLength", "")} for p in result.get("paths", [])]
    _out(rows, ctx, title="OneLake")


@fabric_onelake.command("download")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--path", "file_path", required=True, help="e.g. Lake.Lakehouse/Files/a.csv")
@click.option("--output", "output_file", required=True, type=click.Path())
@click.pass_context
def onelake_download(ctx: click.Context, workspace_id: str, file_path: str,
                     output_file: str) -> None:
    """Download a OneLake file."""
    token = _fab.get_token()
    data = _fab.get(f"{_fab.ONELAKE_DFS_BASE}/{workspace_id}/{file_path}", token)
    raw = data if isinstance(data, bytes) else str(data).encode()
    _Path(output_file).write_bytes(raw)
    console.print(f"[green]Downloaded {len(raw)} bytes → {output_file}[/green]")


@fabric_onelake.command("upload")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--path", "dest_path", required=True, help="Destination OneLake path.")
@click.option("--file", "source_file", required=True, type=click.Path(exists=True))
@click.pass_context
def onelake_upload(ctx: click.Context, workspace_id: str, dest_path: str,
                   source_file: str) -> None:
    """Upload a local file to OneLake (create + append + flush)."""
    token = _fab.get_token()
    data = _Path(source_file).read_bytes()
    base = f"{_fab.ONELAKE_DFS_BASE}/{workspace_id}/{dest_path}"
    _fab.put(f"{base}?resource=file", token)
    _fab.request("PATCH", f"{base}?action=append&position=0", token, data=data,
                 headers={"Content-Type": "application/octet-stream"})
    _fab.request("PATCH", f"{base}?action=flush&position={len(data)}", token)
    console.print(f"[green]Uploaded {len(data)} bytes → {dest_path}[/green]")


@fabric_onelake.command("shortcut")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True, help="Lakehouse/Warehouse item id.")
@click.option("--path", "shortcut_path", default="Files", show_default=True)
@click.option("--name", required=True, help="Shortcut name.")
@click.option("--target-workspace", required=True)
@click.option("--target-item", required=True)
@click.option("--target-path", required=True)
@click.pass_context
def onelake_shortcut(ctx: click.Context, workspace_id: str, item_id: str, shortcut_path: str,
                     name: str, target_workspace: str, target_item: str,
                     target_path: str) -> None:
    """Create a OneLake-to-OneLake shortcut."""
    token = _fab.get_token()
    payload = {
        "path": shortcut_path,
        "name": name,
        "target": {"oneLake": {
            "workspaceId": target_workspace, "itemId": target_item, "path": target_path,
        }},
    }
    result = _fab.post(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}/shortcuts",
        token, payload=payload)
    _out(result, ctx, title="Shortcut Created")


# --- Capacity operations (Azure ARM) ---


@fabric_cmd.group("capacity")
def fabric_capacity_ops() -> None:
    """Capacity operations via Azure ARM: pause, resume, scale."""


_ARM_SCOPE = "https://management.azure.com/.default"
_ARM_API = "2023-11-01"


def _arm_capacity_url(subscription: str, resource_group: str, name: str) -> str:
    return (f"https://management.azure.com/subscriptions/{subscription}"
            f"/resourceGroups/{resource_group}/providers/Microsoft.Fabric"
            f"/capacities/{name}")


@fabric_capacity_ops.command("pause")
@click.option("--subscription", required=True, envvar="AZURE_SUBSCRIPTION_ID")
@click.option("--resource-group", required=True)
@click.option("--name", required=True, help="Capacity name.")
@click.pass_context
def capacity_pause(ctx: click.Context, subscription: str, resource_group: str,
                   name: str) -> None:
    """Pause (suspend) a Fabric capacity — stops CU billing."""
    token = _fab.get_token(scope=_ARM_SCOPE)
    _fab.post(f"{_arm_capacity_url(subscription, resource_group, name)}/suspend"
              f"?api-version={_ARM_API}", token, payload={})
    console.print(f"[green]Capacity {name} suspended.[/green]")


@fabric_capacity_ops.command("resume")
@click.option("--subscription", required=True, envvar="AZURE_SUBSCRIPTION_ID")
@click.option("--resource-group", required=True)
@click.option("--name", required=True)
@click.pass_context
def capacity_resume(ctx: click.Context, subscription: str, resource_group: str,
                    name: str) -> None:
    """Resume a paused Fabric capacity."""
    token = _fab.get_token(scope=_ARM_SCOPE)
    _fab.post(f"{_arm_capacity_url(subscription, resource_group, name)}/resume"
              f"?api-version={_ARM_API}", token, payload={})
    console.print(f"[green]Capacity {name} resumed.[/green]")


@fabric_capacity_ops.command("scale")
@click.option("--subscription", required=True, envvar="AZURE_SUBSCRIPTION_ID")
@click.option("--resource-group", required=True)
@click.option("--name", required=True)
@click.option("--sku", required=True,
              type=click.Choice(["F2", "F4", "F8", "F16", "F32", "F64", "F128", "F256",
                                 "F512", "F1024", "F2048"]))
@click.pass_context
def capacity_scale(ctx: click.Context, subscription: str, resource_group: str,
                   name: str, sku: str) -> None:
    """Scale a Fabric capacity to a different F SKU."""
    token = _fab.get_token(scope=_ARM_SCOPE)
    result = _fab.patch(
        f"{_arm_capacity_url(subscription, resource_group, name)}?api-version={_ARM_API}",
        token, payload={"sku": {"name": sku, "tier": "Fabric"}})
    _out(result if isinstance(result, dict) else {"sku": sku}, ctx, title="Capacity Scaled")


# --- Item jobs (run / monitor / cancel) ---


@fabric_cmd.group("job")
def fabric_job() -> None:
    """Run and monitor item jobs: pipeline runs, notebook runs, refreshes."""


@fabric_job.command("run")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True)
@click.option("--type", "job_type", default="DefaultJob", show_default=True,
              help="e.g. RunNotebook, Pipeline, Refresh, DefaultJob.")
@click.pass_context
def job_run(ctx: click.Context, workspace_id: str, item_id: str, job_type: str) -> None:
    """Start an on-demand job for an item."""
    token = _fab.get_token()
    result = _fab.post(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
        f"/jobs/instances?jobType={job_type}", token, payload={})
    _out(result if isinstance(result, dict) else {"status": "Accepted"}, ctx,
         title="Job Started")


@fabric_job.command("status")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True)
@click.option("--job", "job_id", required=True)
@click.pass_context
def job_status(ctx: click.Context, workspace_id: str, item_id: str, job_id: str) -> None:
    """Get the status of a job instance."""
    token = _fab.get_token()
    result = _fab.get(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
        f"/jobs/instances/{job_id}", token)
    _out(result, ctx, title="Job Status")


@fabric_job.command("cancel")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--item", "item_id", required=True)
@click.option("--job", "job_id", required=True)
@click.pass_context
def job_cancel(ctx: click.Context, workspace_id: str, item_id: str, job_id: str) -> None:
    """Cancel a running job instance."""
    token = _fab.get_token()
    _fab.post(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
        f"/jobs/instances/{job_id}/cancel", token, payload={})
    console.print(f"[green]Cancel requested for job {job_id}.[/green]")


# --- Direct Lake diagnostics ---


@fabric_cmd.group("directlake")
def fabric_directlake() -> None:
    """Direct Lake diagnostics: partition modes, framing, reframe."""


@fabric_directlake.command("status")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--dataset", "dataset_id", required=True)
@click.pass_context
def directlake_status(ctx: click.Context, workspace_id: str, dataset_id: str) -> None:
    """Show partition storage modes and Direct Lake adoption for a dataset."""
    from pbi_cli.backends.rest_backend import RestBackend

    b = RestBackend(workspace_id=workspace_id, dataset_id=dataset_id)
    b.connect(workspace_id=workspace_id, dataset_id=dataset_id)
    partitions = b.partition_list()
    modes: dict[str, int] = {}
    for p in partitions:
        modes[p["mode"] or "?"] = modes.get(p["mode"] or "?", 0) + 1
    direct_lake = [p for p in partitions if str(p["mode"]).lower() in ("directlake", "5")]
    result = {
        "partitions": len(partitions),
        "modes": modes,
        "directLakePartitions": len(direct_lake),
        "directLake": bool(direct_lake),
        "hint": ("Model uses Direct Lake." if direct_lake else
                 "No Direct Lake partitions — `pbi migrate direct-lake --analyze` "
                 "reports import-mode blockers."),
    }
    _out(result, ctx, title="Direct Lake Status")


@fabric_directlake.command("reframe")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--dataset", "dataset_id", required=True)
@click.pass_context
def directlake_reframe(ctx: click.Context, workspace_id: str, dataset_id: str) -> None:
    """Reframe a Direct Lake dataset (full refresh = re-point to latest delta versions)."""
    token = _fab.get_token()
    _fab.post(
        f"{_fab.POWERBI_API_BASE}/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
        token, payload={"type": "full", "commitMode": "transactional"})
    console.print("[green]Reframe (full refresh) requested.[/green]")
