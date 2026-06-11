"""Tests for PBIR report analysis: lint, field usage, diff, a11y."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.pbir_analysis import (
    a11y_check,
    diff_reports,
    extract_fields,
    field_usage,
    lint_report,
    load_report,
)


def _visual(name: str, vtype: str = "barChart", x: int = 0, y: int = 0,
            w: int = 200, h: int = 200, fields: list | None = None,
            alt_text: str = "", hidden: bool = False) -> dict:
    projections = []
    for entity, prop, kind in fields or []:
        projections.append({
            "field": {kind: {"Expression": {"SourceRef": {"Entity": entity}},
                             "Property": prop}},
            "queryRef": f"{entity}.{prop}",
        })
    visual: dict = {
        "name": name,
        "position": {"x": x, "y": y, "width": w, "height": h},
        "visual": {
            "visualType": vtype,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "visualContainerObjects": {},
        },
    }
    if alt_text:
        visual["visual"]["visualContainerObjects"]["general"] = [
            {"properties": {"altText": {"expr": {"Literal": {"Value": f"'{alt_text}'"}}}}}
        ]
    if hidden:
        visual["isHidden"] = True
    return visual


def _write_report(root: Path, pages: dict[str, list[dict]]) -> Path:
    """pages: displayName -> list of visual dicts."""
    report_dir = root / "Demo.Report"
    for idx, (display_name, visuals) in enumerate(pages.items()):
        page_dir = report_dir / "definition" / "pages" / f"page{idx}"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"name": f"page{idx}", "displayName": display_name}), encoding="utf-8")
        for v in visuals:
            vdir = page_dir / "visuals" / v["name"]
            vdir.mkdir(parents=True, exist_ok=True)
            (vdir / "visual.json").write_text(json.dumps(v), encoding="utf-8")
    return root


@pytest.fixture()
def runner():
    return CliRunner()


class TestExtractFields:
    def test_finds_columns_and_measures(self):
        v = _visual("v1", fields=[("Sales", "Revenue", "Column"),
                                  ("Sales", "Total Revenue", "Measure")])
        fields = extract_fields(v)
        assert ("Sales", "Revenue", "Column") in fields
        assert ("Sales", "Total Revenue", "Measure") in fields


class TestLint:
    def test_empty_page_and_alt_text(self, tmp_path):
        _write_report(tmp_path, {
            "Overview": [_visual("v1")],
            "Empty": [],
        })
        violations = lint_report(load_report(tmp_path))
        rules = {v["rule"] for v in violations}
        assert "report.empty-page" in rules
        assert "report.missing-alt-text" in rules

    def test_alt_text_satisfied(self, tmp_path):
        _write_report(tmp_path, {"Overview": [_visual("v1", alt_text="Revenue by month")]})
        rules = {v["rule"] for v in lint_report(load_report(tmp_path))}
        assert "report.missing-alt-text" not in rules

    def test_hidden_and_overlap(self, tmp_path):
        _write_report(tmp_path, {"P": [
            _visual("v1", x=0, y=0, w=100, h=100, alt_text="a", hidden=True),
            _visual("v2", x=10, y=10, w=100, h=100, alt_text="b"),
        ]})
        rules = {v["rule"] for v in lint_report(load_report(tmp_path))}
        assert "report.hidden-visual" in rules
        assert "report.overlapping-visuals" in rules


class TestFieldUsage:
    def test_unused_fields_detected(self, tmp_path):
        _write_report(tmp_path, {"P": [
            _visual("v1", fields=[("Sales", "Revenue", "Column"),
                                  ("Sales", "Total Revenue", "Measure")]),
        ]})
        columns = [
            {"table": "Sales", "name": "Revenue", "isHidden": False},
            {"table": "Sales", "name": "Units", "isHidden": False},
            {"table": "Sales", "name": "SalesKey", "isHidden": True},
        ]
        measures = [
            {"table": "Sales", "name": "Total Revenue", "expression": "SUM(Sales[Revenue])"},
            {"table": "Sales", "name": "Orphan", "expression": "1"},
        ]
        usage = field_usage(load_report(tmp_path), columns, measures)
        assert usage["unused_columns"] == ["Sales[Units]"]  # hidden key not reported
        assert usage["unused_measures"] == ["Sales[Orphan]"]

    def test_dax_referenced_measure_counts_as_used(self, tmp_path):
        _write_report(tmp_path, {"P": [
            _visual("v1", fields=[("Sales", "Margin", "Measure")]),
        ]})
        measures = [
            {"table": "Sales", "name": "Margin", "expression": "[Rev] - [Cost]"},
            {"table": "Sales", "name": "Rev", "expression": "SUM(Sales[Revenue])"},
            {"table": "Sales", "name": "Cost", "expression": "SUM(Sales[Cost])"},
        ]
        usage = field_usage(load_report(tmp_path), [], measures)
        assert usage["unused_measures"] == []


class TestDiff:
    def test_detects_page_visual_and_field_changes(self, tmp_path):
        old_root = tmp_path / "old"
        new_root = tmp_path / "new"
        _write_report(old_root, {
            "P": [_visual("v1", fields=[("Sales", "Revenue", "Column")])],
            "Gone": [],
        })
        _write_report(new_root, {
            "P": [_visual("v1", x=50, fields=[("Sales", "Units", "Column")]),
                  _visual("v2", vtype="lineChart")],
        })
        result = diff_reports(load_report(old_root), load_report(new_root))
        kinds = {c["change"] for c in result["changes"]}
        assert {"page-removed", "visual-added", "visual-moved-or-resized",
                "field-added", "field-removed"} <= kinds

    def test_no_changes(self, tmp_path):
        _write_report(tmp_path, {"P": [_visual("v1")]})
        report = load_report(tmp_path)
        assert diff_reports(report, report)["has_changes"] is False


class TestA11y:
    def test_findings(self, tmp_path):
        _write_report(tmp_path, {"P": [_visual("v1"), _visual("v2", x=300)]})
        findings = a11y_check(load_report(tmp_path))
        rules = {f["rule"] for f in findings}
        assert {"a11y.alt-text", "a11y.title", "a11y.tab-order"} <= rules


class TestCli:
    def test_report_lint_json(self, runner, tmp_path):
        _write_report(tmp_path, {"Overview": [_visual("v1")]})
        result = runner.invoke(cli, ["--json", "report", "lint", "--pbip", str(tmp_path)])
        assert result.exit_code == 0, result.output
        json.loads(result.output)

    def test_report_lint_fail_on(self, runner, tmp_path):
        _write_report(tmp_path, {"Overview": [_visual("v1")]})
        result = runner.invoke(
            cli, ["report", "lint", "--pbip", str(tmp_path), "--fail-on", "warning"])
        assert result.exit_code == 3

    def test_report_diff_cli(self, runner, tmp_path):
        old_root = tmp_path / "a"
        new_root = tmp_path / "b"
        _write_report(old_root, {"P": [_visual("v1")]})
        _write_report(new_root, {"P": [_visual("v1"), _visual("v2")]})
        result = runner.invoke(
            cli, ["--json", "report", "diff", str(old_root), str(new_root)])
        assert result.exit_code == 0
        assert json.loads(result.output)["has_changes"] is True

    def test_field_usage_with_mock_backend(self, runner, tmp_path):
        _write_report(tmp_path, {"P": [
            _visual("v1", fields=[("Sales", "Revenue", "Column")])]})
        result = runner.invoke(cli, [
            "--backend", "mock", "--json", "report", "field-usage",
            "--pbip", str(tmp_path)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "Sales[Revenue]" in data["fields_used_in_report"]
        assert "Sales[Units]" in data["unused_columns"]
