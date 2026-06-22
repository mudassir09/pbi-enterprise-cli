"""Unit tests for PBIR structural + referential validation (pbi report validate).

Builds synthetic PBIR GA projects in tmp_path via PbirBackend, validates a clean
project (no findings), then introduces each defect class and asserts the matching
rule fires. Runs anywhere — no Desktop.
"""

from __future__ import annotations

import json

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import AGG_SUM, FieldDef, VisualSpec, build_card
from pbi_cli.pbir_validate import validate_report


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    (tmp_path / "T.Report").mkdir()
    b = PbirBackend(str(tmp_path))
    b._write_ga_report_json()
    return b


def _fd(prop: str) -> FieldDef:
    return FieldDef(entity="financials", property=prop, agg=AGG_SUM)


def _add_card(b: PbirBackend, page: str) -> str:
    return b.visual_add(page, VisualSpec("card", build_card(_fd("Sales")), 0, 0, 200, 120))["name"]


def _rules(findings) -> set[str]:
    return {f["rule"] for f in findings}


def test_clean_project_has_no_errors(backend, tmp_path):
    backend.page_add("Overview")
    _add_card(backend, "Overview")
    findings = validate_report(str(tmp_path))
    errors = [f for f in findings if f["severity"] == "error"]
    assert errors == [], errors


def test_missing_report_json_flagged(tmp_path):
    (tmp_path / "T.Report" / "definition" / "pages").mkdir(parents=True)
    findings = validate_report(str(tmp_path))
    assert "pbir.missing-report-json" in _rules(findings)


def test_not_ga_format(tmp_path):
    rd = tmp_path / "Legacy.Report"
    rd.mkdir()
    (rd / "report.json").write_text("{}", encoding="utf-8")
    findings = validate_report(str(tmp_path))
    assert "pbir.not-ga" in _rules(findings)


def test_filterconfig_with_schema_is_error(backend, tmp_path):
    backend.page_add("Overview")
    page_dir = backend._ga_find_page_dir("Overview")
    pj = page_dir / "page.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["filterConfig"] = {"$schema": "https://example/x.json", "filters": []}
    pj.write_text(json.dumps(data), encoding="utf-8")

    findings = validate_report(str(tmp_path))
    assert "pbir.filterconfig-schema" in _rules(findings)
    assert any(
        f["severity"] == "error"
        for f in findings if f["rule"] == "pbir.filterconfig-schema"
    )


def test_empty_filter_field_sourceref_is_error(backend, tmp_path):
    # Reproduces the live-Desktop "invalid value" block: a filter whose field
    # SourceRef is empty (neither Entity nor Source).
    backend.page_add("Overview")
    page_dir = backend._ga_find_page_dir("Overview")
    pj = page_dir / "page.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["filterConfig"] = {
        "filters": [
            {
                "name": "f0",
                "type": "Categorical",
                "field": {"Column": {"Expression": {"SourceRef": {}}, "Property": "Country"}},
                "filter": {"Version": 2, "From": [], "Where": []},
            }
        ]
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    findings = validate_report(str(tmp_path))
    assert "pbir.filter-field-sourceref" in _rules(findings)
    assert any(
        f["severity"] == "error"
        for f in findings if f["rule"] == "pbir.filter-field-sourceref"
    )


def test_alias_filter_field_warns(backend, tmp_path):
    # A field SourceRef that uses a query alias (Source) instead of Entity:
    # schema-valid, but Desktop corrupts it on save — flag as a warning.
    backend.page_add("Overview")
    page_dir = backend._ga_find_page_dir("Overview")
    pj = page_dir / "page.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["filterConfig"] = {
        "filters": [
            {
                "name": "f0",
                "type": "Categorical",
                "field": {
                    "Column": {
                        "Expression": {"SourceRef": {"Source": "f"}},
                        "Property": "Segment",
                    }
                },
                "filter": {"Version": 2, "From": [], "Where": []},
            }
        ]
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    findings = validate_report(str(tmp_path))
    assert "pbir.filter-field-alias" in _rules(findings)
    assert "pbir.filter-field-sourceref" not in _rules(findings)


def test_valid_filter_field_sourceref_ok(backend, tmp_path):
    backend.page_add("Overview")
    page_dir = backend._ga_find_page_dir("Overview")
    pj = page_dir / "page.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["filterConfig"] = {
        "filters": [
            {
                "name": "f0",
                "type": "Categorical",
                "field": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": "Financials"}},
                        "Property": "Country",
                    }
                },
                "filter": {"Version": 2, "From": [], "Where": []},
            }
        ]
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    assert "pbir.filter-field-sourceref" not in _rules(validate_report(str(tmp_path)))


def test_dangling_parent_group_ref(backend, tmp_path):
    backend.page_add("Overview")
    name = _add_card(backend, "Overview")
    vj, data = backend._ga_find_visual_json("Overview", name)
    data["parentGroupName"] = "nonexistent_group_id"
    vj.write_text(json.dumps(data), encoding="utf-8")

    findings = validate_report(str(tmp_path))
    assert "pbir.dangling-group-ref" in _rules(findings)


def test_dangling_interaction(backend, tmp_path):
    backend.page_add("Overview")
    a = _add_card(backend, "Overview")
    # Target a visual that doesn't exist.
    backend.set_visual_interaction("Overview", a, "ghost_visual", "NoFilter")
    findings = validate_report(str(tmp_path))
    assert "pbir.dangling-interaction" in _rules(findings)


def test_dangling_page_order(backend, tmp_path):
    backend.page_add("Overview")
    meta = backend._ga_read_pages_json()
    meta["pageOrder"].append("ghost_page_id")
    backend._ga_write_pages_json(meta)
    findings = validate_report(str(tmp_path))
    assert "pbir.dangling-page-order" in _rules(findings)


def test_dangling_bookmark_item(backend, tmp_path):
    backend.page_add("Overview")
    _add_card(backend, "Overview")
    backend.bookmark_add("View A", page="Overview")
    meta = backend._ga_read_bookmarks_json()
    meta["items"].append({"name": "ghost_bookmark"})
    backend._ga_write_bookmarks_json(meta)
    findings = validate_report(str(tmp_path))
    assert "pbir.dangling-bookmark" in _rules(findings)


def test_invalid_json_is_error(backend, tmp_path):
    backend.page_add("Overview")
    page_dir = backend._ga_find_page_dir("Overview")
    (page_dir / "page.json").write_text("{ not json", encoding="utf-8")
    findings = validate_report(str(tmp_path))
    assert "pbir.invalid-json" in _rules(findings)
