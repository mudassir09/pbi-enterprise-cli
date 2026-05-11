"""Unit tests for BPA (Best Practice Analyzer) loader and evaluator."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from pbi_cli.backends.mock_backend import DEFAULT_FIXTURE, MockTomBackend
from pbi_cli.governance.bpa import (
    BpaEvaluator,
    BpaRule,
    _translate_expression,
    load_rules_from_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "TEST_RULE",
    name: str = "Test Rule",
    scope: str = "Column",
    expression: str = 'DataType == "Double"',
    severity: int = 1,
    category: str = "Performance",
) -> BpaRule:
    return BpaRule(
        id=rule_id,
        name=name,
        category=category,
        description="A test rule.",
        severity=severity,
        scope=scope,
        expression=expression,
    )


def _backend_with(**overrides: object) -> MockTomBackend:
    fixture = json.loads(json.dumps(DEFAULT_FIXTURE))
    fixture.update(overrides)
    b = MockTomBackend(fixture=fixture)
    b.connect()
    return b


# ---------------------------------------------------------------------------
# Test: load_rules_from_file
# ---------------------------------------------------------------------------


class TestLoadRulesFromFile:
    def test_load_list_format(self, tmp_path: Path) -> None:
        rules_data = [
            {
                "ID": "AVOID_FLOATS",
                "Name": "Do not use floating point",
                "Category": "Performance",
                "Description": "Use fixed-decimal instead.",
                "Severity": 1,
                "Scope": "Column",
                "Expression": 'DataType = "Double"',
                "FixExpression": None,
                "CompatibilityLevel": 1200,
            }
        ]
        f = tmp_path / "BPARules.json"
        f.write_text(json.dumps(rules_data), encoding="utf-8")
        rules = load_rules_from_file(str(f))
        assert len(rules) == 1
        assert rules[0].id == "AVOID_FLOATS"
        assert rules[0].severity == 1
        assert rules[0].severity_label == "warning"

    def test_load_wrapped_format(self, tmp_path: Path) -> None:
        """Some files wrap the list under a 'Rules' key."""
        rules_data = {
            "Rules": [
                {
                    "ID": "R1",
                    "Name": "Rule 1",
                    "Category": "Cat",
                    "Description": "",
                    "Severity": 2,
                    "Scope": "Table",
                    "Expression": "[IsHidden]",
                    "FixExpression": None,
                    "CompatibilityLevel": 1200,
                }
            ]
        }
        f = tmp_path / "BPARules.json"
        f.write_text(json.dumps(rules_data), encoding="utf-8")
        rules = load_rules_from_file(str(f))
        assert len(rules) == 1
        assert rules[0].id == "R1"
        assert rules[0].severity_label == "error"

    def test_severity_label_mapping(self) -> None:
        rule_w = _make_rule(severity=1)
        rule_e = _make_rule(severity=2)
        rule_i = _make_rule(severity=3)
        assert rule_w.severity_label == "warning"
        assert rule_e.severity_label == "error"
        assert rule_i.severity_label == "info"


# ---------------------------------------------------------------------------
# Test: expression translator
# ---------------------------------------------------------------------------


class TestTranslateExpression:
    def test_equality(self) -> None:
        assert _translate_expression('DataType = "Double"') == 'DataType == "Double"'

    def test_inequality(self) -> None:
        assert _translate_expression('DataType <> "Double"') == 'DataType != "Double"'

    def test_and_operator(self) -> None:
        expr = _translate_expression('DataType = "Double" && IsHidden = "True"')
        assert " and " in expr

    def test_or_operator(self) -> None:
        expr = _translate_expression('DataType = "Double" || IsHidden = "True"')
        assert " or " in expr

    def test_starts_with(self) -> None:
        result = _translate_expression('[Name].StartsWith("_")')
        assert "Name.startswith" in result

    def test_contains(self) -> None:
        result = _translate_expression('[Name].Contains("Revenue")')
        assert '"Revenue" in Name' in result

    def test_bracketed_bool(self) -> None:
        result = _translate_expression("[IsHidden]")
        assert "bool(IsHidden)" in result

    def test_not_expression(self) -> None:
        result = _translate_expression('not DataType = "Double"')
        assert "not" in result and "==" in result


# ---------------------------------------------------------------------------
# Test: BpaEvaluator — Column scope
# ---------------------------------------------------------------------------


class TestBpaEvaluatorColumns:
    def test_float_column_flagged(self) -> None:
        """DataType = 'Double' rule should flag Double columns."""
        b = _backend_with(
            columns=[
                {"table": "Sales", "name": "Price", "dataType": "Double", "isHidden": False},
                {"table": "Sales", "name": "Units", "dataType": "Int64", "isHidden": False},
            ]
        )
        rule = _make_rule(expression='DataType = "Double"')
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        assert len(violations) == 1
        assert violations[0]["object"] == "Sales[Price]"
        assert violations[0]["rule"] == "bpa.test_rule"
        assert violations[0]["bpa_id"] == "TEST_RULE"
        assert violations[0]["severity"] == "warning"
        assert violations[0]["autoFixable"] is False

    def test_no_violations_when_no_doubles(self) -> None:
        b = _backend_with(
            columns=[
                {"table": "Sales", "name": "Revenue", "dataType": "Decimal", "isHidden": False},
            ]
        )
        rule = _make_rule(expression='DataType = "Double"')
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert violations == []
        assert skipped == 0

    def test_violation_dict_keys(self) -> None:
        """Violation dict must have the exact required keys."""
        b = _backend_with(
            columns=[
                {"table": "T", "name": "C", "dataType": "Double", "isHidden": False},
            ]
        )
        rule = _make_rule(expression='DataType = "Double"')
        evaluator = BpaEvaluator()
        violations, _ = evaluator.evaluate([rule], b)
        assert len(violations) == 1
        v = violations[0]
        for key in ("rule", "bpa_id", "object", "message", "description", "severity",
                    "category", "autoFixable"):
            assert key in v, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Test: BpaEvaluator — Measure scope
# ---------------------------------------------------------------------------


class TestBpaEvaluatorMeasures:
    def test_empty_description_measure_flagged(self) -> None:
        """[Description] = '' rule should flag measures with no description."""
        b = _backend_with(
            measures=[
                {
                    "table": "Sales",
                    "name": "Revenue",
                    "expression": "SUM(Sales[Revenue])",
                    "formatString": "#,0",
                    "description": "",
                },
                {
                    "table": "Sales",
                    "name": "Units",
                    "expression": "SUM(Sales[Units])",
                    "formatString": "#,0",
                    "description": "Total units sold",
                },
            ]
        )
        rule = _make_rule(
            scope="Measure",
            expression='[Description] = ""',
        )
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        names = [v["object"] for v in violations]
        assert any("Revenue" in n for n in names)
        assert not any("Units" in n for n in names)

    def test_missing_description_measure_flagged(self) -> None:
        """Measures with no description key at all should be caught."""
        b = _backend_with(
            measures=[
                {"table": "Sales", "name": "Revenue", "expression": "SUM(Sales[Revenue])"},
            ]
        )
        rule = _make_rule(
            scope="Measure",
            expression='[Description] = ""',
        )
        evaluator = BpaEvaluator()
        violations, _ = evaluator.evaluate([rule], b)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# Test: BpaEvaluator — Table scope
# ---------------------------------------------------------------------------


class TestBpaEvaluatorTables:
    def test_hidden_table_flagged(self) -> None:
        """[IsHidden] rule should flag hidden tables."""
        b = _backend_with(
            tables=[
                {"name": "HiddenTable", "isHidden": True},
                {"name": "VisibleTable", "isHidden": False},
            ]
        )
        rule = _make_rule(scope="Table", expression="[IsHidden]")
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        assert len(violations) == 1
        assert violations[0]["object"] == "HiddenTable"

    def test_not_expression_inverts_correctly(self) -> None:
        """not [IsHidden] should flag visible tables only."""
        b = _backend_with(
            tables=[
                {"name": "HiddenTable", "isHidden": True},
                {"name": "VisibleTable", "isHidden": False},
            ]
        )
        rule = _make_rule(scope="Table", expression="not [IsHidden]")
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        assert len(violations) == 1
        assert violations[0]["object"] == "VisibleTable"


# ---------------------------------------------------------------------------
# Test: unsupported expressions
# ---------------------------------------------------------------------------


class TestUnsupportedExpressions:
    def test_unsupported_scope_counted_as_skipped(self) -> None:
        """Rules with unsupported scopes should be skipped, not crash."""
        rule = _make_rule(scope="Partition", expression='Name = "test"')
        b = MockTomBackend()
        b.connect()
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert violations == []
        assert skipped == 1

    def test_unsupported_linq_expression_counted_as_skipped(self) -> None:
        """LINQ-style method calls should be counted as skipped."""
        rule = _make_rule(
            scope="Table",
            expression="Columns.Any(DataType == 'Double')",
        )
        b = MockTomBackend()
        b.connect()
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert violations == []
        assert skipped == 1

    def test_mixed_rules_counts_correctly(self) -> None:
        """Skipped count reflects only unsupported rules, not all rules."""
        good_rule = _make_rule(
            rule_id="GOOD",
            scope="Column",
            expression='DataType = "Double"',
        )
        bad_rule = _make_rule(
            rule_id="BAD",
            scope="Partition",  # unsupported
            expression='Name = "x"',
        )
        b = _backend_with(
            columns=[
                {"table": "Sales", "name": "P", "dataType": "Double", "isHidden": False}
            ]
        )
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([good_rule, bad_rule], b)
        assert skipped == 1
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# Test: severity and category filters
# ---------------------------------------------------------------------------


class TestFilters:
    def _setup_rules(self) -> list[BpaRule]:
        return [
            _make_rule(rule_id="W1", severity=1, category="Performance",
                       scope="Column", expression='DataType = "Double"'),
            _make_rule(rule_id="E1", severity=2, category="Error",
                       scope="Table", expression="[IsHidden]"),
        ]

    def _setup_backend(self) -> MockTomBackend:
        return _backend_with(
            columns=[{"table": "T", "name": "C", "dataType": "Double", "isHidden": False}],
            tables=[{"name": "T", "isHidden": True}],
        )

    def test_severity_filter_warning_only(self) -> None:
        evaluator = BpaEvaluator()
        violations, _ = evaluator.evaluate(
            self._setup_rules(), self._setup_backend(), severity_filter="warning"
        )
        assert all(v["severity"] == "warning" for v in violations)

    def test_severity_filter_error_only(self) -> None:
        evaluator = BpaEvaluator()
        violations, _ = evaluator.evaluate(
            self._setup_rules(), self._setup_backend(), severity_filter="error"
        )
        assert all(v["severity"] == "error" for v in violations)

    def test_category_filter(self) -> None:
        evaluator = BpaEvaluator()
        violations, _ = evaluator.evaluate(
            self._setup_rules(), self._setup_backend(), category_filter="Performance"
        )
        assert all(v["category"] == "Performance" for v in violations)


# ---------------------------------------------------------------------------
# Test: CLI end-to-end with CliRunner
# ---------------------------------------------------------------------------


class TestBpaCheckCli:
    def _make_rules_file(self, tmp_path: Path) -> str:
        rules = [
            {
                "ID": "AVOID_FLOATS",
                "Name": "Do not use floating point data types",
                "Category": "Performance",
                "Description": "Use Decimal instead of Double.",
                "Severity": 1,
                "Scope": "Column",
                "Expression": 'DataType = "Double"',
                "FixExpression": None,
                "CompatibilityLevel": 1200,
            }
        ]
        f = tmp_path / "BPARules.json"
        f.write_text(json.dumps(rules), encoding="utf-8")
        return str(f)

    def test_bpa_check_file_no_violations(self, tmp_path: Path) -> None:
        from pbi_cli.cli import cli

        rules_path = self._make_rules_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--backend", "mock", "govern", "bpa", "check", "--file", rules_path]
        )
        # Default mock fixture has no Double columns
        assert result.exit_code == 0, result.output

    def test_bpa_check_file_with_violation(self, tmp_path: Path) -> None:
        """When a Double column exists, exit code 0 (warning, not error)."""
        from pbi_cli.cli import cli

        rules_path = self._make_rules_file(tmp_path)
        runner = CliRunner()
        # The AVOID_FLOATS rule has severity=1 (warning), so exit code stays 0
        result = runner.invoke(
            cli, ["--backend", "mock", "govern", "bpa", "check", "--file", rules_path]
        )
        assert result.exit_code == 0, result.output

    def test_bpa_check_json_output(self, tmp_path: Path) -> None:
        from pbi_cli.cli import cli

        rules_path = self._make_rules_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--backend", "mock", "--json", "govern", "bpa", "check", "--file", rules_path],
        )
        assert result.exit_code == 0, result.output
        # Output should be valid JSON
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_bpa_check_severity_filter(self, tmp_path: Path) -> None:
        from pbi_cli.cli import cli

        rules_path = self._make_rules_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--backend", "mock", "--json", "govern", "bpa", "check",
                "--file", rules_path,
                "--severity", "error",
            ],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        # Rule is severity=1 (warning), so filtered out → empty list
        assert parsed == []

    def test_bpa_check_category_filter(self, tmp_path: Path) -> None:
        from pbi_cli.cli import cli

        rules_path = self._make_rules_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--backend", "mock", "--json", "govern", "bpa", "check",
                "--file", rules_path,
                "--category", "NonExistentCategory",
            ],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed == []
