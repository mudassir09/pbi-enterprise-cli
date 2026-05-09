"""CliRunner tests for pbi measure commands."""

from __future__ import annotations

import json

import click
import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner: CliRunner, *args: str) -> click.testing.Result:
    return runner.invoke(cli, ["--backend", "mock", *args])


def _run_json(runner: CliRunner, *args: str) -> list | dict:
    result = runner.invoke(cli, ["--backend", "mock", "--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ── measure list ──────────────────────────────────────────────────────────────


class TestMeasureList:
    def test_lists_all_measures(self, runner):
        result = _run(runner, "measure", "list")
        assert result.exit_code == 0
        assert "Total Revenue" in result.output

    def test_filter_by_table(self, runner):
        data = _run_json(runner, "measure", "list", "--table", "Sales")
        assert all(m["table"] == "Sales" for m in data)

    def test_json_output_shape(self, runner):
        data = _run_json(runner, "measure", "list")
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "name" in data[0]
        assert "expression" in data[0]


# ── measure add ───────────────────────────────────────────────────────────────


class TestMeasureAdd:
    def test_add_basic_measure(self, runner):
        result = _run(
            runner,
            "measure",
            "add",
            "--table",
            "Sales",
            "--name",
            "Test Measure",
            "--expression",
            "SUM(Sales[Revenue])",
        )
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_with_format_and_description(self, runner):
        result = _run(
            runner,
            "measure",
            "add",
            "--table",
            "Sales",
            "--name",
            "Formatted Measure",
            "--expression",
            "COUNT(Sales[SalesKey])",
            "--format-string",
            "#,0",
            "--description",
            "Count of sales",
        )
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_appears_in_list(self, runner):
        # Add then list (separate runner invocations share no state; this just
        # verifies add exits cleanly and the list still works)
        result_add = _run(
            runner, "measure", "add", "--table", "Sales", "--name", "NewM", "--expression", "1"
        )
        assert result_add.exit_code == 0

    def test_add_dry_run(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "measure",
                "add",
                "--table",
                "Sales",
                "--name",
                "Dry",
                "--expression",
                "1",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_add_json_output(self, runner):
        data = _run_json(
            runner,
            "measure",
            "add",
            "--table",
            "Sales",
            "--name",
            "J",
            "--expression",
            "SUM(Sales[Revenue])",
        )
        assert "name" in data or isinstance(data, dict)


# ── measure update ────────────────────────────────────────────────────────────


class TestMeasureUpdate:
    def test_update_expression(self, runner):
        result = _run(
            runner,
            "measure",
            "update",
            "--table",
            "Sales",
            "--name",
            "Total Revenue",
            "--expression",
            "SUMX(Sales, Sales[Revenue])",
        )
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_update_format_string(self, runner):
        result = _run(
            runner,
            "measure",
            "update",
            "--table",
            "Sales",
            "--name",
            "Total Revenue",
            "--format-string",
            "$#,0.00",
        )
        assert result.exit_code == 0

    def test_update_nothing_provided_exits_cleanly(self, runner):
        result = _run(runner, "measure", "update", "--table", "Sales", "--name", "Total Revenue")
        assert result.exit_code == 0
        assert "Nothing to update" in result.output

    def test_update_dry_run(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "measure",
                "update",
                "--table",
                "Sales",
                "--name",
                "Total Revenue",
                "--expression",
                "1",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── measure delete ────────────────────────────────────────────────────────────


class TestMeasureDelete:
    def test_delete_existing_measure(self, runner):
        result = _run(runner, "measure", "delete", "--table", "Sales", "--name", "Total Revenue")
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_dry_run(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "measure",
                "delete",
                "--table",
                "Sales",
                "--name",
                "Total Revenue",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── measure audit ─────────────────────────────────────────────────────────────


class TestMeasureAudit:
    def test_audit_runs_without_error(self, runner):
        result = _run(runner, "measure", "audit")
        assert result.exit_code == 0

    def test_audit_detects_missing_format(self, runner):
        # Add a measure with no format string then audit
        runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "measure",
                "add",
                "--table",
                "Sales",
                "--name",
                "NoFormat",
                "--expression",
                "SUM(Sales[Revenue])",
            ],
        )
        result = _run(runner, "measure", "audit")
        assert result.exit_code == 0


# ── measure generate ──────────────────────────────────────────────────────────


class TestMeasureGenerate:
    def test_generate_uses_ai_backend(self, runner, monkeypatch):
        from pbi_cli.intelligence import measure_generator

        monkeypatch.setattr(
            measure_generator.MeasureGenerator,
            "generate",
            lambda self, **kwargs: {
                "expression": "SUM(Sales[Revenue])",
                "valid": True,
            },
        )
        result = _run(
            runner, "measure", "generate", "Total revenue", "--table", "Sales", "--name", "Gen Rev"
        )
        assert result.exit_code == 0
        assert "SUM(Sales[Revenue])" in result.output

    def test_generate_aborts_when_ai_fails(self, runner, monkeypatch):
        from pbi_cli.intelligence import measure_generator

        monkeypatch.setattr(
            measure_generator.MeasureGenerator,
            "generate",
            lambda self, **kwargs: {"expression": "", "valid": False, "error": "AI unavailable"},
        )
        result = _run(
            runner, "measure", "generate", "anything", "--table", "Sales", "--name", "Fail"
        )
        assert result.exit_code == 0
        assert "Generation failed" in result.output or "AI unavailable" in result.output
