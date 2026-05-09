"""Unit tests for pbi model impact command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestModelImpact:
    def test_impact_requires_measure_or_column(self, runner):
        result = _run(runner, "model", "impact")
        assert result.exit_code != 0

    def test_impact_measure_runs(self, runner):
        result = _run(runner, "model", "impact", "--measure", "Total Sales")
        assert result.exit_code == 0
        assert "Total Sales" in result.output
        assert "Impact analysis" in result.output

    def test_impact_column_runs(self, runner):
        result = _run(runner, "model", "impact", "--column", "financials[Sales]")
        assert result.exit_code == 0
        assert "financials[Sales]" in result.output

    def test_impact_shows_dax_dependents_section(self, runner):
        result = _run(runner, "model", "impact", "--measure", "Profit")
        assert result.exit_code == 0
        # Should print DAX dependents section regardless of whether any are found
        assert "DAX dependents" in result.output or "No DAX dependents" in result.output

    def test_impact_json_output(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--json",
                "model",
                "impact",
                "--measure",
                "Total Sales",
            ],
        )
        assert result.exit_code == 0
        # Output should include JSON somewhere
        assert "target" in result.output or "Total Sales" in result.output


class TestImpactHelpers:
    def test_search_terms_measure(self):
        from pbi_cli.commands.model import _impact_search_terms

        terms = _impact_search_terms("Total Sales", is_measure=True)
        assert "Total Sales" in terms
        assert "[Total Sales]" in terms

    def test_search_terms_column(self):
        from pbi_cli.commands.model import _impact_search_terms

        terms = _impact_search_terms("financials[Sales]", is_measure=False)
        assert "financials[Sales]" in terms
        assert "[Sales]" in terms
        assert "Sales" in terms

    def test_search_terms_simple_column(self):
        from pbi_cli.commands.model import _impact_search_terms

        terms = _impact_search_terms("Revenue", is_measure=False)
        assert "Revenue" in terms

    def test_scan_pbir_nonexistent_path(self, tmp_path):
        from pbi_cli.commands.model import _scan_pbir_for_field

        result = _scan_pbir_for_field(str(tmp_path / "no_report"), "Sales", is_measure=True)
        assert result == []

    def test_scan_pbir_finds_reference(self, tmp_path):
        """Creates a mock PBIR folder and verifies scan finds the field."""
        import json

        from pbi_cli.commands.model import _scan_pbir_for_field

        # Build a minimal PBIR structure
        report_dir = tmp_path / "TestReport.Report"
        pages_dir = report_dir / "definition" / "pages"
        page_dir = pages_dir / "abc123"
        visuals_dir = page_dir / "visuals" / "vis001"
        visuals_dir.mkdir(parents=True)

        # Page JSON
        (page_dir / "page.json").write_text(
            json.dumps({"name": "abc123", "displayName": "Sales Page"}),
            encoding="utf-8",
        )

        # Visual JSON with a Sales field reference
        visual_json = {
            "name": "vis001",
            "visual": {
                "visualType": "barChart",
                "projections": {
                    "Category": [{"queryRef": "Sales.Category"}],
                    "Y": [{"queryRef": "Sum(financials.Sales)"}],
                },
                "prototypeQuery": {
                    "Select": [
                        {
                            "Measure": {
                                "Expression": {"SourceRef": {"Entity": "financials"}},
                                "Property": "Sales",
                            },
                            "Name": "financials.Sales",
                        }
                    ]
                },
            },
        }
        (visuals_dir / "visual.json").write_text(json.dumps(visual_json), encoding="utf-8")

        # Create .pbip file
        pbip_file = tmp_path / "TestReport.pbip"
        pbip_file.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

        results = _scan_pbir_for_field(str(tmp_path), "Sales", is_measure=True)
        assert len(results) == 1
        assert results[0]["page"] == "Sales Page"
        assert results[0]["visual_type"] == "barChart"
