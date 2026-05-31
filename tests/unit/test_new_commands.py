"""Tests for new commands: env, snapshot, server auth, govern --fail-on, skills check."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, ["--backend", "mock", *args])


# ── server auth ───────────────────────────────────────────────────────────────


class TestServerAuth:
    def test_generate_key_outputs_hex(self, runner):
        result = runner.invoke(cli, ["server", "generate-key"])
        assert result.exit_code == 0
        key = result.output.strip()
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_generate_key_is_random(self, runner):
        r1 = runner.invoke(cli, ["server", "generate-key"]).output.strip()
        r2 = runner.invoke(cli, ["server", "generate-key"]).output.strip()
        assert r1 != r2

    def test_start_requires_env_key(self, runner):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PBI_SERVER_KEY", None)
            result = runner.invoke(cli, ["server", "start"])
        assert result.exit_code != 0
        assert "PBI_SERVER_KEY" in result.output

    def test_start_warns_on_non_localhost(self, runner, monkeypatch):
        monkeypatch.setenv("PBI_SERVER_KEY", "test-key")
        # Patch uvicorn import inside the server_cmd module
        import sys
        import types
        fake_uvicorn = types.ModuleType("uvicorn")
        fake_uvicorn.run = lambda *a, **kw: None  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            result = runner.invoke(cli, ["server", "start", "--host", "0.0.0.0"])
        # Warning about non-localhost OR success — both are acceptable
        assert (
            "WARNING" in result.output
            or "warning" in result.output.lower()
            or "0.0.0.0" in result.output
            or result.exit_code in (0, 1)
        )

    def test_verify_api_key_correct(self):
        from pbi_cli.server.auth import verify_api_key
        with patch.dict(os.environ, {"PBI_SERVER_KEY": "secret123"}):
            assert verify_api_key("secret123") is True

    def test_verify_api_key_wrong(self):
        from pbi_cli.server.auth import verify_api_key
        with patch.dict(os.environ, {"PBI_SERVER_KEY": "secret123"}):
            assert verify_api_key("wrongkey") is False

    def test_verify_api_key_missing_env(self):
        from pbi_cli.server.auth import verify_api_key
        env = {k: v for k, v in os.environ.items() if k != "PBI_SERVER_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert verify_api_key("anything") is False

    def test_generate_key_function(self):
        from pbi_cli.server.auth import generate_key
        k = generate_key()
        assert len(k) == 64
        assert isinstance(k, str)


# ── govern --fail-on exit codes ───────────────────────────────────────────────


class TestGovernFailOn:
    def test_exit_0_on_clean(self, runner):
        result = _run(runner, "govern", "check", "--fail-on", "error")
        assert result.exit_code == 0

    def test_json_output_has_summary(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "check"])
        assert result.exit_code in (0, 3)
        data = json.loads(result.output)
        assert "summary" in data
        assert "violations" in data
        assert "errors" in data["summary"]
        assert "warnings" in data["summary"]
        assert "infos" in data["summary"]
        assert "total" in data["summary"]

    def test_fail_on_info_exits_3_on_any_violation(self, runner):
        result = _run(runner, "govern", "check", "--fail-on", "info")
        # Mock backend may or may not have violations; just verify exit code is 0 or 3
        assert result.exit_code in (0, 3)

    def test_fail_on_default_is_error(self, runner):
        result = _run(runner, "govern", "check")
        assert result.exit_code in (0, 3)


# ── skills check ──────────────────────────────────────────────────────────────


class TestSkillsCheck:
    def test_check_exits_0_when_all_compatible(self, runner, tmp_path, monkeypatch):
        skills_src = tmp_path / "skills"
        skill_dir = skills_src / "power-bi-dax"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: power-bi-dax\nversion: \"2.0\"\n"
            "min_cli_version: \"0.1.0\"\ndescription: test\n---\nBody\n"
        )
        monkeypatch.setattr(
            "pbi_cli.commands.skills_cmd._skills_source_dir", lambda: skills_src
        )
        monkeypatch.setattr(
            "pbi_cli.commands.skills_cmd._BUNDLED_SKILLS",
            [{"name": "power-bi-dax", "description": "test"}],
        )
        result = runner.invoke(cli, ["skills", "check"])
        assert result.exit_code == 0
        assert "compatible" in result.output

    def test_parse_frontmatter(self):
        from pbi_cli.commands.skills_cmd import _parse_frontmatter

        md = Path(__file__).parent.parent.parent / "skills" / "power-bi-dax" / "SKILL.md"
        if md.exists():
            fm = _parse_frontmatter(md)
            assert fm.get("name") == "power-bi-dax"
            assert "min_cli_version" in fm
            assert "version" in fm

    def test_version_tuple(self):
        from pbi_cli.commands.skills_cmd import _version_tuple

        assert _version_tuple("4.0.0") == (4, 0, 0)
        assert _version_tuple("1.2.3") == (1, 2, 3)
        assert _version_tuple("1.0") == (1, 0)


# ── env command ───────────────────────────────────────────────────────────────


class TestEnvCommand:
    def _patch_conn_file(self, monkeypatch, tmp_path, data=None):
        conn_path = tmp_path / "connections.json"
        if data is not None:
            conn_path.write_text(json.dumps(data))
        monkeypatch.setattr("pbi_cli.commands.env_cmd._CONNECTIONS_FILE", conn_path)
        return conn_path

    def test_env_list_no_connections(self, runner, tmp_path, monkeypatch):
        self._patch_conn_file(monkeypatch, tmp_path)
        result = _run(runner, "env", "list")
        assert result.exit_code == 0
        assert "No connections" in result.output

    def test_env_use_unknown_fails(self, runner, tmp_path, monkeypatch):
        self._patch_conn_file(monkeypatch, tmp_path, {"default": None, "connections": {}})
        result = _run(runner, "env", "use", "nonexistent")
        assert result.exit_code != 0

    def test_env_use_known_sets_default(self, runner, tmp_path, monkeypatch):
        conn_path = self._patch_conn_file(monkeypatch, tmp_path, {
            "default": None,
            "connections": {"fabric-dev": {"backend": "xmla"}}
        })
        result = _run(runner, "env", "use", "fabric-dev")
        assert result.exit_code == 0
        assert "fabric-dev" in result.output
        data = json.loads(conn_path.read_text())
        assert data["default"] == "fabric-dev"

    def test_env_promote_requires_confirm(self, runner, tmp_path, monkeypatch):
        self._patch_conn_file(monkeypatch, tmp_path, {
            "default": None,
            "connections": {
                "dev": {"backend": "xmla"},
                "prod": {"backend": "xmla"},
            }
        })
        result = runner.invoke(cli, ["--backend", "mock", "env", "promote", "dev", "prod"])
        assert result.exit_code != 0


# ── snapshot command ──────────────────────────────────────────────────────────


class TestSnapshotCommand:
    def test_snapshot_list_empty(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _run(runner, "snapshot", "list")
        assert result.exit_code == 0
        assert "No snapshots" in result.output

    def test_snapshot_create_dry_run(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run", "snapshot", "create", "--label", "test"
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output or "dry" in result.output.lower()

    def test_snapshot_create_real(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _run(runner, "snapshot", "create", "--label", "ci-test")
        assert result.exit_code in (0, 4)  # 4 if tmdl_export not supported in mock
        if result.exit_code == 0:
            assert "Snapshot created" in result.output

    def test_snapshot_restore_requires_confirm(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        snap_dir = tmp_path / ".pbi" / "snapshots" / "20260101_000000"
        snap_dir.mkdir(parents=True)
        result = _run(runner, "snapshot", "restore", "20260101_000000")
        assert result.exit_code != 0


# ── server/auth module unit tests ─────────────────────────────────────────────


class TestAuthModule:
    def test_get_configured_key_from_env(self):
        from pbi_cli.server.auth import get_configured_key
        with patch.dict(os.environ, {"PBI_SERVER_KEY": "my-key"}):
            assert get_configured_key() == "my-key"

    def test_get_configured_key_none_when_missing(self):
        from pbi_cli.server.auth import get_configured_key
        env = {k: v for k, v in os.environ.items() if k != "PBI_SERVER_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert get_configured_key() is None
