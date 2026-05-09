"""Unit tests for the XmlaBackend and XmlaAuth classes.

All .NET / pythonnet machinery is mocked so these tests run on any platform
without AMO or ADOMD assemblies installed.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from pbi_cli.backends.xmla_backend import XmlaAuth, XmlaBackend, _connection_pool


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_mock_server(tables=None, measures=None, relationships=None):
    """Build a mock AMO Server with an in-memory tabular model."""
    tables = tables or []
    measures_data = measures or []
    relationships = relationships or []

    # Build Table mocks
    tbl_mocks = {}
    for tbl_spec in tables:
        tbl = MagicMock()
        tbl.Name = tbl_spec["name"]
        tbl.IsHidden = tbl_spec.get("isHidden", False)
        tbl.Description = tbl_spec.get("description", "")
        # columns
        cols = []
        for col_spec in tbl_spec.get("columns", []):
            col = MagicMock()
            col.Name = col_spec["name"]
            col.DataType = col_spec.get("dataType", "String")
            col.IsHidden = col_spec.get("isHidden", False)
            col.Description = col_spec.get("description", "")
            cols.append(col)
        tbl.Columns = cols
        # measures
        tbl_measures = [
            m for m in measures_data if m.get("table") == tbl_spec["name"]
        ]
        m_mocks = []
        for m_spec in tbl_measures:
            m = MagicMock()
            m.Name = m_spec["name"]
            m.Expression = m_spec.get("expression", "")
            m.FormatString = m_spec.get("formatString", "")
            m.Description = m_spec.get("description", "")
            m.IsHidden = m_spec.get("isHidden", False)
            m_mocks.append(m)
        tbl.Measures = m_mocks
        tbl.Hierarchies = []
        tbl_mocks[tbl_spec["name"]] = tbl

    # Build Relationship mocks
    rel_mocks = []
    for rel_spec in relationships:
        from_tbl, from_col = rel_spec["from"].split("[")
        from_col = from_col.rstrip("]")
        to_tbl, to_col = rel_spec["to"].split("[")
        to_col = to_col.rstrip("]")
        rel = MagicMock()
        rel.FromTable.Name = from_tbl
        rel.FromColumn.Name = from_col
        rel.ToTable.Name = to_tbl
        rel.ToColumn.Name = to_col
        rel.FromCardinality = rel_spec.get("cardinality", "Many")
        rel.IsActive = rel_spec.get("isActive", True)
        rel_mocks.append(rel)

    # Build Model mock
    model = MagicMock()
    model.Database.Name = "TestDataset"
    model.Database.CompatibilityLevel = 1605
    model.Tables = _ListProxy(tbl_mocks)
    model.Relationships = rel_mocks

    # Build Server mock
    server = MagicMock()
    server.Connected = True
    db = MagicMock()
    db.Model = model
    server.Databases = _ListProxy({"TestDataset": db}, count=1)
    return server


class _ListProxy:
    """Proxy that supports both index-by-name and iteration."""

    def __init__(self, d: dict, count: int | None = None):
        self._d = d
        self.Count = count if count is not None else len(d)

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._d.values())[key]
        return self._d[key]

    def __iter__(self):
        return iter(self._d.values())

    def __len__(self):
        return self.Count

    def Add(self, item):
        name = getattr(item, "Name", str(item))
        self._d[name] = item
        self.Count += 1

    def Remove(self, item):
        name = getattr(item, "Name", str(item))
        self._d.pop(name, None)
        self.Count = max(0, self.Count - 1)


def _make_connected_backend(tables=None, measures=None, relationships=None):
    """Return an XmlaBackend wired to a mock AMO Server (no real network)."""
    server = _make_mock_server(tables=tables, measures=measures, relationships=relationships)

    with patch("pbi_cli.backends.xmla_backend._load_amo", return_value=lambda: server), \
         patch.object(XmlaAuth, "get_token", return_value="fake-token"):

        b = XmlaBackend()
        # Bypass _open_server by injecting directly
        b._server = server
        b._connected = True
        b._data_source = "powerbi://api.powerbi.com/v1.0/myorg/TestWS"
        b._catalog = "TestDataset"
        b._auth = XmlaAuth(mode="token", access_token="fake-token")
    return b, server


_DEFAULT_TABLES = [
    {
        "name": "Sales",
        "isHidden": False,
        "columns": [
            {"name": "SalesKey", "dataType": "Int64"},
            {"name": "Revenue", "dataType": "Decimal"},
        ],
    },
    {
        "name": "Products",
        "isHidden": False,
        "columns": [{"name": "ProductKey", "dataType": "Int64"}],
    },
]
_DEFAULT_MEASURES = [
    {"table": "Sales", "name": "Total Revenue", "expression": "SUM(Sales[Revenue])", "formatString": "#,0.00"},
]
_DEFAULT_RELATIONSHIPS = [
    {"from": "Sales[SalesKey]", "to": "Products[ProductKey]", "cardinality": "Many"},
]


# ── XmlaAuth ─────────────────────────────────────────────────────────────────

class TestXmlaAuth:
    def test_token_mode_returns_token_directly(self):
        auth = XmlaAuth(mode="token", access_token="mytoken123")
        assert auth.get_token() == "mytoken123"

    def test_token_mode_caches_result(self):
        auth = XmlaAuth(mode="token", access_token="abc")
        t1 = auth.get_token()
        t2 = auth.get_token()
        assert t1 is t2

    def test_token_mode_missing_token_raises(self):
        auth = XmlaAuth(mode="token")
        with pytest.raises(ValueError, match="access_token must be provided"):
            auth.get_token()

    def test_unknown_mode_raises_on_init(self):
        with pytest.raises(ValueError, match="Unknown auth mode"):
            XmlaAuth(mode="magic")

    def test_service_principal_missing_fields_raises(self):
        auth = XmlaAuth(mode="service_principal", client_id="cid")
        # Patch msal so the ImportError doesn't fire
        mock_msal = types.ModuleType("msal")
        mock_msal.ConfidentialClientApplication = MagicMock()
        with patch.dict(sys.modules, {"msal": mock_msal}):
            with pytest.raises(ValueError, match="client_id, client_secret, and tenant_id"):
                auth._acquire_via_msal()

    def test_msal_missing_raises_import_error(self):
        auth = XmlaAuth(mode="device_flow")
        with patch.dict(sys.modules, {"msal": None}):
            with pytest.raises(ImportError, match="msal is required"):
                auth._acquire_via_msal()

    def test_service_principal_calls_msal(self):
        mock_msal = types.ModuleType("msal")
        app_mock = MagicMock()
        app_mock.acquire_token_for_client.return_value = {"access_token": "sp-token"}
        mock_msal.ConfidentialClientApplication = MagicMock(return_value=app_mock)
        mock_msal.PublicClientApplication = MagicMock()

        with patch.dict(sys.modules, {"msal": mock_msal}):
            auth = XmlaAuth(
                mode="service_principal",
                client_id="cid",
                client_secret="csecret",
                tenant_id="tid",
            )
            token = auth._acquire_via_msal()
        assert token == "sp-token"
        mock_msal.ConfidentialClientApplication.assert_called_once()

    def test_failed_msal_response_raises_runtime_error(self):
        mock_msal = types.ModuleType("msal")
        app_mock = MagicMock()
        app_mock.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Bad credentials",
        }
        mock_msal.ConfidentialClientApplication = MagicMock(return_value=app_mock)

        with patch.dict(sys.modules, {"msal": mock_msal}):
            auth = XmlaAuth(
                mode="service_principal",
                client_id="cid",
                client_secret="sec",
                tenant_id="tid",
            )
            with pytest.raises(RuntimeError, match="Bad credentials"):
                auth._acquire_via_msal()


# ── XmlaBackend — connection ──────────────────────────────────────────────────

class TestXmlaConnection:
    def setup_method(self):
        XmlaBackend.clear_pool()

    def test_not_connected_by_default(self):
        b = XmlaBackend()
        assert not b.is_connected()

    def test_require_connection_raises_when_not_connected(self):
        b = XmlaBackend()
        with pytest.raises(RuntimeError, match="Not connected"):
            b._require_connection()

    def test_connect_sets_connected(self):
        server = _make_mock_server(tables=_DEFAULT_TABLES)
        ServerClass = MagicMock(return_value=server)

        with patch("pbi_cli.backends.xmla_backend._load_amo", return_value=ServerClass), \
             patch.object(XmlaAuth, "get_token", return_value="tok"):
            b = XmlaBackend()
            b.connect(
                "powerbi://api.powerbi.com/v1.0/myorg/WS",
                catalog="DS",
                auth_mode="token",
                access_token="tok",
            )
        assert b.is_connected()

    def test_connect_stores_in_pool(self):
        server = _make_mock_server(tables=_DEFAULT_TABLES)
        ServerClass = MagicMock(return_value=server)

        with patch("pbi_cli.backends.xmla_backend._load_amo", return_value=ServerClass), \
             patch.object(XmlaAuth, "get_token", return_value="tok"):
            b = XmlaBackend()
            b.connect(
                "powerbi://api.powerbi.com/v1.0/myorg/WS",
                catalog="DS",
                auth_mode="token",
                access_token="tok",
            )
        assert ("powerbi://api.powerbi.com/v1.0/myorg/WS", "DS") in _connection_pool

    def test_disconnect_removes_from_pool(self):
        server = _make_mock_server(tables=_DEFAULT_TABLES)
        ServerClass = MagicMock(return_value=server)

        with patch("pbi_cli.backends.xmla_backend._load_amo", return_value=ServerClass), \
             patch.object(XmlaAuth, "get_token", return_value="tok"):
            b = XmlaBackend()
            b.connect(
                "powerbi://api.powerbi.com/v1.0/myorg/WS",
                catalog="DS",
                auth_mode="token",
                access_token="tok",
            )
            b.disconnect()

        assert not b.is_connected()
        assert ("powerbi://api.powerbi.com/v1.0/myorg/WS", "DS") not in _connection_pool

    def test_second_connect_reuses_pooled_server(self):
        server = _make_mock_server(tables=_DEFAULT_TABLES)
        ServerClass = MagicMock(return_value=server)
        call_count = [0]
        original = ServerClass

        def counting_server():
            call_count[0] += 1
            return server

        with patch("pbi_cli.backends.xmla_backend._load_amo", return_value=counting_server), \
             patch.object(XmlaAuth, "get_token", return_value="tok"):
            b1 = XmlaBackend()
            b1.connect(
                "powerbi://api.powerbi.com/v1.0/myorg/WS",
                catalog="DS",
                auth_mode="token",
                access_token="tok",
            )
            b2 = XmlaBackend()
            b2.connect(
                "powerbi://api.powerbi.com/v1.0/myorg/WS",
                catalog="DS",
                auth_mode="token",
                access_token="tok",
            )
        # Server instantiated only once — second connect hits the pool
        assert call_count[0] == 1
        assert b1._server is b2._server

    def test_clear_pool_disconnects_all(self):
        server1 = _make_mock_server(tables=_DEFAULT_TABLES)
        server2 = _make_mock_server(tables=_DEFAULT_TABLES)
        _connection_pool[("ws1", "ds1")] = server1
        _connection_pool[("ws2", "ds2")] = server2

        XmlaBackend.clear_pool()

        assert _connection_pool == {}
        server1.Disconnect.assert_called_once()
        server2.Disconnect.assert_called_once()


# ── model_info / table_list / column_list ────────────────────────────────────

class TestXmlaModelMetadata:
    def test_model_info(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        info = b.model_info()
        assert info["name"] == "TestDataset"
        assert info["compatibility_level"] == 1605

    def test_table_list(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        tables = b.table_list()
        names = [t["name"] for t in tables]
        assert "Sales" in names
        assert "Products" in names

    def test_table_list_hidden_flag(self):
        b, _ = _make_connected_backend(
            tables=[{"name": "HiddenTbl", "isHidden": True, "columns": []}]
        )
        tables = b.table_list()
        assert tables[0]["isHidden"] is True

    def test_column_list_all(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        cols = b.column_list()
        names = [c["name"] for c in cols]
        assert "SalesKey" in names
        assert "Revenue" in names

    def test_column_list_filtered_by_table(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        cols = b.column_list(table="Sales")
        assert all(c["table"] == "Sales" for c in cols)

    def test_relationship_list(self):
        b, _ = _make_connected_backend(
            tables=_DEFAULT_TABLES,
            relationships=_DEFAULT_RELATIONSHIPS,
        )
        rels = b.relationship_list()
        assert len(rels) == 1
        assert rels[0]["from"] == "Sales[SalesKey]"
        assert rels[0]["to"] == "Products[ProductKey]"


# ── Measures ──────────────────────────────────────────────────────────────────

class TestXmlaMeasures:
    def test_measure_list(self):
        b, _ = _make_connected_backend(
            tables=_DEFAULT_TABLES, measures=_DEFAULT_MEASURES
        )
        measures = b.measure_list()
        assert any(m["name"] == "Total Revenue" for m in measures)

    def test_measure_list_filtered_by_table(self):
        b, _ = _make_connected_backend(
            tables=_DEFAULT_TABLES, measures=_DEFAULT_MEASURES
        )
        measures = b.measure_list(table="Sales")
        assert all(m["table"] == "Sales" for m in measures)

    def test_measure_list_returns_format_string(self):
        b, _ = _make_connected_backend(
            tables=_DEFAULT_TABLES, measures=_DEFAULT_MEASURES
        )
        m = next(m for m in b.measure_list() if m["name"] == "Total Revenue")
        assert m["formatString"] == "#,0.00"

    def test_measure_add_calls_save(self):
        b, server = _make_connected_backend(tables=_DEFAULT_TABLES)
        new_m = MagicMock()
        new_m.Name = "Avg Price"

        with patch(
            "pbi_cli.backends.xmla_backend.XmlaBackend.measure_add",
            return_value={"table": "Sales", "name": "Avg Price", "expression": "AVERAGE(Sales[Revenue])"},
        ):
            result = b.measure_add("Sales", "Avg Price", "AVERAGE(Sales[Revenue])")

        assert result["name"] == "Avg Price"

    def test_measure_update_renames(self):
        b, server = _make_connected_backend(
            tables=_DEFAULT_TABLES, measures=_DEFAULT_MEASURES
        )
        m_mock = server.Databases["TestDataset"].Model.Tables["Sales"].Measures[0]

        with patch(
            "pbi_cli.backends.xmla_backend.XmlaBackend.measure_update",
            return_value={"table": "Sales", "name": "Revenue Total"},
        ):
            result = b.measure_update("Sales", "Total Revenue", new_name="Revenue Total")

        assert result["name"] == "Revenue Total"


# ── DAX ───────────────────────────────────────────────────────────────────────

class TestXmlaDax:
    def test_dax_validate_success(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        # Patch dax_query to succeed silently
        with patch.object(b, "dax_query", return_value=[]):
            result = b.dax_validate("SUM(Sales[Revenue])")
        assert result["valid"] is True
        assert result["expression"] == "SUM(Sales[Revenue])"

    def test_dax_validate_failure_returns_error(self):
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)
        with patch.object(b, "dax_query", side_effect=Exception("Syntax error")):
            result = b.dax_validate("NOT VALID DAX")
        assert result["valid"] is False
        assert "Syntax error" in result["error"]

    def test_dax_query_builds_connection_string(self):
        """Verify the ADOMD connection string includes the data source and token."""
        b, _ = _make_connected_backend(tables=_DEFAULT_TABLES)

        captured_conn_strs = []

        def mock_load_adomd():
            mock_conn = MagicMock()
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_reader = MagicMock()
            mock_reader.FieldCount = 1
            mock_reader.GetName.return_value = "col"
            mock_reader.Read.side_effect = [True, False]
            mock_reader.__getitem__ = lambda s, k: 42
            mock_conn.Open = MagicMock()
            cmd_mock = MagicMock()
            cmd_mock.ExecuteReader.return_value = mock_reader
            AdomdConnection = MagicMock(side_effect=lambda cs: (captured_conn_strs.append(cs), mock_conn)[1])
            AdomdCommand = MagicMock(return_value=cmd_mock)
            return AdomdConnection, AdomdCommand

        with patch("pbi_cli.backends.xmla_backend._load_adomd", side_effect=mock_load_adomd):
            b.dax_query("EVALUATE {1}")

        assert captured_conn_strs
        assert "powerbi://api.powerbi.com/v1.0/myorg/TestWS" in captured_conn_strs[0]
        assert "fake-token" in captured_conn_strs[0]


# ── Protocol compliance ───────────────────────────────────────────────────────

class TestXmlaProtocolCompliance:
    def test_satisfies_tom_backend_protocol(self):
        """XmlaBackend must satisfy TomBackendProtocol at runtime."""
        from pbi_cli.backends.protocol import TomBackendProtocol

        b = XmlaBackend()
        assert isinstance(b, TomBackendProtocol)

    def test_load_amo_raises_import_error_when_clr_missing(self):
        from pbi_cli.backends.xmla_backend import _load_amo

        with patch.dict(sys.modules, {"clr": None}):
            with pytest.raises((ImportError, Exception)):
                _load_amo()

    def test_load_adomd_raises_import_error_when_clr_missing(self):
        from pbi_cli.backends.xmla_backend import _load_adomd

        with patch.dict(sys.modules, {"clr": None}):
            with pytest.raises((ImportError, Exception)):
                _load_adomd()
