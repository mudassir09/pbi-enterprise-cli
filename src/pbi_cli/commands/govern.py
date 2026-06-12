"""pbi govern — governance rules, lint, auto-fix (Epic D)."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli._audit import write_audit_entry
from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table
from pbi_cli.governance.bpa import COMMUNITY_BPA_URL

console = Console(legacy_windows=False)


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


_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


@govern.command("check")
@click.option(
    "--fail-on",
    "fail_on",
    default="error",
    type=click.Choice(["info", "warning", "error"]),
    show_default=True,
    help="Exit with code 3 when any violation at this severity or higher is found.",
)
@click.option(
    "--sarif", "sarif_path", type=click.Path(), default=None,
    help="Write violations as SARIF 2.1.0 (GitHub code scanning).",
)
@click.option(
    "--markdown", "markdown_path", type=click.Path(), default=None,
    help="Write a markdown summary (PR comments, job summaries).",
)
@click.option(
    "--comment-pr", is_flag=True,
    help="Post the markdown summary as a comment on the current PR (GitHub Actions).",
)
@click.pass_context
def govern_check(
    ctx: click.Context,
    fail_on: str,
    sarif_path: str | None,
    markdown_path: str | None,
    comment_pr: bool,
) -> None:
    """Run all governance rules; output violations with severity (error/warning/info).

    \b
    Exit codes:
      0  — no violations at or above --fail-on threshold
      3  — one or more violations at or above threshold

    \b
    CI usage:
      pbi --backend mock --json govern check --fail-on error | tee results.json
    """
    from pbi_cli.governance.engine import GovernanceEngine

    backend = get_backend(ctx)
    engine = GovernanceEngine(backend)
    violations = engine.run_all()
    is_json = ctx.obj and ctx.obj.get("output_json")

    if sarif_path or markdown_path or comment_pr:
        from pbi_cli.governance.exporters import post_pr_comment, to_markdown, to_sarif

        if sarif_path:
            Path(sarif_path).write_text(
                json.dumps(to_sarif(violations), indent=2), encoding="utf-8"
            )
            console.print(f"[green]SARIF written:[/green] {sarif_path}")
        if markdown_path:
            Path(markdown_path).write_text(to_markdown(violations), encoding="utf-8")
            console.print(f"[green]Markdown written:[/green] {markdown_path}")
        if comment_pr:
            try:
                post_pr_comment(to_markdown(violations))
                console.print("[green]PR comment posted.[/green]")
            except Exception as exc:
                console.print(f"[red]PR comment failed:[/red] {exc}")

    errors = [v for v in violations if v["severity"] == "error"]
    warnings_list = [v for v in violations if v["severity"] == "warning"]
    infos = [v for v in violations if v["severity"] == "info"]

    if is_json:
        summary = {
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings_list),
                "infos": len(infos),
                "total": len(violations),
            },
            "violations": violations,
        }
        click.echo(json.dumps(summary, indent=2))
    elif violations:
        console.print(
            f"[red]{len(errors)} errors[/red], "
            f"[yellow]{len(warnings_list)} warnings[/yellow], "
            f"[blue]{len(infos)} info[/blue]"
        )
        output_json_or_table(violations, ctx, title="Governance Violations")
    else:
        console.print("[green]All governance checks pass.[/green]")

    threshold = _SEVERITY_RANK[fail_on]
    should_fail = any(_SEVERITY_RANK.get(v["severity"], 0) >= threshold for v in violations)
    if should_fail:
        raise SystemExit(3)


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


@govern.group("plugins")
def govern_plugins() -> None:
    """Discover and install community governance rule plugins."""


_PLUGIN_REGISTRY_URL = (
    "https://raw.githubusercontent.com/mudassir09/pbi-enterprise-cli/main"
    "/community/governance-plugins/registry.json"
)
_PLUGIN_DIR = Path.home() / ".pbi-cli" / "rules"


@govern_plugins.command("list")
def plugins_list() -> None:
    """List installed governance plugins in ~/.pbi-cli/rules/."""
    if not _PLUGIN_DIR.exists() or not list(_PLUGIN_DIR.glob("*.py")):
        console.print("[yellow]No plugins installed.[/yellow]")
        console.print(f"Plugin directory: {_PLUGIN_DIR}")
        console.print("\nInstall a plugin:  pbi govern plugins install <name>")
        console.print("Browse plugins:    pbi govern plugins search")
        return
    from rich.table import Table

    table = Table(title="Installed Governance Plugins")
    table.add_column("File")
    table.add_column("Rule ID")
    table.add_column("Size", justify="right")
    for f in sorted(_PLUGIN_DIR.glob("*.py")):
        rule_id = ""
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("RULE_ID"):
                    rule_id = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    break
        except OSError:
            pass
        table.add_row(f.name, rule_id, f"{f.stat().st_size} B")
    console.print(table)


@govern_plugins.command("search")
@click.argument("query", default="", required=False)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
def plugins_search(query: str, output_json: bool) -> None:
    """Search the community plugin registry for governance rules.

    \b
    Examples:
      pbi govern plugins search                  # list all available plugins
      pbi govern plugins search sensitivity      # filter by keyword
    """
    import urllib.request

    from rich.table import Table

    if not output_json:
        console.print(f"[cyan]Fetching registry from:[/cyan] {_PLUGIN_REGISTRY_URL}")
    try:
        with urllib.request.urlopen(_PLUGIN_REGISTRY_URL, timeout=10) as resp:  # noqa: S310
            registry = json.loads(resp.read().decode())
    except Exception as exc:
        if output_json:
            click.echo(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]Could not fetch registry:[/red] {exc}")
            console.print(
                "\nYou can install plugins manually — place any .py file in ~/.pbi-cli/rules/\n"
                "that exports RULE_ID (str) and check(backend) -> list[dict]."
            )
        raise SystemExit(1)

    plugins = registry.get("plugins", [])
    if query:
        plugins = [
            p for p in plugins
            if query.lower() in p.get("name", "").lower()
            or query.lower() in p.get("description", "").lower()
            or query.lower() in p.get("tags", [])
        ]

    if not plugins:
        if output_json:
            click.echo("[]")
        else:
            console.print(f"[yellow]No plugins found matching '{query}'.[/yellow]")
        return

    if output_json:
        click.echo(json.dumps(plugins, indent=2))
        return

    table = Table(title=f"Community Plugins ({len(plugins)} found)")
    table.add_column("Name")
    table.add_column("Rule ID")
    table.add_column("Description")
    table.add_column("Tags")
    for p in plugins:
        table.add_row(
            p.get("name", ""),
            p.get("rule_id", ""),
            p.get("description", ""),
            ", ".join(p.get("tags", [])),
        )
    console.print(table)
    console.print("\nInstall a plugin:  pbi govern plugins install <name>")


@govern_plugins.command("install")
@click.argument("name")
@click.option("--url", default=None, help="Direct URL to plugin .py file (overrides registry).")
def plugins_install(name: str, url: str | None) -> None:
    """Install a governance plugin by name from the community registry.

    \b
    The plugin .py file is downloaded to ~/.pbi-cli/rules/<name>.py
    and is auto-discovered by pbi govern check and pbi govern rules.

    \b
    Examples:
      pbi govern plugins install require-sensitivity-labels
      pbi govern plugins install my-rule --url https://example.com/my_rule.py
    """
    import urllib.request

    _PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = _PLUGIN_DIR / f"{name}.py"

    if url:
        download_url = url
    else:
        # Resolve URL from registry
        console.print(f"[cyan]Looking up '{name}' in registry...[/cyan]")
        try:
            with urllib.request.urlopen(_PLUGIN_REGISTRY_URL, timeout=10) as resp:  # noqa: S310
                registry = json.loads(resp.read().decode())
        except Exception as exc:
            console.print(f"[red]Could not fetch registry:[/red] {exc}")
            raise SystemExit(1)

        plugin = next(
            (p for p in registry.get("plugins", []) if p.get("name") == name),
            None,
        )
        if not plugin:
            console.print(f"[red]Plugin '{name}' not found in registry.[/red]")
            console.print("Run 'pbi govern plugins search' to browse available plugins.")
            raise SystemExit(1)
        download_url = plugin["url"]

    console.print(f"[cyan]Downloading:[/cyan] {download_url}")
    try:
        with urllib.request.urlopen(download_url, timeout=15) as resp:  # noqa: S310
            content = resp.read().decode()
    except Exception as exc:
        console.print(f"[red]Download failed:[/red] {exc}")
        raise SystemExit(1)

    dest.write_text(content, encoding="utf-8")
    console.print(f"[green]Plugin installed:[/green] {dest}")
    console.print("It will be auto-discovered on the next 'pbi govern check' run.")


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


@govern.command("scan")
@click.option(
    "--workspace", "workspace_ids", multiple=True,
    help="Workspace id to scan (repeatable). Default: all workspaces visible to the admin API.",
)
@click.option("--max-workspaces", default=100, show_default=True,
              help="Cap on workspaces scanned in one run.")
@click.option(
    "--fail-on", default="error", type=click.Choice(["info", "warning", "error"]),
    show_default=True, help="Exit 3 when any violation at this severity or higher is found.",
)
@click.option("--timeout", default=300, show_default=True, help="Scan poll timeout (seconds).")
@click.pass_context
def govern_scan(
    ctx: click.Context,
    workspace_ids: tuple[str, ...],
    max_workspaces: int,
    fail_on: str,
    timeout: int,
) -> None:
    """Tenant-wide governance: run rules over every dataset via the Scanner (admin) API.

    Requires a token with Tenant.Read.All (admin) consent. Uses the metadata
    scanning API (workspaces/getInfo) with dataset schema + expressions, then
    runs the local governance engine against each scanned dataset.
    """
    import time

    from pbi_cli import fabric_api
    from pbi_cli.backends.mock_backend import MockTomBackend
    from pbi_cli.governance.engine import GovernanceEngine

    token = fabric_api.get_token()
    base = fabric_api.POWERBI_API_BASE
    quiet = bool(ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")))

    ids = list(workspace_ids)
    if not ids:
        if not quiet:
            console.print("[cyan]Listing workspaces via admin API...[/cyan]")
        modified = fabric_api.get(f"{base}/admin/workspaces/modified", token)
        ids = [w["id"] for w in (modified if isinstance(modified, list) else [])]
    ids = ids[:max_workspaces]
    if not ids:
        raise click.ClickException("No workspaces found to scan.")

    if not quiet:
        console.print(f"[cyan]Requesting scan of {len(ids)} workspace(s)...[/cyan]")
    scan = fabric_api.post(
        f"{base}/admin/workspaces/getInfo"
        "?datasetSchema=True&datasetExpressions=True&lineage=True",
        token,
        payload={"workspaces": ids},
    )
    scan_id = scan["id"]

    deadline = time.monotonic() + timeout
    while True:
        status = fabric_api.get(f"{base}/admin/workspaces/scanStatus/{scan_id}", token)
        if status.get("status") == "Succeeded":
            break
        if time.monotonic() > deadline:
            raise click.ClickException(f"Scan {scan_id} did not finish within {timeout}s.")
        time.sleep(2)

    result = fabric_api.get(f"{base}/admin/workspaces/scanResult/{scan_id}", token)

    all_violations: list[dict] = []
    datasets_scanned = 0
    for ws in result.get("workspaces", []):
        for ds in ws.get("datasets", []):
            datasets_scanned += 1
            fixture: dict = {
                "model": {"name": ds.get("name", ""), "compatibility_level": 1600},
                "tables": [], "columns": [], "measures": [], "relationships": [],
            }
            for t in ds.get("tables", []):
                fixture["tables"].append(
                    {"name": t.get("name", ""), "isHidden": bool(t.get("isHidden"))}
                )
                for c in t.get("columns", []):
                    fixture["columns"].append({
                        "table": t.get("name", ""), "name": c.get("name", ""),
                        "dataType": c.get("dataType", ""), "isHidden": bool(c.get("isHidden")),
                    })
                for m in t.get("measures", []):
                    fixture["measures"].append({
                        "table": t.get("name", ""), "name": m.get("name", ""),
                        "expression": m.get("expression", ""),
                        "description": m.get("description", ""),
                        "formatString": "",
                    })
            b = MockTomBackend(fixture=fixture)
            b.connect()
            for v in GovernanceEngine(b).run_all():
                v["workspace"] = ws.get("name", ws.get("id", ""))
                v["dataset"] = ds.get("name", "")
                all_violations.append(v)

    summary = {
        "workspaces": len(result.get("workspaces", [])),
        "datasets": datasets_scanned,
        "violations": len(all_violations),
    }
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table({"summary": summary, "violations": all_violations}, ctx)
    else:
        console.print(
            f"\n[bold]Scanned {summary['datasets']} datasets in "
            f"{summary['workspaces']} workspaces — {summary['violations']} violations[/bold]"
        )
        if all_violations:
            output_json_or_table(all_violations, ctx, title="Tenant Governance Violations")

    threshold = _SEVERITY_RANK[fail_on]
    if any(_SEVERITY_RANK.get(v["severity"], 0) >= threshold for v in all_violations):
        raise SystemExit(3)


@govern.command("explain")
@click.option("--rule", "rule_filter", default=None, help="Explain only this rule id.")
@click.option("--model", "model_id", default="claude-sonnet-4-6", show_default=True)
@click.pass_context
def govern_explain(ctx: click.Context, rule_filter: str | None, model_id: str) -> None:
    """AI explanation of current violations with concrete fix suggestions (requires [ai] extra)."""
    try:
        import anthropic
    except ImportError:
        raise click.ClickException(
            "The [ai] extra is required: pip install 'pbi-enterprise-cli[ai]' "
            "and set ANTHROPIC_API_KEY."
        )
    from pbi_cli.governance.engine import GovernanceEngine

    backend = get_backend(ctx)
    violations = GovernanceEngine(backend).run_all()
    if rule_filter:
        violations = [v for v in violations if v.get("rule") == rule_filter]
    if not violations:
        console.print("[green]No violations to explain.[/green]")
        return

    client = anthropic.Anthropic()
    prompt = (
        "You are a Power BI governance expert. For each violation below, explain in 1-2 "
        "sentences why the rule matters and give the exact fix (DAX/TMDL/property change). "
        "Be concrete and brief.\n\nViolations:\n"
        + json.dumps(violations[:50], indent=2)
    )
    message = client.messages.create(
        model=model_id, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
    )
    console.print(str(getattr(message.content[0], "text", "")))
