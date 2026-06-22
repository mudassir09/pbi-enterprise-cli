"""Unit tests for pbi filter commands (PBIR file-based).

Filters are written to the page's ``filterConfig`` using the official PBIR
filterConfiguration schema. The previous flat shape is no longer produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.backends import pbir_schemas as schemas
from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_fake_pbip(tmp_path: Path, page_name: str = "Page1") -> str:
    """Create a minimal PBIR GA project structure and return the .pbip path."""
    report_dir = tmp_path / "TestReport.Report"
    pages_dir = report_dir / "definition" / "pages"
    pages_dir.mkdir(parents=True)

    page_id = "aabbccdd1122"
    page_dir = pages_dir / page_id
    page_dir.mkdir()

    page_json = {
        "$schema": schemas.definition_schema("page"),
        "name": page_id,
        "displayName": page_name,
        "width": 1280,
        "height": 720,
    }
    (page_dir / "page.json").write_text(json.dumps(page_json), encoding="utf-8")

    pages_meta = {
        "$schema": schemas.definition_schema("pagesMetadata"),
        "pageOrder": [page_id],
        "activePageName": page_id,
    }
    (pages_dir / "pages.json").write_text(json.dumps(pages_meta), encoding="utf-8")

    pbip_file = tmp_path / "TestReport.pbip"
    pbip_file.write_text(
        json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "TestReport.Report"}}]}),
        encoding="utf-8",
    )
    return str(pbip_file)


def _page_filters(tmp_path: Path) -> list[dict]:
    page_dir = Path(tmp_path) / "TestReport.Report" / "definition" / "pages" / "aabbccdd1122"
    data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
    return data.get("filterConfig", {}).get("filters", [])


def _run(runner, *args):
    return runner.invoke(cli, list(args))


class TestFilterList:
    def test_list_empty_page(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "list", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0
        assert "No filters" in result.output

    def test_list_invalid_page(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "list", "--pbip", pbip, "--page", "NonExistent")
        assert result.exit_code != 0

    def test_list_after_add_value_filter(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Region",
             "--values", "UK,US")
        result = _run(runner, "filter", "list", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0


class TestFilterAddRelativeDate:
    def test_add_relative_date(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-relative-date",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "Calendar", "--column", "Date",
                      "--last", "30", "--unit", "Days")
        assert result.exit_code == 0
        assert "Filter added" in result.output

    def test_add_relative_date_persisted(self, runner, tmp_path):
        """Filter is written under filterConfig with a valid FilterDefinition."""
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-relative-date",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Calendar", "--column", "Date",
             "--last", "7", "--unit", "Weeks")
        filters = _page_filters(tmp_path)
        assert len(filters) == 1
        assert filters[0]["type"] == "RelativeDate"
        # Real PBIR filter shape: name + FilterDefinition (Version/From/Where).
        assert filters[0]["name"]
        definition = filters[0]["filter"]
        assert definition["Version"] == 2
        assert definition["From"][0]["Entity"] == "Calendar"
        assert "Where" in definition

    def test_add_relative_date_dry_run(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = runner.invoke(cli, [
            "--dry-run", "filter", "add-relative-date",
            "--pbip", pbip, "--page", "Page1",
            "--table", "Calendar", "--column", "Date",
            "--last", "30", "--unit", "Days",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


class TestFilterAddAdvanced:
    def test_add_advanced_range(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-advanced",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "financials", "--column", "Profit",
                      "--condition", ">=:0", "--condition", "<=:1000000",
                      "--logic", "And")
        assert result.exit_code == 0
        assert "Filter added" in result.output

    def test_add_advanced_persisted(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-advanced",
             "--pbip", pbip, "--page", "Page1",
             "--table", "financials", "--column", "Profit",
             "--condition", ">=:1000")
        filters = _page_filters(tmp_path)
        assert len(filters) == 1
        assert filters[0]["type"] == "Advanced"
        where = filters[0]["filter"]["Where"][0]["Condition"]
        assert "Comparison" in where
        assert where["Comparison"]["ComparisonKind"] == 2  # >=

    def test_add_advanced_rejects_three_conditions(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-advanced",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "f", "--column", "x",
                      "--condition", ">:1", "--condition", "<:2", "--condition", "=:3")
        assert result.exit_code != 0

    def test_add_advanced_bad_condition(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-advanced",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "f", "--column", "x", "--condition", "notvalid")
        assert result.exit_code != 0


class TestFilterAddValue:
    def test_add_value_success(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-value",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "Sales", "--column", "Region",
                      "--values", "UK,US")
        assert result.exit_code == 0
        assert "Filter added" in result.output

    def test_add_value_persisted(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Segment",
             "--values", "Enterprise,Government")
        filters = _page_filters(tmp_path)
        assert len(filters) == 1
        assert filters[0]["type"] == "Categorical"
        in_expr = filters[0]["filter"]["Where"][0]["Condition"]["In"]
        assert len(in_expr["Values"]) == 2

    def test_add_value_exclude(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Region",
             "--values", "UK", "--exclude")
        filters = _page_filters(tmp_path)
        assert filters[0]["type"] == "Exclude"
        assert "Not" in filters[0]["filter"]["Where"][0]["Condition"]

    def test_add_value_dry_run(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = runner.invoke(cli, [
            "--dry-run", "filter", "add-value",
            "--pbip", pbip, "--page", "Page1",
            "--table", "Sales", "--column", "Region",
            "--values", "UK",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


class TestFilterScope:
    def _report_json_path(self, tmp_path: Path) -> Path:
        return Path(tmp_path) / "TestReport.Report" / "definition" / "report.json"

    def test_report_scope_writes_report_json(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        # report-level filters need definition/report.json to exist.
        rj = self._report_json_path(tmp_path)
        rj.write_text(json.dumps({"$schema": schemas.definition_schema("report")}), encoding="utf-8")
        result = _run(runner, "filter", "add-value",
                      "--pbip", pbip, "--scope", "report",
                      "--table", "Sales", "--column", "Region", "--values", "UK")
        assert result.exit_code == 0, result.output
        data = json.loads(rj.read_text(encoding="utf-8"))
        filters = data.get("filterConfig", {}).get("filters", [])
        assert len(filters) == 1
        # Embedded filterConfig must NOT carry a $schema (Desktop rejects it).
        assert "$schema" not in data["filterConfig"]
        assert "report" in result.output

    def test_report_scope_missing_report_json_errors(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-value",
                      "--pbip", pbip, "--scope", "report",
                      "--table", "Sales", "--column", "Region", "--values", "UK")
        assert result.exit_code != 0

    def test_visual_scope_writes_visual_json(self, runner, tmp_path):
        from pbi_cli.backends.pbir_backend import PbirBackend
        from pbi_cli.intelligence.visual_builder import (
            AGG_SUM, FieldDef, VisualSpec, build_card,
        )

        pbip = _make_fake_pbip(tmp_path)
        b = PbirBackend(pbip)
        spec = VisualSpec("card", build_card(FieldDef(entity="Sales", property="Amount", agg=AGG_SUM)))
        name = b.visual_add("Page1", spec)["name"]

        result = _run(runner, "filter", "add-value",
                      "--pbip", pbip, "--scope", "visual", "--page", "Page1",
                      "--visual", name,
                      "--table", "Sales", "--column", "Region", "--values", "UK")
        assert result.exit_code == 0, result.output
        _, data = b._ga_find_visual_json("Page1", name)
        filters = data.get("filterConfig", {}).get("filters", [])
        assert len(filters) == 1
        assert "$schema" not in data["filterConfig"]

    def test_visual_scope_requires_visual(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-value",
                      "--pbip", pbip, "--scope", "visual", "--page", "Page1",
                      "--table", "Sales", "--column", "Region", "--values", "UK")
        assert result.exit_code != 0


class TestFilterClear:
    def test_clear_empty_page(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "clear", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_clear_removes_filters(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Region", "--values", "UK")
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Segment", "--values", "Enterprise")
        result = _run(runner, "filter", "clear", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0
        assert "2" in result.output
        assert _page_filters(tmp_path) == []

    def test_clear_dry_run(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = runner.invoke(cli, [
            "--dry-run", "filter", "clear",
            "--pbip", pbip, "--page", "Page1",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
