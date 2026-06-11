"""Tests for SARIF/markdown exporters, govern scan, and tenant commands."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.governance.exporters import to_markdown, to_sarif

VIOLATIONS = [
    {"rule": "measure-description-required", "severity": "warning",
     "object": "Measure 'Total Revenue'", "message": "Missing description",
     "autoFixable": True},
    {"rule": "table-pascal-case", "severity": "error",
     "object": "Table 'sales'", "message": "Not PascalCase"},
]


@pytest.fixture()
def runner():
    return CliRunner()


class TestSarif:
    def test_structure(self):
        sarif = to_sarif(VIOLATIONS)
        assert sarif["version"] == "2.1.0"
        run = sarif["runs"][0]
        assert run["tool"]["driver"]["name"] == "pbi-enterprise-cli"
        assert len(run["results"]) == 2
        assert {r["ruleId"] for r in run["results"]} == {
            "measure-description-required", "table-pascal-case"}

    def test_severity_mapping(self):
        results = to_sarif(VIOLATIONS)["runs"][0]["results"]
        levels = {r["ruleId"]: r["level"] for r in results}
        assert levels["table-pascal-case"] == "error"
        assert levels["measure-description-required"] == "warning"

    def test_empty_violations(self):
        sarif = to_sarif([])
        assert sarif["runs"][0]["results"] == []


class TestMarkdown:
    def test_pass_summary(self):
        md = to_markdown([])
        assert "All governance checks pass" in md

    def test_violation_table(self):
        md = to_markdown(VIOLATIONS)
        assert "1 errors" in md
        assert "table-pascal-case" in md
        assert "govern fix --auto" in md


class TestGovernCheckOutputs:
    def test_sarif_file_written(self, runner, tmp_path):
        out = tmp_path / "gov.sarif"
        result = runner.invoke(
            cli, ["--backend", "mock", "govern", "check", "--sarif", str(out),
                  "--fail-on", "error"],
        )
        assert result.exit_code in (0, 3)
        sarif = json.loads(out.read_text(encoding="utf-8"))
        assert sarif["version"] == "2.1.0"

    def test_markdown_file_written(self, runner, tmp_path):
        out = tmp_path / "gov.md"
        result = runner.invoke(
            cli, ["--backend", "mock", "govern", "check", "--markdown", str(out),
                  "--fail-on", "error"],
        )
        assert result.exit_code in (0, 3)
        assert out.read_text(encoding="utf-8").startswith("## Power BI Governance")


class TestGovernScan:
    def test_scan_aggregates_violations(self, runner):
        scan_result = {
            "workspaces": [{
                "id": "ws-1", "name": "Sales WS",
                "datasets": [{
                    "id": "ds-1", "name": "SalesModel",
                    "tables": [{
                        "name": "sales",
                        "columns": [{"name": "Revenue", "dataType": "Decimal"}],
                        "measures": [{"name": "Total", "expression": "SUM(sales[Revenue])"}],
                    }],
                }],
            }]
        }

        def fake_get(url, token, **kw):
            if "scanStatus" in url:
                return {"status": "Succeeded"}
            if "scanResult" in url:
                return scan_result
            raise AssertionError(url)

        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.post", return_value={"id": "scan-1"}), \
             patch("pbi_cli.fabric_api.get", side_effect=fake_get):
            result = runner.invoke(
                cli, ["--json", "govern", "scan", "--workspace", "ws-1",
                      "--fail-on", "error"],
            )
        assert result.exit_code in (0, 3), result.output
        data = json.loads(result.output)
        assert data["summary"]["datasets"] == 1
        assert any(v["dataset"] == "SalesModel" for v in data["violations"])


class TestTenant:
    def test_usage_summary(self, runner):
        events = {"activityEventEntities": [
            {"Activity": "ViewReport", "UserId": "a@x.com", "ReportName": "Sales"},
            {"Activity": "ViewReport", "UserId": "b@x.com", "ReportName": "Sales"},
        ]}
        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.get", return_value=events):
            result = runner.invoke(cli, ["--json", "tenant", "usage", "--days", "1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["total_events"] == 2
        assert data["top_artifacts"][0]["name"] == "Sales"

    def test_access_report_single_workspace(self, runner):
        users = {"value": [
            {"emailAddress": "a@x.com", "groupUserAccessRight": "Admin",
             "principalType": "User"},
        ]}
        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.get", return_value=users):
            result = runner.invoke(
                cli, ["--json", "tenant", "access", "--workspace", "ws-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["role"] == "Admin"

    def test_stale_datasets(self, runner):
        datasets = {"value": [
            {"name": "Old", "id": "1", "workspaceId": "w", "isRefreshable": True,
             "contentLastRefreshTime": "2020-01-01T00:00:00Z"},
            {"name": "Fresh", "id": "2", "workspaceId": "w", "isRefreshable": True,
             "contentLastRefreshTime": "2099-01-01T00:00:00Z"},
        ]}
        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.get", return_value=datasets):
            result = runner.invoke(cli, ["--json", "tenant", "stale", "--days", "90"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [d["dataset"] for d in data] == ["Old"]

    def test_labels_requires_target(self, runner):
        result = runner.invoke(cli, ["tenant", "labels", "set", "--label-id", "guid"])
        assert result.exit_code != 0
