"""CliRunner tests for pbi visual commands (mock/dry-run paths)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


# ── visual recommend ──────────────────────────────────────────────────────────

class TestVisualRecommend:
    def test_returns_recommendations(self, runner):
        result = _run(runner, "visual", "recommend", "--measures", "Total Revenue")
        assert result.exit_code == 0

    def test_json_returns_list(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--json",
            "visual", "recommend", "--measures", "Total Revenue,YTD Revenue",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_recommendations_have_visual_and_rationale(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--json",
            "visual", "recommend", "--measures", "Total Revenue",
        ])
        data = json.loads(result.output)
        for item in data:
            assert "visual" in item
            assert "rationale" in item

    def test_multiple_measures(self, runner):
        result = _run(runner, "visual", "recommend",
                      "--measures", "Revenue,Units,Profit,Margin")
        assert result.exit_code == 0


# ── visual add (dry-run, no PBIR needed) ──────────────────────────────────────

class TestVisualAdd:
    def test_card_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "visual", "add",
            "--pbip", "fake.pbip",
            "--page", "Summary",
            "--type", "card",
            "--table", "Sales",
            "--value", "Revenue",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_bar_requires_category(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock",
            "visual", "add",
            "--pbip", "fake.pbip",
            "--page", "Summary",
            "--type", "bar",
            "--table", "Sales",
            "--value", "Revenue",
            # Missing --category
        ])
        # Should show error about missing category
        assert result.exit_code != 0 or "category" in result.output.lower()

    def test_slicer_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "visual", "add",
            "--pbip", "fake.pbip",
            "--page", "Summary",
            "--type", "slicer",
            "--table", "Calendar",
            "--value", "Year",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── visual delete (dry-run) ───────────────────────────────────────────────────

class TestVisualDelete:
    def test_delete_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "visual", "delete",
            "--pbip", "fake.pbip",
            "--page", "Summary",
            "--name", "Visual1",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── visual screenshot (Playwright not installed) ──────────────────────────────

class TestVisualScreenshot:
    def test_screenshot_fails_gracefully_without_playwright(self, runner, monkeypatch):
        import sys
        # Remove playwright from sys.modules so import fails
        for key in list(sys.modules.keys()):
            if "playwright" in key:
                monkeypatch.delitem(sys.modules, key)

        # Block playwright import by inserting a broken module entry
        monkeypatch.setitem(sys.modules, "playwright", None)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

        result = runner.invoke(cli, [
            "--backend", "mock",
            "visual", "screenshot",
            "--pbip", "fake.pbip",
            "--page", "Summary",
        ])
        # Should fail with ClickException about playwright not installed
        assert result.exit_code != 0 or "playwright" in result.output.lower()
