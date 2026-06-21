"""Tests for `pbi lakehouse` commands."""

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


class TestLakehouseList:
    def test_lists(self, runner):
        items = [{"id": "lh1", "displayName": "Bronze", "description": "raw"}]
        with _mock_token(), patch("pbi_cli.fabric_api.get_paged", return_value=items):
            result = _run(runner, "lakehouse", "list", "--workspace", "ws")
        assert result.exit_code == 0
        assert "Bronze" in result.output

    def test_empty(self, runner):
        with _mock_token(), patch("pbi_cli.fabric_api.get_paged", return_value=[]):
            result = _run(runner, "lakehouse", "list", "--workspace", "ws")
        assert result.exit_code == 0
        assert "No lakehouses" in result.output


class TestLakehouseTables:
    def test_lists_tables_uses_data_key(self, runner):
        tables = [{"name": "Sales", "type": "Managed", "format": "delta",
                   "location": "abfss://..."}]
        with _mock_token(), patch(
            "pbi_cli.fabric_api.get_paged", return_value=tables
        ) as mock_paged:
            result = _run(runner, "--json", "lakehouse", "tables",
                          "--workspace", "ws", "--lakehouse", "lh1")
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["name"] == "Sales"
        # Lakehouse tables endpoint pages under "data", not "value"
        assert mock_paged.call_args.kwargs.get("value_key") == "data"

    def test_empty_tables(self, runner):
        with _mock_token(), patch("pbi_cli.fabric_api.get_paged", return_value=[]):
            result = _run(runner, "lakehouse", "tables",
                          "--workspace", "ws", "--lakehouse", "lh1")
        assert result.exit_code == 0
        assert "No tables" in result.output


class TestLakehouseLoad:
    def test_load_waits_and_posts_payload(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.post", return_value={"status": 202, "headers": {}}
        ) as mock_post, patch(
            "pbi_cli.fabric_api.poll_lro", return_value={"status": "Succeeded"}
        ):
            result = _run(runner, "lakehouse", "load", "--workspace", "ws",
                          "--lakehouse", "lh1", "--table", "Sales",
                          "--path", "Files/sales.csv")
        assert result.exit_code == 0
        assert "completed" in result.output.lower()
        payload = mock_post.call_args.kwargs["payload"]
        assert payload["relativePath"] == "Files/sales.csv"
        assert payload["formatOptions"]["format"] == "Csv"

    def test_parquet_format_options(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.post", return_value={}
        ) as mock_post, patch("pbi_cli.fabric_api.poll_lro", return_value={}):
            _run(runner, "lakehouse", "load", "--workspace", "ws", "--lakehouse", "lh1",
                 "--table", "T", "--path", "Files/p", "--format", "Parquet",
                 "--path-type", "Folder", "--recursive")
        payload = mock_post.call_args.kwargs["payload"]
        assert payload["formatOptions"] == {"format": "Parquet"}
        assert payload["recursive"] is True

    def test_dry_run(self, runner):
        with patch("pbi_cli.fabric_api.post") as mock_post:
            result = _run(runner, "--dry-run", "lakehouse", "load", "--workspace", "ws",
                          "--lakehouse", "lh1", "--table", "T", "--path", "Files/x.csv")
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        mock_post.assert_not_called()


class TestLakehouseMaintenance:
    def test_optimize_and_vacuum_execution_data(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.run_item_job", return_value={"status": "Completed"}
        ) as mock_job:
            result = _run(runner, "lakehouse", "maintenance", "--workspace", "ws",
                          "--lakehouse", "lh1", "--table", "Sales",
                          "--z-order", "Date,Region", "--vacuum")
        assert result.exit_code == 0
        exec_data = mock_job.call_args.kwargs["execution_data"]
        assert exec_data["tableName"] == "Sales"
        assert exec_data["optimizeSettings"]["zOrderBy"] == ["Date", "Region"]
        assert "vacuumSettings" in exec_data

    def test_nothing_to_do_errors(self, runner):
        result = _run(runner, "lakehouse", "maintenance", "--workspace", "ws",
                      "--lakehouse", "lh1", "--table", "Sales", "--no-optimize")
        assert result.exit_code != 0
        assert "Nothing to do" in result.output
