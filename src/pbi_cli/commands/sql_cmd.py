"""pbi sql — run T-SQL against a Fabric Warehouse or Lakehouse SQL endpoint.

The data-engineering counterpart to ``pbi dax query``: ``pbi dax`` runs DAX
against semantic models; ``pbi sql`` runs T-SQL against Warehouses and Lakehouse
SQL analytics endpoints. Discovery is by workspace + item id (REST), or connect
directly with --server/--database.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console(legacy_windows=False)


@click.group("sql")
def sql_cmd() -> None:
    """T-SQL against Fabric Warehouses & Lakehouse SQL endpoints (data engineering)."""


@sql_cmd.command("query")
@click.argument("query", required=False)
@click.option("--workspace", "workspace_id", default=None,
              help="Workspace id (with --item, for endpoint discovery).")
@click.option("--item", "item_id", default=None,
              help="Warehouse / Lakehouse / SQLEndpoint item id to discover the server from.")
@click.option("--server", default=None,
              help="SQL endpoint server FQDN — skip REST discovery and connect directly.")
@click.option("--database", default=None,
              help="Database name (defaults to the item's display name when discovered).")
@click.option("--file", "sql_file", type=click.Path(exists=True), default=None,
              help="Read the query from a .sql file (overrides the QUERY argument).")
@click.option("--driver", default=None,
              help="ODBC driver name (auto-detected; e.g. 'ODBC Driver 18 for SQL Server').")
@click.pass_context
def sql_query(  # noqa: PLR0913
    ctx: click.Context,
    query: str | None,
    workspace_id: str | None,
    item_id: str | None,
    server: str | None,
    database: str | None,
    sql_file: str | None,
    driver: str | None,
) -> None:
    """Run a T-SQL QUERY and print the rows.

    \b
    Discover the endpoint from a Fabric item:
      pbi sql query --workspace <ws> --item <warehouse> "SELECT TOP 10 * FROM dbo.Sales"
    Or connect directly to a known SQL endpoint:
      pbi sql query --server <fqdn> --database <db> --file report.sql
    Machine-readable output:
      pbi --json sql query --server <fqdn> --database <db> "SELECT 1 AS n"

    Needs the [sql] extra and a Microsoft ODBC driver (see the error if missing).
    """
    from pbi_cli import fabric_api as _fab
    from pbi_cli.sql_endpoint import (
        SQL_SCOPE,
        SqlEndpointError,
        resolve_endpoint,
        run_query,
    )

    if sql_file:
        query = Path(sql_file).read_text(encoding="utf-8")
    if not query or not query.strip():
        raise click.ClickException("Provide a QUERY argument or --file with a .sql file.")

    if not server and not (workspace_id and item_id):
        raise click.ClickException(
            "Provide --server (and --database), or --workspace and --item for discovery."
        )

    if dry_run_echo(ctx, "execute T-SQL", query.strip().splitlines()[0][:120]):
        return

    try:
        if not server:
            server, resolved_db = resolve_endpoint(workspace_id, item_id, _fab.get_token())  # type: ignore[arg-type]
            database = database or resolved_db
        sql_token = _fab.get_token(scope=SQL_SCOPE)
        rows = run_query(server, database or "", query, sql_token, driver=driver)
    except SqlEndpointError as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:  # connection / query errors
        raise click.ClickException(f"SQL query failed: {exc}")

    if not rows:
        console.print("[green]OK[/green] — statement executed (no rows returned).")
        return
    output_json_or_table(rows, ctx, title="SQL Results")
