"""Unit tests for the deeper rebind and generic formatting writers.

Synthetic PBIR GA project in tmp_path — runs on any OS, no Desktop required.
"""

from __future__ import annotations

import json

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_bar_chart,
)


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    report_dir = tmp_path / "Test.Report"
    report_dir.mkdir()
    return PbirBackend(str(tmp_path))


def _add_bar(backend: PbirBackend, page: str) -> str:
    spec = VisualSpec(
        visual_type="barChart",
        visual_body=build_bar_chart(
            FieldDef(entity="financials", property="Country", agg=None),
            FieldDef(entity="financials", property="Sales", agg=AGG_SUM),
        ),
        x=0, y=0, width=400, height=300, title="Bar",
    )
    return backend.visual_add(page, spec)["name"]


def _visual_json(backend: PbirBackend, page: str, name: str) -> dict:
    found = backend._ga_find_visual_json(page, name)  # type: ignore[attr-defined]
    assert found
    return found[1]


# ── visual_rebind ───────────────────────────────────────────────────────────────


class TestRebind:
    def test_rebind_replaces_role(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        ok = backend.visual_rebind(
            "P", name, {"Y": [FieldDef(entity="financials", property="Profit", agg=AGG_SUM)]}
        )
        assert ok
        qs = _visual_json(backend, "P", name)["visual"]["query"]["queryState"]
        projs = qs["Y"]["projections"]
        assert len(projs) == 1
        assert "Profit" in projs[0]["queryRef"]
        # Category preserved (not listed, clear_unlisted=False)
        assert "Category" in qs

    def test_rebind_multiple_fields_one_role(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_rebind(
            "P", name,
            {"Y": [
                FieldDef(entity="financials", property="Sales", agg=AGG_SUM),
                FieldDef(entity="financials", property="Profit", agg=AGG_SUM),
            ]},
        )
        qs = _visual_json(backend, "P", name)["visual"]["query"]["queryState"]
        assert len(qs["Y"]["projections"]) == 2

    def test_rebind_clear_unlisted(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_rebind(
            "P", name,
            {"Category": [FieldDef(entity="financials", property="Segment", agg=None)]},
            clear_unlisted=True,
        )
        qs = _visual_json(backend, "P", name)["visual"]["query"]["queryState"]
        assert set(qs) == {"Category"}

    def test_rebind_missing_visual_returns_false(self, backend):
        backend.page_add("P")
        assert backend.visual_rebind("P", "nope", {"Y": []}) is False

    def test_rebind_empty_role_raises(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        with pytest.raises(ValueError):
            backend.visual_rebind("P", name, {"": [FieldDef(entity="t", property="c")]})


# ── visual_set_format ───────────────────────────────────────────────────────────


class TestSetFormat:
    def test_set_bool_property(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        ok = backend.visual_set_format("P", name, "dataLabels", "show", True, value_type="bool")
        assert ok
        objects = _visual_json(backend, "P", name)["visual"]["objects"]
        expr = objects["dataLabels"][0]["properties"]["show"]["expr"]
        assert expr["Literal"]["Value"] == "true"

    def test_set_text_property(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format("P", name, "legend", "position", "Top", value_type="text")
        objects = _visual_json(backend, "P", name)["visual"]["objects"]
        assert objects["legend"][0]["properties"]["position"]["expr"]["Literal"]["Value"] == "'Top'"

    def test_set_color_property(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format(
            "P", name, "background", "color", "#F5F5F5", value_type="color", container_level=True
        )
        vco = _visual_json(backend, "P", name)["visual"]["visualContainerObjects"]
        solid = vco["background"][0]["properties"]["color"]["solid"]
        assert solid["color"]["expr"]["Literal"]["Value"] == "'#F5F5F5'"

    def test_set_number_property(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format("P", name, "general", "transparency", 50, value_type="number")
        objects = _visual_json(backend, "P", name)["visual"]["objects"]
        prop = objects["general"][0]["properties"]["transparency"]
        assert prop["expr"]["Literal"]["Value"] == "50D"

    def test_auto_detects_color(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format("P", name, "background", "color", "#ABCDEF")
        objects = _visual_json(backend, "P", name)["visual"]["objects"]
        assert "solid" in objects["background"][0]["properties"]["color"]

    def test_repeated_calls_merge_into_one_entry(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format("P", name, "legend", "show", True, value_type="bool")
        backend.visual_set_format("P", name, "legend", "position", "Bottom", value_type="text")
        objects = _visual_json(backend, "P", name)["visual"]["objects"]
        assert len(objects["legend"]) == 1
        assert set(objects["legend"][0]["properties"]) == {"show", "position"}

    def test_missing_visual_returns_false(self, backend):
        backend.page_add("P")
        assert backend.visual_set_format("P", "nope", "legend", "show", True) is False

    def test_round_trips_as_valid_json(self, backend):
        backend.page_add("P")
        name = _add_bar(backend, "P")
        backend.visual_set_format("P", name, "legend", "position", "Top")
        found = backend._ga_find_visual_json("P", name)  # type: ignore[attr-defined]
        # Re-read from disk to confirm it serialised cleanly.
        data = json.loads(found[0].read_text(encoding="utf-8"))
        assert data["visual"]["objects"]["legend"]
