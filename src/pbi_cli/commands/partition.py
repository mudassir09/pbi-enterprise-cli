"""pbi partition — manage table partitions and incremental refresh."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console(legacy_windows=False)


@click.group()
def partition() -> None:
    """Manage table partitions and trigger selective refreshes."""


@partition.command("list")
@click.option("--table", default=None, help="Filter to a specific table.")
@click.pass_context
def partition_list(ctx: click.Context, table: str | None) -> None:
    """List all partitions (and their refresh state) across all tables."""
    backend = get_backend(ctx)
    data = backend.partition_list(table=table)
    if not data:
        console.print("[yellow]No partitions found.[/yellow]")
        return
    output_json_or_table(data, ctx, title="Partitions")


@partition.command("add")
@click.option("--table", required=True, help="Table to add the partition to.")
@click.option("--name", required=True, help="Partition name.")
@click.option("--query", required=True, help="M (Power Query) expression for the partition source.")
@click.pass_context
def partition_add(ctx: click.Context, table: str, name: str, query: str) -> None:
    """Add a new M-query partition to a table.

    \b
    Example — date-range partition:
      pbi partition add --table Sales --name "Sales 2024" \\
        --query 'let src = Sales_All,
        filtered = Table.SelectRows(src, each [Year] = 2024) in filtered'
    """
    if dry_run_echo(ctx, f"add partition '{name}' to '{table}'"):
        return
    backend = get_backend(ctx)
    result = backend.partition_add(table=table, name=name, query=query)
    from pbi_cli._audit import write_audit_entry

    write_audit_entry("partition add", extra={"table": table, "name": name})
    output_json_or_table(result, ctx, title="Partition Added")
    console.print(f"[green]Partition added:[/green] '{name}' -> '{table}'")


@partition.command("delete")
@click.option("--table", required=True)
@click.option("--name", required=True)
@click.pass_context
def partition_delete(ctx: click.Context, table: str, name: str) -> None:
    """Delete a partition from a table."""
    if dry_run_echo(ctx, f"delete partition '{name}' from '{table}'"):
        return
    backend = get_backend(ctx)
    backend.partition_delete(table=table, name=name)
    from pbi_cli._audit import write_audit_entry

    write_audit_entry("partition delete", extra={"table": table, "name": name})
    console.print(f"[green]Deleted[/green] partition '{name}' from '{table}'.")


@partition.command("refresh")
@click.option("--table", required=True, help="Table containing the partition.")
@click.option("--name", required=True, help="Partition name to refresh.")
@click.pass_context
def partition_refresh(ctx: click.Context, table: str, name: str) -> None:
    """Trigger a full refresh of a single partition (selective refresh).

    More efficient than refreshing the entire table when only recent data changed.
    """
    if dry_run_echo(ctx, f"refresh partition '{name}' in '{table}'"):
        return
    backend = get_backend(ctx)
    result = backend.partition_refresh(table=table, name=name)
    from pbi_cli._audit import write_audit_entry

    write_audit_entry("partition refresh", extra={"table": table, "name": name})
    console.print(f"[green]Refresh requested:[/green] '{name}' in '{table}'")
    output_json_or_table(result, ctx, title="Partition Refresh")
