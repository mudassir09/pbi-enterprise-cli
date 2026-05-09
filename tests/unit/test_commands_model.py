"""CliRunner tests for pbi model commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


def _run_json(runner, *args):
    result = runner.invoke(cli, ["--backend", "mock", "--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ── model info ────────────────────────────────────────────────────────────────


class TestModelInfo:
    def test_returns_model_name(self, runner):
        result = _run(runner, "model", "info")
        assert result.exit_code == 0
        assert "MockModel" in result.output

    def test_json_output(self, runner):
        data = _run_json(runner, "model", "info")
        assert isinstance(data, dict)
        assert "name" in data


# ── model tables ──────────────────────────────────────────────────────────────


class TestModelTables:
    def test_lists_tables(self, runner):
        result = _run(runner, "model", "tables")
        assert result.exit_code == 0
        assert "Sales" in result.output

    def test_json_returns_list(self, runner):
        data = _run_json(runner, "model", "tables")
        assert isinstance(data, list)
        assert len(data) == 4


# ── model columns ─────────────────────────────────────────────────────────────


class TestModelColumns:
    def test_lists_all_columns(self, runner):
        result = _run(runner, "model", "columns")
        assert result.exit_code == 0
        assert "Revenue" in result.output

    def test_filter_by_table(self, runner):
        data = _run_json(runner, "model", "columns", "--table", "Sales")
        assert all(c["table"] == "Sales" for c in data)

    def test_columns_have_data_type(self, runner):
        data = _run_json(runner, "model", "columns")
        for col in data:
            assert "dataType" in col


# ── model relationships ───────────────────────────────────────────────────────


class TestModelRelationships:
    def test_lists_relationships(self, runner):
        result = _run(runner, "model", "relationships")
        assert result.exit_code == 0

    def test_json_has_from_and_to(self, runner):
        data = _run_json(runner, "model", "relationships")
        assert len(data) == 3
        assert all("from" in r and "to" in r for r in data)


# ── model lint ────────────────────────────────────────────────────────────────


class TestModelLint:
    def test_lint_runs_without_error(self, runner):
        result = _run(runner, "model", "lint")
        assert result.exit_code == 0


# ── model suggest-measures ────────────────────────────────────────────────────


class TestModelSuggestMeasures:
    def test_returns_suggestions(self, runner):
        result = _run(runner, "model", "suggest-measures")
        assert result.exit_code == 0

    def test_json_returns_list(self, runner):
        data = _run_json(runner, "model", "suggest-measures")
        assert isinstance(data, list)
        assert len(data) > 0

    def test_each_suggestion_has_name_and_expression(self, runner):
        data = _run_json(runner, "model", "suggest-measures")
        for s in data:
            assert "name" in s
            assert "expression" in s


# ── model lineage ─────────────────────────────────────────────────────────────


class TestModelLineage:
    def test_json_format(self, runner):
        result = _run(runner, "model", "lineage", "--format", "json")
        assert result.exit_code == 0

    def test_mermaid_format(self, runner):
        result = _run(runner, "model", "lineage", "--format", "mermaid")
        assert result.exit_code == 0
        assert "graph TD" in result.output
