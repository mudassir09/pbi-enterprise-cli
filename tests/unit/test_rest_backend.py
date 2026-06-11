"""Tests for the REST executeQueries backend."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pbi_cli.backends.rest_backend import RestBackend, _strip_brackets


def _exec_response(rows):
    return {"results": [{"tables": [{"rows": rows}]}]}


@pytest.fixture()
def backend():
    b = RestBackend(workspace_id="ws-1", dataset_id="ds-1", token="t")
    b._connected = True
    return b


class TestStripBrackets:
    def test_table_column_keys(self):
        assert _strip_brackets({"Sales[Revenue]": 5}) == {"Revenue": 5}

    def test_bare_bracket_keys(self):
        assert _strip_brackets({"[Name]": "Sales"}) == {"Name": "Sales"}

    def test_plain_keys_unchanged(self):
        assert _strip_brackets({"Name": 1}) == {"Name": 1}


class TestConnect:
    def test_connect_requires_ids(self, monkeypatch):
        monkeypatch.delenv("PBI_WORKSPACE_ID", raising=False)
        monkeypatch.delenv("PBI_DATASET_ID", raising=False)
        b = RestBackend()
        with pytest.raises(ConnectionError):
            b.connect()

    def test_connect_from_env(self, monkeypatch):
        monkeypatch.setenv("PBI_WORKSPACE_ID", "ws-env")
        monkeypatch.setenv("PBI_DATASET_ID", "ds-env")
        with patch("pbi_cli.fabric_api.get_token", return_value="tok"):
            b = RestBackend()
            b.connect()
        assert b.is_connected()
        assert b.workspace_id == "ws-env"


class TestQueries:
    def test_dax_query_posts_and_flattens(self, backend):
        with patch(
            "pbi_cli.fabric_api.post",
            return_value=_exec_response([{"Sales[Revenue]": 100}, {"Sales[Revenue]": 200}]),
        ) as mock_post:
            rows = backend.dax_query("EVALUATE Sales")
        assert rows == [{"Revenue": 100}, {"Revenue": 200}]
        url = mock_post.call_args[0][0]
        assert "ws-1" in url and "ds-1" in url and url.endswith("/executeQueries")

    def test_dax_validate_wraps_scalar(self, backend):
        with patch("pbi_cli.fabric_api.post", return_value=_exec_response([{"[result]": 1}])):
            out = backend.dax_validate("SUM(Sales[Revenue])")
        assert out["valid"]

    def test_measure_list_resolves_table_names(self, backend):
        def fake_post(url, token, payload=None, **kw):
            q = payload["queries"][0]["query"]
            if "INFO.TABLES" in q:
                return _exec_response([{"[ID]": 1, "[Name]": "Sales", "[IsHidden]": False}])
            if "INFO.MEASURES" in q:
                return _exec_response([
                    {"[Name]": "Total Revenue", "[TableID]": 1,
                     "[Expression]": "SUM(Sales[Revenue])", "[FormatString]": "#,0"}
                ])
            raise AssertionError(f"unexpected query {q}")

        with patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            measures = backend.measure_list()
        assert measures == [{
            "table": "Sales", "name": "Total Revenue",
            "expression": "SUM(Sales[Revenue])", "formatString": "#,0",
            "description": "", "isHidden": False,
        }]

    def test_writes_raise(self, backend):
        with pytest.raises(NotImplementedError):
            backend.measure_add("Sales", "X", "1")
        with pytest.raises(NotImplementedError):
            backend.table_delete("Sales")
