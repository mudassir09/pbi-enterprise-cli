"""pbi skills — install, list, and uninstall Claude Code skill files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console()

# Canonical skills bundled with pbi-cli
_BUNDLED_SKILLS: list[dict[str, Any]] = [
    {"name": "power-bi-dax", "description": "DAX query, validate, and unit-test workflows"},
    {
        "name": "power-bi-modeling",
        "description": "Semantic model management: tables, columns, relationships",
    },
    {
        "name": "power-bi-governance",
        "description": "Governance rules, auto-fix, and custom plugin authoring",
    },
    {"name": "power-bi-report", "description": "Report page and scaffold management"},
    {"name": "power-bi-visuals", "description": "Visual add, list, and conditional formatting"},
    {
        "name": "power-bi-sources",
        "description": "Data source profiling and star-schema scaffolding",
    },
    {"name": "power-bi-security", "description": "RLS role management and row-filter testing"},
    {"name": "power-bi-partitions", "description": "Partition management and incremental refresh"},
    {"name": "power-bi-deployment", "description": "Deploy and promote models via XMLA"},
    {"name": "power-bi-deployment-pipeline", "description": "CI/CD pipeline integration patterns"},
    {"name": "power-bi-themes", "description": "WCAG-compliant theme generation"},
    {"name": "power-bi-layout", "description": "Shelf-packing auto-layout and templates"},
    {
        "name": "power-bi-performance",
        "description": "Query tracing, benchmarking, and model health",
    },
    {"name": "power-bi-docs", "description": "Data dictionary and documentation generation"},
    {
        "name": "power-bi-diagnostics",
        "description": "Doctor, environment checks, and troubleshooting",
    },
    {"name": "power-bi-filters", "description": "Report filter management"},
    {
        "name": "power-bi-custom-visuals",
        "description": "Custom visual SDK — scaffold, build, package, import",
    },
    {"name": "power-bi-patterns", "description": "DAX and model design patterns"},
    {"name": "power-bi-troubleshooter", "description": "Guided troubleshooting workflows"},
    {"name": "power-bi-testing", "description": "DAX unit-test suite authoring and CI integration"},
    {"name": "power-bi-pages", "description": "Page type management (drillthrough, tooltip)"},
    {"name": "power-bi-page-designer", "description": "Page layout and visual arrangement"},
    {
        "name": "power-bi-design-system",
        "description": "Colour palette, typography, and brand consistency",
    },
    {
        "name": "power-bi-project-orchestrator",
        "description": "End-to-end project orchestration workflows",
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
