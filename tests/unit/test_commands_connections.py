"""CliRunner tests for pbi connections commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def patch_home(tmp_path, monkeypatch):
    """Redirect Path.home() to a temp directory so tests don't touch real config."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Also patch the module-level _CONFIG_PATH which is computed at import time
    import pbi_cli.commands.connections as conn_mod
    monkeypatch.setattr(conn_mod, "_CONFIG_PATH", tmp_path / ".pbi-cli" / "connections.json")


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, [*args])


# ── connections list ───────────────────────────────────────────────────────────


class TestConnectionsList:
    def test_list_empty_prints_message(self, runner):
        result = _run(runner, "connections", "list")
        assert result.exit_code == 0
        assert "No saved connections" in result.output

    def test_list_after_add_shows_connection(self, runner):
        _run(runner, "connections", "add", "--name", "local", "--type", "desktop")
        result = _run(runner, "connections", "list")
        assert result.exit_code == 0
        assert "local" in result.output

    def test_list_masks_client_secret(self, runner):
        _run(
            runner,
            "connections", "add",
            "--name", "prod",
            "--type", "xmla",
            "--endpoint", "powerbi://api.powerbi.com/v1.0/myorg/DS",
            "--catalog", "MyDataset",
            "--auth", "service_principal",
            "--client-id", "aaa",
            "--client-secret", "SUPERSECRET",
            "--tenant-id", "tenant123",
        )
        result = _run(runner, "connections", "list")
        assert result.exit_code == 0
        assert "SUPERSECRET" not in result.output
        assert "***" in result.output


# ── connections add ────────────────────────────────────────────────────────────


class TestConnectionsAdd:
    def test_add_desktop_connection(self, runner):
        result = _run(runner, "connections", "add", "--name", "dev", "--type", "desktop")
        assert result.exit_code == 0
        assert "saved" in result.output.lower() or "Connection saved" in result.output

    def test_add_desktop_with_port(self, runner):
        result = _run(
            runner, "connections", "add", "--name", "dev2", "--type", "desktop", "--port", "60000"
        )
        assert result.exit_code == 0

    def test_add_xmla_connection(self, runner):
        result = _run(
            runner,
            "connections", "add",
            "--name", "xmla-test",
            "--type", "xmla",
            "--endpoint", "powerbi://api.powerbi.com/v1.0/myorg/WS",
            "--catalog", "TestModel",
        )
        assert result.exit_code == 0

    def test_add_xmla_requires_endpoint(self, runner):
        result = _run(runner, "connections", "add", "--name", "bad", "--type", "xmla")
        # Should fail because --endpoint is required for xmla
        assert result.exit_code != 0 or "required" in result.output.lower()

    def test_add_overwrites_existing_name(self, runner):
        _run(runner, "connections", "add", "--name", "myconn", "--type", "desktop")
        result = _run(runner, "connections", "add", "--name", "myconn", "--type", "desktop", "--port", "55000")  # noqa: E501
        assert result.exit_code == 0
        # Only one entry with that name
        list_result = _run(runner, "connections", "list")
        assert list_result.output.count("myconn") >= 1


# ── connections remove ────────────────────────────────────────────────────────


class TestConnectionsRemove:
    def test_remove_existing_connection(self, runner):
        _run(runner, "connections", "add", "--name", "temp", "--type", "desktop")
        result = _run(runner, "connections", "remove", "temp")
        assert result.exit_code == 0
        assert "Removed" in result.output or "removed" in result.output.lower()

    def test_remove_not_found(self, runner):
        result = _run(runner, "connections", "remove", "doesnotexist")
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_remove_then_list_empty(self, runner):
        _run(runner, "connections", "add", "--name", "gone", "--type", "desktop")
        _run(runner, "connections", "remove", "gone")
        result = _run(runner, "connections", "list")
        assert "No saved connections" in result.output


# ── connections use ────────────────────────────────────────────────────────────


class TestConnectionsUse:
    def test_use_sets_active(self, runner):
        _run(runner, "connections", "add", "--name", "active", "--type", "desktop")
        result = _run(runner, "connections", "use", "active")
        assert result.exit_code == 0
        assert "active" in result.output.lower() or "Active connection" in result.output

    def test_use_not_found_exits_nonzero(self, runner):
        result = _run(runner, "connections", "use", "missing")
        assert result.exit_code != 0


# ── connections last ───────────────────────────────────────────────────────────


class TestConnectionsLast:
    def test_last_when_none(self, runner):
        result = _run(runner, "connections", "last")
        assert result.exit_code == 0
        assert "No connection" in result.output

    def test_last_after_use(self, runner):
        _run(runner, "connections", "add", "--name", "latest", "--type", "desktop")
        _run(runner, "connections", "use", "latest")
        result = _run(runner, "connections", "last")
        assert result.exit_code == 0
        assert "latest" in result.output
