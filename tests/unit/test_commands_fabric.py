"""Tests for pbi fabric command group."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


def _mock_token():
    return patch("pbi_cli.commands.fabric_cmd._get_token", return_value="fake-token")


class TestFabricWorkspaces:
    def test_workspaces_lists_results(self, runner):
        payload = {
            "value": [
                {"id": "ws-001", "name": "Sales Workspace", "type": "Workspace", "state": "Active"},
                {"id": "ws-002", "name": "Finance Workspace", "type": "Workspace", "state": "Active"},
            ]
        }
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "workspaces")
        assert result.exit_code == 0
        assert "Sales Workspace" in result.output
        assert "Finance Workspace" in result.output

    def test_workspaces_json_output(self, runner):
        payload = {"value": [{"id": "ws-001", "name": "Sales", "type": "Workspace", "state": "Active"}]}
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "workspaces", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "Sales"

    def test_workspaces_filter(self, runner):
        payload = {
            "value": [
                {"id": "ws-001", "name": "Sales Workspace", "type": "Workspace", "state": "Active"},
                {"id": "ws-002", "name": "HR Workspace", "type": "Workspace", "state": "Active"},
            ]
        }
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "workspaces", "--filter", "Sales")
        assert result.exit_code == 0
        assert "Sales" in result.output
        assert "HR" not in result.output

    def test_workspaces_empty(self, runner):
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value={"value": []}
        ):
            result = _run(runner, "fabric", "workspaces")
        assert result.exit_code == 0
        assert "No workspaces" in result.output


class TestFabricCapacities:
    def test_capacities_lists_results(self, runner):
        payload = {
            "value": [
                {"id": "cap-01", "displayName": "P1 Capacity", "sku": "P1",
                 "state": "Active", "region": "UK South"},
            ]
        }
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "capacities")
        assert result.exit_code == 0
        assert "P1 Capacity" in result.output
        assert "UK South" in result.output

    def test_capacities_json_output(self, runner):
        payload = {"value": [{"id": "cap-01", "displayName": "F64", "sku": "F64",
                               "state": "Active", "region": "East US"}]}
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "capacities", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["sku"] == "F64"

    def test_capacities_empty(self, runner):
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value={"value": []}
        ):
            result = _run(runner, "fabric", "capacities")
        assert result.exit_code == 0
        assert "No capacities" in result.output


class TestFabricDatasets:
    def test_datasets_lists_results(self, runner):
        payload = {
            "value": [
                {"id": "ds-001", "name": "Sales Model", "configuredBy": "admin@co.com",
                 "isRefreshable": True},
            ]
        }
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "datasets", "ws-001")
        assert result.exit_code == 0
        assert "Sales Model" in result.output

    def test_datasets_json_output(self, runner):
        payload = {"value": [{"id": "ds-001", "name": "Model", "configuredBy": "a@b.com",
                               "isRefreshable": False}]}
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "datasets", "ws-001", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "Model"

    def test_datasets_filter(self, runner):
        payload = {
            "value": [
                {"id": "ds-001", "name": "Sales Model", "configuredBy": "a", "isRefreshable": True},
                {"id": "ds-002", "name": "HR Model", "configuredBy": "a", "isRefreshable": True},
            ]
        }
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_get", return_value=payload
        ):
            result = _run(runner, "fabric", "datasets", "ws-001", "--filter", "Sales")
        assert result.exit_code == 0
        assert "Sales" in result.output
        assert "HR" not in result.output


class TestFabricRefresh:
    def test_refresh_dry_run(self, runner):
        result = _run(runner, "fabric", "refresh", "ws-001", "ds-001", "--dry-run")
        assert result.exit_code == 0
        assert "Would" in result.output or "dry" in result.output.lower()

    def test_refresh_triggers_api(self, runner):
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_post", return_value={}
        ) as mock_post:
            result = _run(runner, "fabric", "refresh", "ws-001", "ds-001")
        assert result.exit_code == 0
        assert "triggered" in result.output.lower()
        mock_post.assert_called_once()

    def test_refresh_type_option(self, runner):
        with _mock_token(), patch(
            "pbi_cli.commands.fabric_cmd._api_post", return_value={}
        ) as mock_post:
            _run(runner, "fabric", "refresh", "ws-001", "ds-001", "--type", "calculate")
        call_payload = mock_post.call_args[0][2]
        assert call_payload["type"] == "calculate"
