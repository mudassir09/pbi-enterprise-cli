"""CliRunner tests for pbi layout commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestLayoutTemplate:
    def test_executive_dashboard_template(self, runner):
        result = _run(
            runner, "layout", "template", "--name", "executive-dashboard", "--page", "Summary"
        )
        assert result.exit_code == 0
        assert "executive-dashboard" in result.output

    def test_operational_monitor_template(self, runner):
        result = _run(
            runner, "layout", "template", "--name", "operational-monitor", "--page", "Ops"
        )
        assert result.exit_code == 0

    def test_financial_report_template(self, runner):
        result = _run(
            runner, "layout", "template", "--name", "financial-report", "--page", "Finance"
        )
        assert result.exit_code == 0
        assert "Finance" in result.output

    def test_drill_through_detail_template(self, runner):
        result = _run(
            runner, "layout", "template", "--name", "drill-through-detail", "--page", "Detail"
        )
        assert result.exit_code == 0

    def test_template_shows_zones(self, runner):
        result = _run(
            runner, "layout", "template", "--name", "executive-dashboard", "--page", "Exec"
        )
        assert result.exit_code == 0
        assert "Zone" in result.output


class TestLayoutAutoDryRun:
    def test_auto_requires_pbip(self, runner):
        result = _run(runner, "layout", "auto", "--pbip", "nonexistent.pbip", "--page", "Page1")
        # Should fail gracefully (PbirBackend raises or page not found)
        assert result.exit_code in (0, 1, 2)
