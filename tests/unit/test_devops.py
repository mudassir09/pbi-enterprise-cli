"""Tests for pbi init, pbi diff, env drift, and the model_diff module."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.model_diff import semantic_diff, snapshot_state, to_release_notes

TABLE_V1 = """\
table Sales

    measure 'Total Revenue' = SUM(Sales[Revenue])
        formatString: #,0.00

    measure 'Old Measure' = 1

    column Revenue
        dataType: decimal
        sourceColumn: Revenue
"""

TABLE_V2 = """\
table Sales

    measure 'Total Revenue' = SUMX(Sales, Sales[Revenue])
        formatString: #,0.00

    measure 'New Measure' = 2

    column Revenue
        dataType: double
        sourceColumn: Revenue
"""


def _write_model(root, table_content):
    d = root / "definition" / "tables"
    d.mkdir(parents=True, exist_ok=True)
    (root / "definition" / "model.tmdl").write_text("model Model\n", encoding="utf-8")
    (d / "Sales.tmdl").write_text(table_content, encoding="utf-8")
    return root


@pytest.fixture()
def runner():
    return CliRunner()


class TestSemanticDiff:
    def test_diff_detects_changes(self, tmp_path):
        from pbi_cli.backends.file_backend import FileBackend

        old_dir = _write_model(tmp_path / "old", TABLE_V1)
        new_dir = _write_model(tmp_path / "new", TABLE_V2)
        old_state = snapshot_state(FileBackend(path=old_dir))
        new_state = snapshot_state(FileBackend(path=new_dir))
        result = semantic_diff(old_state, new_state)
        kinds = {c["change"] for c in result["changes"]}
        assert {"measure-removed", "measure-added", "measure-changed",
                "column-changed"} <= kinds
        changed = next(c for c in result["changes"] if c["change"] == "measure-changed")
        assert "SUMX" in changed["detail"]

    def test_no_changes(self, tmp_path):
        from pbi_cli.backends.file_backend import FileBackend

        d = _write_model(tmp_path, TABLE_V1)
        state = snapshot_state(FileBackend(path=d))
        assert semantic_diff(state, state)["has_changes"] is False

    def test_release_notes(self, tmp_path):
        from pbi_cli.backends.file_backend import FileBackend

        old_dir = _write_model(tmp_path / "old", TABLE_V1)
        new_dir = _write_model(tmp_path / "new", TABLE_V2)
        diff = semantic_diff(
            snapshot_state(FileBackend(path=old_dir)),
            snapshot_state(FileBackend(path=new_dir)),
        )
        notes = to_release_notes(diff)
        assert "Measure Added" in notes
        assert "Sales[New Measure]" in notes


class TestDiffCli:
    def test_diff_two_paths_json(self, runner, tmp_path):
        old_dir = _write_model(tmp_path / "old", TABLE_V1)
        new_dir = _write_model(tmp_path / "new", TABLE_V2)
        result = runner.invoke(cli, ["--json", "diff", str(old_dir), str(new_dir)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["has_changes"] is True
        assert data["summary"]["measure-added"] == 1

    def test_diff_release_notes_file(self, runner, tmp_path):
        old_dir = _write_model(tmp_path / "old", TABLE_V1)
        new_dir = _write_model(tmp_path / "new", TABLE_V2)
        notes = tmp_path / "notes.md"
        result = runner.invoke(
            cli, ["diff", str(old_dir), str(new_dir), "--release-notes", str(notes)])
        assert result.exit_code == 0
        assert "Measure Added" in notes.read_text(encoding="utf-8")


class TestInit:
    def test_init_scaffolds_files(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "pbi.config.toml").exists()
        assert (tmp_path / ".github" / "workflows" / "pbi-govern.yml").exists()
        assert (tmp_path / "tests" / "data" / "data_suite.yaml").exists()

    def test_init_does_not_overwrite(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pbi.config.toml").write_text("custom", encoding="utf-8")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "pbi.config.toml").read_text(encoding="utf-8") == "custom"
        assert "exists" in result.output


class TestEnvDrift:
    def test_drift_against_mock(self, runner, tmp_path):
        # Repo model has one table; mock backend has the default star schema → drift
        model_dir = _write_model(tmp_path, TABLE_V1)
        result = runner.invoke(cli, [
            "--backend", "mock", "--json", "env", "drift",
            "--path", str(model_dir), "--fail-on-drift"])
        assert result.exit_code == 3
        data = json.loads(result.output)
        assert data["has_changes"] is True
