"""Unit tests for pbi filter commands (PBIR file-based)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_fake_pbip(tmp_path: Path, page_name: str = "Page1") -> str:
    """Create a minimal PBIR GA project structure and return the .pbip path."""
    report_dir = tmp_path / "TestReport.Report"
    pages_dir = report_dir / "definition" / "pages"
    pages_dir.mkdir(parents=True)

    # Create a page folder
    page_id = "aabbccdd1122"
    page_dir = pages_dir / page_id
    page_dir.mkdir()

    page_json = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": page_id,
        "displayName": page_name,
        "width": 1280,
        "height": 720,
    }
    (page_dir / "page.json").write_text(json.dumps(page_json), encoding="utf-8")

    # pages.json order index
    pages_meta = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [page_id],
        "activePageName": page_id,
    }
    (pages_dir / "pages.json").write_text(json.dumps(pages_meta), encoding="utf-8")

    # .pbip manifest
    pbip_file = tmp_path / "TestReport.pbip"
    pbip_file.write_text(
        json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "TestReport.Report"}}]}),
        encoding="utf-8",
    )
    return str(pbip_file)


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
        # Add a value filter first
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Region",
             "--values", "UK,US")
        # Now list should show filters
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
        """Filter is written to the page.json file."""
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-relative-date",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Calendar", "--column", "Date",
             "--last", "7", "--unit", "Weeks")
        # Check file
        page_dir = (Path(tmp_path) / "TestReport.Report" / "definition" / "pages" / "aabbccdd1122")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        filters = data.get("filters", [])
        assert len(filters) == 1
        assert filters[0]["type"] == "RelativeDate"

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


class TestFilterAddTopN:
    def test_add_topn(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "add-topn",
                      "--pbip", pbip, "--page", "Page1",
                      "--table", "Products", "--column", "Product",
                      "--n", "10",
                      "--by-table", "Sales", "--by-measure", "Total Revenue",
                      "--direction", "Top")
        assert result.exit_code == 0
        assert "Filter added" in result.output

    def test_add_topn_persisted(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        _run(runner, "filter", "add-topn",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Products", "--column", "Product",
             "--n", "5",
             "--by-table", "Sales", "--by-measure", "Total Revenue",
             "--direction", "Bottom")
        page_dir = (Path(tmp_path) / "TestReport.Report" / "definition" / "pages" / "aabbccdd1122")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        filters = data.get("filters", [])
        assert len(filters) == 1
        assert filters[0]["type"] == "TopN"
        assert filters[0]["operator"] == "BottomCount"

    def test_add_topn_dry_run(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = runner.invoke(cli, [
            "--dry-run", "filter", "add-topn",
            "--pbip", pbip, "--page", "Page1",
            "--table", "Products", "--column", "Product",
            "--n", "10",
            "--by-table", "Sales", "--by-measure", "Total Revenue",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


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
        page_dir = (Path(tmp_path) / "TestReport.Report" / "definition" / "pages" / "aabbccdd1122")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        filters = data.get("filters", [])
        assert len(filters) == 1
        assert filters[0]["type"] == "BasicFilter"
        assert len(filters[0]["values"]) == 2

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


class TestFilterClear:
    def test_clear_empty_page(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = _run(runner, "filter", "clear", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_clear_removes_filters(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        # Add filters first
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Region", "--values", "UK")
        _run(runner, "filter", "add-value",
             "--pbip", pbip, "--page", "Page1",
             "--table", "Sales", "--column", "Segment", "--values", "Enterprise")
        # Now clear
        result = _run(runner, "filter", "clear", "--pbip", pbip, "--page", "Page1")
        assert result.exit_code == 0
        assert "2" in result.output  # "Cleared 2 filter(s)"
        # Verify file state
        page_dir = (Path(tmp_path) / "TestReport.Report" / "definition" / "pages" / "aabbccdd1122")
        data = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        assert data.get("filters", []) == []

    def test_clear_dry_run(self, runner, tmp_path):
        pbip = _make_fake_pbip(tmp_path)
        result = runner.invoke(cli, [
            "--dry-run", "filter", "clear",
            "--pbip", pbip, "--page", "Page1",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
