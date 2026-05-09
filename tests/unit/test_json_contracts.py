"""JSON contract tests — verify that --json output shapes never change silently.

Each test invokes a CLI command with --json and asserts the output matches
the declared schema. These run on every push and block the build if the
contract breaks.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _invoke_json(runner: CliRunner, *args: str) -> list | dict:
    """Run CLI with --backend mock --json and return parsed output."""
    result = runner.invoke(cli, ["--backend", "mock", "--json", *args])
    assert result.exit_code == 0, f"Command failed:\n{result.output}"
    return json.loads(result.output)


# ── measure list ──────────────────────────────────────────────────────────────

class TestMeasureListContract:
    def test_returns_list(self, runner):
        data = _invoke_json(runner, "measure", "list")
        assert isinstance(data, list)

    def test_each_item_has_required_fields(self, runner):
        data = _invoke_json(runner, "measure", "list")
        assert len(data) >= 1
        for item in data:
            assert "name" in item
            assert "table" in item
            assert "expression" in item

    def test_filter_by_table(self, runner):
        data = _invoke_json(runner, "measure", "list", "--table", "Sales")
        for item in data:
            assert item["table"] == "Sales"


# ── model tables ──────────────────────────────────────────────────────────────

class TestModelTablesContract:
    def test_returns_list(self, runner):
        data = _invoke_json(runner, "model", "tables")
        assert isinstance(data, list)

    def test_each_item_has_name(self, runner):
        data = _invoke_json(runner, "model", "tables")
        for item in data:
            assert "name" in item

    def test_default_fixture_has_four_tables(self, runner):
        data = _invoke_json(runner, "model", "tables")
        assert len(data) == 4


# ── model columns ─────────────────────────────────────────────────────────────

class TestModelColumnsContract:
    def test_returns_list(self, runner):
        data = _invoke_json(runner, "model", "columns")
        assert isinstance(data, list)

    def test_each_item_has_required_fields(self, runner):
        data = _invoke_json(runner, "model", "columns")
        for item in data:
            assert "name" in item
            assert "table" in item
            assert "dataType" in item

    def test_filter_by_table_returns_subset(self, runner):
        all_cols = _invoke_json(runner, "model", "columns")
        sales_cols = _invoke_json(runner, "model", "columns", "--table", "Sales")
        assert len(sales_cols) < len(all_cols)
        for col in sales_cols:
            assert col["table"] == "Sales"


# ── model relationships ───────────────────────────────────────────────────────

class TestModelRelationshipsContract:
    def test_returns_list(self, runner):
        data = _invoke_json(runner, "model", "relationships")
        assert isinstance(data, list)

    def test_each_item_has_from_and_to(self, runner):
        data = _invoke_json(runner, "model", "relationships")
        for item in data:
            assert "from" in item
            assert "to" in item

    def test_default_fixture_has_three_relationships(self, runner):
        data = _invoke_json(runner, "model", "relationships")
        assert len(data) == 3


# ── govern check ─────────────────────────────────────────────────────────────

class TestGovernCheckContract:
    def test_returns_list(self, runner):
        # Default fixture has description/format violations
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "check"])
        # May exit 1 if there are error-severity violations; parse output anyway
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_each_violation_has_required_fields(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "check"])
        data = json.loads(result.output)
        for v in data:
            assert "rule" in v
            assert "message" in v
            assert "severity" in v
            assert "autoFixable" in v


# ── source scaffold ───────────────────────────────────────────────────────────

class TestSourceScaffoldContract:
    def test_scaffold_output_has_tables_and_relationships(self, runner, tmp_path):
        import json as _json
        profile = [
            {
                "tableName": "FactOrders",
                "rowCount": 50000,
                "columns": [
                    {"name": "OrderKey", "dataType": "Int64", "nullRate": 0.0},
                    {"name": "ProductKey", "dataType": "Int64", "nullRate": 0.0},
                    {"name": "Amount", "dataType": "Decimal", "nullRate": 0.05},
                ],
            },
            {
                "tableName": "DimProduct",
                "rowCount": 200,
                "columns": [
                    {"name": "ProductKey", "dataType": "Int64", "nullRate": 0.0},
                    {"name": "ProductName", "dataType": "String", "nullRate": 0.0},
                ],
            },
        ]
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(_json.dumps(profile), encoding="utf-8")

        result = runner.invoke(
            cli,
            ["--backend", "mock", "--json", "source", "scaffold", "--profile", str(profile_file)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "tables" in data
        assert "relationships" in data
        assert len(data["tables"]) == 2


# ── visual recommend ─────────────────────────────────────────────────────────

class TestVisualRecommendContract:
    def test_returns_list(self, runner):
        data = _invoke_json(runner, "visual", "recommend", "--measures", "Total Revenue,YTD Revenue")
        assert isinstance(data, list)

    def test_each_item_has_visual_and_rationale(self, runner):
        data = _invoke_json(runner, "visual", "recommend", "--measures", "Total Revenue")
        for item in data:
            assert "visual" in item
            assert "rationale" in item
