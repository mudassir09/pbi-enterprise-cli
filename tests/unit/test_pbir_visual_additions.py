"""Unit tests for the new PBIR visual features:

  - AI visual builders (decomposition tree, key influencers, smart narrative, Q&A)
  - button action wiring (visualLink)
  - constant reference line
  - visual introspection (visual get)

Synthetic PBIR GA project in tmp_path — runs anywhere, no Desktop.
"""

from __future__ import annotations

import json

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
    build_line_chart,
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


class TestAnalytics:
    def _line(self, b, page="P"):
        b.page_add(page)
        spec = VisualSpec(
            "lineChart", build_line_chart(_col("Month"), _meas("Sales")), 0, 0, 400, 300
        )
        return page, b.visual_add(page, spec)["name"]

    def test_trend_line(self, backend, tmp_path):
        page, name = self._line(backend)
        assert backend.visual_add_trend_line(page, name, color="#FF0000", transparency=20)
        _, data = backend._ga_find_visual_json(page, name)
        trend = data["visual"]["objects"]["trend"]
        assert len(trend) == 1
        props = trend[0]["properties"]
        assert props["show"]["expr"]["Literal"]["Value"] == "true"
        assert props["transparency"]["expr"]["Literal"]["Value"] == "20D"
        assert not [f for f in validate_report(str(tmp_path)) if f["severity"] == "error"]

    def test_trend_line_reapply_replaces(self, backend):
        page, name = self._line(backend)
        backend.visual_add_trend_line(page, name)
        backend.visual_add_trend_line(page, name, style="solid")
        _, data = backend._ga_find_visual_json(page, name)
        # Single-instance object: re-applying updates, never stacks duplicates.
        assert len(data["visual"]["objects"]["trend"]) == 1
        assert data["visual"]["objects"]["trend"][0]["properties"][
            "style"]["expr"]["Literal"]["Value"] == "'solid'"

    def test_trend_bad_style_raises(self, backend):
        page, name = self._line(backend)
        with pytest.raises(ValueError):
            backend.visual_add_trend_line(page, name, style="zigzag")

    def test_forecast(self, backend, tmp_path):
        page, name = self._line(backend)
        assert backend.visual_add_forecast(page, name, length=12, confidence_level=0.9,
                                           seasonality=12)
        _, data = backend._ga_find_visual_json(page, name)
        props = data["visual"]["objects"]["forecast"][0]["properties"]
        assert props["forecastLength"]["expr"]["Literal"]["Value"] == "12D"
        assert props["confidenceLevel"]["expr"]["Literal"]["Value"] == "0.9D"
        assert props["seasonality"]["expr"]["Literal"]["Value"] == "12D"
        assert not [f for f in validate_report(str(tmp_path)) if f["severity"] == "error"]

    def test_forecast_bad_confidence_raises(self, backend):
        page, name = self._line(backend)
        with pytest.raises(ValueError):
            backend.visual_add_forecast(page, name, confidence_level=1.5)

    def test_missing_visual_returns_false(self, backend):
        backend.page_add("P")
        assert backend.visual_add_trend_line("P", "ghost") is False
        assert backend.visual_add_forecast("P", "ghost") is False


class TestThemeAndCustomVisual:
    def test_theme_register_writes_file_and_binds_report_json(self, backend, tmp_path):
        path = backend.theme_register({"name": "Brand", "dataColors": ["#112233"]}, name="Brand")
        assert (tmp_path / "T.Report" / "StaticResources" / "RegisteredResources"
                / "Brand.json").exists()
        assert path.endswith("Brand.json")
        rj = json.loads(
            (tmp_path / "T.Report" / "definition" / "report.json").read_text(encoding="utf-8")
        )
        ct = rj["themeCollection"]["customTheme"]
        assert ct["name"] == "Brand"
        assert ct["type"] == "RegisteredResources"
        # Desktop rejects a customTheme without reportVersionAtImport (verified live).
        assert "reportVersionAtImport" in ct
        pkg = next(p for p in rj["resourcePackages"] if p["type"] == "RegisteredResources")
        assert any(it["path"] == "Brand.json" and it["type"] == "CustomTheme"
                   for it in pkg["items"])
        # Base theme is preserved alongside the custom theme.
        assert "baseTheme" in rj["themeCollection"]

    def test_theme_register_reapply_no_duplicate_items(self, backend, tmp_path):
        backend.theme_register({"name": "Brand"}, name="Brand")
        backend.theme_register({"name": "Brand", "dataColors": ["#abcdef"]}, name="Brand")
        rj = json.loads(
            (tmp_path / "T.Report" / "definition" / "report.json").read_text(encoding="utf-8")
        )
        pkg = next(p for p in rj["resourcePackages"] if p["type"] == "RegisteredResources")
        assert len([it for it in pkg["items"] if it["path"] == "Brand.json"]) == 1

    def test_custom_visual_register(self, backend, tmp_path):
        assert backend.custom_visual_register("MyViz1A2B3C") is True
        assert backend.custom_visual_register("MyViz1A2B3C") is False  # idempotent
        rj = json.loads(
            (tmp_path / "T.Report" / "definition" / "report.json").read_text(encoding="utf-8")
        )
        assert rj["publicCustomVisuals"] == ["MyViz1A2B3C"]
        assert not [f for f in validate_report(str(tmp_path)) if f["severity"] == "error"]


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
