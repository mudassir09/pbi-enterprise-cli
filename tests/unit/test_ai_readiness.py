"""Tests for the AI-readiness rule pack (Copilot / Fabric IQ ontology preparation)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.backends.mock_backend import DEFAULT_FIXTURE, MockTomBackend
from pbi_cli.cli import cli
from pbi_cli.governance.engine import GovernanceEngine
from pbi_cli.governance.rules import ai_readiness

# ── Helpers ───────────────────────────────────────────────────────────────────


def _backend_with(**overrides) -> MockTomBackend:
    fixture = json.loads(json.dumps(DEFAULT_FIXTURE))
    fixture.update(overrides)
    b = MockTomBackend(fixture=fixture)
    b.connect()
    return b


def _ai_ready_fixture() -> dict:
    """A model that passes every AI-readiness check."""
    return {
        "model": {"name": "CleanModel", "compatibility_level": 1600},
        "tables": [
            {"name": "Sales", "isHidden": False, "description": "Fact sales"},
            {"name": "Calendar", "isHidden": False, "description": "Date dimension",
             "dataCategory": "Time"},
        ],
        "columns": [
            {"table": "Sales", "name": "SalesKey", "dataType": "Int64",
             "isHidden": True, "description": "Surrogate key"},
            {"table": "Sales", "name": "Revenue", "dataType": "Double",
             "isHidden": False, "description": "Net revenue"},
            {"table": "Sales", "name": "DateKey", "dataType": "Int64",
             "isHidden": True, "description": "Date FK"},
            {"table": "Calendar", "name": "DateKey", "dataType": "Int64",
             "isHidden": True, "description": "Date key"},
            {"table": "Calendar", "name": "Date", "dataType": "DateTime",
             "isHidden": False, "description": "Calendar date"},
        ],
        "relationships": [
            {"from": "Sales[DateKey]", "to": "Calendar[DateKey]", "cardinality": "ManyToOne"},
        ],
        "measures": [
            {"table": "Sales", "name": "Total Revenue", "expression": "SUM(Sales[Revenue])",
             "formatString": "#,0.00", "description": "Total net revenue"},
        ],
    }


def _rules(violations: list[dict]) -> set[str]:
    return {v["rule"] for v in violations}


# ── Individual checks ─────────────────────────────────────────────────────────


class TestMeasureDescriptions:
    def test_default_fixture_measures_flagged(self):
        b = MockTomBackend()
        b.connect()
        violations = ai_readiness.check_measure_descriptions(b)
        assert len(violations) == 2  # Total Revenue + Total Units

    def test_hidden_measures_exempt(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "_Base", "expression": "1", "isHidden": True},
        ])
        assert ai_readiness.check_measure_descriptions(b) == []


class TestColumnDescriptions:
    def test_visible_undescribed_columns_flagged_as_info(self):
        b = MockTomBackend()
        b.connect()
        violations = ai_readiness.check_column_descriptions(b)
        assert violations
        assert all(v["severity"] == "info" for v in violations)

    def test_hidden_columns_exempt(self):
        b = _backend_with(columns=[
            {"table": "Sales", "name": "SalesKey", "dataType": "Int64", "isHidden": True},
        ])
        assert ai_readiness.check_column_descriptions(b) == []


class TestTechnicalColumnsVisible:
    def test_visible_key_columns_flagged(self):
        b = MockTomBackend()
        b.connect()
        violations = ai_readiness.check_technical_columns_visible(b)
        objects = " ".join(v["object"] for v in violations)
        assert "SalesKey" in objects
        assert "DateKey" in objects

    def test_id_suffix_requires_capital_i(self):
        b = _backend_with(
            tables=[{"name": "Sales", "isHidden": False}],
            columns=[
                {"table": "Sales", "name": "Paid", "dataType": "Boolean", "isHidden": False},
                {"table": "Sales", "name": "CustomerID", "dataType": "Int64", "isHidden": False},
            ],
        )
        violations = ai_readiness.check_technical_columns_visible(b)
        objects = " ".join(v["object"] for v in violations)
        assert "CustomerID" in objects
        assert "Paid" not in objects

    def test_hidden_key_columns_pass(self):
        b = _backend_with(
            tables=[{"name": "Sales", "isHidden": False}],
            columns=[
                {"table": "Sales", "name": "SalesKey", "dataType": "Int64", "isHidden": True},
            ],
        )
        assert ai_readiness.check_technical_columns_visible(b) == []


class TestDateTableMarked:
    def test_unmarked_model_with_datetime_flagged(self):
        b = MockTomBackend()
        b.connect()
        violations = ai_readiness.check_date_table_marked(b)
        assert len(violations) == 1
        assert violations[0]["rule"] == "ai-date-table-marked"

    def test_marked_date_table_passes(self):
        b = MockTomBackend(fixture=_ai_ready_fixture())
        b.connect()
        assert ai_readiness.check_date_table_marked(b) == []

    def test_model_without_datetime_columns_exempt(self):
        b = _backend_with(columns=[
            {"table": "Sales", "name": "Revenue", "dataType": "Double", "isHidden": False},
        ])
        assert ai_readiness.check_date_table_marked(b) == []


class TestAutoDatetimeTables:
    def test_local_date_tables_flagged(self):
        b = _backend_with(tables=[
            {"name": "Sales", "isHidden": False},
            {"name": "LocalDateTable_c6286cb1-04e5-44c2", "isHidden": True},
            {"name": "DateTableTemplate_4b82381b", "isHidden": True},
        ])
        violations = ai_readiness.check_auto_datetime_tables(b)
        assert len(violations) == 2
        assert all(v["rule"] == "ai-auto-datetime" for v in violations)


class TestDecimalColumns:
    def test_decimal_column_flagged(self):
        b = MockTomBackend()
        b.connect()
        violations = ai_readiness.check_decimal_columns(b)
        assert len(violations) == 1  # Sales[Revenue] is Decimal in the default fixture
        assert "Revenue" in violations[0]["object"]

    def test_double_column_passes(self):
        b = _backend_with(columns=[
            {"table": "Sales", "name": "Revenue", "dataType": "Double", "isHidden": False},
        ])
        assert ai_readiness.check_decimal_columns(b) == []


class TestIsolatedTables:
    def test_default_fixture_all_related(self):
        b = MockTomBackend()
        b.connect()
        assert ai_readiness.check_isolated_tables(b) == []

    def test_unrelated_table_flagged_as_info(self):
        b = _backend_with(
            tables=[
                {"name": "Sales", "isHidden": False},
                {"name": "Orphan", "isHidden": False},
            ],
            relationships=[],
        )
        violations = ai_readiness.check_isolated_tables(b)
        names = " ".join(v["object"] for v in violations)
        assert "Orphan" in names
        assert all(v["severity"] == "info" for v in violations)

    def test_single_table_model_exempt(self):
        b = _backend_with(tables=[{"name": "Sales", "isHidden": False}], relationships=[])
        assert ai_readiness.check_isolated_tables(b) == []


# ── Pack + engine + CLI ───────────────────────────────────────────────────────


class TestPack:
    def test_default_fixture_has_expected_rule_mix(self):
        b = MockTomBackend()
        b.connect()
        rules = _rules(ai_readiness.check(b))
        assert "ai-measure-description" in rules
        assert "ai-technical-column-visible" in rules
        assert "ai-date-table-marked" in rules
        assert "ai-decimal-column" in rules

    def test_ai_ready_model_passes_everything(self):
        b = MockTomBackend(fixture=_ai_ready_fixture())
        b.connect()
        assert ai_readiness.check(b) == []

    def test_engine_run_ai_readiness(self):
        b = MockTomBackend()
        b.connect()
        violations = GovernanceEngine(b).run_ai_readiness()
        assert violations
        assert all(v["rule"].startswith("ai-") for v in violations)

    def test_run_all_unaffected_by_ai_pack(self):
        """The AI pack must not leak into the default govern check rule set."""
        b = MockTomBackend(fixture=_ai_ready_fixture())
        b.connect()
        rules = _rules(GovernanceEngine(b).run_all())
        assert not any(r.startswith("ai-") for r in rules)


@pytest.fixture()
def runner():
    return CliRunner()


class TestCli:
    def test_json_output_and_default_exit_zero(self, runner):
        # Default fixture has warnings/infos but no errors → exit 0 at --fail-on error
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "ai-readiness"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["summary"]["total"] > 0
        assert data["summary"]["errors"] == 0

    def test_fail_on_warning_exits_3(self, runner):
        result = runner.invoke(
            cli, ["--backend", "mock", "govern", "ai-readiness", "--fail-on", "warning"])
        assert result.exit_code == 3
