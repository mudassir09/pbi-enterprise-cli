"""Unit tests for each governance rule module and the GovernanceEngine."""

from __future__ import annotations

import pytest

from pbi_cli.backends.mock_backend import MockTomBackend, DEFAULT_FIXTURE
from pbi_cli.governance.engine import GovernanceEngine
from pbi_cli.governance.rules import (
    measure_brackets,
    measure_description,
    measure_format,
    measure_naming,
    table_pascal_case,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _backend_with(**overrides) -> MockTomBackend:
    """Build a MockTomBackend from DEFAULT_FIXTURE with selective overrides."""
    import json
    fixture = json.loads(json.dumps(DEFAULT_FIXTURE))
    fixture.update(overrides)
    b = MockTomBackend(fixture=fixture)
    b.connect()
    return b


# ── table_pascal_case ─────────────────────────────────────────────────────────

class TestTablePascalCase:
    def test_clean_model_no_violations(self):
        b = MockTomBackend()
        b.connect()
        violations = table_pascal_case.check(b)
        # Default fixture has PascalCase tables: Sales, Products, Customers, Calendar
        assert violations == []

    def test_snake_case_table_flagged(self):
        b = _backend_with(tables=[{"name": "sales_data", "isHidden": False}])
        violations = table_pascal_case.check(b)
        assert len(violations) == 1
        assert violations[0]["rule"] == "table-pascal-case"
        assert violations[0]["autoFixable"] is True

    def test_fact_prefix_allowed(self):
        b = _backend_with(tables=[{"name": "FACT_Sales", "isHidden": False}])
        violations = table_pascal_case.check(b)
        assert violations == []

    def test_dim_prefix_allowed(self):
        b = _backend_with(tables=[{"name": "DIM_Product", "isHidden": False}])
        violations = table_pascal_case.check(b)
        assert violations == []

    def test_lowercase_table_flagged(self):
        b = _backend_with(tables=[{"name": "customers", "isHidden": False}])
        violations = table_pascal_case.check(b)
        assert len(violations) == 1

    def test_multiple_bad_tables_all_flagged(self):
        b = _backend_with(tables=[
            {"name": "sales_data"},
            {"name": "product list"},
            {"name": "GoodTable"},
        ])
        violations = table_pascal_case.check(b)
        names = [v["object"] for v in violations]
        assert any("sales_data" in n for n in names)
        assert any("product list" in n for n in names)
        assert all("GoodTable" not in n for n in names)


# ── measure_brackets ──────────────────────────────────────────────────────────

class TestMeasureBrackets:
    def test_clean_measure_names_no_violations(self):
        b = MockTomBackend()
        b.connect()
        violations = measure_brackets.check(b)
        assert violations == []

    def test_bracketed_name_flagged(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "[Total Revenue]", "expression": "SUM(Sales[Revenue])", "formatString": "#,0"}
        ])
        violations = measure_brackets.check(b)
        assert len(violations) == 1
        assert violations[0]["rule"] == "measure-brackets"
        assert violations[0]["autoFixable"] is False

    def test_partial_brackets_not_flagged(self):
        # Only fully-bracketed names are caught
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue [YTD]", "expression": "1", "formatString": "#,0"}
        ])
        violations = measure_brackets.check(b)
        assert violations == []


# ── measure_description ───────────────────────────────────────────────────────

class TestMeasureDescription:
    def test_measures_without_description_flagged(self):
        b = MockTomBackend()
        b.connect()
        # Default fixture measures have no description
        violations = measure_description.check(b)
        assert len(violations) == 2  # Total Revenue + Total Units

    def test_measure_with_description_passes(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])",
             "formatString": "#,0", "description": "Total net revenue"}
        ])
        violations = measure_description.check(b)
        assert violations == []

    def test_empty_description_flagged(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])",
             "formatString": "#,0", "description": ""}
        ])
        violations = measure_description.check(b)
        assert len(violations) == 1

    def test_description_is_now_auto_fixable(self):
        """measure-description-required must be autoFixable=True after gap fix."""
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"}
        ])
        violations = measure_description.check(b)
        assert violations[0]["autoFixable"] is True

    def test_auto_fix_sets_placeholder_description(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"}
        ])
        violations = measure_description.check(b)
        fixed = measure_description.fix(b, violations[0])
        assert fixed is True
        updated = next(m for m in b.measure_list() if m["name"] == "Revenue")
        assert updated.get("description"), "description must be set after fix"
        assert "Revenue" in updated["description"], "placeholder should mention measure name"


# ── measure_naming ────────────────────────────────────────────────────────────

class TestMeasureNaming:
    def test_clean_measure_no_violations(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Total Revenue", "expression": "1",
             "formatString": "#,0", "isHidden": False}
        ])
        violations = measure_naming.check(b)
        assert violations == []

    def test_all_caps_measure_flagged(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "TOTAL_REVENUE", "expression": "1",
             "formatString": "#,0", "isHidden": False}
        ])
        violations = measure_naming.check(b)
        assert any(v["rule"] == "measure-naming" for v in violations)
        assert any("TOTAL_REVENUE" in v["object"] for v in violations)
        assert any(v["autoFixable"] for v in violations)

    def test_all_caps_fix_renames_to_title_case(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "TOTAL_REVENUE", "expression": "1",
             "formatString": "#,0", "isHidden": False}
        ])
        violations = measure_naming.check(b)
        fixable = [v for v in violations if v.get("autoFixable") and v.get("suggestedName")]
        assert fixable
        fixed = measure_naming.fix(b, fixable[0])
        assert fixed is True
        names = [m["name"] for m in b.measure_list()]
        assert "Total Revenue" in names, f"Expected 'Total Revenue' in {names}"
        assert "TOTAL_REVENUE" not in names

    def test_hidden_measure_without_prefix_flagged(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Base Sales", "expression": "1",
             "formatString": "#,0", "isHidden": True}
        ])
        violations = measure_naming.check(b)
        assert any(v["rule"] == "measure-naming" for v in violations)
        assert any("hidden" in v["message"].lower() for v in violations)

    def test_non_hidden_with_underscore_flagged_not_fixable(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "_Revenue", "expression": "1",
             "formatString": "#,0", "isHidden": False}
        ])
        violations = measure_naming.check(b)
        assert any(v["rule"] == "measure-naming" for v in violations)
        underscore_v = next(v for v in violations if "_Revenue" in v["object"])
        assert underscore_v["autoFixable"] is False

    def test_to_title_conversion(self):
        assert measure_naming._to_title("TOTAL_REVENUE") == "Total Revenue"
        assert measure_naming._to_title("YTD_SALES") == "Ytd Sales"
        assert measure_naming._to_title("NET_PROFIT_MARGIN") == "Net Profit Margin"


# ── measure_format ────────────────────────────────────────────────────────────

class TestMeasureFormat:
    def test_default_fixture_measures_missing_format_not_flagged(self):
        b = MockTomBackend()
        b.connect()
        # Default fixture already has formatString set on both measures
        violations = measure_format.check(b)
        assert violations == []

    def test_measure_without_format_flagged(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"}
        ])
        violations = measure_format.check(b)
        assert len(violations) == 1
        assert violations[0]["rule"] == "measure-format-required"
        assert violations[0]["autoFixable"] is True

    def test_auto_fix_applies_default_format(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"}
        ])
        violations = measure_format.check(b)
        assert len(violations) == 1
        fixed = measure_format.fix(b, violations[0])
        assert fixed is True
        updated = next(m for m in b.measure_list() if m["name"] == "Revenue")
        assert updated.get("formatString") == "#,0.00"


# ── GovernanceEngine (integration) ────────────────────────────────────────────

class TestGovernanceEngine:
    def test_run_all_returns_combined_violations(self):
        # A model with a bad table name and missing formats/descriptions
        b = _backend_with(
            tables=[{"name": "sales_data"}],
            measures=[{"table": "sales_data", "name": "Revenue", "expression": "1"}],
        )
        engine = GovernanceEngine(b)
        violations = engine.run_all()
        rule_ids = {v["rule"] for v in violations}
        assert "table-pascal-case" in rule_ids
        assert "measure-format-required" in rule_ids
        assert "measure-description-required" in rule_ids

    def test_auto_fix_resolves_fixable_violations(self):
        b = _backend_with(measures=[
            {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"}
        ])
        engine = GovernanceEngine(b)
        violations = engine.run_all()
        fixable = [v for v in violations if v.get("autoFixable")]
        assert len(fixable) >= 1
        fixed_count = engine.auto_fix(fixable)
        assert fixed_count >= 1

    def test_severity_levels_present(self):
        b = _backend_with(
            tables=[{"name": "bad_table"}],
            measures=[{"table": "bad_table", "name": "M", "expression": "1"}],
        )
        engine = GovernanceEngine(b)
        violations = engine.run_all()
        severities = {v["severity"] for v in violations}
        assert "warning" in severities

    def test_clean_model_no_violations(self):
        b = _backend_with(
            tables=[{"name": "Sales"}],
            measures=[{
                "table": "Sales", "name": "Revenue",
                "expression": "SUM(Sales[Amount])",
                "formatString": "#,0.00",
                "description": "Total net revenue",
            }],
        )
        engine = GovernanceEngine(b)
        violations = engine.run_all()
        assert violations == []
