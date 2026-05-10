"""CliRunner tests for pbi deploy commands (stub / dry-run coverage)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestDeployPush:
    def test_push_prints_workspace(self, runner):
        result = _run(runner, "deploy", "push", "--workspace", "MyWorkspace")
        assert result.exit_code == 0
        assert "MyWorkspace" in result.output

    def test_push_dry_run(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "deploy",
                "push",
                "--workspace",
                "TestWS",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


class TestDeployDiff:
    def test_diff_runs(self, runner):
        result = _run(runner, "deploy", "diff", "--workspace", "MyWorkspace")
        assert result.exit_code == 0
        assert "Diffing" in result.output


class TestDeployPromote:
    def test_promote_dry_run(self, runner):
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "deploy",
                "promote",
                "--from",
                "Dev",
                "--to",
                "Prod",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_promote_prints_workspaces(self, runner):
        result = _run(runner, "deploy", "promote", "--from", "Dev", "--to", "Prod")
        assert result.exit_code == 0
        assert "Dev" in result.output
        assert "Prod" in result.output
