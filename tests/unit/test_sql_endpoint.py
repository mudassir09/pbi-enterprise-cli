"""Tests for the Fabric SQL endpoint helper (resolve + run)."""

from __future__ import annotations

import datetime
import decimal
from unittest.mock import patch

import pytest

from pbi_cli import sql_endpoint as se


class TestResolveEndpoint:
    def test_warehouse_connection_string(self):
        item = {
            "displayName": "SalesWH",
            "type": "Warehouse",
            "properties": {"connectionString": "abc.datawarehouse.fabric.microsoft.com"},
        }
        with patch.object(se._fab, "get", return_value=item):
            server, db = se.resolve_endpoint("ws", "wh", "tok")
        assert server == "abc.datawarehouse.fabric.microsoft.com"
        assert db == "SalesWH"

    def test_lakehouse_nested_connection_string(self):
        item = {
            "displayName": "Bronze",
            "type": "Lakehouse",
            "properties": {
                "sqlEndpointProperties": {"connectionString": "xyz.fabric.microsoft.com"}
            },
        }
        with patch.object(se._fab, "get", return_value=item):
            server, db = se.resolve_endpoint("ws", "lh", "tok")
        assert server == "xyz.fabric.microsoft.com"
        assert db == "Bronze"

    def test_item_without_sql_endpoint_raises(self):
        item = {"displayName": "AReport", "type": "Report", "properties": {}}
        with patch.object(se._fab, "get", return_value=item):
            with pytest.raises(se.SqlEndpointError, match="no SQL connection"):
                se.resolve_endpoint("ws", "rp", "tok")


class TestHelpers:
    def test_token_struct_roundtrip_length(self):
        packed = se._token_struct("hello")
        # 4-byte length prefix + UTF-16-LE payload (2 bytes/char)
        assert packed[:4] == (len("hello") * 2).to_bytes(4, "little")
        assert len(packed) == 4 + len("hello") * 2

    def test_detect_driver_prefers_installed(self):
        class FakePyodbc:
            @staticmethod
            def drivers():
                return ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]

        assert se._detect_driver(FakePyodbc) == "ODBC Driver 18 for SQL Server"

    def test_detect_driver_default_when_none(self):
        class FakePyodbc:
            @staticmethod
            def drivers():
                return ["Some Other Driver"]

        assert se._detect_driver(FakePyodbc) == "ODBC Driver 18 for SQL Server"

    def test_coerce_serialises_special_types(self):
        assert se._coerce(decimal.Decimal("1.50")) == "1.50"
        assert se._coerce(datetime.date(2026, 1, 2)) == "2026-01-02"
        assert se._coerce(b"\x00\xff") == "00ff"
        assert se._coerce(42) == 42


class TestRunQueryGuards:
    def test_missing_pyodbc_gives_actionable_error(self):
        # Simulate pyodbc not installed.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pyodbc":
                raise ImportError("no pyodbc")
            return real_import(name, *a, **k)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(se.SqlEndpointError, match=r"\[sql\] extra"):
                se.run_query("srv", "db", "SELECT 1", "tok")
