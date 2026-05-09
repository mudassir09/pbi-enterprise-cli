"""CliRunner tests for pbi dax commands."""

from __future__ import annotations

import json

import pytest
import yaml
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


# ── dax query ─────────────────────────────────────────────────────────────────


class TestDaxQuery:
    def test_query_runs(self, runner):
        result = _run(runner, "dax", "query", "EVALUATE VALUES(Sales)")
        assert result.exit_code == 0

    def test_query_json_output(self, runner):
        result = runner.invoke(
            cli, ["--backend", "mock", "--json", "dax", "query", 'EVALUATE ROW("x", 1)']
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ── dax validate ──────────────────────────────────────────────────────────────


class TestDaxValidate:
    def test_valid_expression(self, runner):
        result = _run(runner, "dax", "validate", "SUM(Sales[Revenue])")
        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_invalid_expression_shown(self, runner, monkeypatch):
        from pbi_cli.backends import mock_backend

        monkeypatch.setattr(
            mock_backend.MockTomBackend,
            "dax_validate",
            lambda self, expr: {"valid": False, "error": "Unknown column 'X'"},
        )
        result = _run(runner, "dax", "validate", "SUM(X[Y])")
        assert result.exit_code == 0
        assert "Invalid" in result.output
        assert "Unknown column" in result.output


# ── dax test ──────────────────────────────────────────────────────────────────


class TestDaxTest:
    def _write_suite(self, tmp_path, tests: list) -> str:
        suite_file = tmp_path / "suite.yaml"
        suite_file.write_text(yaml.dump({"tests": tests}), encoding="utf-8")
        return str(suite_file)

    def test_passing_row_count(self, runner, tmp_path):
        suite = self._write_suite(
            tmp_path,
            [
                {
                    "name": "row count check",
                    "dax": "EVALUATE VALUES(Sales[SalesKey])",
                    "assert": [{"row_count": 1}],  # mock returns 1 row
                }
            ],
        )
        result = _run(runner, "dax", "test", "--suite", suite)
        assert "1 passed" in result.output

    def test_failing_row_count_exits_nonzero(self, runner, tmp_path):
        suite = self._write_suite(
            tmp_path,
            [
                {
                    "name": "fail",
                    "dax": "EVALUATE VALUES(Sales[SalesKey])",
                    "assert": [{"row_count": 99}],  # mock returns 1
                }
            ],
        )
        result = _run(runner, "dax", "test", "--suite", suite)
        assert result.exit_code == 1
        assert "0 passed" in result.output
        assert "1 failed" in result.output

    def test_min_rows_pass(self, runner, tmp_path):
        suite = self._write_suite(
            tmp_path,
            [
                {
                    "name": "min rows",
                    "dax": "EVALUATE VALUES(Sales[SalesKey])",
                    "assert": [{"min_rows": 1}],
                }
            ],
        )
        result = _run(runner, "dax", "test", "--suite", suite)
        assert "1 passed" in result.output

    def test_max_rows_fail(self, runner, tmp_path):
        suite = self._write_suite(
            tmp_path,
            [
                {
                    "name": "max rows fail",
                    "dax": "EVALUATE VALUES(Sales[SalesKey])",
                    "assert": [{"max_rows": 0}],
                }
            ],
        )
        result = _run(runner, "dax", "test", "--suite", suite)
        assert result.exit_code == 1

    def test_not_blank_assertion(self, runner, tmp_path):
        suite = self._write_suite(
            tmp_path,
            [
                {
                    "name": "not blank",
                    "dax": "EVALUATE VALUES(Sales[SalesKey])",
                    "assert": [{"column": "__result", "not_blank": True}],
                }
            ],
        )
        result = _run(runner, "dax", "test", "--suite", suite)
        assert result.exit_code == 0

    def test_empty_tests_list(self, runner, tmp_path):
        suite = self._write_suite(tmp_path, [])
        result = _run(runner, "dax", "test", "--suite", suite)
        assert result.exit_code == 0
        assert "0 passed, 0 failed" in result.output
