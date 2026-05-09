"""Unit tests for pbi visual format (conditional formatting)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli

_PBIP_PATH = Path(r"C:\Users\GGPC\Documents\financials.pbip")
_REPORT_DIR = Path(r"C:\Users\GGPC\Documents\financials.Report")


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def pbip_copy(tmp_path) -> str:
    if not _REPORT_DIR.exists():
        pytest.skip("financials.Report not found")
    report_copy = tmp_path / "financials.Report"
    shutil.copytree(_REPORT_DIR, report_copy)
    pbip_file = tmp_path / "financials.pbip"
    pbip_file.write_text(
        json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "financials.Report"}}]}),
        encoding="utf-8",
    )
    return str(pbip_file)


def _run(runner, *args):
    return runner.invoke(cli, list(args))


class TestVisualFormat:
    def test_format_missing_visual_exits_nonzero(self, runner, pbip_copy):
        result = _run(
            runner,
            "visual", "format",
            "--pbip", pbip_copy,
            "--page", "Executive Summary",
            "--visual", "definitely_does_not_exist_xyz",
            "--type", "color-scale",
            "--table", "financials",
            "--measure", "Sales",
        )
        assert result.exit_code != 0

    def test_format_dry_run(self, runner, pbip_copy):
        result = runner.invoke(cli, [
            "--dry-run",
            "visual", "format",
            "--pbip", pbip_copy,
            "--page", "Executive Summary",
            "--visual", "some_visual",
            "--type", "data-bar",
            "--table", "financials",
            "--measure", "Sales",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_format_color_scale_writes_back_color_property(self, runner, pbip_copy):
        """visual.json must use 'backColor' (not 'background') — Desktop's property name."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import FieldDef, VisualSpec, build_table, AGG_SUM

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([FieldDef(entity="financials", property="Sales", agg=AGG_SUM)]),
            x=16, y=16, width=600, height=300,
        )
        b.page_add("BackColorTest")
        info = b.visual_add("BackColorTest", spec)
        b.visual_format_color_scale("BackColorTest", info["name"], "financials", "Sales")
        b.page_delete("BackColorTest")  # cleanup

        # Re-add to inspect the written file
        b.page_add("BackColorTest2")
        info2 = b.visual_add("BackColorTest2", spec)
        b.visual_format_color_scale("BackColorTest2", info2["name"], "financials", "Sales",
                                    low_color="#FF6B6B", mid_color="#FFD93D", high_color="#6BCB77")

        vj = b._ga_find_visual_json("BackColorTest2", info2["name"])
        assert vj is not None
        _, vdata = vj
        values = vdata["visual"]["objects"]["values"]
        assert len(values) == 1
        props = values[0]["properties"]
        assert "backColor" in props, f"expected 'backColor', got keys: {list(props)}"
        assert "background" not in props, "'background' is wrong — Desktop uses 'backColor'"
        b.page_delete("BackColorTest2")

    def test_format_color_scale_uses_linear_gradient3_lowercase(self, runner, pbip_copy):
        """FillRule must use 'linearGradient3' (lowercase) — Desktop's exact key name."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import FieldDef, VisualSpec, build_table, AGG_SUM

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([FieldDef(entity="financials", property="Sales", agg=AGG_SUM)]),
            x=16, y=16, width=600, height=300,
        )
        b.page_add("GradientTest")
        info = b.visual_add("GradientTest", spec)
        b.visual_format_color_scale("GradientTest", info["name"], "financials", "Sales")
        _, vdata = b._ga_find_visual_json("GradientTest", info["name"])
        expr = vdata["visual"]["objects"]["values"][0]["properties"]["backColor"]["solid"]["color"]["expr"]
        fill_rule_def = expr["FillRule"]["FillRule"]
        assert "linearGradient3" in fill_rule_def, (
            f"expected 'linearGradient3', got keys: {list(fill_rule_def)}"
        )
        assert "LinearGradient3" not in fill_rule_def, "'LinearGradient3' uppercase is wrong"
        b.page_delete("GradientTest")

    def test_format_color_scale_selector_has_data_wildcard(self, runner, pbip_copy):
        """Selector must have both 'data' (dataViewWildcard) and 'metadata' fields."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import FieldDef, VisualSpec, build_table, AGG_SUM

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([FieldDef(entity="financials", property="Sales", agg=AGG_SUM)]),
            x=16, y=16, width=600, height=300,
        )
        b.page_add("SelectorTest")
        info = b.visual_add("SelectorTest", spec)
        b.visual_format_color_scale("SelectorTest", info["name"], "financials", "Sales")
        _, vdata = b._ga_find_visual_json("SelectorTest", info["name"])
        sel = vdata["visual"]["objects"]["values"][0]["selector"]
        assert "metadata" in sel, "selector must have 'metadata'"
        assert "data" in sel, "selector must have 'data' (dataViewWildcard)"
        assert isinstance(sel["data"], list), "selector.data must be a list"
        assert sel["data"][0].get("dataViewWildcard") is not None, (
            "selector.data[0] must be a dataViewWildcard"
        )
        b.page_delete("SelectorTest")

    def test_format_color_scale_no_duplicate_entries(self, runner, pbip_copy):
        """Applying color-scale twice on same field must not create duplicate entries."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import FieldDef, VisualSpec, build_table, AGG_SUM

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([FieldDef(entity="financials", property="Sales", agg=AGG_SUM)]),
            x=16, y=16, width=600, height=300,
        )
        b.page_add("DedupTest")
        info = b.visual_add("DedupTest", spec)
        b.visual_format_color_scale("DedupTest", info["name"], "financials", "Sales")
        b.visual_format_color_scale("DedupTest", info["name"], "financials", "Sales",
                                    low_color="#000000")
        _, vdata = b._ga_find_visual_json("DedupTest", info["name"])
        values = vdata["visual"]["objects"]["values"]
        assert len(values) == 1, f"expected 1 entry after re-apply, got {len(values)}"
        b.page_delete("DedupTest")

    def test_format_color_scale_on_existing_visual(self, runner, pbip_copy):
        """Add a table visual, then apply color-scale formatting."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import (
            FieldDef, VisualSpec, build_table, AGG_SUM,
        )

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([
                FieldDef(entity="financials", property="Sales", agg=AGG_SUM),
                FieldDef(entity="financials", property="Profit", agg=AGG_SUM),
            ]),
            x=16, y=16, width=600, height=300,
            title="Test Table",
        )
        b.page_add("FormatTest")
        result_info = b.visual_add("FormatTest", spec)
        visual_name = result_info["name"]

        try:
            result = _run(
                runner,
                "visual", "format",
                "--pbip", pbip_copy,
                "--page", "FormatTest",
                "--visual", visual_name,
                "--type", "color-scale",
                "--table", "financials",
                "--measure", "Sales",
                "--low-color", "#FF0000",
                "--mid-color", "#FFFF00",
                "--high-color", "#00FF00",
            )
            assert result.exit_code == 0
            assert "color-scale" in result.output.lower() or "conditional" in result.output.lower()
        finally:
            b.page_delete("FormatTest")

    def test_format_data_bar_on_existing_visual(self, runner, pbip_copy):
        """Add a table visual, then apply data-bar formatting."""
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import (
            FieldDef, VisualSpec, build_table, AGG_SUM,
        )

        b = PbirBackend(pbip_copy)
        spec = VisualSpec(
            visual_type="tableEx",
            visual_body=build_table([
                FieldDef(entity="financials", property="Profit", agg=AGG_SUM),
            ]),
            x=16, y=16, width=600, height=300,
        )
        b.page_add("DataBarTest")
        result_info = b.visual_add("DataBarTest", spec)
        visual_name = result_info["name"]

        try:
            result = _run(
                runner,
                "visual", "format",
                "--pbip", pbip_copy,
                "--page", "DataBarTest",
                "--visual", visual_name,
                "--type", "data-bar",
                "--table", "financials",
                "--measure", "Profit",
            )
            assert result.exit_code == 0
        finally:
            b.page_delete("DataBarTest")
