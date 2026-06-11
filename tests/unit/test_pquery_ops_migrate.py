"""Tests for pquery, ops, migrate, and docs erd/site commands."""

from __future__ import annotations

import json
import zipfile
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli

SQL_TABLE = """\
table Sales

    column Revenue
        dataType: decimal
        sourceColumn: Revenue

    column Margin = Sales[Revenue] * 0.3
        dataType: decimal

    partition Sales = m
        mode: import
        source =
                let
                    Source = Sql.Database("prod-server", "dw"),
                    Indexed = Table.AddIndexColumn(Source, "Idx"),
                    Buffered = Table.Buffer(Indexed)
                in
                    Buffered
"""

LOCAL_TABLE = """\
table Budget

    column Amount
        dataType: decimal
        sourceColumn: Amount

    partition Budget = m
        mode: import
        source =
                let
                    Source = Excel.Workbook(File.Contents("C:\\\\Users\\\\bob\\\\budget.xlsx"))
                in
                    Source
"""

CALC_TABLE = """\
table DateDim

    column Date
        dataType: dateTime

    partition DateDim = calculated
        mode: import
        source = CALENDAR(DATE(2020,1,1), DATE(2026,12,31))
"""


@pytest.fixture()
def tmdl_project(tmp_path):
    d = tmp_path / "M.SemanticModel" / "definition" / "tables"
    d.mkdir(parents=True)
    (d / "Sales.tmdl").write_text(SQL_TABLE, encoding="utf-8")
    (d / "Budget.tmdl").write_text(LOCAL_TABLE, encoding="utf-8")
    (d / "DateDim.tmdl").write_text(CALC_TABLE, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def runner():
    return CliRunner()


def _file_args(project):
    return ["--backend", "file", "--path", str(project)]


class TestPquery:
    def test_list(self, runner, tmdl_project):
        result = runner.invoke(cli, [*_file_args(tmdl_project), "--json", "pquery", "list"])
        assert result.exit_code == 0, result.output
        names = {r["name"] for r in json.loads(result.output)}
        assert any("Sales" in n for n in names)

    def test_folding_check_flags_breakers(self, runner, tmdl_project):
        result = runner.invoke(
            cli, [*_file_args(tmdl_project), "--json", "pquery", "folding-check"])
        assert result.exit_code == 0, result.output
        findings = json.loads(result.output)
        text = json.dumps(findings)
        assert "Table.AddIndexColumn" in text
        assert "Table.Buffer" in text

    def test_folding_fail_flag(self, runner, tmdl_project):
        result = runner.invoke(
            cli, [*_file_args(tmdl_project), "pquery", "folding-check", "--fail-on-breaker"])
        assert result.exit_code == 3

    def test_lint_finds_local_path(self, runner, tmdl_project):
        result = runner.invoke(
            cli, [*_file_args(tmdl_project), "--json", "pquery", "lint"])
        assert result.exit_code == 3  # local path is an error
        findings = json.loads(result.output)
        assert any(f["rule"] == "pquery.local-path" for f in findings)


class TestOps:
    def test_refresh_completed(self, runner):
        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.post", return_value={}), \
             patch("pbi_cli.fabric_api.get",
                   return_value={"value": [{"status": "Completed", "endTime": "now"}]}):
            result = runner.invoke(cli, [
                "--json", "ops", "refresh", "--workspace", "w", "--dataset", "d"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == "Completed"

    def test_refresh_failure_notifies_and_exits_4(self, runner):
        sent = {}

        def fake_webhook(url, message):
            sent["url"], sent["message"] = url, message

        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.post", return_value={}), \
             patch("pbi_cli.fabric_api.get",
                   return_value={"value": [{"status": "Failed",
                                            "serviceExceptionJson": "boom"}]}), \
             patch("pbi_cli.commands.ops_cmd.send_webhook", side_effect=fake_webhook):
            result = runner.invoke(cli, [
                "ops", "refresh", "--workspace", "w", "--dataset", "d",
                "--notify", "https://hooks.example/x"])
        assert result.exit_code == 4
        assert "failed" in sent["message"].lower()

    def test_refresh_chain_short_circuits(self, runner, tmp_path):
        plan = tmp_path / "plan.yaml"
        plan.write_text(
            "steps:\n"
            "  - {workspace: w, dataset: d1}\n"
            "  - {workspace: w, dataset: d2}\n",
            encoding="utf-8")

        with patch("pbi_cli.fabric_api.get_token", return_value="t"), \
             patch("pbi_cli.fabric_api.post", return_value={}), \
             patch("pbi_cli.fabric_api.get",
                   return_value={"value": [{"status": "Failed",
                                            "serviceExceptionJson": "x"}]}):
            result = runner.invoke(cli, [
                "--json", "ops", "refresh-chain", "--plan", str(plan)])
        assert result.exit_code == 4
        results = json.loads(result.output)
        assert len(results) == 1  # second step never ran


class TestMigrate:
    def test_direct_lake_analyze(self, runner, tmdl_project):
        result = runner.invoke(
            cli, [*_file_args(tmdl_project), "--json", "migrate", "direct-lake"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        kinds = {b["blocker"] for b in data["blockers"]}
        assert "calculated-column" in kinds       # Margin has no sourceColumn
        assert "calculated-table" in kinds        # DateDim
        assert "non-lakehouse-source" in kinds    # Sql.Database partition
        assert data["summary"]["ready"] is False

    def test_pbix_extract(self, runner, tmp_path):
        pbix = tmp_path / "legacy.pbix"
        layout = json.dumps({"sections": [
            {"name": "s0", "visualContainers": [{}, {}]},
        ]})
        with zipfile.ZipFile(pbix, "w") as z:
            z.writestr("Report/Layout", layout.encode("utf-16-le"))
            z.writestr("Version", "1.28")
            z.writestr("DataModel", b"\x00\x01")
        out = tmp_path / "extracted"
        result = runner.invoke(cli, [
            "--json", "migrate", "pbix-extract", str(pbix), "--output", str(out)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["pages"] == 1
        assert data["visuals"] == 2
        assert data["hasDataModel"] is True
        assert (out / "Layout.json").exists()

    def test_dbt_mapping_and_contract(self, runner, tmp_path):
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({
            "nodes": {
                "model.proj.sales": {"name": "sales", "schema": "dbo",
                                     "columns": {"Revenue": {}, "Units": {}}},
                "model.proj.unmatched": {"name": "unmatched", "schema": "dbo",
                                         "columns": {}},
            }
        }), encoding="utf-8")
        contract = tmp_path / "contract.yaml"
        result = runner.invoke(cli, [
            "--backend", "mock", "--json", "migrate", "dbt",
            "--manifest", str(manifest), "--contract-out", str(contract)])
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        mapped = {r["dbt_model"]: r["semantic_table"] for r in rows}
        assert mapped["sales"] == "Sales"
        assert mapped["unmatched"] == "(unmapped)"
        assert contract.exists()


class TestDocsOutputs:
    def test_erd_mermaid(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "docs", "erd"])
        assert result.exit_code == 0, result.output
        assert result.output.startswith("erDiagram")
        assert "Sales" in result.output

    def test_site_generation(self, runner, tmp_path):
        out = tmp_path / "site"
        result = runner.invoke(cli, [
            "--backend", "mock", "docs", "site", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert (out / "mkdocs.yml").exists()
        measures_md = (out / "docs" / "measures.md").read_text(encoding="utf-8")
        assert "Total Revenue" in measures_md
        assert "```dax" in measures_md
