"""pbi govern — governance rules, lint, auto-fix (Epic D)."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli._audit import write_audit_entry
from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table
from pbi_cli.governance.bpa import COMMUNITY_BPA_URL

console = Console()


@click.group()
def govern() -> None:
    """Enforce naming conventions, required metadata, and model quality rules."""


@govern.command("init")
@click.pass_context
def govern_init(ctx: click.Context) -> None:
    """Create ~/.pbi-cli/governance.json with default rules."""
    config_dir = Path.home() / ".pbi-cli"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "governance.json"
    if config_file.exists():
        console.print(f"[yellow]Already exists:[/yellow] {config_file}")
        return
    defaults = {
        "naming": {
            "tables": "PascalCase",
            "measures": "Title Case in [Brackets]",
            "hiddenPrefix": "_",
            "factPrefix": "FACT_",
            "dimPrefix": "DIM_",
        },
        "required": {
            "measureDescription": True,
            "tableDataCategory": False,
        },
        "complexity": {
            "maxMeasureLength": 500,
            "maxIteratorDepth": 3,
        },
    }
    config_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
    console.print(f"[green]Created:[/green] {config_file}")


@govern.command("check")
@click.pass_context
def govern_check(ctx: click.Context) -> None:
    """Run all governance rules; output violations with severity (error/warning/info)."""
    from pbi_cli.governance.engine import GovernanceEngine

    backend = get_backend(ctx)
    engine = GovernanceEngine(backend)
    violations = engine.run_all()
    is_json = ctx.obj and ctx.obj.get("output_json")
    if violations:
        errors = [v for v in violations if v["severity"] == "error"]
        warnings_list = [v for v in violations if v["severity"] == "warning"]
        if not is_json:
            console.print(
                f"[red]{len(errors)} errors[/red], [yellow]{len(warnings_list)} warnings[/yellow]"
            )
        output_json_or_table(violations, ctx, title="Governance Violations")
        if errors:
            raise SystemExit(1)
    else:
        if not is_json:
            console.print("[green]All governance checks pass.[/green]")
        else:
            import click

            click.echo("[]")


@govern.command("fix")
@click.option("--auto", is_flag=True, help="Auto-fix safe violations.")
@click.pass_context
def govern_fix(ctx: click.Context, auto: bool) -> None:
    """Auto-fix safe violations: PascalCase, FORMAT strings, folder sort."""
    from pbi_cli.governance.engine import GovernanceEngine

    backend = get_backend(ctx)
    engine = GovernanceEngine(backend)
    violations = engine.run_all()
    fixable = [v for v in violations if v.get("autoFixable")]
    console.print(f"[cyan]{len(fixable)} auto-fixable violations[/cyan]")
    if not auto:
        console.print("Use --auto to apply fixes.")
        return
    if dry_run_echo(ctx, f"apply {len(fixable)} auto-fixes"):
        return
    fixed = engine.auto_fix(fixable)
    write_audit_entry("govern fix", extra={"violations_fixed": fixed})
    console.print(f"[green]Fixed {fixed} violations.[/green]")


@govern.group("bpa")
@click.pass_context
def govern_bpa(ctx: click.Context) -> None:
    """Run BPA (Best Practice Analyzer) rules — the same rules as Tabular Editor."""


@govern_bpa.command("check")
@click.option("--file", "rules_file", default=None, help="Path to a local BPARules.json file.")
@click.option(
    "--url",
    "rules_url",
    default=None,
    help="URL of a BPARules.json to fetch (default: Microsoft community rules).",
)
@click.option(
    "--severity",
    default=None,
    type=click.Choice(["info", "warning", "error"]),
    help="Only show violations at this severity level.",
)
@click.option("--category", default=None, help="Filter violations by category name.")
@click.pass_context
def bpa_check(
    ctx: click.Context,
    rules_file: str | None,
    rules_url: str | None,
    severity: str | None,
    category: str | None,
) -> None:
    """Run BPA rules against the current model.

    \b
    Sources (in priority order):
      1. --file PATH   — local BPARules.json
      2. --url  URL    — custom remote URL
      3. (default)     — Microsoft community BPA rules fetched live
    """
    from pbi_cli.governance.bpa import BpaEvaluator, load_rules_from_file, load_rules_from_url

    backend = get_backend(ctx)
    is_json = ctx.obj and ctx.obj.get("output_json")

    # Load rules
    try:
        if rules_file:
            rules = load_rules_from_file(rules_file)
            source_label = rules_file
        else:
            url = rules_url or COMMUNITY_BPA_URL
            if not is_json:
                console.print(f"[cyan]Fetching BPA rules from:[/cyan] {url}")
            rules = load_rules_from_url(url)
            source_label = url
    except Exception as exc:
        console.print(f"[red]Failed to load BPA rules:[/red] {exc}")
        raise SystemExit(1)

    if not is_json:
        console.print(f"[cyan]Loaded {len(rules)} rules from:[/cyan] {source_label}")

    evaluator = BpaEvaluator()
    violations, skipped = evaluator.evaluate(
        rules, backend, severity_filter=severity, category_filter=category
    )

    if not is_json:
        errors = [v for v in violations if v["severity"] == "error"]
        warnings_list = [v for v in violations if v["severity"] == "warning"]
        infos = [v for v in violations if v["severity"] == "info"]
        console.print(
            f"[red]{len(errors)} errors[/red], "
            f"[yellow]{len(warnings_list)} warnings[/yellow], "
            f"[blue]{len(infos)} info[/blue]  "
            f"([dim]{skipped} rules skipped — unsupported expressions[/dim])"
        )

    if violations:
        output_json_or_table(violations, ctx, title="BPA Violations")
    else:
        if not is_json:
            console.print("[green]No BPA violations found.[/green]")
        else:
            click.echo("[]")

    if not is_json:
        console.print(
            f"\n[dim]{len(violations)} violations found, {skipped} rules skipped "
            f"(unsupported expressions)[/dim]"
        )

    # Exit 1 if any errors found
    if any(v["severity"] == "error" for v in violations):
        raise SystemExit(1)


@govern.command("rules")
@click.pass_context
def govern_rules(ctx: click.Context) -> None:
    """List all registered governance rules (built-in and plugins).

    \b
    Plugin rules are loaded from: ~/.pbi-cli/rules/*.py
    Each plugin file must expose: RULE_ID (str) and check(backend) -> list[dict]
    """
    from pbi_cli.commands._shared import output_json_or_table
    from pbi_cli.governance.engine import GovernanceEngine

    rules = GovernanceEngine.list_rules()
    output_json_or_table(rules, ctx, title="Governance Rules")
    plugin_count = sum(1 for r in rules if r["source"] == "plugin")
    if plugin_count:
        console.print(f"\n[cyan]{plugin_count} plugin rule(s) loaded[/cyan] from ~/.pbi-cli/rules/")
    else:
        console.print(
            "\n[yellow]No plugin rules loaded.[/yellow] Place *.py rule files in ~/.pbi-cli/rules/"
        )
