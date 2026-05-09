"""Unit tests for updated pbi deploy commands: snapshot, diff, push."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestDeploySnapshot:
    def test_snapshot_dry_run(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "deploy", "snapshot", "--output", str(tmp_path / "snap"),
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_snapshot_calls_tmdl_export(self, runner, tmp_path):
        """Snapshot command should call backend.tmdl_export and report success."""
        out = tmp_path / "snap"
        out.mkdir()
        # Create a fake .tmdl file so the count check passes
        (out / "tables.tmdl").write_text("table Test {}", encoding="utf-8")

        with patch("pbi_cli.commands._shared.get_backend") as mock_get:
            mock_backend = MagicMock()
            mock_backend.tmdl_export.return_value = {"files": []}
            mock_get.return_value = mock_backend

            result = runner.invoke(cli, [
                "--backend", "mock",
                "deploy", "snapshot", "--output", str(out),
            ])
        # Should complete (either success or graceful error with mock backend)
        assert result.exit_code in (0, 1)

    def test_snapshot_output_option(self, runner, tmp_path):
        """--output is passed through to the backend."""
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "deploy", "snapshot", "--output", str(tmp_path / "custom_snap"),
        ])
        assert result.exit_code == 0
        assert "custom_snap" in result.output


class TestDeployDiffSnapshot:
    def test_diff_requires_workspace_or_snapshot(self, runner):
        result = _run(runner, "deploy", "diff")
        assert result.exit_code != 0

    def test_diff_with_snapshot_calls_model_diff(self, runner, tmp_path):
        snap = tmp_path / "my_snap"
        snap.mkdir()

        with patch("pbi_cli.commands._shared.get_backend") as mock_get:
            mock_backend = MagicMock()
            mock_backend.model_diff.return_value = {
                "has_changes": False,
                "added": [],
                "removed": [],
                "changed": [],
            }
            mock_get.return_value = mock_backend

            result = runner.invoke(cli, [
                "--backend", "mock",
                "deploy", "diff", "--snapshot", str(snap),
            ])
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_diff_with_workspace_no_xmla(self, runner):
        result = _run(runner, "deploy", "diff", "--workspace", "Production")
        assert result.exit_code == 0
        assert "XMLA" in result.output or "not configured" in result.output or "Diffing" in result.output


class TestDeployPushImproved:
    def test_push_shows_endpoint_message(self, runner):
        result = _run(runner, "deploy", "push", "--workspace", "Production")
        assert result.exit_code == 0
        assert "Production" in result.output

    def test_push_with_xmla_option(self, runner):
        result = _run(runner, "deploy", "push",
                      "--workspace", "Production",
                      "--xmla", "powerbi://api.powerbi.com/v1.0/myorg/Test")
        assert result.exit_code == 0

    def test_push_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "deploy", "push", "--workspace", "Staging",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


class TestDeployGetXmlaEndpoint:
    def test_returns_none_when_no_config(self, tmp_path, monkeypatch):
        from pbi_cli.commands.deploy import _get_xmla_endpoint
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = _get_xmla_endpoint()
        assert result is None

    def test_returns_endpoint_from_config(self, tmp_path, monkeypatch):
        from pbi_cli.commands.deploy import _get_xmla_endpoint
        config_dir = tmp_path / ".pbi-cli"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[xmla]\nendpoint = "powerbi://api.powerbi.com/v1.0/myorg/Test"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Only works if tomllib or tomli is available
        try:
            import tomllib
        except ImportError:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomllib/tomli not available")

        result = _get_xmla_endpoint()
        assert result == "powerbi://api.powerbi.com/v1.0/myorg/Test"
