"""Main CLI entry point for pbi-cli."""

from pathlib import Path

import click
from rich.console import Console

from pbi_cli import __version__
from pbi_cli.commands import (
    calendar_cmd,
    connections,
    custom_visual,
    database,
    dax,
    deploy,
    docs,
    filter_cmd,
    govern,
    layout,
    measure,
    model,
    partition,
    repl,
    report,
    security,
    server_cmd,
    skills_cmd,
    source,
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
    "--backend",
    type=click.Choice(["desktop", "xmla", "mock"]),
    default="desktop",
    show_default=True,
    help="Backend to use for Power BI connection.",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Override the local Analysis Services port (desktop backend).",
)
@click.pass_context
def cli(ctx: click.Context, output_json: bool, backend: str, port: int | None) -> None:
    """pbi — Power BI one-stop-shop CLI for AI-driven development.

    Connect, model, visualize, govern, test, and deploy Power BI solutions
    from the command line. Designed for use with Claude Code.
    """
    ctx.ensure_object(dict)
    ctx.obj.setdefault("dry_run", False)
    ctx.obj["output_json"] = output_json
    ctx.obj["backend"] = backend
    if port:
        ctx.obj["port"] = port


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
cli.add_command(calendar_cmd.calendar_cmd)
cli.add_command(calendar_cmd.culture_cmd)
cli.add_command(repl.repl)
cli.add_command(custom_visual.custom_visual)


@cli.command()
@click.option("--port", type=int, default=None, help="Explicit port (auto-detected if omitted).")
@click.pass_context
def connect(ctx: click.Context, port: int | None) -> None:
    """Connect to the running Power BI Desktop instance and show model info."""
    from pbi_cli.backends.tom_backend import TomBackend, find_pbi_port

    detected = port or find_pbi_port()
    if not detected:
        console.print("[red]No running Power BI Desktop found.[/red]")
        console.print("Open a PBIX file in Power BI Desktop and try again.")
        raise SystemExit(1)
    console.print(f"[cyan]Connecting to localhost:{detected}...[/cyan]")
    b = TomBackend()
    b.connect(port=detected)
    info = b.model_info()
    console.print(
        f"[green]Connected![/green] Model: [bold]{info['name']}[/bold]  (CompatibilityLevel {info['compatibilityLevel']})"  # noqa: E501
    )
    tables = b.table_list()
    console.print(f"Tables: {', '.join(t['name'] for t in tables)}")
    b.disconnect()


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
