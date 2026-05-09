"""Unit tests for REST source profiling helpers (auth, pagination, schema inference)."""

from __future__ import annotations

from pbi_cli.commands.source import (
    _detect_next_link,
    _extract_records,
    _flatten_record,
    _infer_columns,
    _infer_pbi_type,
    _url_to_table_name,
)

# ── _extract_records ──────────────────────────────────────────────────────────


class TestExtractRecords:
    def test_plain_list(self):
        data = [{"id": 1}, {"id": 2}]
        assert _extract_records(data, None) == data

    def test_odata_value_envelope(self):
        data = {"value": [{"id": 1}], "@odata.count": 1}
        assert _extract_records(data, None) == [{"id": 1}]

    def test_data_envelope(self):
        data = {"data": [{"id": 1}]}
        assert _extract_records(data, None) == [{"id": 1}]

    def test_results_envelope(self):
        data = {"results": [{"id": 1}], "total": 1}
        assert _extract_records(data, None) == [{"id": 1}]

    def test_items_envelope(self):
        data = {"items": [{"id": 1}]}
        assert _extract_records(data, None) == [{"id": 1}]

    def test_dot_path_extraction(self):
        data = {"response": {"data": [{"id": 1}, {"id": 2}]}}
        assert _extract_records(data, "response.data") == [{"id": 1}, {"id": 2}]

    def test_invalid_dot_path_returns_empty(self):
        data = {"response": {"data": [{"id": 1}]}}
        assert _extract_records(data, "response.nonexistent") == []

    def test_non_dict_records_filtered(self):
        data = {"value": [{"id": 1}, "not a dict", 42]}
        result = _extract_records(data, None)
        assert result == [{"id": 1}]

    def test_empty_response_returns_empty(self):
        assert _extract_records({}, None) == []
        assert _extract_records([], None) == []


# ── _detect_next_link ─────────────────────────────────────────────────────────


class TestDetectNextLink:
    def test_odata_next_link(self):
        data = {
            "value": [{"id": 1}],
            "@odata.nextLink": "https://api.example.com/v1/orders?$skip=10",
        }
        result = _detect_next_link(data, "https://api.example.com/v1/orders", 1)
        assert result == "https://api.example.com/v1/orders?$skip=10"

    def test_json_api_links_next(self):
        data = {
            "data": [{"id": 1}],
            "links": {"next": "https://api.example.com/v1/products?page=2"},
        }
        result = _detect_next_link(data, "https://api.example.com/v1/products", 1)
        assert result == "https://api.example.com/v1/products?page=2"

    def test_no_pagination_returns_none(self):
        data = {"value": [{"id": 1}]}
        result = _detect_next_link(data, "https://api.example.com/orders", 1)
        assert result is None

    def test_non_dict_returns_none(self):
        assert _detect_next_link([{"id": 1}], "http://example.com", 1) is None


# ── _flatten_record ───────────────────────────────────────────────────────────


class TestFlattenRecord:
    def test_flat_record_unchanged(self):
        record = {"id": 1, "name": "Test"}
        assert _flatten_record(record) == {"id": 1, "name": "Test"}

    def test_nested_dict_flattened(self):
        record = {"id": 1, "address": {"city": "London", "country": "UK"}}
        flat = _flatten_record(record)
        assert flat["id"] == 1
        assert flat["address.city"] == "London"
        assert flat["address.country"] == "UK"

    def test_array_values_represented_as_string(self):
        record = {"id": 1, "tags": ["a", "b", "c"]}
        flat = _flatten_record(record)
        assert "[Array(3)]" in flat["tags"]


# ── _infer_pbi_type ───────────────────────────────────────────────────────────


class TestInferPbiType:
    def test_integers_map_to_int64(self):
        assert _infer_pbi_type([1, 2, 3]) == "Int64"

    def test_floats_map_to_decimal(self):
        assert _infer_pbi_type([1.5, 2.3]) == "Decimal"

    def test_mixed_int_float_map_to_decimal(self):
        assert _infer_pbi_type([1, 2.5, 3]) == "Decimal"

    def test_booleans_map_to_boolean(self):
        assert _infer_pbi_type([True, False]) == "Boolean"

    def test_strings_map_to_string(self):
        assert _infer_pbi_type(["hello", "world"]) == "String"

    def test_iso_date_strings_map_to_datetime(self):
        assert _infer_pbi_type(["2024-01-15", "2024-02-20"]) == "DateTime"

    def test_datetime_with_time_component(self):
        assert _infer_pbi_type(["2024-01-15T10:30:00Z"]) == "DateTime"

    def test_empty_values_default_to_string(self):
        assert _infer_pbi_type([]) == "String"

    def test_mixed_types_map_to_mixed(self):
        assert _infer_pbi_type([1, "text", True]) == "Mixed"


# ── _infer_columns ────────────────────────────────────────────────────────────


class TestInferColumns:
    def test_basic_schema_inference(self):
        sample = [
            {"id": 1, "name": "Alice", "score": 95.5},
            {"id": 2, "name": "Bob", "score": 87.0},
        ]
        cols = _infer_columns(sample)
        by_name = {c["name"]: c for c in cols}
        assert by_name["id"]["dataType"] == "Int64"
        assert by_name["name"]["dataType"] == "String"
        assert by_name["score"]["dataType"] == "Decimal"

    def test_null_rate_calculated(self):
        sample = [{"id": 1, "opt": "x"}, {"id": 2, "opt": None}]
        cols = _infer_columns(sample)
        opt_col = next(c for c in cols if c["name"] == "opt")
        assert opt_col["nullRate"] == 0.5

    def test_empty_sample_returns_empty(self):
        assert _infer_columns([]) == []

    def test_sample_values_limited_to_3(self):
        sample = [{"v": i} for i in range(10)]
        cols = _infer_columns(sample)
        assert len(cols[0]["sampleValues"]) <= 3


# ── _url_to_table_name ────────────────────────────────────────────────────────


class TestUrlToTableName:
    def test_simple_path_segment(self):
        assert _url_to_table_name("https://api.example.com/v1/orders") == "Orders"

    def test_hyphenated_path(self):
        assert _url_to_table_name("https://api.example.com/v1/sales-data") == "SalesData"

    def test_underscore_path(self):
        assert _url_to_table_name("https://api.example.com/v1/product_catalog") == "ProductCatalog"

    def test_fallback_for_root(self):
        result = _url_to_table_name("https://api.example.com/")
        assert result  # non-empty


# ── Integration: _profile_rest with mocked httpx ─────────────────────────────


class TestProfileRestIntegration:
    def test_profile_rest_with_odata_response(self, monkeypatch):
        """Mock httpx to verify full REST profile pipeline with OData pagination."""
        from unittest.mock import MagicMock

        import httpx

        pages = [
            {
                "value": [
                    {"id": 1, "name": "Widget A", "price": 9.99, "inStock": True},
                    {"id": 2, "name": "Widget B", "price": 14.99, "inStock": False},
                ],
                "@odata.nextLink": "https://api.example.com/v1/products?$skip=2",
            },
            {
                "value": [
                    {"id": 3, "name": "Widget C", "price": 4.99, "inStock": True},
                ],
            },
        ]
        call_count = [0]

        def mock_get(url, headers):
            resp = MagicMock()
            resp.json.return_value = pages[min(call_count[0], len(pages) - 1)]
            resp.raise_for_status = MagicMock()
            call_count[0] += 1
            return resp

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = mock_get
        monkeypatch.setattr(httpx, "Client", lambda **kw: mock_client)

        from pbi_cli.commands.source import _profile_rest

        result = _profile_rest("https://api.example.com/v1/products", max_pages=2)

        assert len(result) == 1
        profile = result[0]
        assert profile["tableName"] == "Products"
        assert profile["rowCount"] == 3
        by_name = {c["name"]: c for c in profile["columns"]}
        assert by_name["id"]["dataType"] == "Int64"
        assert by_name["price"]["dataType"] == "Decimal"
        assert by_name["inStock"]["dataType"] == "Boolean"
        assert by_name["name"]["dataType"] == "String"

    def test_profile_rest_bearer_auth_header_sent(self, monkeypatch):
        """Verify the Authorization: Bearer header is included in the request."""
        from unittest.mock import MagicMock

        import httpx

        sent_headers = []

        def mock_get(url, headers):
            sent_headers.append(dict(headers))
            resp = MagicMock()
            resp.json.return_value = [{"id": 1}]
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = mock_get
        monkeypatch.setattr(httpx, "Client", lambda **kw: mock_client)

        from pbi_cli.commands.source import _profile_rest

        _profile_rest("https://api.example.com/v1/data", bearer_token="my-secret-token")

        assert sent_headers, "No requests made"
        assert sent_headers[0].get("Authorization") == "Bearer my-secret-token"
