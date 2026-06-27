"""pbi fabric — Microsoft Fabric REST API commands."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console(legacy_windows=False)

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
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from pbi_cli import fabric_api as _fab  # noqa: E402
from pbi_cli.commands._shared import output_json_or_table as _out  # noqa: E402
from pbi_cli.fabric_api import FabricApiError  # noqa: E402  (stable except target)
from pbi_cli.tmdl_util import atomic_write_text as _atomic_write_text  # noqa: E402


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


# --- Fabric IQ: ontology (preview) ---


@fabric_cmd.group("ontology")
def fabric_ontology() -> None:
    """Fabric IQ ontology (preview): the semantic layer for AI agents.

    \b
    An ontology defines entity types, properties, and relationship types over
    OneLake data. Ontologies can be generated in the Fabric portal from a
    semantic model (Direct Lake mode required for data bindings); this CLI
    manages the resulting ontology items via the REST API.

    \b
    Prep a semantic model for good ontology generation first:
      pbi govern ai-readiness
    """


@fabric_ontology.command("list")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id.")
@click.pass_context
def ontology_list(ctx: click.Context, workspace_id: str) -> None:
    """List ontology items in a workspace."""
    token = _fab.get_token()
    items = _fab.get_paged(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies", token)
    rows = [{"id": o.get("id", ""), "name": o.get("displayName", ""),
             "description": o.get("description", "")} for o in items]
    _out(rows, ctx, title="Ontologies (Fabric IQ, preview)")


@fabric_ontology.command("get")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--ontology", "ontology_id", required=True, help="Ontology item id.")
@click.option("--output", "output_dir", default=None, type=click.Path(),
              help="Download the ontology definition parts into this folder.")
@click.pass_context
def ontology_get(ctx: click.Context, workspace_id: str, ontology_id: str,
                 output_dir: str | None) -> None:
    """Get an ontology; with --output, download its full definition."""
    token = _fab.get_token()
    base = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies/{ontology_id}"
    ontology = _fab.get(base, token)
    if not output_dir:
        _out(ontology, ctx, title="Ontology")
        return
    result = _fab.poll_lro(_fab.post(f"{base}/getDefinition", token, payload={}), token)
    parts = (result.get("definition") or {}).get("parts", [])
    written = _parts_to_folder(parts, _Path(output_dir))
    console.print(f"[green]{len(written)} definition part(s) written to {output_dir}[/green]")


@fabric_ontology.command("create")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--name", "display_name", required=True)
@click.option("--definition", "definition_dir", default=None, type=click.Path(exists=True),
              help="Folder of ontology definition parts to upload.")
@click.option("--description", default=None)
@click.pass_context
def ontology_create(ctx: click.Context, workspace_id: str, display_name: str,
                    definition_dir: str | None, description: str | None) -> None:
    """Create an ontology item (empty, or from a definition folder)."""
    token = _fab.get_token()
    payload: dict = {"displayName": display_name}
    if description:
        payload["description"] = description
    if definition_dir:
        payload["definition"] = {"parts": _folder_to_parts(_Path(definition_dir))}
    result = _fab.poll_lro(
        _fab.post(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies", token,
                  payload=payload),
        token,
    )
    _out(result, ctx, title="Ontology Created")


@fabric_ontology.command("update")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--ontology", "ontology_id", required=True)
@click.option("--definition", "definition_dir", required=True, type=click.Path(exists=True),
              help="Folder of ontology definition parts to upload.")
@click.pass_context
def ontology_update(ctx: click.Context, workspace_id: str, ontology_id: str,
                    definition_dir: str) -> None:
    """Replace an ontology's definition (updateDefinition LRO)."""
    token = _fab.get_token()
    url = (f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies/{ontology_id}"
           "/updateDefinition?updateMetadata=true")
    payload = {"definition": {"parts": _folder_to_parts(_Path(definition_dir))}}
    result = _fab.poll_lro(_fab.post(url, token, payload=payload), token)
    _out(result if isinstance(result, dict) else {"status": "Succeeded"}, ctx,
         title="Ontology Updated")


@fabric_ontology.command("delete")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--ontology", "ontology_id", required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation.")
@click.pass_context
def ontology_delete(ctx: click.Context, workspace_id: str, ontology_id: str, yes: bool) -> None:
    """Delete an ontology item."""
    if not yes:
        click.confirm(f"Delete ontology {ontology_id}?", abort=True)
    token = _fab.get_token()
    _fab.delete(f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies/{ontology_id}",
                token)
    console.print(f"[green]Deleted ontology {ontology_id}.[/green]")


# --- Reports: PBIR-specific CRUD + definition transport ---


def _resolve_report(workspace_id: str, name_or_id: str, token: str) -> str:
    """Resolve a report display name or GUID to a report ID."""
    import re
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    name_or_id, re.IGNORECASE):
        return name_or_id
    reports = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports", token
    )
    for r in reports:
        if r.get("displayName", "").lower() == name_or_id.lower():
            return r["id"]
    raise click.ClickException(
        f"Report '{name_or_id}' not found in workspace {workspace_id}."
    )


def _model_inventory(workspace_id: str, dataset_id: str, token: str) -> dict[str, Any]:
    """Return the model's tables, columns and measures by parsing its TMDL definition.

    Downloads the semantic model's TMDL via ``getDefinition`` (the LRO result) and
    reads the schema with the pure-Python ``FileBackend`` parser. This is robust
    across every model type — verified live that the ``executeQueries`` ``INFO.*``
    functions are *not* available on all models, whereas the TMDL definition always
    is. Propagates ``FabricApiError`` so callers can fail *closed* (abort the push)
    rather than assume the model is fine when it could not actually be read.

    Returns ``{"tables": set[str], "columns": set[(table, column)],
    "measures": set[str]}``.
    """
    url = (
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/semanticModels/{dataset_id}/getDefinition?format=TMDL"
    )
    result = _fab.poll_lro(_fab.post(url, token, payload={}), token)
    parts = (result.get("definition") or {}).get("parts", []) if isinstance(result, dict) else []
    if not parts:
        raise FabricApiError(
            0, f"Could not retrieve the TMDL definition for semantic model {dataset_id}."
        )
    tmp = _Path(_tempfile.mkdtemp(prefix="pbi-bindverify-"))
    try:
        _fab.decode_parts(parts, tmp)
        from pbi_cli.backends.file_backend import FileBackend

        fb = FileBackend(path=tmp)
        return {
            "tables": {t["name"] for t in fb.table_list()},
            "columns": {(c["table"], c["name"]) for c in fb.column_list()},
            "measures": {m["name"] for m in fb.measure_list()},
        }
    finally:
        _shutil.rmtree(tmp, ignore_errors=True)


def _report_level_measures(pbir_folder: _Path) -> set[str]:
    """Names of report-level measures (reportExtensions.json) — valid but not in the model."""
    names: set[str] = set()
    ext = pbir_folder / "definition" / "reportExtensions.json"
    if ext.exists():
        try:
            data = json.loads(ext.read_text(encoding="utf-8"))
            for entity in data.get("entities", []):
                for meas in entity.get("measures", []):
                    n = meas.get("name")
                    if isinstance(n, str) and n:
                        names.add(n)
        except Exception:
            pass
    return names


def _collect_refs(pbir_folder: _Path) -> dict[str, Any]:
    """Collect every table/column/measure binding referenced by the report's visuals.

    PBIR field expressions name a table via ``SourceRef.Entity`` and a field via
    ``Property`` inside a ``Column`` or ``Measure`` node; bare ``Entity`` strings
    (From clauses, filters) are table references too. Returns the same shape as
    :func:`_model_inventory`.
    """
    refs: dict[str, Any] = {"tables": set(), "columns": set(), "measures": set()}

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for kind in ("Column", "Measure"):
                spec = node.get(kind)
                if isinstance(spec, dict):
                    ent = ((spec.get("Expression") or {}).get("SourceRef") or {}).get("Entity")
                    prop = spec.get("Property")
                    if isinstance(ent, str) and ent:
                        refs["tables"].add(ent)
                        if isinstance(prop, str) and prop:
                            if kind == "Column":
                                refs["columns"].add((ent, prop))
                            else:
                                refs["measures"].add(prop)
            ent = node.get("Entity")
            if isinstance(ent, str) and ent:
                refs["tables"].add(ent)
            for val in node.values():
                _walk(val)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for vf in pbir_folder.rglob("visual.json"):
        try:
            _walk(json.loads(vf.read_text(encoding="utf-8")))
        except Exception:
            pass
    return refs


def _verify_bindings(
    pbir_folder: _Path, workspace_id: str, dataset_id: str, token: str
) -> list[str]:
    """Return human-readable bindings referenced by the report that the model lacks.

    Checks table (``Entity``), column (``table[column]``) and measure references
    against the target semantic model's actual tables/columns/measures. Column
    mismatches are only reported when the table exists (a missing table already
    covers its columns); report-level measures are treated as valid.

    Raises ``FabricApiError`` if the model cannot be inventoried — the caller must
    treat that as a verification *failure*, never a pass. A safety check that
    silently passes when it couldn't run is worse than no check at all.
    """
    refs = _collect_refs(pbir_folder)
    if not (refs["tables"] or refs["columns"] or refs["measures"]):
        return []
    inv = _model_inventory(workspace_id, dataset_id, token)
    local_measures = _report_level_measures(pbir_folder)

    mismatches: list[str] = []
    for t in sorted(refs["tables"] - inv["tables"]):
        mismatches.append(f"table '{t}'")
    for tname, cname in sorted(refs["columns"]):
        if tname in inv["tables"] and (tname, cname) not in inv["columns"]:
            mismatches.append(f"column {tname}[{cname}]")
    for m in sorted(refs["measures"] - inv["measures"] - local_measures):
        mismatches.append(f"measure '{m}'")
    return mismatches


def _datasetref_kind(pbir_folder: _Path) -> str | None:
    """Return 'byPath' / 'byConnection' / None for the report's definition.pbir binding."""
    pbir = pbir_folder / "definition.pbir"
    if not pbir.exists():
        return None
    try:
        ref = (json.loads(pbir.read_text(encoding="utf-8")).get("datasetReference") or {})
    except Exception:
        return None
    if "byConnection" in ref:
        return "byConnection"
    if "byPath" in ref:
        return "byPath"
    return None


# definition.pbir property schema. Fabric's report import rejects a definition.pbir
# missing $schema with an opaque "Workload_FailedToParseFile" (verified live), so a
# rebind ensures it is present.
_PBIR_DEFINITION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report"
    "/definitionProperties/2.0.0/schema.json"
)


def _byconnection_ref(workspace_name: str, model_name: str, dataset_id: str) -> dict[str, Any]:
    """Build the PBIR ``byConnection`` reference Fabric itself emits for a live model.

    Verified against a real Fabric report: the shape is a single ``connectionString``
    (not the XMLA-style ``pbiModelDatabaseName`` form) keyed by ``semanticmodelid``.
    """
    cs = (
        f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};"
        f'initial catalog="{model_name}";integrated security=ClaimsToken;'
        f"semanticmodelid={dataset_id}"
    )
    return {"byConnection": {"connectionString": cs}}


def _display_name(url: str, token: str, default: str) -> str:
    """Resolve an item/workspace displayName via REST, falling back to *default*."""
    try:
        data = _fab.get(url, token)
    except FabricApiError:
        return default
    name = data.get("displayName") if isinstance(data, dict) else None
    return name or default


def _rebind_pbir(
    pbir_folder: _Path, dataset_id: str, workspace_name: str, model_name: str
) -> bool:
    """Rewrite definition.pbir's datasetReference to a live byConnection.

    A locally-authored .pbip binds to a *sibling* ``.SemanticModel`` folder with a
    ``byPath`` reference; Fabric requires a live ``byConnection`` reference to a
    *published* model. First-time publish must rebind or the report uploads
    unbound and every visual renders empty. Idempotent — returns True if changed.
    """
    pbir = pbir_folder / "definition.pbir"
    if not pbir.exists():
        return False
    data = json.loads(pbir.read_text(encoding="utf-8"))
    ref = data.get("datasetReference") or {}
    conn = (ref.get("byConnection") or {}).get("connectionString") or ""
    if "byPath" not in ref and f"semanticmodelid={dataset_id}".lower() in conn.lower():
        return False  # already bound to this model
    data["datasetReference"] = _byconnection_ref(workspace_name, model_name, dataset_id)
    # A .pbip whose definition.pbir omits these fails Fabric's import; ensure they exist.
    data.setdefault("$schema", _PBIR_DEFINITION_SCHEMA)
    data.setdefault("version", "4.0")
    _atomic_write_text(pbir, json.dumps(data, indent=2))
    return True


def _parse_remaps(remaps: tuple[str, ...]) -> dict[str, str]:
    """Parse repeatable ``--remap Old=New`` options into a substitution map."""
    mapping: dict[str, str] = {}
    for raw in remaps:
        if "=" not in raw:
            raise click.UsageError(f"--remap expects 'Old=New', got: {raw!r}")
        old, _, new = raw.partition("=")
        old, new = old.strip(), new.strip()
        if not old or not new:
            raise click.UsageError(f"--remap expects non-empty 'Old=New', got: {raw!r}")
        mapping[old] = new
    return mapping


def _apply_remap(pbir_folder: _Path, mapping: dict[str, str]) -> int:
    """Rename table (``Entity``) references across every visual.json. Returns the count.

    Deterministic, user-specified substitutions for migrations where the target
    model renamed a table. Binding lives in ``Entity``; ``queryRef`` strings are
    cosmetic and regenerated by Power BI, so only ``Entity`` is rewritten.
    """
    if not mapping:
        return 0
    total = 0
    for vf in pbir_folder.rglob("visual.json"):
        try:
            data = json.loads(vf.read_text(encoding="utf-8"))
        except Exception:
            continue
        changed = 0

        def _walk(node: Any) -> None:
            nonlocal changed
            if isinstance(node, dict):
                ent = node.get("Entity")
                if isinstance(ent, str) and ent in mapping:
                    node["Entity"] = mapping[ent]
                    changed += 1
                for val in node.values():
                    _walk(val)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(data)
        if changed:
            _atomic_write_text(vf, json.dumps(data, indent=2))
            total += changed
    return total


@fabric_cmd.group("report")
def fabric_report() -> None:
    """Report items: PBIR-aware CRUD, pull/push round-trip, binding verification."""


@fabric_report.command("list")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id.")
@click.pass_context
def report_list(ctx: click.Context, workspace_id: str) -> None:
    """List all reports in a workspace."""
    token = _fab.get_token()
    reports = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports", token
    )
    rows = [
        {
            "id": r.get("id", ""),
            "name": r.get("displayName", ""),
            "datasetId": r.get("datasetId", ""),
            "description": r.get("description", ""),
        }
        for r in reports
    ]
    _out(rows, ctx, title=f"Reports in {workspace_id[:8]}…")


@fabric_report.command("get")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--report", "report_ref", required=True, help="Report name or id.")
@click.pass_context
def report_get(ctx: click.Context, workspace_id: str, report_ref: str) -> None:
    """Get report metadata."""
    token = _fab.get_token()
    report_id = _resolve_report(workspace_id, report_ref, token)
    result = _fab.get(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports/{report_id}", token
    )
    _out(result, ctx, title="Report")


@fabric_report.command("pull")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--report", "report_ref", required=True, help="Report name or id.")
@click.option("--output", "output_dir", default=None, type=click.Path(),
              help="Local directory to write PBIR files. Defaults to <report-name>.Report/")
@click.pass_context
def report_pull(
    ctx: click.Context, workspace_id: str, report_ref: str, output_dir: str | None
) -> None:
    """Download a report's PBIR definition to a local folder.

    Retrieves the definition from Fabric (getDefinition?format=PBIR), polls the LRO
    to completion, and decodes all parts into a local directory ready for editing
    with 'pbi report' and 'pbi visual' commands.

    Examples:

      pbi fabric report pull --workspace <id> --report "Sales Dashboard"
      pbi fabric report pull --workspace <id> --report <report-id> --output ./local/Sales.Report
    """
    token = _fab.get_token()
    report_id = _resolve_report(workspace_id, report_ref, token)
    url = (
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports/{report_id}"
        "/getDefinition?format=PBIR"
    )
    result = _fab.poll_lro(_fab.post(url, token, payload={}), token)
    parts = (result.get("definition") or {}).get("parts", [])
    if not parts:
        raise click.ClickException(
            "No definition parts returned — report may be in PBIR-Legacy format "
            "which is not supported. Use 'pbi fabric item get --format PBIR' to check."
        )
    dest = _Path(output_dir) if output_dir else _Path(f"{report_ref}.Report")
    written = _parts_to_folder(parts, dest)
    console.print(f"[green]{len(written)} file(s) written to {dest}[/green]")
    console.print(
        f"  Edit locally, then push back:\n"
        f"  [cyan]pbi fabric report push --workspace {workspace_id} "
        f"--report '{report_ref}' --definition {dest}[/cyan]"
    )


@fabric_report.command("push")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--report", "report_ref", required=True,
              help="Report display name. Used to detect create-vs-update.")
@click.option("--definition", "definition_dir", required=True, type=click.Path(exists=True),
              help="Local PBIR folder to upload (e.g. MyReport.Report/).")
@click.option("--dataset-id", default=None,
              help="Semantic model id to bind. Required when creating a new report.")
@click.option("--bind-verify", is_flag=True,
              help="Verify every table/column/measure reference in the report exists in the "
                   "target semantic model before pushing. Requires --dataset-id. Prevents the "
                   "most common publish failure (name mismatches → empty visuals).")
@click.option("--remap", "remaps", multiple=True,
              help="Rename a table reference before push: --remap 'Old=New' (repeatable). "
                   "Use when the target model renamed a table. Applied to a temp copy; your "
                   "local files are not modified.")
@click.option("--description", default=None)
@click.pass_context
def report_push(
    ctx: click.Context,
    workspace_id: str,
    report_ref: str,
    definition_dir: str,
    dataset_id: str | None,
    bind_verify: bool,
    remaps: tuple[str, ...],
    description: str | None,
) -> None:
    """Publish a local PBIR folder to Fabric — creates or updates automatically.

    Checks whether a report with the given name already exists in the workspace.
    If it does, runs updateDefinition (LRO). If not, creates a new report item.

    When --dataset-id is given the report's definition.pbir is rebound to that
    published model (byConnection) — required for a locally-authored .pbip, whose
    model reference is a local byPath. Transforms are applied to a temp copy, so
    your local files are never modified.

    Examples:

      # First publish (create) — rebinds the local byPath model to the Fabric model:
      pbi fabric report push --workspace <id> --report "Sales" \
        --definition ./Sales.Report --dataset-id <id>

      # Re-publish after local edits (update):
      pbi fabric report push --workspace <id> --report "Sales" --definition ./Sales.Report

      # Publish with binding check + a table rename:
      pbi fabric report push --workspace <id> --report "Sales" --definition ./Sales.Report \\
        --dataset-id <id> --bind-verify --remap "Sales Data=Sales"
    """
    token = _fab.get_token()
    src = _Path(definition_dir)
    remap_map = _parse_remaps(remaps)

    # Warn early if publishing a local (byPath) report with no model to bind to.
    if not dataset_id and _datasetref_kind(src) == "byPath":
        console.print(
            "[yellow]Warning:[/yellow] this report's definition.pbir uses a local "
            "(byPath) model reference. Without --dataset-id it publishes unbound and "
            "visuals may render empty. Pass --dataset-id <model-id> to rebind it."
        )

    tmp_root: _Path | None = None
    try:
        # Apply transforms on a throwaway copy — never mutate the user's local files.
        if dataset_id or remap_map:
            tmp_root = _Path(_tempfile.mkdtemp(prefix="pbi-report-push-"))
            push_dir = tmp_root / src.name
            _shutil.copytree(src, push_dir)
            if dataset_id:
                base = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}"
                ws_name = _display_name(base, token, workspace_id)
                model_name = _display_name(f"{base}/items/{dataset_id}", token, dataset_id)
                if _rebind_pbir(push_dir, dataset_id, ws_name, model_name):
                    console.print(
                        f"[cyan]Rebound report to semantic model "
                        f"'{model_name}' ({dataset_id}) via byConnection.[/cyan]"
                    )
            if remap_map:
                n = _apply_remap(push_dir, remap_map)
                pairs = ", ".join(f"{k}→{v}" for k, v in remap_map.items())
                console.print(f"[cyan]Remapped {n} table reference(s): {pairs}[/cyan]")
        else:
            push_dir = src

        if bind_verify:
            if not dataset_id:
                raise click.ClickException("--bind-verify requires --dataset-id.")
            console.print("[cyan]Verifying bindings…[/cyan]")
            try:
                mismatches = _verify_bindings(push_dir, workspace_id, dataset_id, token)
            except FabricApiError as exc:
                # Fail closed: if we could not query the model we must NOT pretend the
                # bindings are valid. Abort so the user fixes access or skips the check.
                raise click.ClickException(
                    f"Could not verify bindings — the semantic model could not be queried "
                    f"({exc}). Check --dataset-id and your access to the model, or re-run "
                    f"without --bind-verify to skip the check."
                )
            if mismatches:
                raise click.ClickException(
                    f"Binding check failed — {len(mismatches)} reference(s) not found in the "
                    f"semantic model:\n  " + "\n  ".join(mismatches)
                    + "\nFix the field references, pass --remap 'Old=New' to rename a table, "
                      "or check --dataset-id."
                )
            console.print("[green]Binding check passed.[/green]")

        parts = _folder_to_parts(push_dir)

        existing_id: str | None = None
        try:
            existing_id = _resolve_report(workspace_id, report_ref, token)
        except click.ClickException:
            pass  # doesn't exist yet → create

        if existing_id:
            url = (
                f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports/{existing_id}"
                "/updateDefinition?updateMetadata=true"
            )
            result = _fab.poll_lro(
                _fab.post(url, token, payload={"definition": {"parts": parts}}), token
            )
            summary = result if isinstance(result, dict) else {
                "status": "Succeeded", "reportId": existing_id,
            }
            _out(summary, ctx, title="Report Updated")
        else:
            if not dataset_id:
                raise click.ClickException(
                    "Creating a new report requires --dataset-id. "
                    "If updating an existing report, ensure --report matches the exact "
                    "display name."
                )
            payload: dict = {
                "displayName": report_ref,
                "type": "Report",
                "definition": {"parts": parts},
            }
            if description:
                payload["description"] = description
            result = _fab.poll_lro(
                _fab.post(
                    f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports",
                    token, payload=payload,
                ),
                token,
            )
            _out(result, ctx, title="Report Created")
    finally:
        if tmp_root is not None:
            _shutil.rmtree(tmp_root, ignore_errors=True)


@fabric_report.command("update")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--report", "report_ref", required=True, help="Report name or id.")
@click.option("--name", "new_name", default=None, help="New display name.")
@click.option("--description", default=None, help="New description.")
@click.pass_context
def report_update(
    ctx: click.Context,
    workspace_id: str,
    report_ref: str,
    new_name: str | None,
    description: str | None,
) -> None:
    """Update a report's display name or description (metadata only, no definition change)."""
    token = _fab.get_token()
    report_id = _resolve_report(workspace_id, report_ref, token)
    payload: dict = {}
    if new_name:
        payload["displayName"] = new_name
    if description:
        payload["description"] = description
    if not payload:
        raise click.UsageError("Provide at least one of --name or --description.")
    result = _fab.patch(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports/{report_id}",
        token, payload=payload,
    )
    _out(result if isinstance(result, dict) else {"status": "Updated"}, ctx, title="Report Updated")


@fabric_report.command("delete")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--report", "report_ref", required=True, help="Report name or id.")
@click.option("--yes", is_flag=True, help="Skip confirmation.")
@click.pass_context
def report_delete(
    ctx: click.Context, workspace_id: str, report_ref: str, yes: bool
) -> None:
    """Delete a report from a workspace."""
    token = _fab.get_token()
    report_id = _resolve_report(workspace_id, report_ref, token)
    if not yes:
        click.confirm(f"Delete report '{report_ref}' ({report_id})?", abort=True)
    _fab.delete(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/reports/{report_id}", token
    )
    console.print(f"[green]Deleted report '{report_ref}'.[/green]")
