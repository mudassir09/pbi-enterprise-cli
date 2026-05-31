"""Tests for pbi env command group."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


class TestEnvList:
    def test_list_no_connections(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "pbi_cli.commands.env_cmd._CONNECTIONS_FILE",
            tmp_path / "no-connections.json",
        )
        result = _run(runner, "env", "list")
        assert result.exit_code == 0
        assert "No connections" in result.output

    def test_list_shows_connections(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": "dev",
                "connections": {
                    "dev": {"backend": "xmla", "xmla_endpoint": "powerbi://dev"},
                    "prod": {"backend": "xmla", "xmla_endpoint": "powerbi://prod"},
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "list")
        assert result.exit_code == 0
        assert "dev" in result.output
        assert "prod" in result.output

    def test_list_marks_default(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": "staging",
                "connections": {
                    "staging": {"backend": "xmla", "xmla_endpoint": "powerbi://staging"},
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "list")
        assert result.exit_code == 0
        assert "staging" in result.output


class TestEnvUse:
    def test_use_sets_default(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": None,
                "connections": {"fabric-dev": {"backend": "xmla"}},
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "use", "fabric-dev")
        assert result.exit_code == 0
        data = json.loads(conn_file.read_text())
        assert data["default"] == "fabric-dev"

    def test_use_missing_connection_exits_1(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({"default": None, "connections": {}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "use", "does-not-exist")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_use_prints_confirmation(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": None,
                "connections": {"fabric-prod": {"backend": "xmla"}},
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "use", "fabric-prod")
        assert "fabric-prod" in result.output


class TestEnvDiff:
    def test_diff_missing_source(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({"default": None, "connections": {"target": {"backend": "xmla"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "diff", "missing", "target")
        assert result.exit_code != 0

    def test_diff_both_exist_prints_info(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": None,
                "connections": {
                    "dev": {"backend": "xmla"},
                    "prod": {"backend": "xmla"},
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "diff", "dev", "prod")
        assert result.exit_code == 0
        assert "dev" in result.output and "prod" in result.output


class TestEnvPromote:
    def test_promote_requires_confirm_flag(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": None,
                "connections": {
                    "dev": {"backend": "xmla"},
                    "prod": {"backend": "xmla"},
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "promote", "dev", "prod")
        assert result.exit_code != 0

    def test_promote_missing_connection(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({"default": None, "connections": {"dev": {"backend": "xmla"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "promote", "dev", "missing", "--confirm")
        assert result.exit_code != 0

    def test_promote_with_confirm_exits_cleanly(self, runner, tmp_path, monkeypatch):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps({
                "default": None,
                "connections": {
                    "dev": {"backend": "xmla"},
                    "prod": {"backend": "xmla"},
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_file)
        result = _run(runner, "env", "promote", "dev", "prod", "--confirm")
        assert result.exit_code == 0
        assert "dev" in result.output and "prod" in result.output
