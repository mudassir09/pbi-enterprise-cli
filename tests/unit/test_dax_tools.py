"""Tests for the DAX formatter and linter."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.dax_tools import format_dax, lint_expression, lint_measures, tokenize


@pytest.fixture()
def runner():
    return CliRunner()


class TestTokenizer:
    def test_basic_tokens(self):
        kinds = [k for k, _ in tokenize("SUM(Sales[Revenue]) + 1")]
        assert kinds == ["ident", "punct", "ident", "bracket", "punct", "op", "number"]

    def test_strings_and_comments_preserved(self):
        toks = tokenize('IF(TRUE(), "a,b") // trailing')
        assert ("string", '"a,b"') in toks
        assert any(k == "comment" for k, _ in toks)

    def test_quoted_table_names(self):
        toks = tokenize("'Sales Data'[Revenue]")
        assert toks[0] == ("table", "'Sales Data'")


class TestFormatter:
    def test_uppercases_functions_and_keywords(self):
        out = format_dax("sum(Sales[Revenue])")
        assert out.startswith("SUM")

    def test_short_expression_stays_one_line(self):
        out = format_dax("SUM(Sales[Revenue])")
        assert "\n" not in out

    def test_long_expression_breaks_args(self):
        expr = ("CALCULATE(SUM(Sales[Revenue]), FILTER(ALL(Calendar), "
                "Calendar[Year] = 2024 && Calendar[Month] >= 6), KEEPFILTERS(Products[Category] = \"Bikes\"))")  # noqa: E501
        out = format_dax(expr, width=60)
        assert "\n" in out
        assert out.startswith("CALCULATE (")

    def test_var_return_structure(self):
        out = format_dax("VAR x = SUM(Sales[Revenue]) RETURN x * 2")
        lines = out.splitlines()
        assert lines[0].startswith("VAR x")
        assert any(line == "RETURN" or line.startswith("RETURN") for line in lines)

    def test_idempotent(self):
        expr = "DIVIDE(SUM(Sales[Revenue]), SUM(Sales[Units]))"
        once = format_dax(expr)
        assert format_dax(once) == once


class TestLinter:
    def test_division_operator(self):
        rules = {v["rule"] for v in lint_expression("M", "SUM(Sales[A]) / SUM(Sales[B])")}
        assert "dax.division-operator" in rules

    def test_divide_function_ok(self):
        rules = {v["rule"] for v in lint_expression("M", "DIVIDE(SUM(Sales[A]), SUM(Sales[B]))")}
        assert "dax.division-operator" not in rules

    def test_division_in_comment_ignored(self):
        rules = {v["rule"] for v in lint_expression("M", "SUM(Sales[A]) // per-unit / ratio")}
        assert "dax.division-operator" not in rules

    def test_iferror_and_earlier(self):
        rules = {v["rule"] for v in lint_expression(
            "M", "IFERROR(EARLIER(Sales[A]), 0)")}
        assert {"dax.iferror", "dax.earlier"} <= rules

    def test_nested_if(self):
        expr = "IF(a, IF(b, IF(c, 1, 2), 3), 4)"
        rules = {v["rule"] for v in lint_expression("M", expr)}
        assert "dax.nested-if" in rules

    def test_volatile_and_hardcoded_year(self):
        rules = {v["rule"] for v in lint_expression(
            "M", "IF(YEAR(TODAY()) = 2024, 1, 0)")}
        assert {"dax.volatile-function", "dax.hardcoded-year"} <= rules

    def test_year_inside_column_ref_not_flagged(self):
        rules = {v["rule"] for v in lint_expression("M", "SUM(Sales[Revenue2024])")}
        assert "dax.hardcoded-year" not in rules

    def test_unqualified_aggregator(self):
        rules = {v["rule"] for v in lint_expression("M", "SUM([Revenue])")}
        assert "dax.unqualified-aggregator" in rules

    def test_calculate_filter_table(self):
        expr = "CALCULATE(SUM(Sales[A]), FILTER(Sales, Sales[B] > 0))"
        rules = {v["rule"] for v in lint_expression("M", expr)}
        assert "dax.calculate-filter-table" in rules

    def test_iterator_over_filter(self):
        expr = "SUMX(FILTER(Sales, Sales[B] > 0), Sales[A])"
        rules = {v["rule"] for v in lint_expression("M", expr)}
        assert "dax.iterator-over-filter" in rules

    def test_qualified_measure_ref(self):
        violations = lint_measures([
            {"table": "Sales", "name": "Total", "expression": "SUM(Sales[A])"},
            {"table": "Sales", "name": "Double", "expression": "Sales[Total] * 2"},
        ])
        assert any(v["rule"] == "dax.qualified-measure-ref" for v in violations)

    def test_clean_expression_no_violations(self):
        assert lint_expression("M", "SUM(Sales[Revenue])") == []


class TestCli:
    def test_format_expression(self, runner):
        result = runner.invoke(cli, ["dax", "format", "-e", "sum(Sales[Revenue])"])
        assert result.exit_code == 0
        assert "SUM" in result.output

    def test_lint_mock_backend_json(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--json", "dax", "lint"])
        assert result.exit_code == 0
        json.loads(result.output)

    def test_lint_fail_on_warning(self, runner):
        result = runner.invoke(
            cli, ["dax", "lint", "-e", "A / B", "--fail-on", "warning"]
        )
        assert result.exit_code == 3

    def test_format_check_mode(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "dax", "format", "--check"])
        assert result.exit_code in (0, 1)

    def test_coverage_against_fixture_suite(self, runner):
        result = runner.invoke(
            cli,
            ["--backend", "mock", "--json", "dax", "coverage",
             "--suite", "tests/fixtures/measures/sales_suite.yaml"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["measures"] == 2
        assert data["coverage_pct"] == 100
