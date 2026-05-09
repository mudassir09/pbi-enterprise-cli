"""CliRunner tests for pbi database commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestDatabaseExportTmdl:
    def test_export_dry_run(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "database", "export-tmdl", str(tmp_path / "tmdl"),
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_export_runs_against_mock(self, runner, tmp_path):
        out_dir = str(tmp_path / "tmdl")
        result = _run(runner, "database", "export-tmdl", out_dir)
        assert result.exit_code == 0
        assert "exported" in result.output.lower()


class TestDatabaseImportTmdl:
    def test_import_dry_run(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "database", "import-tmdl", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_import_runs_against_mock(self, runner, tmp_path):
        result = _run(runner, "database", "import-tmdl", str(tmp_path))
        assert result.exit_code == 0
        assert "imported" in result.output.lower()
