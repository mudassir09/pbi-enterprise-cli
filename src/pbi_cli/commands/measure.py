"""pbi measure — DAX measure CRUD commands."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli._audit import write_audit_entry
from pbi_cli.commands._shared import (
    dry_run_echo,
    get_backend,
    output_json_or_table,
    snapshot_before_write,
)

console = Console(legacy_windows=False)


@click.group()
def measure() -> None:
    """Manage DAX measures: add, list, update, delete, generate, audit."""


@measure.command("list")
@click.option("--table", default=None, help="Filter to a specific table.")
@click.pass_context
def measure_list(ctx: click.Context, table: str | None) -> None:
    """List all measures in the connected model."""
    backend = get_backend(ctx)
    if not backend.is_connected():
        console.print("[red]Not connected. Use 'pbi connect' first.[/red]")
        raise click.Abort()
    data = backend.measure_list(table=table)
    output_json_or_table(data, ctx, title="Measures")


@measure.command("add")
@click.option("--table", required=True, help="Table to add the measure to.")
@click.option("--name", required=True, help="Measure name (use [Brackets] convention).")
@click.option("--expression", required=True, help="DAX expression.")
@click.option("--format-string", default=None, help="Format string (e.g. #,0.00).")
@click.option("--description", default=None, help="Measure description.")
@click.pass_context
def measure_add(
    ctx: click.Context,
    table: str,
    name: str,
    expression: str,
    format_string: str | None,
    description: str | None,
) -> None:
    """Add a new DAX measure."""
    detail = f"measure '{name}' to '{table}': {expression}"
    if dry_run_echo(ctx, f"add measure '{name}' to table '{table}'", detail):
        return
    backend = get_backend(ctx)
    snapshot_before_write(ctx)
    kwargs = {}
    if format_string:
        kwargs["formatString"] = format_string
    if description:
        kwargs["description"] = description
    result = backend.measure_add(table=table, name=name, expression=expression, **kwargs)
    write_audit_entry("measure add", after=result)
    if not (ctx.obj and ctx.obj.get("output_json")):
        console.print(f"[green]Added[/green] measure '{name}' to '{table}'")
    output_json_or_table(result, ctx)


@measure.command("update")
@click.option("--table", required=True, help="Table containing the measure.")
@click.option("--name", required=True, help="Measure name to update.")
@click.option("--expression", default=None, help="New DAX expression.")
@click.option("--format-string", default=None, help="New format string.")
@click.option("--description", default=None, help="New description.")
@click.pass_context
def measure_update(
    ctx: click.Context,
    table: str,
    name: str,
    expression: str | None,
    format_string: str | None,
    description: str | None,
) -> None:
    """Update an existing DAX measure (expression, format string, or description)."""
    kwargs: dict = {}
    if expression:
        kwargs["expression"] = expression
    if format_string:
        kwargs["formatString"] = format_string
    if description:
        kwargs["description"] = description
    if not kwargs:
        console.print("[yellow]Nothing to update — provide at least one option.[/yellow]")
        return
    detail = f"update measure '{name}' in '{table}': {kwargs}"
    if dry_run_echo(ctx, f"update measure '{name}' in table '{table}'", detail):
        return
    backend = get_backend(ctx)
    snapshot_before_write(ctx)
    before = next((m for m in backend.measure_list(table=table) if m["name"] == name), None)
    result = backend.measure_update(table=table, name=name, **kwargs)
    write_audit_entry("measure update", before=before, after=result)
    if not (ctx.obj and ctx.obj.get("output_json")):
        console.print(f"[green]Updated[/green] measure '{name}' in '{table}'")
    output_json_or_table(result, ctx)


@measure.command("delete")
@click.option("--table", required=True, help="Table containing the measure.")
@click.option("--name", required=True, help="Measure name to delete.")
@click.pass_context
def measure_delete(ctx: click.Context, table: str, name: str) -> None:
    """Delete a measure."""
    if dry_run_echo(ctx, f"delete measure '{name}' from '{table}'"):
        return
    backend = get_backend(ctx)
    snapshot_before_write(ctx)
    before = next((m for m in backend.measure_list(table=table) if m["name"] == name), None)
    backend.measure_delete(table=table, name=name)
    write_audit_entry("measure delete", before=before)
    console.print(f"[red]Deleted[/red] measure '{name}' from '{table}'")


@measure.command("generate")
@click.argument("description")
@click.option("--table", required=True, help="Target table.")
@click.option("--name", required=True, help="Measure name.")
@click.pass_context
def measure_generate(ctx: click.Context, description: str, table: str, name: str) -> None:
    """Generate a DAX measure from a natural language description using Claude."""
    from pbi_cli.intelligence.measure_generator import MeasureGenerator

    console.print(f"[cyan]Generating DAX for:[/cyan] {description}")
    backend = get_backend(ctx)
    schema = backend.column_list() if backend.is_connected() else []
    gen = MeasureGenerator()
    result = gen.generate(description=description, schema=schema)
    expression = result.get("expression", "")
    console.print(f"[bold]Generated DAX:[/bold]\n{expression}")

    if not result.get("valid"):
        console.print(f"[yellow]Generation failed:[/yellow] {result.get('error')}")
        console.print("Review the expression above and add manually.")
        return

    # Validate the generated DAX via the backend before writing
    console.print("[cyan]Validating DAX...[/cyan]")
    validation = backend.dax_validate(expression)
    if not validation.get("valid", True):
        console.print("[yellow]DAX validation failed — showing expression for review:[/yellow]")
        console.print(f"  {validation.get('error', 'Syntax error')}")
        console.print("Use 'pbi measure add' to write it manually after correction.")
        return

    if dry_run_echo(ctx, f"add measure '{name}' to '{table}'", expression):
        return
    backend.measure_add(table=table, name=name, expression=expression)
    write_audit_entry(
        "measure generate", after={"table": table, "name": name, "expression": expression}
    )
    console.print(f"[green]Written[/green] measure '{name}' to '{table}'")


@measure.command("audit")
@click.pass_context
def measure_audit(ctx: click.Context) -> None:
    """Audit all measures: unused, circular deps, missing FORMAT, hardcoded dates."""
    backend = get_backend(ctx)
    measures = backend.measure_list()
    issues: list[dict] = []
    for m in measures:
        expr = m.get("expression", "")
        if not m.get("formatString"):
            issues.append(
                {"measure": m["name"], "issue": "missing FORMAT string", "severity": "warning"}
            )
        if "NOW()" in expr.upper() or "TODAY()" in expr.upper():
            issues.append(
                {"measure": m["name"], "issue": "hardcoded date function", "severity": "warning"}
            )
    if issues:
        output_json_or_table(issues, ctx, title="Measure Audit Issues")
    else:
        console.print("[green]No issues found.[/green]")
