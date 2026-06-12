"""pbi skills — install, list, and uninstall Claude Code skill files."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console(legacy_windows=False)


def _parse_frontmatter(md_path: Path) -> dict[str, str]:
    """Extract YAML-like frontmatter key: value pairs from a SKILL.md."""
    text = md_path.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    in_front = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_front:
                in_front = True
                continue
            else:
                break
        if in_front and ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"')
    return result


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convert '4.0.0' → (4, 0, 0)."""
    return tuple(int(x) for x in re.split(r"[.\-]", v) if x.isdigit())

# Consolidated skill set: 24 narrow skills → 10 broad category-based skills.
# Every original topic area is preserved inside the consolidated skill files.
_BUNDLED_SKILLS: list[dict[str, Any]] = [
    {
        "name": "power-bi-modeling",
        "description": (
            "Star schema design, source profiling, partitions, incremental refresh, "
            "calendar generation, M queries, and locale settings"
        ),
    },
    {
        "name": "power-bi-dax",
        "description": (
            "DAX authoring, validation, Time Intelligence, YAML unit-test suites, "
            "filter context, design patterns, and measure audit"
        ),
    },
    {
        "name": "power-bi-performance",
        "description": (
            "Query tracing, benchmarking, VertiPaq Analyzer, "
            "storage vs formula engine diagnosis, and slow DAX investigation"
        ),
    },
    {
        "name": "power-bi-report-design",
        "description": (
            "Report pages, 32 visual types, bookmarks, drillthrough, auto-layout, "
            "conditional formatting, filter pane, and PBIR authoring"
        ),
    },
    {
        "name": "power-bi-design-system",
        "description": (
            "WCAG-compliant theme generation, brand colour enforcement, typography, "
            "and custom visual SDK (scaffold, build, package, import .pbiviz)"
        ),
    },
    {
        "name": "power-bi-governance",
        "description": (
            "Built-in rules + BPA runner, custom plugin authoring, auto-fix, "
            "CI gate (exit code 1), severity/category filtering, and naming conventions"
        ),
    },
    {
        "name": "power-bi-security-and-docs",
        "description": (
            "RLS role definition, DAX row-filter expressions, perspective management, "
            "role testing, data dictionary generation, audit logs, and lineage docs"
        ),
    },
    {
        "name": "power-bi-deployment",
        "description": (
            "TMDL snapshot/diff/restore, XMLA push to Premium/Fabric, "
            "multi-stage pipeline orchestration, and service principal / device-flow auth"
        ),
    },
    {
        "name": "power-bi-diagnostics",
        "description": (
            "pbi doctor interpretation, pythonnet/AMO resolution, platform detection, "
            "connection troubleshooting, error taxonomy, and fix playbook"
        ),
    },
    {
        "name": "power-bi-project-orchestrator",
        "description": (
            "Coordinates multi-skill workflows: model → DAX → governance → report → deploy. "
            "Knows which skill to invoke, handles handoffs, resolves conflicts"
        ),
    },
]


def _skills_source_dir() -> Path:
    """Return the bundled skills directory (ships with pbi-cli)."""
    return Path(__file__).parent.parent.parent.parent / "skills"


def _claude_skills_dir() -> Path:
    """Return the Claude Code global skills directory."""
    return Path.home() / ".claude" / "skills"


@click.group("skills")
def skills_cmd() -> None:
    """Manage Claude Code skill files for Power BI development."""


@skills_cmd.command("list")
@click.option("--installed", is_flag=True, help="Show only installed skills.")
def skills_list(installed: bool) -> None:
    """List all available (or installed) pbi-cli skills."""
    target_dir = _claude_skills_dir()
    table = Table(title="pbi-cli Skills")
    table.add_column("Name")
    table.add_column("Installed", justify="center")
    table.add_column("Description")
    for skill in _BUNDLED_SKILLS:
        is_installed = (target_dir / skill["name"]).exists()
        if installed and not is_installed:
            continue
        status = "[green]✓[/green]" if is_installed else "[dim]–[/dim]"
        table.add_row(skill["name"], status, skill["description"])
    console.print(table)
    if not installed:
        console.print("\n[dim]Install all with:[/dim] pbi skills install --all")


@skills_cmd.command("install")
@click.argument("skill_names", nargs=-1)
@click.option("--all", "install_all", is_flag=True, help="Install all bundled skills.")
@click.option(
    "--target",
    default=None,
    type=click.Path(),
    help="Override target directory (default: ~/.claude/skills/).",
)
def skills_install(skill_names: tuple[str, ...], install_all: bool, target: str | None) -> None:
    """Install one or more pbi-cli skills into the Claude Code skills directory.

    \b
    Examples:
      pbi skills install power-bi-dax power-bi-governance
      pbi skills install --all
    """
    target_dir = Path(target) if target else _claude_skills_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    source_dir = _skills_source_dir()

    names = [s["name"] for s in _BUNDLED_SKILLS] if install_all else list(skill_names)
    if not names:
        console.print("[yellow]Specify skill names or use --all.[/yellow]")
        console.print("Run 'pbi skills list' to see available skills.")
        return

    installed = 0
    for name in names:
        src = source_dir / name
        if not src.exists():
            console.print(f"  [yellow]Not found:[/yellow] {name}")
            continue
        dst = target_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        console.print(f"  [green]Installed:[/green] {name}  →  {dst}")
        installed += 1

    console.print(f"\n[green]{installed} skill(s) installed[/green] to {target_dir}")
    if installed:
        console.print("[dim]Restart Claude Code to pick up newly installed skills.[/dim]")


@skills_cmd.command("check")
def skills_check() -> None:
    """Validate that all bundled skills are compatible with the installed CLI version.

    \b
    Exit codes:
      0  — all skills compatible
      1  — one or more skills incompatible or missing version info
    """
    from pbi_cli import __version__

    source_dir = _skills_source_dir()
    cli_ver = _version_tuple(__version__)

    table = Table(title=f"Skill Compatibility Check  (CLI {__version__})")
    table.add_column("Skill")
    table.add_column("Skill Ver", justify="center")
    table.add_column("Requires ≥", justify="center")
    table.add_column("Status", justify="center")

    incompatible = 0
    for skill in _BUNDLED_SKILLS:
        md = source_dir / skill["name"] / "SKILL.md"
        if not md.exists():
            table.add_row(skill["name"], "?", "?", "[red]✗ missing[/red]")
            incompatible += 1
            continue
        fm = _parse_frontmatter(md)
        skill_ver = fm.get("version", "?")
        min_cli = fm.get("min_cli_version", "")
        if not min_cli:
            table.add_row(  # noqa: E501
                skill["name"], skill_ver, "[dim]not set[/dim]", "[yellow]⚠ no constraint[/yellow]"
            )
            continue
        try:
            req = _version_tuple(min_cli)
            if cli_ver >= req:
                table.add_row(skill["name"], skill_ver, min_cli, "[green]✓ compatible[/green]")
            else:
                table.add_row(skill["name"], skill_ver, min_cli, "[red]✗ needs CLI upgrade[/red]")
                incompatible += 1
        except Exception:
            table.add_row(skill["name"], skill_ver, min_cli, "[yellow]⚠ parse error[/yellow]")

    console.print(table)
    compatible = len(_BUNDLED_SKILLS) - incompatible
    console.print(
        f"\n[green]{compatible} compatible[/green], [red]{incompatible} incompatible[/red]"
    )
    if incompatible:
        raise SystemExit(1)


@skills_cmd.command("uninstall")
@click.argument("skill_names", nargs=-1)
@click.option("--all", "uninstall_all", is_flag=True, help="Uninstall all pbi-cli skills.")
@click.option("--target", default=None, type=click.Path(), help="Override target directory.")
def skills_uninstall(skill_names: tuple[str, ...], uninstall_all: bool, target: str | None) -> None:
    """Remove installed pbi-cli skills from the Claude Code skills directory."""
    target_dir = Path(target) if target else _claude_skills_dir()
    names = [s["name"] for s in _BUNDLED_SKILLS] if uninstall_all else list(skill_names)
    if not names:
        console.print("[yellow]Specify skill names or use --all.[/yellow]")
        return
    removed = 0
    for name in names:
        dst = target_dir / name
        if dst.exists():
            shutil.rmtree(dst)
            console.print(f"  [red]Removed:[/red] {name}")
            removed += 1
        else:
            console.print(f"  [dim]Not installed:[/dim] {name}")
    console.print(f"\n[green]{removed} skill(s) removed.[/green]")
