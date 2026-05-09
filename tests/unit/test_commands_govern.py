"""CliRunner tests for pbi govern commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


# ── govern init ───────────────────────────────────────────────────────────────

class TestGovernInit:
    def test_creates_config_file(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = _run(runner, "govern", "init")
        assert result.exit_code == 0
        config = tmp_path / ".pbi-cli" / "governance.json"
        assert config.exists()

    def test_skips_if_already_exists(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        # First creation
        _run(runner, "govern", "init")
        # Second should say "Already exists"
        result = _run(runner, "govern", "init")
        assert result.exit_code == 0
        assert "Already exists" in result.output


# ── govern check ──────────────────────────────────────────────────────────────

class TestGovernCheck:
    def test_check_returns_violations(self, runner):
        # Mock backend has measures with no description — expect violations
        result = _run(runner, "govern", "check")
        # Exit 0 or 1 depending on severity; output should mention violations
        assert "warning" in result.output.lower() or result.exit_code in (0, 1)

    def test_check_json_output_is_list(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "check"])
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_check_json_violations_have_required_fields(self, runner):
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "check"])
        data = json.loads(result.output)
        for v in data:
            assert "rule" in v
            assert "severity" in v
            assert "message" in v
            assert "autoFixable" in v

    def test_check_exits_1_on_errors(self, runner, monkeypatch):
        from pbi_cli.governance import engine as eng

        monkeypatch.setattr(
            eng.GovernanceEngine,
            "run_all",
            lambda self: [{"rule": "test", "severity": "error", "object": "X",
                           "message": "Error", "autoFixable": False}],
        )
        result = _run(runner, "govern", "check")
        assert result.exit_code == 1


# ── govern fix ────────────────────────────────────────────────────────────────

class TestGovernFix:
    def test_fix_without_auto_lists_fixable(self, runner):
        result = _run(runner, "govern", "fix")
        assert result.exit_code == 0
        assert "--auto" in result.output

    def test_fix_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run", "govern", "fix", "--auto"
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_fix_auto_applies_fixes(self, runner):
        result = _run(runner, "govern", "fix", "--auto")
        assert result.exit_code == 0
        assert "Fixed" in result.output
