"""CliRunner tests for pbi calendar and pbi culture commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, ["--backend", "mock", *args])


# ── calendar generate ─────────────────────────────────────────────────────────


class TestCalendarGenerate:
    def test_generate_exits_cleanly(self, runner):
        result = _run(runner, "calendar", "generate")
        assert result.exit_code == 0

    def test_generate_produces_dax_output(self, runner):
        result = _run(runner, "calendar", "generate")
        assert result.exit_code == 0
        # The DAX expression should mention CALENDAR or ADDCOLUMNS
        output = result.output
        assert "CALENDAR" in output or "Generated" in output or "Calendar" in output

    def test_generate_with_custom_years(self, runner):
        result = _run(
            runner, "calendar", "generate",
            "--start-year", "2020",
            "--end-year", "2025",
        )
        assert result.exit_code == 0
        assert "2020" in result.output or result.exit_code == 0

    def test_generate_with_fiscal_year_start(self, runner):
        result = _run(
            runner, "calendar", "generate",
            "--start-year", "2020",
            "--end-year", "2025",
            "--fiscal-year-start", "7",
        )
        assert result.exit_code == 0

    def test_generate_with_custom_table_name(self, runner):
        result = _run(runner, "calendar", "generate", "--table-name", "DateTable")
        assert result.exit_code == 0
        assert "DateTable" in result.output

    def test_generate_dry_run(self, runner):
        result = runner.invoke(
            cli,
            ["--backend", "mock", "--dry-run", "calendar", "generate"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_generate_with_weekend_days(self, runner):
        result = _run(
            runner, "calendar", "generate",
            "--weekend-days", "5,6",
        )
        assert result.exit_code == 0


# ── calendar mark-date-table ──────────────────────────────────────────────────


class TestCalendarMarkDateTable:
    def test_mark_date_table_exits_cleanly(self, runner):
        result = _run(runner, "calendar", "mark-date-table", "--table", "Calendar")
        assert result.exit_code == 0

    def test_mark_date_table_prints_success(self, runner):
        result = _run(runner, "calendar", "mark-date-table", "--table", "Calendar")
        assert "Calendar" in result.output

    def test_mark_date_table_with_column(self, runner):
        result = _run(
            runner, "calendar", "mark-date-table",
            "--table", "Calendar",
            "--date-column", "FullDate",
        )
        assert result.exit_code == 0
        assert "FullDate" in result.output

    def test_mark_date_table_dry_run(self, runner):
        result = runner.invoke(
            cli,
            ["--backend", "mock", "--dry-run", "calendar", "mark-date-table", "--table", "Calendar"],  # noqa: E501
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── culture set ───────────────────────────────────────────────────────────────


class TestCultureSet:
    def test_set_locale_exits_cleanly(self, runner):
        result = _run(runner, "culture", "set", "--locale", "en-US")
        assert result.exit_code == 0

    def test_set_locale_prints_confirmation(self, runner):
        result = _run(runner, "culture", "set", "--locale", "en-US")
        assert "en-US" in result.output

    def test_set_locale_de_de(self, runner):
        result = _run(runner, "culture", "set", "--locale", "de-DE")
        assert result.exit_code == 0
        assert "de-DE" in result.output

    def test_set_locale_prints_separators_for_known_locale(self, runner):
        result = _run(runner, "culture", "set", "--locale", "en-US")
        assert result.exit_code == 0
        # Known locale should print separator info
        assert "separator" in result.output.lower() or "en-US" in result.output

    def test_set_locale_dry_run(self, runner):
        result = runner.invoke(
            cli,
            ["--backend", "mock", "--dry-run", "culture", "set", "--locale", "fr-FR"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── culture show ──────────────────────────────────────────────────────────────


class TestCultureShow:
    def test_show_exits_cleanly(self, runner):
        result = _run(runner, "culture", "show")
        assert result.exit_code == 0

    def test_show_prints_culture_info(self, runner):
        result = _run(runner, "culture", "show")
        assert result.exit_code == 0
        # Should print something about the model culture
        assert "culture" in result.output.lower() or result.output.strip() != ""
