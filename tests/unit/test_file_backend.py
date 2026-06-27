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
        date_rel = next(
            r for r in rels
            if r["from"] == "Sales[DateKey]" and r["to"] == "Calendar[DateKey]"
        )
        assert date_rel["cardinality"] == "ManyToOne"
        assert date_rel["isActive"] is True
        assert date_rel["crossFilteringBehavior"] == "OneDirection"
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

    def test_structural_writes_persist(self, tmdl_project):
        # Structural edits are now serialised back to TMDL and survive a reload.
        b = FileBackend(path=tmdl_project)
        b.column_add("Sales", "Margin", "decimal")
        b.partition_add("Sales", "p2", "let Source = 1 in Source")
        b.role_add("Auditor", "Sales", 'Sales[Region] = "East"')
        b.relationship_add("Sales", "DateKey", "Calendar", "DateKey",
                            crossFilteringBehavior="bothDirections")

        b2 = FileBackend(path=tmdl_project)
        assert any(c["name"] == "Margin" for c in b2.column_list("Sales"))
        assert any(p["name"] == "p2" for p in b2.partition_list("Sales"))
        assert any(r["name"] == "Auditor" for r in b2.role_list())
        assert any(
            r["from"] == "Sales[DateKey]" and r["to"] == "Calendar[DateKey]"
            and r["crossFilteringBehavior"] == "bothDirections"
            for r in b2.relationship_list()
        )

    def test_partition_refresh_still_fails_loud(self, tmdl_project):
        # No engine to process data — refresh must raise, not pretend success.
        b = FileBackend(path=tmdl_project)
        with pytest.raises(NotImplementedError):
            b.partition_refresh("Sales", "Sales")

    def test_table_add_persists_and_syncs_ref(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        d = tmdl_project / "Demo.SemanticModel" / "definition"
        b.table_add("Ghost")
        assert (d / "tables" / "Ghost.tmdl").exists()
        # model.tmdl gains the ref table line (TMDL does not auto-discover files).
        assert "ref table Ghost" in (d / "model.tmdl").read_text(encoding="utf-8")
        assert "Ghost" in {t["name"] for t in FileBackend(path=tmdl_project).table_list()}

    def test_table_delete_removes_file_and_ref(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        d = tmdl_project / "Demo.SemanticModel" / "definition"
        b.table_add("Ghost")
        b.table_delete("Ghost")
        assert not (d / "tables" / "Ghost.tmdl").exists()
        assert "ref table Ghost" not in (d / "model.tmdl").read_text(encoding="utf-8")

    def test_column_delete_persists(self, tmdl_project):
        b = FileBackend(path=tmdl_project)
        b.column_delete("Sales", "Revenue")
        names = [c["name"] for c in FileBackend(path=tmdl_project).column_list("Sales")]
        assert "Revenue" not in names and "SalesKey" in names

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

    def test_source_scaffold_persists_on_file_backend(self, tmdl_project):
        # `source scaffold` materialises tables via backend.table_add — now
        # persisted to TMDL on the file backend.
        profile = tmdl_project / "profile.json"
        profile.write_text(
            json.dumps(
                [
                    {
                        "tableName": "FactOrders",
                        "rowCount": 1000,
                        "columns": [
                            {"name": "OrderKey", "dataType": "int64"},
                            {"name": "Amount", "dataType": "decimal"},
                        ],
                    },
                    {
                        "tableName": "DimDate",
                        "rowCount": 365,
                        "columns": [{"name": "DateKey", "dataType": "int64"}],
                    },
                ]
            ),
            encoding="utf-8",
        )
        d = tmdl_project / "Demo.SemanticModel" / "definition"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--backend", "file", "--path", str(tmdl_project),
             "source", "scaffold", "--profile", str(profile)],
        )

        assert result.exit_code == 0
        # Tables were materialised to disk and ref-table lines added to model.tmdl.
        assert (d / "tables" / "FactOrders.tmdl").exists()
        assert (d / "tables" / "DimDate.tmdl").exists()
        model_text = (d / "model.tmdl").read_text(encoding="utf-8")
        assert "ref table FactOrders" in model_text and "ref table DimDate" in model_text
        # Re-parsing the project sees the scaffolded tables and their columns.
        b = FileBackend(path=tmdl_project)
        assert {"FactOrders", "DimDate"}.issubset({t["name"] for t in b.table_list()})
        assert {c["name"] for c in b.column_list("FactOrders")} == {"OrderKey", "Amount"}
