"""Integration tests for CLI commands that require a live .pbip project.

Uses the financials.pbip from Documents for read-only tests.
Write tests (scaffold, page-add, visual-add) operate on a tmp_path copy.
Skipped automatically when the file is not present.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli

_PBIP = r"C:\Users\GGPC\Documents\financials.pbip"
_REPORT_DIR = Path(r"C:\Users\GGPC\Documents\financials.Report")

pytestmark = pytest.mark.skipif(
    not Path(_PBIP).exists(),
    reason="financials.pbip not found — skipping PBIR CLI integration tests",
)


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def pbip_copy(tmp_path) -> str:
    """Return path to a writable copy of the financials.pbip project."""
    report_copy = tmp_path / "financials.Report"
    shutil.copytree(_REPORT_DIR, report_copy)
    pbip_copy = tmp_path / "financials.pbip"
    shutil.copy2(_PBIP, pbip_copy)
    return str(pbip_copy)


def _run(runner, *args):
    return runner.invoke(cli, list(args))


# ── report pages ──────────────────────────────────────────────────────────────


class TestReportPages:
    def test_lists_pages(self, runner):
        result = _run(runner, "report", "pages", "--pbip", _PBIP)
        assert result.exit_code == 0
        assert "Executive Summary" in result.output

    def test_json_output(self, runner):
        result = _run(runner, "--json", "report", "pages", "--pbip", _PBIP)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        names = [p["displayName"] for p in data]
        assert "Executive Summary" in names
        assert "Sales Analysis" in names

    def test_pages_in_fixture(self, runner):
        result = _run(runner, "--json", "report", "pages", "--pbip", _PBIP)
        data = json.loads(result.output)
        assert (
            len(data) >= 3
        )  # fixture has Executive Summary, Sales Analysis, Profit Analysis (+ any extras)


# ── report page-add / page-delete ─────────────────────────────────────────────


class TestReportPageWrite:
    def test_page_add_dry_run(self, runner):
        result = _run(
            runner, "--dry-run", "report", "page-add", "--pbip", _PBIP, "--name", "TestPage"
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_page_add_and_delete(self, runner, pbip_copy):
        add = _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "IntegTest")
        assert add.exit_code == 0
        assert "IntegTest" in add.output

        delete = _run(runner, "report", "page-delete", "--pbip", pbip_copy, "--name", "IntegTest")
        assert delete.exit_code == 0

    def test_page_delete_dry_run(self, runner):
        result = _run(
            runner,
            "--dry-run",
            "report",
            "page-delete",
            "--pbip",
            _PBIP,
            "--name",
            "Executive Summary",
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_clear_page_dry_run(self, runner):
        result = _run(
            runner,
            "--dry-run",
            "report",
            "clear-page",
            "--pbip",
            _PBIP,
            "--page",
            "Executive Summary",
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── report scaffold ───────────────────────────────────────────────────────────


class TestReportScaffold:
    def test_scaffold_dry_run(self, runner):
        result = _run(runner, "--dry-run", "report", "scaffold", "--pbip", _PBIP)
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_scaffold_one_page_on_copy(self, runner, pbip_copy):
        result = _run(
            runner, "report", "scaffold", "--pbip", pbip_copy, "--pages", "1", "--replace"
        )
        assert result.exit_code == 0
        assert "Executive Summary" in result.output

    def test_scaffold_three_pages_on_copy(self, runner, pbip_copy):
        result = _run(
            runner, "report", "scaffold", "--pbip", pbip_copy, "--pages", "3", "--replace"
        )
        assert result.exit_code == 0
        assert "Sales Analysis" in result.output
        assert "Profit Analysis" in result.output


# ── visual list ───────────────────────────────────────────────────────────────


class TestVisualList:
    def test_lists_visuals_on_page(self, runner):
        result = _run(runner, "visual", "list", "--pbip", _PBIP, "--page", "Executive Summary")
        assert result.exit_code == 0

    def test_json_output(self, runner):
        result = _run(
            runner, "--json", "visual", "list", "--pbip", _PBIP, "--page", "Executive Summary"
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_visuals_have_type_and_position(self, runner):
        result = _run(
            runner, "--json", "visual", "list", "--pbip", _PBIP, "--page", "Executive Summary"
        )
        data = json.loads(result.output)
        for v in data:
            assert "visualType" in v
            assert "x" in v
            assert "y" in v

    def test_unknown_page_returns_no_visuals(self, runner):
        result = _run(runner, "visual", "list", "--pbip", _PBIP, "--page", "NonExistentPageXYZ")
        assert result.exit_code == 0
        assert "No visuals" in result.output


# ── visual add ────────────────────────────────────────────────────────────────


class TestVisualAdd:
    def test_add_card_to_copy(self, runner, pbip_copy):
        # Add a new page then a card visual
        _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "VisualTestPage")
        result = _run(
            runner,
            "visual",
            "add",
            "--pbip",
            pbip_copy,
            "--page",
            "VisualTestPage",
            "--type",
            "card",
            "--table",
            "financials",
            "--value",
            "Sales",
        )
        assert result.exit_code == 0
        assert "Visual added" in result.output

    def test_add_bar_chart_to_copy(self, runner, pbip_copy):
        _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "BarTestPage")
        result = _run(
            runner,
            "visual",
            "add",
            "--pbip",
            pbip_copy,
            "--page",
            "BarTestPage",
            "--type",
            "bar",
            "--table",
            "financials",
            "--value",
            "Sales",
            "--category",
            "Segment",
        )
        assert result.exit_code == 0

    def test_add_slicer_to_copy(self, runner, pbip_copy):
        _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "SlicerTestPage")
        result = _run(
            runner,
            "visual",
            "add",
            "--pbip",
            pbip_copy,
            "--page",
            "SlicerTestPage",
            "--type",
            "slicer",
            "--table",
            "financials",
            "--value",
            "Year",
        )
        assert result.exit_code == 0

    def test_add_table_visual_to_copy(self, runner, pbip_copy):
        _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "TableTestPage")
        result = _run(
            runner,
            "visual",
            "add",
            "--pbip",
            pbip_copy,
            "--page",
            "TableTestPage",
            "--type",
            "table",
            "--table",
            "financials",
            "--value",
            "Sales",
            "--extra-columns",
            "Profit,Segment",
        )
        assert result.exit_code == 0


# ── layout auto ───────────────────────────────────────────────────────────────


class TestLayoutAuto:
    def test_layout_auto_dry_run(self, runner):
        result = _run(
            runner, "--dry-run", "layout", "auto", "--pbip", _PBIP, "--page", "Executive Summary"
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_layout_auto_on_copy(self, runner, pbip_copy):
        result = _run(runner, "layout", "auto", "--pbip", pbip_copy, "--page", "Executive Summary")
        assert result.exit_code == 0
        assert "Repositioned" in result.output or "visuals" in result.output.lower()

    def test_layout_auto_no_visuals_page(self, runner, pbip_copy):
        _run(runner, "report", "page-add", "--pbip", pbip_copy, "--name", "EmptyPage")
        result = _run(runner, "layout", "auto", "--pbip", pbip_copy, "--page", "EmptyPage")
        assert result.exit_code == 0
        assert "No visuals" in result.output
