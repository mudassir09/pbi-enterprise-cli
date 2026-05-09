"""Unit tests for pbi partition commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestPartitionList:
    def test_list_empty(self, runner):
        """Fresh mock backend has no partitions."""
        result = _run(runner, "partition", "list")
        assert result.exit_code == 0
        assert "No partitions" in result.output

    def test_list_with_table_filter(self, runner):
        """--table option filters by table name without errors."""
        result = _run(runner, "partition", "list", "--table", "Sales")
        assert result.exit_code == 0
        assert "No partitions" in result.output

    def test_list_json_flag(self, runner):
        """--json flag is accepted; with no partitions the command exits cleanly."""
        result = runner.invoke(cli, ["--backend", "mock", "--json", "partition", "list"])
        assert result.exit_code == 0
        # Mock has no partitions — command prints "No partitions found." and returns early
        assert "No partitions" in result.output


class TestPartitionAdd:
    def test_add_success(self, runner):
        result = _run(runner, "partition", "add",
                      "--table", "Sales",
                      "--name", "P1",
                      "--query", "SELECT * FROM Sales")
        assert result.exit_code == 0
        assert "P1" in result.output

    def test_add_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "partition", "add",
            "--table", "Sales",
            "--name", "P1",
            "--query", "SELECT * FROM Sales",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_add_missing_table(self, runner):
        result = _run(runner, "partition", "add",
                      "--name", "P1",
                      "--query", "SELECT * FROM Sales")
        assert result.exit_code != 0

    def test_add_missing_name(self, runner):
        result = _run(runner, "partition", "add",
                      "--table", "Sales",
                      "--query", "SELECT * FROM Sales")
        assert result.exit_code != 0


class TestPartitionDelete:
    def test_delete_success(self, runner):
        result = _run(runner, "partition", "delete",
                      "--table", "Sales",
                      "--name", "P1")
        assert result.exit_code == 0
        assert "P1" in result.output

    def test_delete_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "partition", "delete",
            "--table", "Sales",
            "--name", "P1",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_delete_missing_name(self, runner):
        result = _run(runner, "partition", "delete", "--table", "Sales")
        assert result.exit_code != 0


class TestPartitionRefresh:
    def test_refresh_success(self, runner):
        result = _run(runner, "partition", "refresh",
                      "--table", "Sales",
                      "--name", "P1")
        assert result.exit_code == 0
        assert "P1" in result.output

    def test_refresh_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "partition", "refresh",
            "--table", "Sales",
            "--name", "P1",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_refresh_missing_table(self, runner):
        result = _run(runner, "partition", "refresh", "--name", "P1")
        assert result.exit_code != 0
