"""pbi model — semantic model commands."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()


@click.group()
def model() -> None:
    """Inspect and manage the semantic model: tables, columns, relationships, lint."""


@model.command("info")
@click.pass_context
def model_info(ctx: click.Context) -> None:
    """Show model name and compatibility level."""
    backend = get_backend(ctx)
    data = backend.model_info()
    output_json_or_table(data, ctx, title="Model Info")


@model.command("tables")
@click.pass_context
def model_tables(ctx: click.Context) -> None:
    """List all tables."""
    backend = get_backend(ctx)
    data = backend.table_list()
    output_json_or_table(data, ctx, title="Tables")


@model.command("columns")
@click.option("--table", default=None, help="Filter to a specific table.")
@click.pass_context
def model_columns(ctx: click.Context, table: str | None) -> None:
    """List columns."""
    backend = get_backend(ctx)
    data = backend.column_list(table=table)
    output_json_or_table(data, ctx, title="Columns")


@model.command("relationships")
@click.pass_context
def model_relationships(ctx: click.Context) -> None:
    """List relationships."""
    backend = get_backend(ctx)
    data = backend.relationship_list()
    output_json_or_table(data, ctx, title="Relationships")


@model.command("lint")
@click.pass_context
def model_lint(ctx: click.Context) -> None:
    """Check naming conventions (PascalCase tables, [Measure] brackets, _ hidden prefix)."""
    from pbi_cli.governance.engine import GovernanceEngine
    backend = get_backend(ctx)
    engine = GovernanceEngine(backend)
    violations = engine.run_naming_rules()
    if violations:
        output_json_or_table(violations, ctx, title="Lint Violations")
    else:
        console.print("[green]All naming conventions pass.[/green]")


@model.command("suggest-measures")
@click.pass_context
def model_suggest_measures(ctx: click.Context) -> None:
    """Suggest standard measures: Time Intelligence, % of total, MoM, YoY, Running Total."""
    backend = get_backend(ctx)
    tables = backend.table_list()
    columns = backend.column_list()
    suggestions = _build_measure_suggestions(tables, columns)
    output_json_or_table(suggestions, ctx, title="Suggested Measures")


@model.command("lineage")
@click.option("--format", "fmt", type=click.Choice(["json", "mermaid"]), default="json")
@click.pass_context
def model_lineage(ctx: click.Context, fmt: str) -> None:
    """Output measure dependency graph as JSON or Mermaid diagram."""
    backend = get_backend(ctx)
    measures = backend.measure_list()
    if fmt == "mermaid":
        console.print("graph TD")
        for m in measures:
            console.print(f"    {m['table']}_{m['name'].replace(' ','_')}[{m['name']}]")
    else:
        output_json_or_table(measures, ctx, title="Measure Lineage")


@model.command("hierarchies")
@click.option("--table", default=None, help="Filter to a specific table.")
@click.pass_context
def model_hierarchies(ctx: click.Context, table: str | None) -> None:
    """List hierarchies in the model."""
    backend = get_backend(ctx)
    data = backend.hierarchy_list(table=table)
    output_json_or_table(data, ctx, title="Hierarchies")


@model.command("hierarchy-add")
@click.option("--table", required=True, help="Table to add hierarchy to.")
@click.option("--name", required=True, help="Hierarchy name.")
@click.option("--levels", required=True, help='JSON array: [{"name":"Year","column":"Year"},{"name":"Month","column":"Month Name"}]')
@click.pass_context
def model_hierarchy_add(ctx: click.Context, table: str, name: str, levels: str) -> None:
    """Add a hierarchy to a table."""
    import json
    if dry_run_echo(ctx, f"add hierarchy '{name}' to '{table}'"):
        return
    backend = get_backend(ctx)
    levels_list = json.loads(levels)
    result = backend.hierarchy_add(table=table, name=name, levels=levels_list)
    output_json_or_table(result, ctx, title="Hierarchy Added")


@model.command("hierarchy-delete")
@click.option("--table", required=True)
@click.option("--name", required=True)
@click.pass_context
def model_hierarchy_delete(ctx: click.Context, table: str, name: str) -> None:
    """Delete a hierarchy."""
    if dry_run_echo(ctx, f"delete hierarchy '{name}' from '{table}'"):
        return
    backend = get_backend(ctx)
    backend.hierarchy_delete(table=table, name=name)
    console.print(f"[green]Deleted[/green] hierarchy '{name}' from '{table}'.")


@model.command("calc-groups")
@click.pass_context
def model_calc_groups(ctx: click.Context) -> None:
    """List calculation groups in the model."""
    backend = get_backend(ctx)
    data = backend.calc_group_list()
    if not data:
        console.print("[yellow]No calculation groups found.[/yellow]")
        return
    output_json_or_table(data, ctx, title="Calculation Groups")


@model.command("calc-group-add")
@click.option("--name", required=True, help="Name of the new calculation group table.")
@click.option("--precedence", default=0, show_default=True, help="Calculation group precedence (higher = evaluated first).")
@click.pass_context
def model_calc_group_add(ctx: click.Context, name: str, precedence: int) -> None:
    """Create a new calculation group table."""
    if dry_run_echo(ctx, f"create calculation group '{name}' (precedence={precedence})"):
        return
    backend = get_backend(ctx)
    result = backend.calc_group_add(name=name, precedence=precedence)
    output_json_or_table(result, ctx, title="Calculation Group Created")


@model.command("calc-item-add")
@click.option("--group", required=True, help="Calculation group table name.")
@click.option("--name", required=True, help="Calculation item name (e.g. 'YTD', 'MTD').")
@click.option("--expression", required=True, help="DAX expression for the calculation item.")
@click.option("--ordinal", default=0, show_default=True, help="Display order.")
@click.pass_context
def model_calc_item_add(ctx: click.Context, group: str, name: str, expression: str, ordinal: int) -> None:
    """Add a calculation item to a calculation group."""
    if dry_run_echo(ctx, f"add calc item '{name}' to group '{group}'"):
        return
    backend = get_backend(ctx)
    result = backend.calc_item_add(group_table=group, name=name, expression=expression, ordinal=ordinal)
    output_json_or_table(result, ctx, title="Calculation Item Added")


@model.command("calc-item-delete")
@click.option("--group", required=True)
@click.option("--name", required=True)
@click.pass_context
def model_calc_item_delete(ctx: click.Context, group: str, name: str) -> None:
    """Delete a calculation item from a calculation group."""
    if dry_run_echo(ctx, f"delete calc item '{name}' from '{group}'"):
        return
    backend = get_backend(ctx)
    backend.calc_item_delete(group_table=group, name=name)
    console.print(f"[green]Deleted[/green] calc item '{name}' from '{group}'.")


@model.command("stats")
@click.pass_context
def model_stats(ctx: click.Context) -> None:
    """Show health statistics for the model: object counts, complexity score, warnings."""
    backend = get_backend(ctx)

    tables = backend.table_list()
    columns = backend.column_list()
    measures = backend.measure_list()
    relationships = backend.relationship_list()

    hidden_tables = [t for t in tables if t.get("isHidden")]
    hidden_cols = [c for c in columns if c.get("isHidden")]
    hidden_measures = [m for m in measures if m.get("isHidden")]

    # Relationship complexity: count many-to-many and bidirectional
    m2m = [r for r in relationships if r.get("fromCardinality") == "Many" and r.get("toCardinality") == "Many"]
    bidir = [r for r in relationships if r.get("crossFilteringBehavior") == "BothDirections"]

    # Warnings
    warnings: list[str] = []
    if m2m:
        warnings.append(f"{len(m2m)} many-to-many relationship(s) — may cause unexpected aggregation")
    if bidir:
        warnings.append(f"{len(bidir)} bidirectional relationship(s) — can degrade query performance")
    no_desc = [m for m in measures if not m.get("description")]
    if no_desc:
        warnings.append(f"{len(no_desc)} measure(s) missing descriptions")
    no_fmt = [m for m in measures if not m.get("formatString")]
    if no_fmt:
        warnings.append(f"{len(no_fmt)} measure(s) missing format strings")

    # Complexity score: simple heuristic
    complexity = (
        len(tables) * 2
        + len(relationships)
        + len(measures) * 3
        + len(m2m) * 10
        + len(bidir) * 5
    )
    complexity_label = "Low" if complexity < 100 else "Medium" if complexity < 300 else "High"

    stats = {
        "tables": len(tables),
        "columns": len(columns),
        "measures": len(measures),
        "relationships": len(relationships),
        "hidden_tables": len(hidden_tables),
        "hidden_columns": len(hidden_cols),
        "hidden_measures": len(hidden_measures),
        "many_to_many_relationships": len(m2m),
        "bidirectional_relationships": len(bidir),
        "complexity_score": complexity,
        "complexity_label": complexity_label,
        "warnings": warnings,
    }

    if ctx.obj and ctx.obj.get("output_json"):
        import json as _json
        console.print(_json.dumps(stats, indent=2))
        return

    from rich.table import Table as RichTable
    tbl = RichTable(title="Model Statistics", show_header=True, header_style="bold cyan")
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value")
    tbl.add_row("Tables", str(len(tables)))
    tbl.add_row("Columns", str(len(columns)))
    tbl.add_row("Measures", str(len(measures)))
    tbl.add_row("Relationships", str(len(relationships)))
    tbl.add_row("Hidden tables", str(len(hidden_tables)))
    tbl.add_row("Hidden columns", str(len(hidden_cols)))
    tbl.add_row("Hidden measures", str(len(hidden_measures)))
    tbl.add_row("Many-to-many rels", str(len(m2m)))
    tbl.add_row("Bidirectional rels", str(len(bidir)))
    tbl.add_row("Complexity score", f"{complexity} ({complexity_label})")
    console.print(tbl)

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  ⚠  {w}")
    else:
        console.print("\n[green]No warnings — model looks healthy.[/green]")


@model.command("diff")
@click.option("--snapshot", required=True, help="Path to a TMDL snapshot directory to compare against.")
@click.pass_context
def model_diff(ctx: click.Context, snapshot: str) -> None:
    """Compare current model against a saved TMDL snapshot and show what changed."""
    backend = get_backend(ctx)
    result = backend.model_diff(snapshot_path=snapshot)
    if not result["has_changes"]:
        console.print("[green]No changes detected[/green] — model matches snapshot.")
        return
    output_json_or_table(result, ctx, title="Model Diff")
    console.print(f"[yellow]Changes:[/yellow] {len(result['added'])} added, {len(result['removed'])} removed, {len(result['changed'])} modified")


@model.command("impact")
@click.option("--measure",  default=None, help="Measure name to trace impact for.")
@click.option("--column",   default=None, help="Column name (format: Table[Column]) to trace impact for.")
@click.option("--pbip",     default=None, help="Optional .pbip path to also scan report visuals for references.")
@click.pass_context
def model_impact(
    ctx: click.Context, measure: str | None, column: str | None, pbip: str | None
) -> None:
    """Trace downstream impact of a measure or column change.

    Shows which other measures reference it and which report visuals use it.

    \b
    Examples:
      pbi model impact --measure "Total Sales"
      pbi model impact --column "financials[Sales]" --pbip MyReport
    """
    if not measure and not column:
        raise click.UsageError("Provide --measure or --column.")

    target_name = measure or column
    assert target_name

    backend = get_backend(ctx)

    # 1. Find direct DAX dependents in the model
    dax_dependents: list[dict] = []
    try:
        all_measures = backend.measure_list()
        for m in all_measures:
            expr = m.get("expression", "") or ""
            # Check if target is referenced in the DAX expression
            search_terms = _impact_search_terms(target_name, is_measure=bool(measure))
            if any(term.lower() in expr.lower() for term in search_terms):
                dax_dependents.append({
                    "type": "measure",
                    "table": m.get("table", ""),
                    "name": m.get("name", ""),
                    "expression_snippet": expr[:120].replace("\n", " "),
                })
    except Exception as e:
        console.print(f"[yellow]Could not scan DAX expressions: {e}[/yellow]")

    # 2. Scan PBIR visuals if --pbip provided
    visual_refs: list[dict] = []
    if pbip:
        try:
            visual_refs = _scan_pbir_for_field(pbip, target_name, is_measure=bool(measure))
        except Exception as e:
            console.print(f"[yellow]Could not scan PBIR visuals: {e}[/yellow]")

    # 3. Report results
    console.print(f"\n[bold]Impact analysis:[/bold] {target_name}")
    console.print(f"  Type: {'measure' if measure else 'column'}")
    console.print()

    if dax_dependents:
        console.print(f"[cyan]DAX dependents[/cyan] ({len(dax_dependents)}):")
        for dep in dax_dependents:
            console.print(f"  [{dep['table']}].[{dep['name']}]")
            console.print(f"    {dep['expression_snippet']}...")
    else:
        console.print("[green]No DAX dependents found.[/green]")

    if pbip:
        if visual_refs:
            console.print(f"\n[cyan]Report visual references[/cyan] ({len(visual_refs)}):")
            for ref in visual_refs:
                console.print(f"  Page '{ref['page']}' -> {ref['visual_type']} ({ref['visual_name']})")
        else:
            console.print("[green]No report visual references found.[/green]")

    if ctx.obj and ctx.obj.get("output_json"):
        import json as _json
        result = {
            "target": target_name,
            "type": "measure" if measure else "column",
            "dax_dependents": dax_dependents,
            "visual_refs": visual_refs,
        }
        console.print(_json.dumps(result, indent=2))


def _impact_search_terms(name: str, is_measure: bool) -> list[str]:
    """Return search patterns to look for in DAX expressions."""
    terms = [name]
    if is_measure:
        terms.append(f"[{name}]")
    else:
        # column: "Table[Col]" or just "[Col]"
        if "[" in name:
            table, col = name.split("[", 1)
            col = col.rstrip("]")
            terms.extend([f"{table}[{col}]", f"[{col}]", col])
    return terms


def _scan_pbir_for_field(pbip: str, name: str, is_measure: bool) -> list[dict]:
    """Scan all PBIR visual.json files for references to a field or measure."""
    import json as _json
    from pathlib import Path

    results: list[dict] = []
    root = Path(pbip)
    # Handle both .pbip file path and directory path
    if root.is_file() and root.suffix == ".pbip":
        root = root.parent
    report_dirs = list(root.glob("*.Report"))
    if not report_dirs:
        return results

    report_dir = report_dirs[0]
    pages_dir = report_dir / "definition" / "pages"
    if not pages_dir.exists():
        return results

    # Determine what to look for
    prop_name = name
    if "[" in name:
        prop_name = name.split("[", 1)[1].rstrip("]")

    for page_dir in pages_dir.iterdir():
        if not page_dir.is_dir():
            continue
        pj = page_dir / "page.json"
        page_name = page_dir.name
        if pj.exists():
            try:
                pdata = _json.loads(pj.read_text(encoding="utf-8"))
                page_name = pdata.get("displayName", page_dir.name)
            except Exception:
                pass

        visuals_dir = page_dir / "visuals"
        if not visuals_dir.exists():
            continue

        for vdir in visuals_dir.iterdir():
            if not vdir.is_dir():
                continue
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            try:
                vdata = _json.loads(vj.read_text(encoding="utf-8"))
                content = _json.dumps(vdata)
                # Look for the property name in the JSON content
                if f'"Property": "{prop_name}"' in content:
                    results.append({
                        "page": page_name,
                        "visual_name": vdata.get("name", vdir.name),
                        "visual_type": vdata.get("visual", {}).get("visualType", "unknown"),
                    })
            except Exception:
                pass
    return results


def _build_measure_suggestions(tables: list, columns: list) -> list[dict]:
    suggestions = []
    date_cols = [c for c in columns if c.get("dataType") in ("DateTime", "Date")]
    numeric_cols = [c for c in columns if c.get("dataType") in ("Decimal", "Double", "Int64")]
    for col in numeric_cols[:3]:
        suggestions.append({
            "name": f"YTD {col['name']}",
            "expression": f"TOTALYTD(SUM({col['table']}[{col['name']}]), Calendar[Date])",
            "category": "Time Intelligence",
        })
        suggestions.append({
            "name": f"MoM {col['name']} %",
            "expression": f"DIVIDE(SUM({col['table']}[{col['name']}]) - CALCULATE(SUM({col['table']}[{col['name']}]), DATEADD(Calendar[Date], -1, MONTH)), CALCULATE(SUM({col['table']}[{col['name']}]), DATEADD(Calendar[Date], -1, MONTH)))",
            "category": "Time Intelligence",
        })
    return suggestions
