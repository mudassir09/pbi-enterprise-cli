"""pbi init / pbi diff — project scaffolding and semantic model diff."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import output_json_or_table

console = Console(legacy_windows=False)

_WORKFLOW = """\
name: Power BI Governance

on: [push, pull_request]

permissions:
  contents: read
  pull-requests: write
  security-events: write

jobs:
  govern:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli

      - name: Governance rules (live TMDL from this repo)
        run: pbi --backend file --path . govern check --fail-on error --sarif governance.sarif

      - name: BPA check
        run: pbi --backend file --path . govern bpa check --severity error

      - name: DAX lint
        run: pbi --backend file --path . dax lint --fail-on error

      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: governance.sarif
"""

_CONFIG_TOML = """\
# pbi-enterprise-cli project defaults (overridden by CLI flags)
[defaults]
backend = "file"        # desktop | xmla | mock | file | rest
fail_on = "error"

[governance]
# rule ids to skip in this project
exclude = []
"""

_DATA_SUITE = """\
# pbi test data --suite tests/data/
tests:
  - {table: Sales, row_count: {min: 1}}
  # - {type: not_null, table: Sales, column: Revenue}
  # - {type: unique, table: Customers, column: CustomerKey}
  # - {type: relationship, table: Sales, column: ProductKey,
  #    to_table: Products, to_column: ProductKey}
"""

_MEASURE_SUITE = """\
# pbi dax test --suite tests/measures/
suite: "Measure assertions"
tests:
  - name: "Example: at least one measure exists"
    assert_min_count: 1
"""

_CONTRACT = """\
# pbi test schema --contract tests/contracts/schema.yaml
tables: {}
#  Sales:
#    columns:
#      Revenue: {dataType: decimal}
#    measures: ["Total Revenue"]
"""

_PRECOMMIT = """\
repos:
  - repo: https://github.com/mudassir09/pbi-enterprise-cli
    rev: v1.0.2
    hooks:
      - id: pbi-govern
      - id: pbi-dax-lint
"""


@click.command("init")
@click.option("--force", is_flag=True, help="Overwrite files that already exist.")
@click.pass_context
def init_cmd(ctx: click.Context, force: bool) -> None:
    """Scaffold a Power BI project: tests, governance gate, CI workflow, config.

    Creates pbi.config.toml, tests/measures + tests/data + tests/contracts suites,
    a GitHub Actions governance workflow, and a pre-commit config. Safe to run in
    an existing repo — nothing is overwritten without --force.
    """
    files = {
        "pbi.config.toml": _CONFIG_TOML,
        "tests/measures/measures_suite.yaml": _MEASURE_SUITE,
        "tests/data/data_suite.yaml": _DATA_SUITE,
        "tests/contracts/schema.yaml": _CONTRACT,
        ".github/workflows/pbi-govern.yml": _WORKFLOW,
        ".pre-commit-config.yaml": _PRECOMMIT,
    }
    created, skipped = [], []
    for rel, content in files.items():
        target = Path(rel)
        if target.exists() and not force:
            skipped.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(rel)

    for rel in created:
        console.print(f"  [green]created[/green]  {rel}")
    for rel in skipped:
        console.print(f"  [yellow]exists[/yellow]   {rel} (use --force to overwrite)")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  pbi --backend file --path . govern check     — run governance on this repo")
    console.print("  pbi --backend file --path . dax lint         — lint the DAX")
    console.print("  git add . && git commit                      — the CI gate is ready")


def _state_from_path(path: str) -> dict:
    from pbi_cli.backends.file_backend import FileBackend
    from pbi_cli.model_diff import snapshot_state

    b = FileBackend(path=path)
    b.connect()
    return snapshot_state(b)


def _state_from_git_ref(ref: str, path: str) -> dict:
    """Materialize a git ref in a temp worktree and snapshot its TMDL state."""
    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        worktree = str(Path(tmp) / "ref")
        subprocess.run(
            ["git", "worktree", "add", "--detach", worktree, ref],
            capture_output=True, text=True, check=True, cwd=repo_root,
        )
        try:
            rel = Path(path).resolve().relative_to(Path(repo_root).resolve())
            return _state_from_path(str(Path(worktree) / rel))
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", worktree],
                           capture_output=True, cwd=repo_root)


@click.command("diff")
@click.argument("old_ref")
@click.argument("new_ref", default=".")
@click.option("--git", "use_git", is_flag=True,
              help="Treat OLD_REF as a git ref (branch/tag/commit) instead of a path.")
@click.option("--release-notes", "notes_path", type=click.Path(), default=None,
              help="Also write the diff as markdown release notes.")
@click.pass_context
def diff_cmd(ctx: click.Context, old_ref: str, new_ref: str, use_git: bool,
             notes_path: str | None) -> None:
    """Semantic TMDL diff: measures/columns/tables/relationships, not raw text.

    \b
    Examples:
      pbi diff ./snapshots/v1 .          — two TMDL folders
      pbi diff main . --git              — git branch vs working tree
    """
    from pbi_cli.model_diff import semantic_diff, to_release_notes

    old_state = _state_from_git_ref(old_ref, new_ref) if use_git else _state_from_path(old_ref)
    new_state = _state_from_path(new_ref)
    result = semantic_diff(old_state, new_state)

    if notes_path:
        Path(notes_path).write_text(to_release_notes(result), encoding="utf-8")
        console.print(f"[green]Release notes written:[/green] {notes_path}")

    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table(result, ctx)
        return
    if not result["has_changes"]:
        console.print("[green]No model changes.[/green]")
        return
    output_json_or_table(result["changes"], ctx, title="Model Changes")
    console.print(f"\n[bold]{len(result['changes'])} change(s)[/bold]")
