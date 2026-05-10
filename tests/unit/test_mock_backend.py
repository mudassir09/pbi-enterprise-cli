"""Unit tests for MockTomBackend."""

import pytest

from pbi_cli.backends.mock_backend import MockTomBackend


def test_connect_and_disconnect():
    backend = MockTomBackend()
    assert not backend.is_connected()
    backend.connect()
    assert backend.is_connected()
    backend.disconnect()
    assert not backend.is_connected()


def test_measure_list_default_fixture():
    backend = MockTomBackend()
    backend.connect()
    measures = backend.measure_list()
    assert len(measures) == 2
    assert measures[0]["name"] == "Total Revenue"


def test_measure_add_and_list():
    backend = MockTomBackend()
    backend.connect()
    backend.measure_add("Sales", "Test Measure", "SUM(Sales[Revenue])")
    measures = backend.measure_list(table="Sales")
    names = [m["name"] for m in measures]
    assert "Test Measure" in names


def test_measure_delete():
    backend = MockTomBackend()
    backend.connect()
    backend.measure_delete("Sales", "Total Revenue")
    names = [m["name"] for m in backend.measure_list()]
    assert "Total Revenue" not in names


def test_measure_delete_not_found():
    backend = MockTomBackend()
    backend.connect()
    with pytest.raises(KeyError):
        backend.measure_delete("Sales", "Nonexistent")


def test_write_log_tracks_operations():
    backend = MockTomBackend()
    backend.connect()
    backend.measure_add("Sales", "X", "1")
    backend.measure_delete("Sales", "X")
    log = backend.get_write_log()
    assert log[0]["op"] == "measure_add"
    assert log[1]["op"] == "measure_delete"


def test_table_operations():
    backend = MockTomBackend()
    backend.connect()
    backend.table_add("NewTable")
    tables = [t["name"] for t in backend.table_list()]
    assert "NewTable" in tables
    backend.table_delete("NewTable")
    tables = [t["name"] for t in backend.table_list()]
    assert "NewTable" not in tables


def test_relationship_add():
    backend = MockTomBackend()
    backend.connect()
    backend.relationship_add("Sales", "DateKey", "Calendar", "DateKey")
    rels = backend.relationship_list()
    assert any("Sales[DateKey]" in r["from"] for r in rels)


def test_dax_validate_returns_valid():
    backend = MockTomBackend()
    backend.connect()
    result = backend.dax_validate("SUM(Sales[Revenue])")
    assert result["valid"] is True


def test_custom_fixture():
    fixture = {
        "model": {"name": "TestModel", "compatibility_level": 1500},
        "tables": [{"name": "FactSales"}],
        "columns": [],
        "relationships": [],
        "measures": [],
    }
    backend = MockTomBackend(fixture=fixture)
    backend.connect()
    info = backend.model_info()
    assert info["name"] == "TestModel"
    tables = backend.table_list()
    assert tables[0]["name"] == "FactSales"
