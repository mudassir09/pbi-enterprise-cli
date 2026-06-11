"""Main CLI entry point for pbi-cli."""

from pathlib import Path

import click
from rich.console import Console

from pbi_cli import __version__
from pbi_cli.commands import (
    agent_cmd,
    calendar_cmd,
    connections,
    custom_visual,
    database,
    dax,
    deploy,
    devops_cmd,
    docs,
    env_cmd,
    fabric_cmd,
    filter_cmd,
    govern,
    layout,
    measure,
    migrate_cmd,
    model,
    ops_cmd,
    partition,
    pquery_cmd,
    repl,
    report,
    security,
    server_cmd,
    skills_cmd,
    snapshot,
    source,
    tenant_cmd,
    test_cmd,
    theme,
    trace,
    visual,
    watch,
)

console = Console()


def _apply_dry_run(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    ctx.ensure_object(dict)
    ctx.obj["dry_run"] = value
    return value


@click.group()
@click.version_option(__version__, prog_name="pbi")
@click.option(
    "--dry-run",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_apply_dry_run,
    help="Show what would change without applying any writes.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results as JSON.",
)
@click.option(
    "--yaml",
    "output_yaml",
    is_flag=True,
    help="Output results as YAML (structured, human-readable alternative to --json).",
)
@click.option(
    "--backend",
    type=click.Choice(["desktop", "xmla", "mock", "file", "rest"]),
    default="desktop",
    show_default=True,
    help="Backend: desktop (TOM), xmla (Premium/Fabric), mock (CI fixtures), "
    "file (TMDL/PBIP folder — any OS), rest (executeQueries API — any OS).",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Override the local Analysis Services port (desktop backend).",
)
@click.option(
    "--path",
    "model_path",
    type=click.Path(),
    default=None,
    help="TMDL/PBIP project folder (file backend). Defaults to the current directory.",
)
@click.pass_context
def cli(  # noqa: PLR0913
    ctx: click.Context,
    output_json: bool,
    output_yaml: bool,
    backend: str,
    port: int | None,
    model_path: str | None,
) -> None:
    """pbi — Power BI one-stop-shop CLI for AI-driven development.

    Connect, model, visualize, govern, test, and deploy Power BI solutions
    from the command line. Designed for use with Claude Code.
    """
    ctx.ensure_object(dict)
    ctx.obj.setdefault("dry_run", False)
    ctx.obj["output_json"] = output_json
    ctx.obj["output_yaml"] = output_yaml
    ctx.obj["backend"] = backend
    if port:
        ctx.obj["port"] = port
    if model_path:
        ctx.obj["path"] = model_path


# Register command groups
cli.add_command(source.source)
cli.add_command(measure.measure)
cli.add_command(model.model)
cli.add_command(dax.dax)
cli.add_command(report.report)
cli.add_command(visual.visual)
cli.add_command(layout.layout)
cli.add_command(theme.theme)
cli.add_command(govern.govern)
cli.add_command(deploy.deploy)
cli.add_command(docs.docs)
cli.add_command(database.database)
cli.add_command(server_cmd.server)
cli.add_command(watch.watch)
cli.add_command(security.security)
cli.add_command(partition.partition)
cli.add_command(filter_cmd.filter_cmd)
cli.add_command(trace.trace)
cli.add_command(trace.benchmark)
cli.add_command(connections.connections)
cli.add_command(skills_cmd.skills_cmd)
cli.add_command(env_cmd.env_cmd)
cli.add_command(snapshot.snapshot_cmd)
cli.add_command(fabric_cmd.fabric_cmd)
cli.add_command(calendar_cmd.calendar_cmd)
cli.add_command(calendar_cmd.culture_cmd)
cli.add_command(repl.repl)
cli.add_command(custom_visual.custom_visual)
cli.add_command(tenant_cmd.tenant_cmd)
cli.add_command(test_cmd.test_cmd)
cli.add_command(devops_cmd.init_cmd)
cli.add_command(devops_cmd.diff_cmd)
cli.add_command(agent_cmd.mcp_cmd)
cli.add_command(agent_cmd.ask_cmd)
cli.add_command(agent_cmd.introspect_cmd)
cli.add_command(pquery_cmd.pquery_cmd)
cli.add_command(ops_cmd.ops_cmd)
cli.add_command(migrate_cmd.migrate_cmd)


@cli.command()
@click.option("--port", type=int, default=None, help="Explicit port (auto-detected if omitted).")
@click.option(
    "--install-skills/--no-install-skills",
    default=True,
    show_default=True,
    help="Install bundled skills into ~/.claude/skills/ after connecting.",
)
@click.pass_context
def connect(ctx: click.Context, port: int | None, install_skills: bool) -> None:
    """Auto-setup: connect to Power BI Desktop, install Claude Code skills, show model summary.

    Scans for an open .pbip/.pbix session, verifies the connection, installs all
    10 bundled skills into ~/.claude/skills/, and prints a success summary.
    Time-to-first-value target: under 60 seconds.
    """
    import time

    from rich.panel import Panel
    from rich.table import Table

    t0 = time.monotonic()

    # --- 1. Detect and connect ---
    from pbi_cli.backends.tom_backend import TomBackend, find_pbi_port

    console.print("[cyan]Scanning for Power BI Desktop...[/cyan]")
    detected = port or find_pbi_port()
    if not detected:
        console.print("[red]No running Power BI Desktop found.[/red]")
        console.print(
            "Open a .pbip or .pbix file in Power BI Desktop, then run [bold]pbi connect[/bold]."
        )
        raise SystemExit(2)

    console.print(f"[cyan]Connecting to localhost:{detected}...[/cyan]")
    b = TomBackend()
    b.connect(port=detected)
    info = b.model_info()
    tables = b.table_list()
    measures = b.measure_list() if hasattr(b, "measure_list") else []
    b.disconnect()

    # --- 2. Install skills ---
    skills_installed: list[str] = []
    skills_dir = None
    if install_skills:
        import shutil  # noqa: PLC0415

        from pbi_cli.commands.skills_cmd import (  # noqa: PLC0415
            _BUNDLED_SKILLS,
            _claude_skills_dir,
            _skills_source_dir,
        )

        source_dir = _skills_source_dir()
        target_dir = _claude_skills_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        for skill in _BUNDLED_SKILLS:
            src = source_dir / skill["name"]
            if not src.exists():
                continue
            dst = target_dir / skill["name"]
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            skills_installed.append(skill["name"])

        skills_dir = target_dir

    elapsed = time.monotonic() - t0

    # --- 3. Print success summary ---
    console.print()
    console.print(
        Panel.fit(
            f"[bold green]Connected![/bold green]  "
            f"Model: [bold]{info['name']}[/bold]  "
            f"(CompatibilityLevel {info['compatibilityLevel']})",
            title="pbi connect",
        )
    )

    model_table = Table(show_header=True, header_style="bold")
    model_table.add_column("Property")
    model_table.add_column("Value")
    model_table.add_row("Model name", info["name"])
    model_table.add_row("Compatibility level", str(info["compatibilityLevel"]))
    model_table.add_row("Tables", str(len(tables)))
    model_table.add_row("Measures", str(len(measures)))
    model_table.add_row("Backend port", str(detected))
    console.print(model_table)

    if tables:
        console.print(f"\n[dim]Tables:[/dim] {', '.join(t['name'] for t in tables[:10])}"
                      + (" ..." if len(tables) > 10 else ""))

    if skills_installed:
        console.print(
            f"\n[green]{len(skills_installed)} skills installed[/green] → {skills_dir}"
        )
        console.print("[dim]Restart Claude Code to pick up the new skills.[/dim]")
    elif install_skills:
        console.print(
            "\n[yellow]No skill files found in package — skipping skill install.[/yellow]"
        )

    console.print(f"\n[dim]Setup completed in {elapsed:.1f}s[/dim]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  pbi model tables         — explore the semantic model")
    console.print("  pbi govern check         — run governance rules")
    console.print("  pbi measure list         — list all DAX measures")


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Diagnose setup issues: pythonnet, DLL compatibility, XMLA connectivity."""
    from pbi_cli.commands._doctor import run_doctor

    run_doctor(ctx.obj.get("output_json", False))


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def undo(ctx: click.Context, yes: bool) -> None:
    """Revert the last write command using the auto-snapshot."""
    from pbi_cli._snapshot import latest_snapshot, restore_snapshot

    snapshot = latest_snapshot()
    if not snapshot:
        console.print("[yellow]No snapshots found. Nothing to undo.[/yellow]")
        console.print("Snapshots are created automatically before each write operation.")
        return

    console.print(f"[cyan]Latest snapshot:[/cyan] {snapshot.name}")
    if not yes:
        click.confirm(
            "Restore this snapshot? This will overwrite current measure state.", abort=True
        )

    from pbi_cli.backends.tom_backend import TomBackend, find_pbi_port

    port = find_pbi_port()
    if not port:
        console.print("[red]No running Power BI Desktop found.[/red]")
        raise SystemExit(1)
    b = TomBackend()
    b.connect(port=port)
    restored = restore_snapshot(snapshot, b)
    b.disconnect()

    from pbi_cli._audit import write_audit_entry

    write_audit_entry("undo", extra={"snapshot": snapshot.name, "restored": restored})
    console.print(
        f"[green]Restored:[/green] {restored['measures_restored']} measures from snapshot {snapshot.name}"  # noqa: E501
    )


@cli.command("skill-validate")
@click.argument("skill_path", type=click.Path(exists=True))
@click.pass_context
def skill_validate(ctx: click.Context, skill_path: str) -> None:
    """Lint a SKILL.md file: validate frontmatter fields, description triggers, and structure (F4)."""  # noqa: E501
    import re
    from pathlib import Path

    path = Path(skill_path)
    if path.is_dir():
        skill_file = path / "SKILL.md"
    else:
        skill_file = path

    if not skill_file.exists():
        console.print(f"[red]SKILL.md not found:[/red] {skill_file}")
        raise SystemExit(1)

    content = skill_file.read_text(encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []

    # Extract frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        errors.append("Missing YAML frontmatter block (--- ... ---)")
        _report_validation(skill_file, errors, warnings, ctx)
        return

    fm_text = fm_match.group(1)

    # Required frontmatter fields
    required_fields = ["name", "description", "version", "requires"]
    for field in required_fields:
        if not re.search(rf"^{field}:", fm_text, re.MULTILINE):
            errors.append(f"Missing required frontmatter field: '{field}'")

    # Description must contain action triggers (Use when / triggers on)
    if re.search(r"^description:", fm_text, re.MULTILINE):
        desc_block = re.search(r"^description:(.+?)(?=^\w|\Z)", fm_text, re.DOTALL | re.MULTILINE)
        if desc_block:
            desc_text = desc_block.group(1)
            if not re.search(
                r"(Use when|triggers on|trigger|when the user)", desc_text, re.IGNORECASE
            ):
                warnings.append(
                    "description should include trigger phrases like 'Use when' or 'triggers on'"
                )
            if not re.search(r"Do NOT", desc_text, re.IGNORECASE):
                warnings.append("description should include a 'Do NOT trigger' exclusion clause")

    # Body must have at least one code block
    body = content[fm_match.end() :]
    if "```" not in body:
        warnings.append("No code blocks found — SKILL.md should include command examples")

    # Must have a Quick Reference or Commands section
    if not re.search(r"^#{1,3}\s+(Quick Reference|Commands|Usage)", body, re.MULTILINE):
        warnings.append("No 'Quick Reference' or 'Commands' section found")

    _report_validation(skill_file, errors, warnings, ctx)


def _report_validation(
    skill_file: "Path", errors: list, warnings: list, ctx: "click.Context"
) -> None:
    console.print(f"[bold]Validating:[/bold] {skill_file}")
    if not errors and not warnings:
        console.print("[green]OK SKILL.md is valid.[/green]")
        return
    for e in errors:
        console.print(f"  [red][ERROR][/red] {e}")
    for w in warnings:
        console.print(f"  [yellow][WARN][/yellow]  {w}")
    if errors:
        raise SystemExit(1)


@cli.command()
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish", "powershell"]),
    default=None,
    help="Shell to generate completions for (auto-detected if omitted).",
)
def completions(shell: str | None) -> None:
    """Print shell completion setup instructions or generate the completion script (F6).

    \b
    Bash:        source <(pbi completions --shell bash)
    Zsh:         pbi completions --shell zsh > ~/.zfunc/_pbi && autoload -U compinit && compinit
    Fish:        pbi completions --shell fish > ~/.config/fish/completions/pbi.fish
    PowerShell:  pbi completions --shell powershell | Out-String | Invoke-Expression
    """
    import os
    import subprocess

    detected = shell or _detect_shell()
    env_var = f"_{cli.name.upper().replace('-', '_')}_COMPLETE"  # type: ignore[union-attr]

    env = {**os.environ, env_var: f"{detected}_source"}
    try:
        result = subprocess.run(
            ["pbi"],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            click.echo(result.stdout, nl=False)
        else:
            _print_completion_instructions(detected)
    except Exception:
        _print_completion_instructions(detected)


def _detect_shell() -> str:
    import os

    shell_env = os.environ.get("SHELL", "")
    if "zsh" in shell_env:
        return "zsh"
    if "fish" in shell_env:
        return "fish"
    if os.name == "nt":
        return "powershell"
    return "bash"


def _print_completion_instructions(shell: str) -> None:
    instructions = {
        "bash": ('# Add to ~/.bashrc:\neval "$(_PBI_COMPLETE=bash_source pbi)"'),
        "zsh": ('# Add to ~/.zshrc:\neval "$(_PBI_COMPLETE=zsh_source pbi)"'),
        "fish": (
            "# Save to ~/.config/fish/completions/pbi.fish:\n_PBI_COMPLETE=fish_source pbi | source"
        ),
        "powershell": (
            "# Add to your PowerShell profile:\n"
            '$env:_PBI_COMPLETE = "powershell_source"; pbi | Out-String | Invoke-Expression'
        ),
    }
    console.print(instructions.get(shell, f"Shell '{shell}' not recognised."))


if __name__ == "__main__":
    cli()
