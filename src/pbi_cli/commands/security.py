"""pbi security — Row-Level Security role management and testing."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()


@click.group()
def security() -> None:
    """Manage RLS roles and test row-level security filters."""


@security.command("roles")
@click.pass_context
def security_roles(ctx: click.Context) -> None:
    """List all RLS roles and their table filter expressions."""
    backend = get_backend(ctx)
    data = backend.role_list()
    if not data:
        console.print("[yellow]No RLS roles defined.[/yellow]")
        return
    output_json_or_table(data, ctx, title="RLS Roles")


@security.command("role-add")
@click.option("--name", required=True, help="Role name (e.g. 'Region Manager').")
@click.option("--table", required=True, help="Table to apply the filter to.")
@click.option("--filter", "filter_expression", required=True,
              help='DAX filter expression (e.g. "[Region] = USERNAME()").')
@click.pass_context
def security_role_add(ctx: click.Context, name: str, table: str, filter_expression: str) -> None:
    """Add an RLS role with a DAX row filter on a table."""
    if dry_run_echo(ctx, f"add RLS role '{name}' on '{table}'", f"filter: {filter_expression}"):
        return
    backend = get_backend(ctx)
    result = backend.role_add(name=name, table=table, filter_expression=filter_expression)
    from pbi_cli._audit import write_audit_entry
    write_audit_entry("security role-add", extra={"name": name, "table": table})
    output_json_or_table(result, ctx, title="RLS Role Added")
    console.print(f"[green]Role added:[/green] '{name}' — {table}: {filter_expression}")


@security.command("role-delete")
@click.option("--name", required=True, help="Role name to delete.")
@click.pass_context
def security_role_delete(ctx: click.Context, name: str) -> None:
    """Delete an RLS role."""
    if dry_run_echo(ctx, f"delete RLS role '{name}'"):
        return
    backend = get_backend(ctx)
    backend.role_delete(name=name)
    from pbi_cli._audit import write_audit_entry
    write_audit_entry("security role-delete", extra={"name": name})
    console.print(f"[green]Deleted[/green] RLS role '{name}'.")


@security.command("test")
@click.option("--role", required=True, help="Role name to test.")
@click.option("--query", required=True,
              help='DAX EVALUATE query to run under the role (e.g. "EVALUATE Sales").')
@click.pass_context
def security_test(ctx: click.Context, role: str, query: str) -> None:
    """Execute a DAX query with a specific RLS role applied and show the filtered result.

    Use this to verify that a role restricts data correctly.

    \b
    Example:
      pbi security test --role "Region Manager" --query "EVALUATE SUMMARIZE(Sales, Sales[Region])"
    """
    backend = get_backend(ctx)
    console.print(f"[cyan]Testing RLS:[/cyan] role='{role}'")
    result = backend.role_test(role_name=role, dax_expression=query)
    console.print(f"  Rows returned under role: [bold]{result['rowCount']}[/bold]")
    if result["rows"]:
        output_json_or_table(result["rows"], ctx, title=f"Query Result (role: {role})")
