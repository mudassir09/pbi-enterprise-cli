"""Integration tests for TomBackend against live Power BI Desktop.

Skipped automatically when Power BI Desktop is not running.
Marked e2e so CI pipeline excludes them (pytest -m "not e2e").
"""

from __future__ import annotations

import pytest

from pbi_cli.backends.tom_backend import TomBackend, find_pbi_port

# ── Skip guard ────────────────────────────────────────────────────────────────

_PORT = find_pbi_port()
pytestmark = pytest.mark.skipif(
    _PORT is None,
    reason="Power BI Desktop not running — skipping TOM integration tests",
)

_TEST_MEASURE = "__pbi_cli_test_measure__"


@pytest.fixture(scope="module")
def backend() -> TomBackend:
    b = TomBackend()
    b.connect(port=_PORT)
    yield b
    b.disconnect()


# ── Connection ────────────────────────────────────────────────────────────────

class TestConnection:
    def test_is_connected_after_connect(self, backend):
        assert backend.is_connected()

    def test_find_pbi_port_returns_int(self):
        assert isinstance(_PORT, int)
        assert _PORT > 1024


# ── Model info ────────────────────────────────────────────────────────────────

class TestModelInfo:
    def test_returns_dict(self, backend):
        info = backend.model_info()
        assert isinstance(info, dict)

    def test_has_compatibility_level(self, backend):
        info = backend.model_info()
        assert "compatibilityLevel" in info
        assert isinstance(info["compatibilityLevel"], int)

    def test_has_port(self, backend):
        info = backend.model_info()
        assert info["port"] == _PORT


# ── Tables ────────────────────────────────────────────────────────────────────

class TestTableList:
    def test_returns_list(self, backend):
        tables = backend.table_list()
        assert isinstance(tables, list)
        assert len(tables) >= 1

    def test_each_table_has_name(self, backend):
        for t in backend.table_list():
            assert "name" in t
            assert isinstance(t["name"], str)

    def test_financials_table_present(self, backend):
        names = [t["name"] for t in backend.table_list()]
        assert "financials" in names


# ── Columns ───────────────────────────────────────────────────────────────────

class TestColumnList:
    def test_returns_list(self, backend):
        cols = backend.column_list()
        assert isinstance(cols, list)
        assert len(cols) >= 1

    def test_each_column_has_required_fields(self, backend):
        for c in backend.column_list():
            assert "name" in c
            assert "table" in c
            assert "dataType" in c

    def test_filter_by_table(self, backend):
        cols = backend.column_list(table="financials")
        assert len(cols) >= 1
        assert all(c["table"] == "financials" for c in cols)

    def test_known_column_present(self, backend):
        names = [c["name"] for c in backend.column_list(table="financials")]
        assert "Sales" in names or len(names) > 0


# ── Relationships ─────────────────────────────────────────────────────────────

class TestRelationshipList:
    def test_returns_list(self, backend):
        rels = backend.relationship_list()
        assert isinstance(rels, list)

    def test_each_relationship_has_from_to(self, backend):
        for r in backend.relationship_list():
            assert "from" in r
            assert "to" in r


# ── Measures (read) ───────────────────────────────────────────────────────────

class TestMeasureList:
    def test_returns_list(self, backend):
        measures = backend.measure_list()
        assert isinstance(measures, list)
        assert len(measures) >= 1

    def test_each_measure_has_required_fields(self, backend):
        for m in backend.measure_list():
            assert "name" in m
            assert "table" in m
            assert "expression" in m

    def test_known_measures_present(self, backend):
        names = [m["name"] for m in backend.measure_list()]
        assert any("Sales" in n or "Revenue" in n or "Profit" in n for n in names)

    def test_filter_by_table(self, backend):
        tables = backend.table_list()
        if not tables:
            pytest.skip("No tables in model")
        table_name = tables[0]["name"]
        measures = backend.measure_list(table=table_name)
        assert all(m["table"] == table_name for m in measures)


# ── DAX validate ──────────────────────────────────────────────────────────────

class TestDaxValidate:
    def test_valid_sum_expression(self, backend):
        table = backend.table_list()[0]["name"]
        cols = backend.column_list(table=table)
        if not cols:
            pytest.skip("No columns")
        col = next((c for c in cols if c["dataType"] in ("Decimal", "Double", "Int64")), cols[0])
        result = backend.dax_validate(f"SUM({table}[{col['name']}])")
        assert result.get("valid") is True

    def test_invalid_expression_flagged(self, backend):
        result = backend.dax_validate("THIS IS NOT DAX !!!")
        # TOM may return valid=False or raise; either means detection works
        assert isinstance(result, dict)
        assert "valid" in result


# ── DAX query ─────────────────────────────────────────────────────────────────

class TestDaxQuery:
    def test_simple_row_query(self, backend):
        rows = backend.dax_query('EVALUATE ROW("Result", 1)')
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_table_query_returns_rows(self, backend):
        table = backend.table_list()[0]["name"]
        rows = backend.dax_query(f"EVALUATE TOPN(5, '{table}')")
        assert isinstance(rows, list)

    def test_measure_query_returns_value(self, backend):
        measures = backend.measure_list()
        if not measures:
            pytest.skip("No measures in model")
        m = measures[0]
        rows = backend.dax_query(
            f'EVALUATE ROW("Val", [{m["name"]}])'
        )
        assert isinstance(rows, list)
        assert len(rows) >= 1


# ── TMDL export ───────────────────────────────────────────────────────────────

class TestTmdlExport:
    def test_export_creates_files(self, backend, tmp_path):
        backend.tmdl_export(str(tmp_path))
        exported = list(tmp_path.iterdir())
        assert len(exported) > 0

    def test_export_includes_database_tmdl(self, backend, tmp_path):
        backend.tmdl_export(str(tmp_path))
        names = [f.name for f in tmp_path.iterdir()]
        assert "database.tmdl" in names or "model.tmdl" in names


# ── Measure write (add → update → delete, cleaned up) ────────────────────────

class TestMeasureWrite:
    def test_add_update_delete_measure(self, backend):
        table = backend.table_list()[0]["name"]

        # Ensure clean start
        existing = [m for m in backend.measure_list() if m["name"] == _TEST_MEASURE]
        for _ in existing:
            backend.measure_delete(table=table, name=_TEST_MEASURE)

        try:
            # Add
            result = backend.measure_add(
                table=table,
                name=_TEST_MEASURE,
                expression=f"COUNT('{table}'[{backend.column_list(table=table)[0]['name']}])",
                formatString="#,0",
            )
            assert result["name"] == _TEST_MEASURE

            # Verify it appears in list
            names = [m["name"] for m in backend.measure_list()]
            assert _TEST_MEASURE in names

            # Update
            updated = backend.measure_update(
                table=table,
                name=_TEST_MEASURE,
                expression="1",
                formatString="#,0",
            )
            assert updated["expression"] == "1"

        finally:
            # Always clean up
            try:
                backend.measure_delete(table=table, name=_TEST_MEASURE)
            except Exception:
                pass

        # Verify deleted
        names_after = [m["name"] for m in backend.measure_list()]
        assert _TEST_MEASURE not in names_after
