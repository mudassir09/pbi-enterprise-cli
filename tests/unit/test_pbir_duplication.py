"""Unit tests for PBIR page duplication and visual clone/move.

Verifies the copy is fully independent (fresh ids, remapped group / interaction
references) and that the resulting report still passes structural validation.
"""

from __future__ import annotations

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_bar_chart,
    build_card,
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


def _add_card(b, page) -> str:
    spec = VisualSpec("card", build_card(_meas("Sales")), 0, 0, 200, 120)
    return b.visual_add(page, spec)["name"]


def _add_bar(b, page) -> str:
    spec = VisualSpec(
        "barChart", build_bar_chart(_col("Country"), _meas("Sales")), 0, 200, 400, 300
    )
    return b.visual_add(page, spec)["name"]


def _errors(tmp_path):
    return [f for f in validate_report(str(tmp_path)) if f["severity"] == "error"]


class TestPageDuplicate:
    def test_duplicate_creates_independent_page(self, backend, tmp_path):
        backend.page_add("Sales")
        a = _add_card(backend, "Sales")
        b = _add_bar(backend, "Sales")
        backend.set_visual_interaction("Sales", a, b, "NoFilter")

        result = backend.page_duplicate("Sales", new_display_name="Sales (copy)")
        pages = {p["displayName"]: p for p in backend.page_list()}
        assert "Sales (copy)" in pages
        assert result["visuals"] == 2

        # New page's visuals have different ids than the source.
        src_ids = {v["name"] for v in backend.visual_list("Sales")}
        new_ids = {v["name"] for v in backend.visual_list("Sales (copy)")}
        assert src_ids.isdisjoint(new_ids)
        # Still valid (interactions remapped to the new ids, no danglers).
        assert _errors(tmp_path) == []

    def test_duplicate_remaps_group_membership(self, backend, tmp_path):
        backend.page_add("G")
        a = _add_card(backend, "G")
        b = _add_bar(backend, "G")
        backend.visual_group_add("G", [a, b], display_name="grp")

        backend.page_duplicate("G")
        assert _errors(tmp_path) == []  # no dangling parentGroupName

    def test_duplicate_missing_page_raises(self, backend):
        with pytest.raises(ValueError):
            backend.page_duplicate("Nope")


class TestVisualClone:
    def test_clone_in_place_offsets(self, backend):
        backend.page_add("P")
        name = _add_card(backend, "P")
        res = backend.visual_clone("P", name, dx=24, dy=24)
        assert res and res["name"] != name
        visuals = {v["name"]: v for v in backend.visual_list("P")}
        assert visuals[res["name"]]["x"] == visuals[name]["x"] + 24

    def test_clone_to_other_page(self, backend, tmp_path):
        backend.page_add("A")
        backend.page_add("B")
        name = _add_bar(backend, "A")
        res = backend.visual_clone("A", name, target_page="B")
        assert res and res["page"] == "B"
        assert any(v["name"] == res["name"] for v in backend.visual_list("B"))
        assert _errors(tmp_path) == []

    def test_clone_missing_returns_none(self, backend):
        backend.page_add("P")
        assert backend.visual_clone("P", "ghost") is None


class TestVisualMove:
    def test_move_keeps_id_and_scrubs_interactions(self, backend, tmp_path):
        backend.page_add("A")
        backend.page_add("B")
        a = _add_card(backend, "A")
        b = _add_bar(backend, "A")
        backend.set_visual_interaction("A", a, b, "NoFilter")

        res = backend.visual_move("A", b, "B")
        assert res and res["name"] == b
        assert any(v["name"] == b for v in backend.visual_list("B"))
        assert all(v["name"] != b for v in backend.visual_list("A"))
        # The interaction referencing the moved visual is gone — no danglers.
        assert _errors(tmp_path) == []

    def test_move_same_page_raises(self, backend):
        backend.page_add("A")
        name = _add_card(backend, "A")
        with pytest.raises(ValueError):
            backend.visual_move("A", name, "A")
