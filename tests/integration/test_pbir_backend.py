"""Integration tests for PbirBackend against the live financials.pbip project.

Skipped automatically when the file is not present.
Marked e2e so CI excludes them (pytest -m "not e2e").
Write tests operate on a tmp_path copy so the live report is never modified.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import AGG_SUM, FieldDef, VisualSpec, build_card

_PBIP_PATH = Path(r"C:\Users\GGPC\Documents\financials.pbip")
_REPORT_DIR = Path(r"C:\Users\GGPC\Documents\financials.Report")

pytestmark = pytest.mark.skipif(
    not _PBIP_PATH.exists(),
    reason="financials.pbip not found — skipping PBIR integration tests",
)

_PAGE_EXECUTIVE = "Executive Summary"
_PAGE_SALES = "Sales Analysis"
_PAGE_PROFIT = "Profit Analysis"


@pytest.fixture(scope="module")
def backend() -> PbirBackend:
    return PbirBackend(str(_PBIP_PATH))


@pytest.fixture()
def write_backend(tmp_path) -> PbirBackend:
    """Backend pointing at a temp copy of the report — safe to modify."""
    report_copy = tmp_path / "financials.Report"
    shutil.copytree(_REPORT_DIR, report_copy)
    pbip_copy = tmp_path / "financials.pbip"
    pbip_copy.write_text(
        json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "financials.Report"}}]}),
        encoding="utf-8",
    )
    return PbirBackend(str(pbip_copy))


# ── Format detection ──────────────────────────────────────────────────────────


class TestFormatDetection:
    def test_format_is_pbir_ga(self, backend):
        assert backend.format == "pbir_ga"

    def test_report_dir_exists(self, backend):
        assert backend.report_dir.exists()


# ── Page list ─────────────────────────────────────────────────────────────────


class TestPageList:
    def test_returns_list(self, backend):
        pages = backend.page_list()
        assert isinstance(pages, list)
        assert len(pages) >= 1

    def test_known_pages_present(self, backend):
        names = [p["displayName"] for p in backend.page_list()]
        assert _PAGE_EXECUTIVE in names
        assert _PAGE_SALES in names
        assert _PAGE_PROFIT in names

    def test_each_page_has_display_name(self, backend):
        for p in backend.page_list():
            assert "displayName" in p
            assert isinstance(p["displayName"], str)


# ── Visual list ───────────────────────────────────────────────────────────────


class TestVisualList:
    def test_executive_summary_has_visuals(self, backend):
        visuals = backend.visual_list(_PAGE_EXECUTIVE)
        assert isinstance(visuals, list)
        assert len(visuals) >= 1

    def test_each_visual_has_required_fields(self, backend):
        for v in backend.visual_list(_PAGE_EXECUTIVE):
            assert "name" in v
            assert "visualType" in v
            assert "x" in v
            assert "y" in v
            assert "width" in v
            assert "height" in v

    def test_visual_types_are_strings(self, backend):
        for v in backend.visual_list(_PAGE_EXECUTIVE):
            assert isinstance(v["visualType"], str)
            assert len(v["visualType"]) > 0

    def test_positions_are_non_negative(self, backend):
        for v in backend.visual_list(_PAGE_EXECUTIVE):
            assert v["x"] >= 0
            assert v["y"] >= 0
            assert v["width"] > 0
            assert v["height"] > 0

    def test_sales_analysis_has_visuals(self, backend):
        visuals = backend.visual_list(_PAGE_SALES)
        assert len(visuals) >= 1

    def test_profit_analysis_has_visuals(self, backend):
        visuals = backend.visual_list(_PAGE_PROFIT)
        assert len(visuals) >= 1

    def test_unknown_page_returns_empty(self, backend):
        visuals = backend.visual_list("NonExistentPage_XYZ")
        assert visuals == []


# ── Page add / delete (on tmp copy) ──────────────────────────────────────────


class TestPageWrite:
    def test_add_and_delete_page(self, write_backend):
        test_page = "TestPage_pbi_cli"

        # Add page
        result = write_backend.page_add(test_page)
        assert "name" in result

        # Verify it appears in page list
        names = [p["displayName"] for p in write_backend.page_list()]
        assert test_page in names

        # Delete page
        write_backend.page_delete(test_page)

        # Verify gone
        names_after = [p["displayName"] for p in write_backend.page_list()]
        assert test_page not in names_after

    def test_page_add_returns_dict_with_name(self, write_backend):
        test_page = "TestPage2_pbi_cli"
        result = write_backend.page_add(test_page)
        assert isinstance(result, dict)
        assert "name" in result
        write_backend.page_delete(test_page)

    def test_clear_page_removes_visuals(self, write_backend):
        test_page = "ClearTest_pbi_cli"
        write_backend.page_add(test_page)

        # Add a visual
        spec = VisualSpec(
            visual_type="card",
            visual_body=build_card(FieldDef(entity="financials", property="Sales", agg=AGG_SUM)),
            x=16,
            y=16,
            width=280,
            height=120,
        )
        write_backend.visual_add(test_page, spec)

        # Clear page
        write_backend.page_clear(test_page)
        visuals = write_backend.visual_list(test_page)
        assert visuals == []

        write_backend.page_delete(test_page)


# ── Visual add / delete (on tmp copy) ────────────────────────────────────────


class TestVisualWrite:
    def _make_page(self, backend, name="VisualTest_pbi_cli"):
        backend.page_add(name)
        return name

    def test_add_card_visual(self, write_backend):
        page = self._make_page(write_backend)
        try:
            spec = VisualSpec(
                visual_type="card",
                visual_body=build_card(
                    FieldDef(entity="financials", property="Sales", agg=AGG_SUM)
                ),
                x=16,
                y=16,
                width=280,
                height=120,
                title="Total Sales",
            )
            result = write_backend.visual_add(page, spec)
            assert "name" in result
            visuals = write_backend.visual_list(page)
            assert len(visuals) >= 1
        finally:
            write_backend.page_delete(page)

    def test_add_visual_position_stored(self, write_backend):
        page = self._make_page(write_backend, "PosTest_pbi_cli")
        try:
            spec = VisualSpec(
                visual_type="card",
                visual_body=build_card(
                    FieldDef(entity="financials", property="Sales", agg=AGG_SUM)
                ),
                x=100,
                y=200,
                width=300,
                height=150,
            )
            write_backend.visual_add(page, spec)
            visuals = write_backend.visual_list(page)
            assert len(visuals) == 1
            v = visuals[0]
            assert v["x"] == 100
            assert v["y"] == 200
            assert v["width"] == 300
            assert v["height"] == 150
        finally:
            write_backend.page_delete(page)

    def test_delete_visual(self, write_backend):
        page = self._make_page(write_backend, "DelTest_pbi_cli")
        try:
            spec = VisualSpec(
                visual_type="card",
                visual_body=build_card(
                    FieldDef(entity="financials", property="Sales", agg=AGG_SUM)
                ),
                x=16,
                y=16,
                width=280,
                height=120,
            )
            result = write_backend.visual_add(page, spec)
            visual_name = result["name"]

            write_backend.visual_delete(page, visual_name)
            visuals = write_backend.visual_list(page)
            assert all(v["name"] != visual_name for v in visuals)
        finally:
            write_backend.page_delete(page)
