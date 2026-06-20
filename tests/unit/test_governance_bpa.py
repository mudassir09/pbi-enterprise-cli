"""Unit tests for BPA (Best Practice Analyzer) loader and evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.backends.mock_backend import DEFAULT_FIXTURE, MockTomBackend
from pbi_cli.governance.bpa import (
    BpaEvaluator,
    BpaRule,
    load_rules_from_file,
)
from pbi_cli.governance.bpa_expr import (
    BpaContext,
    BpaUnsupported,
    evaluate_expression,
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
# Test: expression evaluator (AST, no eval())
# ---------------------------------------------------------------------------


class TestExpressionEvaluator:
    def _col(self, **props: object) -> BpaContext:
        return BpaContext(props)

    def test_equality(self) -> None:
        assert evaluate_expression('DataType = "Double"', self._col(DataType="Double"))
        assert not evaluate_expression('DataType = "Double"', self._col(DataType="Int64"))

    def test_double_equals(self) -> None:
        assert evaluate_expression('DataType == "Double"', self._col(DataType="Double"))

    def test_inequality(self) -> None:
        assert evaluate_expression('DataType <> "Double"', self._col(DataType="Int64"))
        assert evaluate_expression('DataType != "Double"', self._col(DataType="Int64"))
        assert not evaluate_expression('DataType <> "Double"', self._col(DataType="Double"))

    def test_and_operator(self) -> None:
        ctx = self._col(DataType="Double", IsHidden=False)
        assert evaluate_expression('DataType = "Double" && not IsHidden', ctx)
        assert not evaluate_expression('DataType = "Double" && IsHidden', ctx)

    def test_or_operator(self) -> None:
        ctx = self._col(DataType="Int64", IsHidden=True)
        assert evaluate_expression('DataType = "Double" || IsHidden', ctx)

    def test_starts_with(self) -> None:
        assert evaluate_expression('[Name].StartsWith("_")', self._col(Name="_hidden"))
        assert not evaluate_expression('[Name].StartsWith("_")', self._col(Name="Visible"))

    def test_contains(self) -> None:
        assert evaluate_expression('[Name].Contains("Revenue")', self._col(Name="Total Revenue"))

    def test_regex_is_match(self) -> None:
        assert evaluate_expression('RegEx.IsMatch(Name, "^[a-z]")', self._col(Name="lower"))
        assert not evaluate_expression('RegEx.IsMatch(Name, "^[a-z]")', self._col(Name="Upper"))

    def test_string_length(self) -> None:
        assert evaluate_expression("[Name].Length > 3", self._col(Name="abcd"))
        assert not evaluate_expression("[Name].Length > 3", self._col(Name="ab"))

    def test_bracketed_bool(self) -> None:
        assert evaluate_expression("[IsHidden]", self._col(IsHidden=True))
        assert not evaluate_expression("[IsHidden]", self._col(IsHidden=False))

    def test_bool_vs_string_literal(self) -> None:
        assert evaluate_expression('IsHidden = "True"', self._col(IsHidden=True))
        assert not evaluate_expression('IsHidden = "True"', self._col(IsHidden=False))

    def test_not_expression(self) -> None:
        assert evaluate_expression('not DataType = "Double"', self._col(DataType="Int64"))
        assert not evaluate_expression('not DataType = "Double"', self._col(DataType="Double"))

    def test_collection_any(self) -> None:
        table = BpaContext(
            {"Name": "Sales"},
            {"Columns": [self._col(DataType="Double"), self._col(DataType="Int64")]},
        )
        assert evaluate_expression('Columns.Any(DataType == "Double")', table)
        assert not evaluate_expression('Columns.Any(DataType == "String")', table)

    def test_collection_all_and_count(self) -> None:
        table = BpaContext(
            {"Name": "Sales"},
            {"Columns": [self._col(IsHidden=True), self._col(IsHidden=True)]},
        )
        assert evaluate_expression("Columns.All(IsHidden)", table)
        assert evaluate_expression("Columns.Count > 1", table)
        assert evaluate_expression("Columns.Count() == 2", table)

    def test_unknown_property_raises_unsupported(self) -> None:
        # IsKey is not modelled — must skip honestly, not default to false
        with pytest.raises(BpaUnsupported):
            evaluate_expression("[IsKey]", self._col(Name="C"))

    def test_unparseable_raises_unsupported(self) -> None:
        with pytest.raises(BpaUnsupported):
            evaluate_expression("DataType ===", self._col(DataType="Double"))


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
        """Rules scoped only to object types we don't model should be skipped."""
        rule = _make_rule(scope="KPI", expression='Name = "test"')
        b = MockTomBackend()
        b.connect()
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert violations == []
        assert skipped == 1

    def test_linq_any_now_evaluated(self) -> None:
        """LINQ-style collection methods are now evaluated, not skipped."""
        rule = _make_rule(
            scope="Table",
            expression="Columns.Any(DataType == 'Double')",
        )
        b = _backend_with(
            tables=[{"name": "Sales", "isHidden": False}],
            columns=[{"table": "Sales", "name": "Price", "dataType": "Double"}],
        )
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        assert len(violations) == 1
        assert violations[0]["object"] == "Sales"

    def test_unmodelled_property_counted_as_skipped(self) -> None:
        """A rule referencing a property we don't model is skipped, not guessed."""
        rule = _make_rule(scope="Column", expression="[KeepUniqueRows]")
        b = _backend_with(
            columns=[{"table": "Sales", "name": "Price", "dataType": "Double"}]
        )
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert violations == []
        assert skipped == 1

    def test_compound_tom_scope_is_evaluated(self) -> None:
        """The community ruleset uses compound TOM scopes like
        'DataColumn, CalculatedColumn, CalculatedTableColumn' — these must map to
        the Column family and actually run, not be skipped."""
        rule = _make_rule(
            scope="DataColumn, CalculatedColumn, CalculatedTableColumn",
            expression='DataType = "Double"',
        )
        b = _backend_with(
            columns=[{"table": "Sales", "name": "Price", "dataType": "Double"}]
        )
        evaluator = BpaEvaluator()
        violations, skipped = evaluator.evaluate([rule], b)
        assert skipped == 0
        assert len(violations) == 1
        assert violations[0]["object"] == "Sales[Price]"

    def test_mixed_rules_counts_correctly(self) -> None:
        """Skipped count reflects only unsupported rules, not all rules."""
        good_rule = _make_rule(
            rule_id="GOOD",
            scope="Column",
            expression='DataType = "Double"',
        )
        bad_rule = _make_rule(
            rule_id="BAD",
            scope="KPI",  # unsupported — object type we don't model
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


# ---------------------------------------------------------------------------
# Test: UsedInRelationships graph + predicate closures (current/it)
# ---------------------------------------------------------------------------


class TestRelationshipGraphAndClosures:
    """A star schema: Sales[ProductFK] -(many)-> Products[ProductPK];
    Products[CatFK] -(many)-> Category[CatPK]; Orphan has no relationships.
    Products is therefore a snowflake hop (both a from- and a to-table)."""

    def _model(self) -> MockTomBackend:
        return _backend_with(
            tables=[
                {"name": "Sales", "isHidden": False},
                {"name": "Products", "isHidden": False},
                {"name": "Category", "isHidden": False},
                {"name": "Orphan", "isHidden": False},
            ],
            columns=[
                {"table": "Sales", "name": "ProductFK", "dataType": "Int64", "isHidden": False},
                {"table": "Products", "name": "ProductPK", "dataType": "Int64", "isHidden": False},
                {"table": "Products", "name": "CatFK", "dataType": "Int64", "isHidden": False},
                {"table": "Category", "name": "CatPK", "dataType": "Int64", "isHidden": False},
                {"table": "Orphan", "name": "X", "dataType": "Int64", "isHidden": False},
            ],
            relationships=[
                {"from": "Sales[ProductFK]", "to": "Products[ProductPK]",
                 "cardinality": "ManyToOne"},
                {"from": "Products[CatFK]", "to": "Category[CatPK]",
                 "cardinality": "ManyToOne"},
            ],
        )

    def test_tables_without_relationships(self) -> None:
        """UsedInRelationships.Count() == 0 flags only the orphan table."""
        rule = _make_rule(scope="Table", expression="UsedInRelationships.Count() == 0")
        v, skipped = BpaEvaluator().evaluate([rule], self._model())
        assert skipped == 0
        assert {x["object"] for x in v} == {"Orphan"}

    def test_foreign_key_detection_uses_current_closure(self) -> None:
        """Flag visible many-side FK columns — uses FromColumn.Name, current, cardinality."""
        rule = _make_rule(
            scope="Column",
            expression=(
                "UsedInRelationships.Any(FromColumn.Name == current.Name "
                'and FromCardinality == "Many") and IsHidden == false'
            ),
        )
        v, skipped = BpaEvaluator().evaluate([rule], self._model())
        assert skipped == 0
        flagged = {x["object"] for x in v}
        assert flagged == {"Sales[ProductFK]", "Products[CatFK]"}

    def test_snowflake_hop_detection(self) -> None:
        """A table that is both a from-table and a to-table is a snowflake hop."""
        rule = _make_rule(
            scope="Table",
            expression=(
                "UsedInRelationships.Any(current.Name == FromTable.Name) "
                "and UsedInRelationships.Any(current.Name == ToTable.Name)"
            ),
        )
        v, skipped = BpaEvaluator().evaluate([rule], self._model())
        assert skipped == 0
        assert {x["object"] for x in v} == {"Products"}

    def test_relationship_columns_should_be_integer(self) -> None:
        """UsedInRelationships.Any() + enum constant DataType.Int64."""
        model = _backend_with(
            tables=[{"name": "Sales", "isHidden": False}, {"name": "Dim", "isHidden": False}],
            columns=[
                {"table": "Sales", "name": "DimKey", "dataType": "String", "isHidden": False},
                {"table": "Dim", "name": "DimKey", "dataType": "Int64", "isHidden": False},
            ],
            relationships=[
                {"from": "Sales[DimKey]", "to": "Dim[DimKey]", "cardinality": "ManyToOne"}
            ],
        )
        rule = _make_rule(
            scope="Column",
            expression="UsedInRelationships.Any() and DataType != DataType.Int64",
        )
        v, skipped = BpaEvaluator().evaluate([rule], model)
        assert skipped == 0
        assert {x["object"] for x in v} == {"Sales[DimKey]"}

    def test_model_allcolumns_with_current(self) -> None:
        """Model back-reference + current closure: duplicate column names across tables."""
        model = _backend_with(
            tables=[{"name": "A", "isHidden": False}, {"name": "B", "isHidden": False}],
            columns=[
                {"table": "A", "name": "Dup", "dataType": "Int64", "isHidden": False},
                {"table": "B", "name": "Dup", "dataType": "Int64", "isHidden": False},
                {"table": "A", "name": "Unique", "dataType": "Int64", "isHidden": False},
            ],
        )
        rule = _make_rule(
            scope="Column",
            expression=(
                "Model.AllColumns.Any(Name == current.Name "
                "and Table.Name != current.Table.Name)"
            ),
        )
        v, skipped = BpaEvaluator().evaluate([rule], model)
        assert skipped == 0
        assert {x["object"] for x in v} == {"A[Dup]", "B[Dup]"}


# ---------------------------------------------------------------------------
# Test: type-aware scoping + DAX dependency graph
# ---------------------------------------------------------------------------


class TestTypeAwareScopingAndDependencies:
    def test_calculatedcolumn_scope_excludes_data_columns(self) -> None:
        """A rule scoped only to CalculatedColumn must not flag data columns."""
        b = _backend_with(
            tables=[{"name": "T", "isHidden": False}],
            columns=[
                {"table": "T", "name": "DataCol", "dataType": "Int64"},
                {"table": "T", "name": "CalcCol", "dataType": "Int64",
                 "columnType": "Calculated", "expression": "1+1"},
            ],
        )
        # string.IsNullOrWhitespace(Expression) flags expression-less objects;
        # scoped to CalculatedColumn it must only consider the calc column.
        rule = _make_rule(scope="CalculatedColumn",
                          expression="string.IsNullOrWhitespace(Expression)")
        v, skipped = BpaEvaluator().evaluate([rule], b)
        assert skipped == 0
        # CalcCol has an expression -> not flagged; DataCol is out of scope
        assert v == []

    def test_datacolumn_scope_excludes_calculated_columns(self) -> None:
        b = _backend_with(
            tables=[{"name": "T", "isHidden": False}],
            columns=[
                {"table": "T", "name": "DataCol", "dataType": "Int64",
                 "sourceColumn": "DataCol"},
                {"table": "T", "name": "CalcCol", "dataType": "Int64",
                 "columnType": "Calculated", "expression": "1+1"},
            ],
        )
        # DATA_COLUMNS_MUST_HAVE_A_SOURCE_COLUMN — only data columns are in scope.
        rule = _make_rule(scope="DataColumn",
                          expression="string.IsNullOrWhitespace(SourceColumn)")
        v, skipped = BpaEvaluator().evaluate([rule], b)
        assert skipped == 0
        assert v == []  # DataCol has a source column; CalcCol is out of scope

    def test_dependson_unqualified_column_reference(self) -> None:
        """DAX_COLUMNS_FULLY_QUALIFIED: flag measures referencing a column unqualified."""
        b = _backend_with(
            tables=[{"name": "Sales", "isHidden": False}],
            columns=[{"table": "Sales", "name": "Amount", "dataType": "Int64"}],
            measures=[
                {"table": "Sales", "name": "Good", "expression": "SUM(Sales[Amount])"},
                {"table": "Sales", "name": "Bad", "expression": "SUM([Amount])"},
            ],
        )
        rule = _make_rule(
            scope="Measure",
            expression='DependsOn.Any(Key.ObjectType = "Column" and Value.Any(not FullyQualified))',
        )
        v, skipped = BpaEvaluator().evaluate([rule], b)
        assert skipped == 0
        assert {x["object"] for x in v} == {"Sales[Bad]"}

    def test_calculation_group_scope(self) -> None:
        """Object-type scope wired from backend.calc_group_list()."""
        class B(MockTomBackend):
            def calc_group_list(self):
                return [
                    {"table": "CG Empty", "items": []},
                    {"table": "CG Full", "items": [{"name": "YTD", "expression": "X"}]},
                ]

        b = B()
        b.connect()
        rule = _make_rule(scope="CalculationGroup",
                          expression="CalculationItems.Count == 0")
        v, skipped = BpaEvaluator().evaluate([rule], b)
        assert skipped == 0
        assert {x["object"] for x in v} == {"CG Empty"}
