"""Unit tests for the PBIR features added to close report-layer gaps:

  - visual update/patch (position + title)
  - rule-based / font-color conditional formatting
  - bookmark state capture (sections + hidden visuals)
  - page visual interactions
  - slicer sync groups

All tests build a synthetic PBIR GA project in tmp_path, so they run on any
OS with no Power BI Desktop and no live .pbip fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_card,
    build_slicer,
    build_table,
)


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    """A fresh, empty PBIR GA report backed by tmp_path."""
    report_dir = tmp_path / "Test.Report"
    report_dir.mkdir()
    return PbirBackend(str(tmp_path))


def _add_table(backend: PbirBackend, page: str, *fields: FieldDef, title: str = "") -> str:
    spec = VisualSpec(
        visual_type="tableEx",
        visual_body=build_table(list(fields)),
        x=16,
        y=16,
        width=600,
        height=300,
        title=title,
    )
    return backend.visual_add(page, spec)["name"]


def _add_card(backend: PbirBackend, page: str) -> str:
    spec = VisualSpec(
        visual_type="card",
        visual_body=build_card(FieldDef(entity="financials", property="Sales", agg=AGG_SUM)),
        x=0,
        y=0,
        width=200,
        height=120,
    )
    return backend.visual_add(page, spec)["name"]


# ── Format detection ────────────────────────────────────────────────────────────


def test_synthetic_report_is_ga(backend):
    assert backend.format == "pbir_ga"


# ── Visual update ─────────────────────────────────────────────────────────────


class TestVisualUpdate:
    def test_update_position(self, backend):
        backend.page_add("P1")
        name = _add_card(backend, "P1")
        assert backend.visual_update("P1", name, x=120, y=240, width=480, height=200)
        v = next(v for v in backend.visual_list("P1") if v["name"] == name)
        assert (v["x"], v["y"], v["width"], v["height"]) == (120, 240, 480, 200)

    def test_update_title_only_preserves_position(self, backend):
        backend.page_add("P2")
        name = _add_card(backend, "P2")
        before = next(v for v in backend.visual_list("P2") if v["name"] == name)
        assert backend.visual_update("P2", name, title="New Title")
        _, data = backend._ga_find_visual_json("P2", name)
        title = data["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]
        assert title["expr"]["Literal"]["Value"] == "'New Title'"
        after = next(v for v in backend.visual_list("P2") if v["name"] == name)
        assert (after["x"], after["y"]) == (before["x"], before["y"])

    def test_update_partial_leaves_other_fields(self, backend):
        backend.page_add("P3")
        name = _add_card(backend, "P3")
        backend.visual_update("P3", name, x=99)
        v = next(v for v in backend.visual_list("P3") if v["name"] == name)
        assert v["x"] == 99
        assert v["width"] == 200  # unchanged from add

    def test_update_missing_visual_returns_false(self, backend):
        backend.page_add("P4")
        assert backend.visual_update("P4", "nope", x=1) is False


# ── Conditional formatting: rules + font color ────────────────────────────────


class TestFormatRules:
    def _setup(self, backend, page="RuleP"):
        backend.page_add(page)
        name = _add_table(
            backend, page, FieldDef(entity="financials", property="Profit", agg=AGG_SUM)
        )
        return page, name

    def test_rules_backcolor_conditional_cases(self, backend):
        page, name = self._setup(backend)
        ok = backend.visual_format_rules(
            page,
            name,
            "financials",
            "Profit",
            [(">=", 1000, "#00FF00"), ("<", 0, "#FF0000")],
            target="backColor",
        )
        assert ok
        _, data = backend._ga_find_visual_json(page, name)
        entry = data["visual"]["objects"]["values"][0]
        cases = entry["properties"]["backColor"]["solid"]["color"]["expr"]["Conditional"]["Cases"]
        assert len(cases) == 2
        # first rule: >= maps to ComparisonKind 2, literal '1000D'
        cmp = cases[0]["Condition"]["Comparison"]
        assert cmp["ComparisonKind"] == 2
        assert cmp["Right"]["Literal"]["Value"] == "1000D"
        assert cases[0]["Value"]["Literal"]["Value"] == "'#00FF00'"
        # second rule: < maps to ComparisonKind 3
        assert cases[1]["Condition"]["Comparison"]["ComparisonKind"] == 3

    def test_font_color_uses_fontcolor_property(self, backend):
        page, name = self._setup(backend, "FontP")
        backend.visual_format_rules(
            page, name, "financials", "Profit", [("<", 0, "#A4262C")], target="fontColor"
        )
        _, data = backend._ga_find_visual_json(page, name)
        props = data["visual"]["objects"]["values"][0]["properties"]
        assert "fontColor" in props
        assert "backColor" not in props

    def test_backcolor_and_fontcolor_merge_into_one_entry(self, backend):
        page, name = self._setup(backend, "MergeP")
        backend.visual_format_rules(
            page, name, "financials", "Profit", [(">=", 0, "#00FF00")], target="backColor"
        )
        backend.visual_format_rules(
            page, name, "financials", "Profit", [("<", 0, "#FF0000")], target="fontColor"
        )
        _, data = backend._ga_find_visual_json(page, name)
        values = data["visual"]["objects"]["values"]
        assert len(values) == 1, "same field should keep a single values entry"
        props = values[0]["properties"]
        assert "backColor" in props and "fontColor" in props

    def test_selector_has_data_wildcard_and_metadata(self, backend):
        page, name = self._setup(backend, "SelP")
        backend.visual_format_rules(
            page, name, "financials", "Profit", [(">=", 0, "#00FF00")]
        )
        _, data = backend._ga_find_visual_json(page, name)
        sel = data["visual"]["objects"]["values"][0]["selector"]
        assert sel["data"][0]["dataViewWildcard"]["matchingOption"] == 1
        assert sel["metadata"] == "Sum(financials[Profit])"

    def test_bad_operator_raises(self, backend):
        page, name = self._setup(backend, "BadP")
        with pytest.raises(ValueError):
            backend.visual_format_rules(
                page, name, "financials", "Profit", [("!!", 0, "#000000")]
            )

    def test_bad_target_raises(self, backend):
        page, name = self._setup(backend, "BadT")
        with pytest.raises(ValueError):
            backend.visual_format_rules(
                page, name, "financials", "Profit", [(">=", 0, "#000")], target="border"
            )


# ── Bookmark state capture ────────────────────────────────────────────────────


class TestBookmarkCapture:
    def test_capture_records_page_visuals(self, backend):
        backend.page_add("BMPage")
        v1 = _add_card(backend, "BMPage")
        v2 = _add_table(
            backend, "BMPage", FieldDef(entity="financials", property="Sales", agg=AGG_SUM)
        )
        result = backend.bookmark_add("Snapshot", page="BMPage")

        bm_file = backend._ga_bookmarks_dir() / f"{result['name']}.bookmark.json"
        data = json.loads(Path(bm_file).read_text(encoding="utf-8"))
        sections = data["explorationState"]["sections"]
        assert len(sections) == 1
        page_state = next(iter(sections.values()))
        vcs = page_state["visualContainers"]
        assert set(vcs) == {v1, v2}
        assert all("singleVisual" in vc for vc in vcs.values())

    def test_hidden_visual_gets_display_mode_hidden(self, backend):
        backend.page_add("HidePage")
        v1 = _add_card(backend, "HidePage")
        v2 = _add_card(backend, "HidePage")
        result = backend.bookmark_add("HideOne", page="HidePage", hidden_visuals=[v2])

        bm_file = backend._ga_bookmarks_dir() / f"{result['name']}.bookmark.json"
        data = json.loads(Path(bm_file).read_text(encoding="utf-8"))
        vcs = next(iter(data["explorationState"]["sections"].values()))["visualContainers"]
        assert "display" not in vcs[v1]["singleVisual"]
        assert vcs[v2]["singleVisual"]["display"]["mode"] == "hidden"
        assert result["hiddenCount"] == 1

    def test_target_visual_names_populated(self, backend):
        backend.page_add("TgtPage")
        _add_card(backend, "TgtPage")
        result = backend.bookmark_add("Tgt", page="TgtPage")
        assert len(result["options"]["targetVisualNames"]) == 1

    def test_no_capture_writes_empty_sections(self, backend):
        backend.page_add("EmptyPage")
        _add_card(backend, "EmptyPage")
        result = backend.bookmark_add("Skel", page="EmptyPage", capture=False)
        bm_file = backend._ga_bookmarks_dir() / f"{result['name']}.bookmark.json"
        data = json.loads(Path(bm_file).read_text(encoding="utf-8"))
        assert data["explorationState"]["sections"] == {}


# ── Visual interactions ───────────────────────────────────────────────────────


class TestVisualInteractions:
    def test_set_interaction_writes_page_json(self, backend):
        backend.page_add("IxPage")
        src = _add_card(backend, "IxPage")
        tgt = _add_card(backend, "IxPage")
        backend.set_visual_interaction("IxPage", src, tgt, "NoFilter")

        page_dir = backend._ga_find_page_dir("IxPage")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        ix = data["visualInteractions"]
        assert ix == [{"source": src, "target": tgt, "type": "NoFilter"}]

    def test_set_interaction_replaces_same_pair(self, backend):
        backend.page_add("IxPage2")
        src = _add_card(backend, "IxPage2")
        tgt = _add_card(backend, "IxPage2")
        backend.set_visual_interaction("IxPage2", src, tgt, "NoFilter")
        backend.set_visual_interaction("IxPage2", src, tgt, "HighlightFilter")
        page_dir = backend._ga_find_page_dir("IxPage2")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        assert len(data["visualInteractions"]) == 1
        assert data["visualInteractions"][0]["type"] == "HighlightFilter"

    def test_bad_type_raises(self, backend):
        backend.page_add("IxBad")
        a = _add_card(backend, "IxBad")
        b = _add_card(backend, "IxBad")
        with pytest.raises(ValueError):
            backend.set_visual_interaction("IxBad", a, b, "Bogus")

    def test_missing_page_raises(self, backend):
        with pytest.raises(ValueError):
            backend.set_visual_interaction("NoPage", "a", "b", "NoFilter")


# ── Slicer sync ───────────────────────────────────────────────────────────────


class TestSlicerSync:
    def test_sync_writes_sync_group(self, backend):
        backend.page_add("SyncPage")
        spec = VisualSpec(
            visual_type="slicer",
            visual_body=build_slicer(FieldDef(entity="financials", property="Country", agg=None)),
            x=0,
            y=0,
            width=200,
            height=300,
        )
        name = backend.visual_add("SyncPage", spec)["name"]
        assert backend.set_slicer_sync("SyncPage", name, "Region", filter_changes=False)
        _, data = backend._ga_find_visual_json("SyncPage", name)
        sg = data["visual"]["syncGroup"]
        assert sg["groupName"] == "Region"
        assert sg["fieldChanges"] is True
        assert sg["filterChanges"] is False

    def test_sync_missing_visual_returns_false(self, backend):
        backend.page_add("SyncMiss")
        assert backend.set_slicer_sync("SyncMiss", "nope", "G") is False


# ── CLI surface ───────────────────────────────────────────────────────────────


class TestCliSurface:
    """Exercise the click commands end-to-end against a synthetic project."""

    @pytest.fixture()
    def project(self, tmp_path):
        from click.testing import CliRunner

        report_dir = tmp_path / "Cli.Report"
        report_dir.mkdir()
        b = PbirBackend(str(tmp_path))
        b.page_add("Sales")
        name = _add_table(
            b, "Sales", FieldDef(entity="financials", property="Profit", agg=AGG_SUM)
        )
        # second card to act as interaction target
        card = _add_card(b, "Sales")
        return CliRunner(), str(tmp_path), name, card

    def _run(self, runner, *args):
        from pbi_cli.cli import cli

        return runner.invoke(cli, list(args))

    def test_update_requires_a_property(self, project):
        runner, pbip, name, _ = project
        r = self._run(runner, "visual", "update", "--pbip", pbip, "--page", "Sales", "--name", name)
        assert r.exit_code != 0
        assert "at least one" in r.output.lower()

    def test_update_title_and_position(self, project):
        runner, pbip, name, _ = project
        r = self._run(
            runner, "visual", "update", "--pbip", pbip, "--page", "Sales",
            "--name", name, "--x", "50", "--title", "Revenue",
        )
        assert r.exit_code == 0, r.output
        assert "Updated" in r.output

    def test_format_rules_via_cli(self, project):
        runner, pbip, name, _ = project
        r = self._run(
            runner, "visual", "format", "--pbip", pbip, "--page", "Sales",
            "--visual", name, "--type", "rules", "--target", "text",
            "--table", "financials", "--measure", "Profit",
            "--rule", ">=:0:#107C10", "--rule", "<:0:#A4262C",
        )
        assert r.exit_code == 0, r.output
        assert "rules" in r.output.lower()

    def test_format_rules_requires_rule(self, project):
        runner, pbip, name, _ = project
        r = self._run(
            runner, "visual", "format", "--pbip", pbip, "--page", "Sales",
            "--visual", name, "--type", "rules",
            "--table", "financials", "--measure", "Profit",
        )
        assert r.exit_code != 0

    def test_format_rule_bad_format(self, project):
        runner, pbip, name, _ = project
        r = self._run(
            runner, "visual", "format", "--pbip", pbip, "--page", "Sales",
            "--visual", name, "--type", "rules",
            "--table", "financials", "--measure", "Profit", "--rule", "garbage",
        )
        assert r.exit_code != 0

    def test_interaction_via_cli(self, project):
        runner, pbip, name, card = project
        r = self._run(
            runner, "visual", "interaction", "--pbip", pbip, "--page", "Sales",
            "--source", name, "--target", card, "--type", "NoFilter",
        )
        assert r.exit_code == 0, r.output
        assert "Interaction set" in r.output

    def test_sync_slicer_via_cli(self, project):
        runner, pbip, name, _ = project
        r = self._run(
            runner, "visual", "sync-slicer", "--pbip", pbip, "--page", "Sales",
            "--name", name, "--group", "Region",
        )
        assert r.exit_code == 0, r.output

    def test_bookmark_add_hidden_via_cli(self, project):
        runner, pbip, name, card = project
        r = self._run(
            runner, "report", "bookmark-add", "--pbip", pbip, "--name", "HideBM",
            "--page", "Sales", "--hidden-visual", card,
        )
        assert r.exit_code == 0, r.output
        assert "Captured" in r.output
