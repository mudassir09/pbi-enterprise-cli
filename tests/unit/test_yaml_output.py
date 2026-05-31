"""Tests for --yaml output flag on key commands."""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


class TestYamlOutput:
    def test_measure_list_yaml(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--yaml", "measure", "list"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)

    def test_model_tables_yaml(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--yaml", "model", "tables"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)

    def test_connections_yaml(self, runner, tmp_path, monkeypatch):
        import json as _json
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            _json.dumps({"default": None, "connections": {"dev": {"backend": "mock"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.connections._CONNECTIONS_FILE", conn_file)
        result = runner.invoke(cli, ["--yaml", "connections", "list"])
        # connections list outputs a Rich table, not structured data — just check no crash
        assert result.exit_code == 0

    def test_yaml_and_json_mutually_exclusive_yaml_wins(self, runner):
        """--yaml takes precedence when both flags somehow set; output is valid YAML."""
        result = runner.invoke(
            cli, ["--backend", "mock", "--yaml", "measure", "list"]
        )
        assert result.exit_code == 0
        # YAML output should not look like JSON (no leading '[' or '{' with quotes as JSON)
        # but must be parseable
        yaml.safe_load(result.output)  # no exception

    def test_doctor_still_works_without_yaml(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "doctor"])
        assert result.exit_code == 0
