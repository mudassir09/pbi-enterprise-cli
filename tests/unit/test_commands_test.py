"""Tests for the pbi test group: data, schema, rls, seed."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.commands.test_cmd import _compile_data_test


@pytest.fixture()
def runner():
    return CliRunner()


class TestDataTestCompiler:
    def test_row_count(self):
        desc, dax = _compile_data_test({"table": "Sales", "row_count": {"min": 1}})
        assert "COUNTROWS(Sales)" in dax

    def test_not_null(self):
        _, dax = _compile_data_test({"type": "not_null", "table": "Sales", "column": "Revenue"})
        assert "ISBLANK(Sales[Revenue])" in dax

    def test_unique(self):
        _, dax = _compile_data_test(
            {"type": "unique", "table": "Customers", "column": "CustomerKey"})
        assert "DISTINCTCOUNT(Customers[CustomerKey])" in dax

    def test_accepted_values_quotes_strings(self):
        _, dax = _compile_data_test({
            "type": "accepted_values", "table": "Products", "column": "Category",
            "values": ["Bikes", 7]})
        assert '"Bikes"' in dax and "7" in dax

    def test_relationship(self):
        _, dax = _compile_data_test({
            "type": "relationship", "table": "Sales", "column": "ProductKey",
            "to_table": "Products", "to_column": "ProductKey"})
        assert "VALUES(Products[ProductKey])" in dax

    def test_quoted_table_names(self):
        _, dax = _compile_data_test({"table": "Sales Data", "row_count": 5})
        assert "'Sales Data'" in dax


class TestDataSuite:
    def test_suite_pass_and_fail(self, runner, tmp_path):
        suite = tmp_path / "suite.yaml"
        suite.write_text(
            "tests:\n"
            "  - {table: Sales, row_count: 3}\n"
            "  - {type: not_null, table: Sales, column: Revenue}\n",
            encoding="utf-8",
        )

        def fake_query(self, expression):
            if "COUNTROWS(Sales)" in expression and "ISBLANK" not in expression:
                return [{"result": 3}]
            return [{"result": 2}]  # 2 blanks → fail

        with patch("pbi_cli.backends.mock_backend.MockTomBackend.dax_query", fake_query):
            result = runner.invoke(
                cli, ["--backend", "mock", "--json", "test", "data", "--suite", str(suite)])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 1

    def test_all_pass_exit_zero(self, runner, tmp_path):
        suite = tmp_path / "suite.yaml"
        suite.write_text("tests:\n  - {type: unique, table: Sales, column: SalesKey}\n",
                         encoding="utf-8")
        with patch("pbi_cli.backends.mock_backend.MockTomBackend.dax_query",
                   lambda self, e: [{"result": 0}]):
            result = runner.invoke(
                cli, ["--backend", "mock", "test", "data", "--suite", str(suite)])
        assert result.exit_code == 0


class TestSchemaContract:
    def test_contract_pass(self, runner, tmp_path):
        contract = tmp_path / "contract.yaml"
        contract.write_text(
            "tables:\n"
            "  Sales:\n"
            "    columns:\n"
            "      Revenue: {dataType: decimal}\n"
            "    measures: [\"Total Revenue\"]\n"
            "  Calendar: {}\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli, ["--backend", "mock", "test", "schema", "--contract", str(contract)])
        assert result.exit_code == 0, result.output

    def test_contract_missing_table_fails(self, runner, tmp_path):
        contract = tmp_path / "contract.yaml"
        contract.write_text("tables:\n  Nonexistent: {}\n", encoding="utf-8")
        result = runner.invoke(
            cli, ["--backend", "mock", "--json", "test", "schema",
                  "--contract", str(contract)])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["summary"]["failed"] == 1

    def test_contract_wrong_type_fails(self, runner, tmp_path):
        contract = tmp_path / "contract.yaml"
        contract.write_text(
            "tables:\n  Sales:\n    columns:\n      Revenue: {dataType: string}\n",
            encoding="utf-8")
        result = runner.invoke(
            cli, ["--backend", "mock", "test", "schema", "--contract", str(contract)])
        assert result.exit_code == 1


class TestRlsMatrix:
    def test_matrix_with_mock_roles(self, runner, tmp_path):
        matrix = tmp_path / "rls.yaml"
        matrix.write_text(
            "personas:\n"
            "  - role: Regional\n"
            "    tests:\n"
            "      - {dax: \"EVALUATE VALUES(Sales[Region])\", row_count: 1}\n",
            encoding="utf-8",
        )
        # Mock backend role_test returns rowCount=1; add the role first via fixture
        from pbi_cli.backends.mock_backend import MockTomBackend

        with patch.object(MockTomBackend, "role_list",
                          lambda self: [{"name": "Regional"}]):
            result = runner.invoke(
                cli, ["--backend", "mock", "test", "rls", "--matrix", str(matrix)])
        assert result.exit_code == 0, result.output

    def test_unknown_role_fails(self, runner, tmp_path):
        matrix = tmp_path / "rls.yaml"
        matrix.write_text("personas:\n  - role: Ghost\n    tests: []\n", encoding="utf-8")
        from pbi_cli.backends.mock_backend import MockTomBackend

        with patch.object(MockTomBackend, "role_list", lambda self: [{"name": "Real"}]):
            result = runner.invoke(
                cli, ["--backend", "mock", "test", "rls", "--matrix", str(matrix)])
        assert result.exit_code == 1


class TestSeed:
    def test_seed_writes_fixture(self, runner, tmp_path):
        out = tmp_path / "fixture.json"
        result = runner.invoke(
            cli, ["--backend", "mock", "test", "seed", "--rows", "5",
                  "--output", str(out)])
        assert result.exit_code == 0, result.output
        fixture = json.loads(out.read_text(encoding="utf-8"))
        assert len(fixture["rows"]["Sales"]) == 5
        # Key columns are sequential, data columns vary
        keys = [r["SalesKey"] for r in fixture["rows"]["Sales"]]
        assert keys == [1, 2, 3, 4, 5]

    def test_seed_deterministic(self, runner, tmp_path):
        out1, out2 = tmp_path / "f1.json", tmp_path / "f2.json"
        for out in (out1, out2):
            runner.invoke(cli, ["--backend", "mock", "test", "seed", "--rows", "3",
                                "--output", str(out)])
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
