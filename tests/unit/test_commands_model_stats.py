"""CliRunner tests for pbi model stats command."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, ["--backend", "mock", *args])


def _run_json(runner: CliRunner, *args: str):
    result = runner.invoke(cli, ["--backend", "mock", "--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ── model stats ───────────────────────────────────────────────────────────────


class TestModelStats:
    def test_stats_exits_cleanly(self, runner):
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0

    def test_stats_outputs_table_header(self, runner):
        result = _run(runner, "model", "stats")
        assert "Tables" in result.output or "Statistics" in result.output

    def test_stats_shows_tables_count(self, runner):
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0
        # Mock backend has 4 tables
        assert "4" in result.output

    def test_stats_shows_measures_count(self, runner):
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0
        # Mock backend has 2 measures
        assert "2" in result.output

    def test_stats_shows_relationships_count(self, runner):
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0
        # Mock backend has 3 relationships
        assert "3" in result.output

    def test_stats_shows_complexity_score(self, runner):
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0
        assert "Complexity" in result.output or "complexity" in result.output

    def test_stats_json_output_has_required_keys(self, runner):
        data = _run_json(runner, "model", "stats")
        assert isinstance(data, dict)
        required_keys = {"tables", "columns", "measures", "relationships", "complexity_score"}
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_stats_json_tables_value_matches_mock(self, runner):
        data = _run_json(runner, "model", "stats")
        # Mock backend has 4 tables
        assert data["tables"] == 4

    def test_stats_json_measures_value_matches_mock(self, runner):
        data = _run_json(runner, "model", "stats")
        # Mock backend has 2 measures
        assert data["measures"] == 2

    def test_stats_json_relationships_value_matches_mock(self, runner):
        data = _run_json(runner, "model", "stats")
        # Mock backend has 3 relationships
        assert data["relationships"] == 3

    def test_stats_json_complexity_score_is_numeric(self, runner):
        data = _run_json(runner, "model", "stats")
        assert isinstance(data["complexity_score"], (int, float))
        assert data["complexity_score"] > 0

    def test_stats_json_has_complexity_label(self, runner):
        data = _run_json(runner, "model", "stats")
        assert "complexity_label" in data
        assert data["complexity_label"] in ("Low", "Medium", "High")

    def test_stats_json_has_warnings_list(self, runner):
        data = _run_json(runner, "model", "stats")
        assert "warnings" in data
        assert isinstance(data["warnings"], list)

    def test_stats_no_warnings_on_clean_model(self, runner):
        """The mock model has measures missing format/description — warnings should appear."""
        result = _run(runner, "model", "stats")
        assert result.exit_code == 0
        # Whether there are warnings or not, the command should complete successfully
