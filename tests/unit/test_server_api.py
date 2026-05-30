"""Unit tests for the FastAPI REST server using TestClient + mock backend."""

from __future__ import annotations

import pytest

# Skip entire module if fastapi/httpx not installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from pbi_cli.backends.mock_backend import MockTomBackend


@pytest.fixture(autouse=True)
def mock_backend(monkeypatch):
    """Replace the server's TOM backend singleton with a connected mock."""
    import pbi_cli.server.api as api_module

    b = MockTomBackend()
    b.connect()
    monkeypatch.setattr(api_module, "_backend", b)
    return b


_TEST_API_KEY = "test-api-key-for-unit-tests"


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Set PBI_SERVER_KEY so auth passes in all tests."""
    monkeypatch.setenv("PBI_SERVER_KEY", _TEST_API_KEY)


@pytest.fixture()
def client() -> TestClient:
    from pbi_cli.server.api import app

    return TestClient(app, headers={"X-PBI-API-Key": _TEST_API_KEY})


# ── /api/status ───────────────────────────────────────────────────────────────


class TestStatus:
    def test_status_returns_200(self, client, monkeypatch):
        import pbi_cli.backends.tom_backend as tom

        monkeypatch.setattr(tom, "find_pbi_port", lambda: 12345)
        r = client.get("/api/status")
        assert r.status_code == 200

    def test_status_no_pbi_desktop(self, client, monkeypatch):
        import pbi_cli.backends.tom_backend as tom

        monkeypatch.setattr(tom, "find_pbi_port", lambda: None)
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["connected"] is False


# ── /api/tables ───────────────────────────────────────────────────────────────


class TestTables:
    def test_list_tables_returns_200(self, client):
        r = client.get("/api/tables")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tables_have_name_field(self, client):
        data = client.get("/api/tables").json()
        assert len(data) >= 1
        for t in data:
            assert "name" in t

    def test_default_fixture_has_four_tables(self, client):
        data = client.get("/api/tables").json()
        assert len(data) == 4


# ── /api/columns ──────────────────────────────────────────────────────────────


class TestColumns:
    def test_list_all_columns(self, client):
        r = client.get("/api/columns")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_filter_by_table(self, client):
        r = client.get("/api/columns?table=Sales")
        assert r.status_code == 200
        data = r.json()
        assert all(c["table"] == "Sales" for c in data)

    def test_columns_have_required_fields(self, client):
        data = client.get("/api/columns").json()
        for c in data:
            assert "name" in c
            assert "table" in c
            assert "dataType" in c


# ── /api/relationships ────────────────────────────────────────────────────────


class TestRelationships:
    def test_list_relationships(self, client):
        r = client.get("/api/relationships")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_relationships_have_from_to(self, client):
        data = client.get("/api/relationships").json()
        for rel in data:
            assert "from" in rel
            assert "to" in rel


# ── /api/measures ─────────────────────────────────────────────────────────────


class TestMeasures:
    def test_list_measures(self, client):
        r = client.get("/api/measures")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filter_by_table(self, client):
        r = client.get("/api/measures?table=Sales")
        assert r.status_code == 200
        data = r.json()
        assert all(m["table"] == "Sales" for m in data)

    def test_create_measure(self, client):
        r = client.post(
            "/api/measures",
            json={
                "table": "Sales",
                "name": "API Test Measure",
                "expression": "SUM(Sales[Revenue])",
                "formatString": "#,0.00",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "API Test Measure"

    def test_create_measure_appears_in_list(self, client):
        client.post(
            "/api/measures",
            json={
                "table": "Sales",
                "name": "ListCheck",
                "expression": "1",
            },
        )
        data = client.get("/api/measures").json()
        names = [m["name"] for m in data]
        assert "ListCheck" in names

    def test_update_measure(self, client):
        r = client.patch(
            "/api/measures/Sales/Total Revenue",
            json={
                "expression": "SUMX(Sales, Sales[Revenue])",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["expression"] == "SUMX(Sales, Sales[Revenue])"

    def test_update_nonexistent_measure_returns_404(self, client):
        r = client.patch(
            "/api/measures/Sales/DoesNotExist",
            json={
                "expression": "1",
            },
        )
        assert r.status_code == 404

    def test_delete_measure(self, client):
        client.post(
            "/api/measures",
            json={
                "table": "Sales",
                "name": "ToDelete",
                "expression": "1",
            },
        )
        r = client.delete("/api/measures/Sales/ToDelete")
        assert r.status_code == 204

    def test_delete_nonexistent_measure_returns_404(self, client):
        r = client.delete("/api/measures/Sales/GhostMeasure")
        assert r.status_code == 404


# ── /api/dax ──────────────────────────────────────────────────────────────────


class TestDax:
    def test_dax_query(self, client):
        r = client.post("/api/dax/query", json={"expression": "EVALUATE VALUES(Sales)"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_dax_validate_valid(self, client):
        r = client.post("/api/dax/validate", json={"expression": "SUM(Sales[Revenue])"})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_dax_validate_returns_expression(self, client):
        expr = "SUM(Sales[Revenue])"
        r = client.post("/api/dax/validate", json={"expression": expr})
        data = r.json()
        assert data["expression"] == expr


# ── /api/govern ───────────────────────────────────────────────────────────────


class TestGovern:
    def test_govern_check_returns_list(self, client):
        r = client.get("/api/govern/check")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_govern_check_violations_have_fields(self, client):
        data = client.get("/api/govern/check").json()
        for v in data:
            assert "rule" in v
            assert "severity" in v

    def test_govern_fix_returns_fixed_count(self, client):
        r = client.post("/api/govern/fix")
        assert r.status_code == 200
        data = r.json()
        assert "fixed" in data
        assert isinstance(data["fixed"], int)


# ── /api/docs/markdown ────────────────────────────────────────────────────────


class TestDocs:
    def test_docs_markdown_returns_text(self, client):
        r = client.get("/api/docs/markdown")
        assert r.status_code == 200
        assert "Data Dictionary" in r.text


# ── /api/suggest ──────────────────────────────────────────────────────────────


class TestSuggest:
    def test_suggest_measures_returns_list(self, client):
        r = client.get("/api/suggest/measures")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_suggest_visuals_returns_list(self, client):
        r = client.post("/api/suggest/visuals", json={"measures": ["Total Revenue"]})
        assert r.status_code == 200
        assert isinstance(r.json(), list)
