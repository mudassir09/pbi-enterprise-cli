"""Unit tests for the new PBIR visual features:

  - AI visual builders (decomposition tree, key influencers, smart narrative, Q&A)
  - button action wiring (visualLink)
  - constant reference line
  - visual introspection (visual get)

Synthetic PBIR GA project in tmp_path — runs anywhere, no Desktop.
"""

from __future__ import annotations

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_action_button,
    build_bar_chart,
    build_card,
    build_decomposition_tree,
    build_key_influencers,
    build_qna,
    build_smart_narrative,
)
from pbi_cli.pbir_validate import validate_report


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    (tmp_path / "T.Report").mkdir()
    b = PbirBackend(str(tmp_path))
    b._write_ga_report_json()
    return b


def _col(p: str) -> FieldDef:
    return FieldDef(entity="financials", property=p, agg=None)


def _meas(p: str) -> FieldDef:
    return FieldDef(entity="financials", property=p, agg=AGG_SUM)


class TestAIBuilders:
    def test_decomposition_tree_roles(self):
        body = build_decomposition_tree(_meas("Sales"), [_col("Country"), _col("Segment")])
        qs = body["query"]["queryState"]
        assert body["visualType"] == "decompositionTreeVisual"
        assert len(qs["Analyze"]["projections"]) == 1
        assert len(qs["Explain"]["projections"]) == 2

    def test_key_influencers_roles(self):
        body = build_key_influencers(_meas("Profit"), [_col("Segment")])
        assert body["visualType"] == "keyDrivers"
        assert "Analyze" in body["query"]["queryState"]

    def test_narrative_and_qna_have_no_query(self):
        assert build_smart_narrative()["visualType"] == "narrativeVisual"
        assert "query" not in build_qna()


class TestButtonAction:
    def _button(self, b, page="Home"):
        b.page_add(page)
        body = build_action_button(shape="blank", text="Go")
        return page, b.visual_add(page, VisualSpec(body["visualType"], body, 0, 0, 120, 40))["name"]

    def test_page_navigation_resolves_page_id(self, backend):
        backend.page_add("Detail")
        page, name = self._button(backend)
        assert backend.visual_set_action(page, name, "PageNavigation", target="Detail")
        info = backend.visual_get(page, name)
        assert info["action"] == "PageNavigation"
        # navigationSection must be the page GUID, not the display name.
        detail_id = next(p["name"] for p in backend.page_list() if p["displayName"] == "Detail")
        _, data = backend._ga_find_visual_json(page, name)
        link = data["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]
        assert link["navigationSection"]["expr"]["Literal"]["Value"] == f"'{detail_id}'"

    def test_bookmark_action(self, backend):
        page, name = self._button(backend)
        backend.bookmark_add("Q4 View", page=page, capture=False)
        assert backend.visual_set_action(page, name, "Bookmark", target="Q4 View")
        assert backend.visual_get(page, name)["action"] == "Bookmark"

    def test_back_needs_no_target(self, backend):
        page, name = self._button(backend)
        assert backend.visual_set_action(page, name, "Back")

    def test_pagenav_without_target_raises(self, backend):
        page, name = self._button(backend)
        with pytest.raises(ValueError):
            backend.visual_set_action(page, name, "PageNavigation")

    def test_bad_action_type_raises(self, backend):
        page, name = self._button(backend)
        with pytest.raises(ValueError):
            backend.visual_set_action(page, name, "Teleport")


class TestReferenceLine:
    def _bar(self, b, page="P"):
        b.page_add(page)
        spec = VisualSpec(
            "barChart", build_bar_chart(_col("Country"), _meas("Sales")), 0, 0, 400, 300
        )
        return page, b.visual_add(page, spec)["name"]

    def test_add_reference_line(self, backend, tmp_path):
        page, name = self._bar(backend)
        assert backend.visual_add_reference_line(page, name, 1000000, name="Target")
        _, data = backend._ga_find_visual_json(page, name)
        lines = data["visual"]["objects"]["referenceLine"]
        assert len(lines) == 1
        assert lines[0]["properties"]["value"]["expr"]["Literal"]["Value"] == "1000000D"
        assert validate_report(str(tmp_path)) == [] or all(
            f["severity"] != "error" for f in validate_report(str(tmp_path))
        )

    def test_two_lines_distinct_ids(self, backend):
        page, name = self._bar(backend)
        backend.visual_add_reference_line(page, name, 100, name="Low")
        backend.visual_add_reference_line(page, name, 900, name="High")
        _, data = backend._ga_find_visual_json(page, name)
        lines = data["visual"]["objects"]["referenceLine"]
        assert len({line["selector"]["id"] for line in lines}) == 2

    def test_bad_style_raises(self, backend):
        page, name = self._bar(backend)
        with pytest.raises(ValueError):
            backend.visual_add_reference_line(page, name, 1, style="wavy")


class TestVisualGet:
    def test_get_reports_bindings_and_formatting(self, backend):
        backend.page_add("P")
        spec = VisualSpec(
            "barChart", build_bar_chart(_col("Country"), _meas("Sales")), 0, 0, 400, 300,
            title="Sales by Country",
        )
        name = backend.visual_add("P", spec)["name"]
        info = backend.visual_get("P", name)
        assert info["visualType"] == "barChart"
        assert "Category" in info["bindings"]
        assert "Y" in info["bindings"]
        assert "title" in info["containerObjects"]
        assert info["filters"] == 0

    def test_get_reports_conditional_formatting(self, backend):
        backend.page_add("P")
        spec = VisualSpec("card", build_card(_meas("Sales")), 0, 0, 200, 120)
        name = backend.visual_add("P", spec)["name"]
        backend.visual_format_data_bar("P", name, "financials", "Sales")
        info = backend.visual_get("P", name)
        assert any(cf["property"] == "dataBarEnabled" for cf in info["conditionalFormatting"])

    def test_get_missing_returns_none(self, backend):
        backend.page_add("P")
        assert backend.visual_get("P", "ghost") is None
