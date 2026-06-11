"""Tests for the TMDL/PBIP file backend."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.backends.file_backend import FileBackend, parse_tmdl, resolve_definition_dir
from pbi_cli.cli import cli

SALES_TMDL = """\
/// Fact table for sales transactions
table Sales

    measure 'Total Revenue' = SUM(Sales[Revenue])
        formatString: #,0.00

    /// Year-to-date revenue
    measure 'Revenue YTD' =
            TOTALYTD(
                [Total Revenue],
                'Calendar'[Date]
            )
        formatString: #,0.00
        displayFolder: Time Intelligence

    measure 'Units Fenced' = ```
            SUM(Sales[Units])
            ```

    column SalesKey
        dataType: int64
        isHidden
        sourceColumn: SalesKey

    column Revenue
        dataType: decimal
        sourceColumn: Revenue

    hierarchy 'Product Drill'
        level Category
            column: Category
        level Product
            column: ProductName

    partition Sales = m
        mode: import
        source =
                let
                    Source = Sql.Database("srv", "db")
                in
                    Source
"""

CALENDAR_TMDL = """\
table Calendar

    column Date
        dataType: dateTime
        sourceColumn: Date

    column Year
        dataType: int64
        sourceColumn: Year
"""

RELATIONSHIPS_TMDL = """\
relationship a1b2c3
    fromColumn: Sales.DateKey
    toColumn: Calendar.DateKey

relationship d4e5f6
    isActive: false
    fromColumn: Sales.ProductKey
    toColumn: 'Product Catalog'.ProductKey
"""

ROLE_TMDL = """\
role Regional
    modelPermission: read

    tablePermission Sales = Sales[Region] = "West"
"""

MODEL_TMDL = """\
model Model
    culture: en-US
"""

DATABASE_TMDL = """\
database
    compatibilityLevel: 1601
"""


@pytest.fixture()
def tmdl_project(tmp_path):
    d = tmp_path / "Demo.SemanticModel" / "definition"
    (d / "tables").mkdir(parents=True)
    (d / "roles").mkdir()
    (d / "model.tmdl").write_text(MODEL_TMDL, encoding="utf-8")
    (d / "database.tmdl").write_text(DATABASE_TMDL, encoding="utf-8")
    (d / "tables" / "Sales.tmdl").write_text(SALES_TMDL, encoding="utf-8")
    (d / "tables" / "Calendar.tmdl").write_text(CALENDAR_TMDL, encoding="utf-8")
    (d / "relationships.tmdl").write_text(RELATIONSHIPS_TMDL, encoding="utf-8")
    (d / "roles" / "Regional.tmdl").write_text(ROLE_TMDL, encoding="utf-8")
    return tmp_path


class TestParser:
    def test_parses_declarations_and_props(self):
        roots = parse_tmdl(SALES_TMDL)
        assert len(roots) == 1
        table = roots[0]
        assert table.keyword == "table"
        assert table.name == "Sales"
        assert table.description == "Fact table for sales transactions"
        measures = [c for c in table.children if c.keyword == "measure"]
        assert [m.name for m in measures] == ["Total Revenue", "Revenue YTD", "Units Fenced"]

    def test_inline_expression(self):
        table = parse_tmdl(SALES_TMDL)[0]
        m = next(c for c in table.children if c.name == "Total Revenue")
        assert m.expression == "SUM(Sales[Revenue])"
        assert m.props["formatString"] == "#,0.00"

    def test_multiline_expression(self):
        table = parse_tmdl(SALES_TMDL)[0]
        m = next(c for c in table.children if c.name == "Revenue YTD")
        assert "TOTALYTD(" in m.expression
        assert "'Calendar'[Date]" in m.expression
        assert m.props["displayFolder"] == "Time Intelligence"
        assert m.description == "Year-to-date revenue"

    def test_fenced_expression(self):
        table = parse_tmdl(SALES_TMDL)[0]
        m = next(c for c in table.children if c.name == "Units Fenced")
        assert m.expression == "SUM(Sales[Units])"

    def test_boolean_flag_property(self):
        table = parse_tmdl(SALES_TMDL)[0]
        col = next(c for c in table.children if c.keyword == "column" and c.name == "SalesKey")
        assert col.props["isHidden"] == "true"
        assert col.props["dataType"] == "int64"


class TestFileBackend:
    def test_resolves_semantic_model_dir(self, tmdl_project):
        d = resolve_definition_dir(tmdl_project)
        assert d.name == "definition"

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_definition_dir(tmp_path)

    def test_model_info(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        info = b.model_info()
        assert info["compatibility_level"] == 1601

    def test_tables_columns_measures(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        assert {t["name"] for t in b.table_list()} == {"Sales", "Calendar"}
        assert len(b.column_list("Sales")) == 2
        measures = b.measure_list()
        assert len(measures) == 3
        ytd = next(m for m in measures if m["name"] == "Revenue YTD")
        assert ytd["displayFolder"] == "Time Intelligence"

    def test_relationships(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        rels = b.relationship_list()
        assert {"from": "Sales[DateKey]", "to": "Calendar[DateKey]",
                "cardinality": "ManyToOne", "isActive": True} in rels
        inactive = next(r for r in rels if not r["isActive"])
        assert inactive["to"] == "Product Catalog[ProductKey]"

    def test_roles_and_partitions_and_hierarchies(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        roles = b.role_list()
        assert roles[0]["name"] == "Regional"
        assert roles[0]["tablePermissions"][0]["filterExpression"] == 'Sales[Region] = "West"'
        parts = b.partition_list("Sales")
        assert parts and parts[0]["mode"] == "import"
        assert "Sql.Database" in parts[0]["source"]
        hier = b.hierarchy_list("Sales")
        assert hier[0]["name"] == "Product Drill"
        assert [lv["name"] for lv in hier[0]["levels"]] == ["Category", "Product"]

    def test_measure_add_persists(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        b.measure_add("Sales", "Avg Price", "DIVIDE([Total Revenue], SUM(Sales[Units]))",
                      formatString="#,0.00")
        b2 = FileBackend(path=tmdl_project)
        names = [m["name"] for m in b2.measure_list("Sales")]
        assert "Avg Price" in names

    def test_measure_update_persists(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        b.measure_update("Sales", "Total Revenue", expression="SUMX(Sales, Sales[Revenue])")
        b2 = FileBackend(path=tmdl_project)
        m = next(x for x in b2.measure_list("Sales") if x["name"] == "Total Revenue")
        assert m["expression"] == "SUMX(Sales, Sales[Revenue])"

    def test_measure_delete_persists(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        b.measure_delete("Sales", "Revenue YTD")
        b2 = FileBackend(path=tmdl_project)
        names = [m["name"] for m in b2.measure_list("Sales")]
        assert "Revenue YTD" not in names
        # The other measures survive the block surgery
        assert "Total Revenue" in names and "Units Fenced" in names

    def test_dax_query_not_supported(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        with pytest.raises(NotImplementedError):
            b.dax_query("EVALUATE Sales")

    def test_dax_validate_static(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        assert b.dax_validate("SUM(Sales[Revenue])")["valid"]
        assert not b.dax_validate("SUM(Sales[Revenue]")["valid"]


class TestFileBackendCli:
    def test_model_tables_via_cli(self, tmdl_project):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--backend", "file", "--path", str(tmdl_project), "--json", "model", "tables"]
        )
        assert result.exit_code == 0
        names = {t["name"] for t in json.loads(result.output)}
        assert names == {"Sales", "Calendar"}

    def test_govern_check_via_cli(self, tmdl_project):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--backend", "file", "--path", str(tmdl_project), "--json", "govern", "check"]
        )
        assert result.exit_code in (0, 3)  # violations are fine; crash is not

    def test_bad_path_aborts(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--backend", "file", "--path", str(tmp_path), "model", "tables"]
        )
        assert result.exit_code != 0
