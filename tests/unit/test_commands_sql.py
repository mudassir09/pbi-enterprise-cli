"""Tests for the `pbi sql query` command wiring."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


def _mock_token():
    return patch("pbi_cli.fabric_api.get_token", return_value="fake-token")


class TestSqlQuery:
    def test_direct_server_returns_rows(self, runner):
        rows = [{"n": 1, "name": "Acme"}, {"n": 2, "name": "Globex"}]
        with _mock_token(), patch(
            "pbi_cli.sql_endpoint.run_query", return_value=rows
        ) as mock_run:
            result = _run(runner, "sql", "query", "--server", "srv.fabric.com",
                          "--database", "WH", "SELECT * FROM Customers")
        assert result.exit_code == 0
        assert "Acme" in result.output and "Globex" in result.output
        mock_run.assert_called_once()

    def test_json_output(self, runner):
        rows = [{"n": 1}]
        with _mock_token(), patch("pbi_cli.sql_endpoint.run_query", return_value=rows):
            result = _run(runner, "--json", "sql", "query", "--server", "s",
                          "--database", "d", "SELECT 1 AS n")
        assert result.exit_code == 0
        assert json.loads(result.output) == rows

    def test_discovery_by_workspace_and_item(self, runner):
        with _mock_token(), patch(
            "pbi_cli.sql_endpoint.resolve_endpoint",
            return_value=("srv.fabric.com", "Bronze"),
        ) as mock_resolve, patch(
            "pbi_cli.sql_endpoint.run_query", return_value=[{"c": 5}]
        ) as mock_run:
            result = _run(runner, "sql", "query", "--workspace", "ws", "--item", "lh",
                          "SELECT COUNT(*) AS c FROM t")
        assert result.exit_code == 0
        mock_resolve.assert_called_once()
        # database defaulted to the discovered item name
        assert mock_run.call_args[0][1] == "Bronze"

    def test_no_rows_message(self, runner):
        with _mock_token(), patch("pbi_cli.sql_endpoint.run_query", return_value=[]):
            result = _run(runner, "sql", "query", "--server", "s", "--database", "d",
                          "CREATE TABLE x (a int)")
        assert result.exit_code == 0
        assert "no rows returned" in result.output.lower()

    def test_requires_server_or_discovery_args(self, runner):
        result = _run(runner, "sql", "query", "SELECT 1")
        assert result.exit_code != 0
        assert "Provide --server" in result.output

    def test_empty_query_rejected(self, runner):
        result = _run(runner, "sql", "query", "--server", "s", "--database", "d", "   ")
        assert result.exit_code != 0
        assert "Provide a QUERY" in result.output

    def test_file_option_reads_sql(self, runner, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT 99 AS answer", encoding="utf-8")
        with _mock_token(), patch(
            "pbi_cli.sql_endpoint.run_query", return_value=[{"answer": 99}]
        ) as mock_run:
            result = _run(runner, "sql", "query", "--server", "s", "--database", "d",
                          "--file", str(sql_file))
        assert result.exit_code == 0
        assert "99" in result.output
        assert "SELECT 99" in mock_run.call_args[0][2]

    def test_dry_run_skips_execution(self, runner):
        with patch("pbi_cli.sql_endpoint.run_query") as mock_run:
            result = _run(runner, "--dry-run", "sql", "query", "--server", "s",
                          "--database", "d", "DELETE FROM t")
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        mock_run.assert_not_called()

    def test_endpoint_error_is_clean(self, runner):
        from pbi_cli.sql_endpoint import SqlEndpointError

        with _mock_token(), patch(
            "pbi_cli.sql_endpoint.resolve_endpoint",
            side_effect=SqlEndpointError("Item 'X' (Report) exposes no SQL connection string."),
        ):
            result = _run(runner, "sql", "query", "--workspace", "ws", "--item", "rp",
                          "SELECT 1")
        assert result.exit_code != 0
        assert "no SQL connection" in result.output
