"""Unit tests for the second batch of PBIR features:

  - icon-set conditional formatting (default percent + custom absolute)
  - between-bounds colour rules
  - visual field rebinding
  - report-level measures (reportExtensions.json)
  - bookmark groups
  - non-data element builders (textbox / button / navigators)
  - pbi project new scaffold (openable PBIP)

Synthetic PBIR GA project in tmp_path — runs anywhere, no Desktop needed.
"""

from __future__ import annotations

import json

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_card,
    build_table,
)


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    (tmp_path / "T.Report").mkdir()
    return PbirBackend(str(tmp_path))


def _fd(prop: str) -> FieldDef:
    return FieldDef(entity="financials", property=prop, agg=AGG_SUM)


def _add_table(b: PbirBackend, page: str, *props: str) -> str:
    spec = VisualSpec("tableEx", build_table([_fd(p) for p in props]), 16, 16, 600, 300)
    return b.visual_add(page, spec)["name"]


def _add_card(b: PbirBackend, page: str) -> str:
    spec = VisualSpec("card", build_card(_fd("Sales")), 0, 0, 200, 120)
    return b.visual_add(page, spec)["name"]


# ── Icon-set conditional formatting ───────────────────────────────────────────


class TestIconCF:
    def _setup(self, backend, page="IconP"):
        backend.page_add(page)
        return page, _add_table(backend, page, "Profit")

    def test_default_three_band_percent(self, backend):
        page, name = self._setup(backend)
        assert backend.visual_format_icons(page, name, "financials", "Profit")
        _, d = backend._ga_find_visual_json(page, name)
        icon = d["visual"]["objects"]["values"][0]["properties"]["icon"]
        assert icon["kind"] == "Icon"
        cases = icon["value"]["expr"]["Conditional"]["Cases"]
        assert [c["Value"]["Literal"]["Value"] for c in cases] == [
            "'CircleHigh'", "'SignMedium'", "'SignLow'"
        ]
        top = cases[0]["Condition"]["Comparison"]
        assert top["ComparisonKind"] == 2
        assert top["Right"]["RangePercent"]["Percent"] == 0.67
        assert "And" in cases[1]["Condition"]
        assert top["Left"] == {"SelectRef": {"ExpressionName": "Sum(financials[Profit])"}}

    def test_custom_absolute_icon_rules(self, backend):
        page, name = self._setup(backend, "IconAbs")
        backend.visual_format_icons(
            page, name, "financials", "Profit",
            rules=[(">=", 0, "ArrowUp"), ("<", 0, "ArrowDown")],
        )
        _, d = backend._ga_find_visual_json(page, name)
        cases = d["visual"]["objects"]["values"][0]["properties"]["icon"][
            "value"]["expr"]["Conditional"]["Cases"]
        assert [c["Value"]["Literal"]["Value"] for c in cases] == ["'ArrowUp'", "'ArrowDown'"]
        assert "Literal" in cases[0]["Condition"]["Comparison"]["Right"]

    def test_icon_merges_with_existing_color(self, backend):
        page, name = self._setup(backend, "IconMerge")
        backend.visual_format_color_scale(page, name, "financials", "Profit", mid_color=None)
        backend.visual_format_icons(page, name, "financials", "Profit")
        _, d = backend._ga_find_visual_json(page, name)
        values = d["visual"]["objects"]["values"]
        assert len(values) == 1
        assert {"backColor", "icon"} <= set(values[0]["properties"])

    def test_color_scale_after_icon_preserves_icon(self, backend):
        # Reverse order of the merge test: color scale must not clobber the icon
        # already applied to the same field (regression for the remove-all bug).
        page, name = self._setup(backend, "ColorAfterIcon")
        backend.visual_format_icons(page, name, "financials", "Profit")
        backend.visual_format_color_scale(page, name, "financials", "Profit", mid_color=None)
        _, d = backend._ga_find_visual_json(page, name)
        values = d["visual"]["objects"]["values"]
        assert len(values) == 1
        assert {"backColor", "icon"} <= set(values[0]["properties"])

    def test_data_bar_and_color_scale_coexist(self, backend):
        page, name = self._setup(backend, "BarPlusScale")
        backend.visual_format_data_bar(page, name, "financials", "Profit")
        backend.visual_format_color_scale(page, name, "financials", "Profit")
        _, d = backend._ga_find_visual_json(page, name)
        values = d["visual"]["objects"]["values"]
        assert len(values) == 1
        assert {"backColor", "dataBarEnabled"} <= set(values[0]["properties"])


# ── Between-bounds colour rules ───────────────────────────────────────────────


class TestBetweenRules:
    def test_between_builds_and_condition(self, backend):
        backend.page_add("BetP")
        name = _add_table(backend, "BetP", "Sales")
        backend.visual_format_rules(
            "BetP", name, "financials", "Sales",
            [("between", 0, 1000, "#00FF00"), (">=", 1000, "#FF0000")],
        )
        _, d = backend._ga_find_visual_json("BetP", name)
        cases = d["visual"]["objects"]["values"][0]["properties"][
            "backColor"]["solid"]["color"]["expr"]["Conditional"]["Cases"]
        andc = cases[0]["Condition"]["And"]
        assert andc["Left"]["Comparison"]["ComparisonKind"] == 2
        assert andc["Right"]["Comparison"]["ComparisonKind"] == 3
        assert "Comparison" in cases[1]["Condition"]


# ── Field rebinding ───────────────────────────────────────────────────────────


class TestFieldRebind:
    def test_replace_role_projection(self, backend):
        backend.page_add("RbP")
        name = _add_table(backend, "RbP", "Sales")
        assert backend.visual_set_field("RbP", name, "Values", "financials", "Profit", agg=AGG_SUM)
        _, d = backend._ga_find_visual_json("RbP", name)
        projs = d["visual"]["query"]["queryState"]["Values"]["projections"]
        assert len(projs) == 1
        assert projs[0]["queryRef"] == "Sum(financials[Profit])"

    def test_append_role_projection(self, backend):
        backend.page_add("RbP2")
        name = _add_table(backend, "RbP2", "Sales")
        backend.visual_set_field(
            "RbP2", name, "Values", "financials", "Profit", agg=AGG_SUM, replace=False
        )
        _, d = backend._ga_find_visual_json("RbP2", name)
        refs = [p["queryRef"] for p in d["visual"]["query"]["queryState"]["Values"]["projections"]]
        assert refs == ["Sum(financials[Sales])", "Sum(financials[Profit])"]

    def test_missing_visual_returns_false(self, backend):
        backend.page_add("RbP3")
        assert backend.visual_set_field("RbP3", "nope", "Values", "financials", "Sales") is False


# ── Report-level measures ─────────────────────────────────────────────────────


class TestReportMeasures:
    def test_add_and_list(self, backend):
        backend.report_measure_add(
            "financials", "Margin %",
            "DIVIDE(SUM(financials[Profit]),SUM(financials[Sales]))", format_string="0.0%",
        )
        measures = backend.report_measure_list()
        assert len(measures) == 1
        assert measures[0]["name"] == "Margin %"
        ext = json.loads((backend.report_dir / "definition" / "reportExtensions.json").read_text())
        assert ext["name"] == "extension"
        ent = ext["entities"][0]
        assert ent["name"] == "financials" and "extends" not in ent
        m = ent["measures"][0]
        assert m["dataType"] == "Double"  # required by schema
        assert m["formatString"] == "0.0%"

    def test_replace_same_name(self, backend):
        backend.report_measure_add("financials", "M", "1")
        backend.report_measure_add("financials", "M", "2")
        measures = backend.report_measure_list()
        assert len(measures) == 1 and measures[0]["expression"] == "2"


# ── Bookmark groups ───────────────────────────────────────────────────────────


class TestBookmarkGroups:
    def test_group_nests_members(self, backend):
        backend.page_add("BGP")
        _add_card(backend, "BGP")
        backend.bookmark_add("A", page="BGP")
        backend.bookmark_add("B", page="BGP")
        result = backend.bookmark_group_add("Story", ["A", "B"])
        meta = backend._ga_read_bookmarks_json()
        group = next(it for it in meta["items"] if it.get("name") == result["name"])
        assert group["displayName"] == "Story"
        assert len(group["children"]) == 2
        top_names = {it["name"] for it in meta["items"] if "children" not in it}
        assert not (set(result["members"]) & top_names)


# ── Non-data element builders ─────────────────────────────────────────────────


class TestElements:
    def test_textbox_with_text(self):
        from pbi_cli.intelligence.visual_builder import build_textbox
        body = build_textbox("Hello")
        assert body["visualType"] == "textbox"
        runs = body["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"]
        assert runs[0]["value"] == "Hello"

    def test_action_button_shape(self):
        from pbi_cli.intelligence.visual_builder import build_action_button
        icon = build_action_button(shape="blank")["objects"]["icon"][0]
        assert icon["properties"]["shapeType"]["expr"]["Literal"]["Value"] == "'blank'"
        assert icon["selector"] == {"id": "default"}

    def test_navigators(self):
        from pbi_cli.intelligence.visual_builder import (
            build_bookmark_navigator,
            build_page_navigator,
        )
        assert build_page_navigator()["visualType"] == "pageNavigator"
        assert build_bookmark_navigator()["visualType"] == "bookmarkNavigator"

    def test_add_element_via_backend(self, backend):
        from pbi_cli.intelligence.visual_builder import build_page_navigator
        backend.page_add("ElP")
        body = build_page_navigator()
        spec = VisualSpec(visual_type=body["visualType"], visual_body=body,
                          x=0, y=0, width=800, height=60)
        backend.visual_add("ElP", spec)
        assert "pageNavigator" in [v["visualType"] for v in backend.visual_list("ElP")]


# ── project scaffold ──────────────────────────────────────────────────────────


class TestProjectScaffold:
    def test_creates_openable_structure(self, tmp_path):
        from pbi_cli.project_scaffold import create_project
        pbip = create_project(str(tmp_path), name="Acme", table="Financials")
        assert pbip.exists()
        root = tmp_path / "Acme"
        model = (root / "Acme.SemanticModel" / "definition" / "model.tmdl").read_text()
        assert "ref table Financials" in model
        assert "ref cultureInfo en-US" in model
        b = PbirBackend(str(pbip))
        assert b.format == "pbir_ga"
        assert "Overview" in [p["displayName"] for p in b.page_list()]
        assert len(b.visual_list("Overview")) >= 4
        assert (root / "Acme.Report" / "definition" / "version.json").exists()
