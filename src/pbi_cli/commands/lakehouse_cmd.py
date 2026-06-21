"""pbi lakehouse — Fabric Lakehouse table operations (data engineering).

First-class commands for the Lakehouse: list lakehouses, list Delta tables,
load a OneLake file/folder into a table, and run table maintenance
(OPTIMIZE / V-Order / VACUUM). Previously these were only reachable as a generic
``fabric item`` of type Lakehouse with no table ergonomics.
"""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console(legacy_windows=False)


@click.group("lakehouse")
def lakehouse_cmd() -> None:
    """Fabric Lakehouse: list, tables, load-to-table, maintenance (OPTIMIZE/VACUUM)."""


@lakehouse_cmd.command("list")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id.")
@click.pass_context
def lakehouse_list(ctx: click.Context, workspace_id: str) -> None:
    """List lakehouses in a workspace."""
    from pbi_cli import fabric_api as _fab

    token = _fab.get_token()
    items = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses", token
    )
    rows = [
        {"id": lh.get("id", ""), "name": lh.get("displayName", ""),
         "description": lh.get("description", "")}
        for lh in items
    ]
    if not rows:
        console.print("[yellow]No lakehouses found in this workspace.[/yellow]")
        return
    output_json_or_table(rows, ctx, title="Lakehouses")


@lakehouse_cmd.command("tables")
@click.option("--workspace", "workspace_id", required=True, help="Workspace id.")
@click.option("--lakehouse", "lakehouse_id", required=True, help="Lakehouse item id.")
@click.pass_context
def lakehouse_tables(ctx: click.Context, workspace_id: str, lakehouse_id: str) -> None:
    """List the Delta tables in a lakehouse."""
    from pbi_cli import fabric_api as _fab

    token = _fab.get_token()
    # The Lakehouse tables endpoint returns rows under "data" (not "value").
    tables = _fab.get_paged(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables",
        token, value_key="data",
    )
    rows = [
        {"name": t.get("name", ""), "type": t.get("type", ""),
         "format": t.get("format", ""), "location": t.get("location", "")}
        for t in tables
    ]
    if not rows:
        console.print("[yellow]No tables found in this lakehouse.[/yellow]")
        return
    output_json_or_table(rows, ctx, title="Lakehouse Tables")


def _format_options(file_format: str) -> dict:
    if file_format == "Parquet":
        return {"format": "Parquet"}
    return {"format": "Csv", "header": True, "delimiter": ","}


@lakehouse_cmd.command("load")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--lakehouse", "lakehouse_id", required=True)
@click.option("--table", "table_name", required=True, help="Destination Delta table name.")
@click.option("--path", "relative_path", required=True,
              help="OneLake relative path, e.g. Files/raw/sales.csv")
@click.option("--format", "file_format", type=click.Choice(["Csv", "Parquet"]),
              default="Csv", show_default=True)
@click.option("--mode", type=click.Choice(["Overwrite", "Append"]),
              default="Overwrite", show_default=True)
@click.option("--path-type", type=click.Choice(["File", "Folder"]),
              default="File", show_default=True, help="Load a single file or a folder.")
@click.option("--recursive/--no-recursive", default=False, show_default=True,
              help="Recurse into subfolders (folder loads only).")
@click.option("--wait/--no-wait", default=True, show_default=True,
              help="Poll the load operation to completion.")
@click.pass_context
def lakehouse_load(  # noqa: PLR0913
    ctx: click.Context,
    workspace_id: str,
    lakehouse_id: str,
    table_name: str,
    relative_path: str,
    file_format: str,
    mode: str,
    path_type: str,
    recursive: bool,
    wait: bool,
) -> None:
    """Load a OneLake file/folder into a Delta table (loadTable LRO)."""
    from pbi_cli import fabric_api as _fab

    if dry_run_echo(ctx, f"load {relative_path} into table '{table_name}'",
                    f"{file_format}, mode={mode}"):
        return

    token = _fab.get_token()
    payload: dict = {
        "relativePath": relative_path,
        "pathType": path_type,
        "mode": mode,
        "formatOptions": _format_options(file_format),
    }
    if path_type == "Folder":
        payload["recursive"] = recursive

    url = (f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
           f"/tables/{table_name}/load")
    resp = _fab.post(url, token, payload=payload)
    if wait:
        resp = _fab.poll_lro(resp, token)
    console.print(
        f"[green]Load into '{table_name}' "
        f"{'completed' if wait else 'started'}.[/green]"
    )
    output_json_or_table(resp if isinstance(resp, dict) else {"status": "Accepted"},
                         ctx, title="Load Table")


@lakehouse_cmd.command("maintenance")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--lakehouse", "lakehouse_id", required=True)
@click.option("--table", "table_name", required=True, help="Table to maintain.")
@click.option("--schema", "schema_name", default=None,
              help="Schema name (schema-enabled lakehouses).")
@click.option("--optimize/--no-optimize", default=True, show_default=True,
              help="Run OPTIMIZE (bin-compaction + V-Order).")
@click.option("--z-order", "z_order", default=None,
              help="Comma-separated columns to Z-ORDER by.")
@click.option("--vacuum/--no-vacuum", default=False, show_default=True,
              help="Run VACUUM to purge unreferenced files.")
@click.option("--vacuum-retention", default="7.00:00:00", show_default=True,
              help="VACUUM retention period (d.hh:mm:ss).")
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.pass_context
def lakehouse_maintenance(  # noqa: PLR0913
    ctx: click.Context,
    workspace_id: str,
    lakehouse_id: str,
    table_name: str,
    schema_name: str | None,
    optimize: bool,
    z_order: str | None,
    vacuum: bool,
    vacuum_retention: str,
    wait: bool,
) -> None:
    """Run table maintenance (OPTIMIZE / V-Order / VACUUM) via the job scheduler."""
    from pbi_cli import fabric_api as _fab

    if not optimize and not vacuum:
        raise click.ClickException("Nothing to do: enable --optimize and/or --vacuum.")

    exec_data: dict = {"tableName": table_name}
    if schema_name:
        exec_data["schemaName"] = schema_name
    if optimize:
        opt: dict = {"vOrder": True}
        if z_order:
            opt["zOrderBy"] = [c.strip() for c in z_order.split(",") if c.strip()]
        exec_data["optimizeSettings"] = opt
    if vacuum:
        exec_data["vacuumSettings"] = {"retentionPeriod": vacuum_retention}

    actions = ", ".join(filter(None, ["OPTIMIZE" if optimize else "", "VACUUM" if vacuum else ""]))
    if dry_run_echo(ctx, f"run maintenance ({actions}) on '{table_name}'"):
        return

    token = _fab.get_token()
    result = _fab.run_item_job(
        workspace_id, lakehouse_id, "TableMaintenance", token,
        execution_data=exec_data, wait=wait,
    )
    console.print(
        f"[green]Maintenance ({actions}) on '{table_name}' "
        f"{'completed' if wait else 'started'}.[/green]"
    )
    output_json_or_table(result, ctx, title="Table Maintenance")
