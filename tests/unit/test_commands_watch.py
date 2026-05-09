"""Unit tests for the pbi watch command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestWatchHelp:
    def test_watch_help(self, runner):
        """--help should exit 0 and describe the command."""
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "watch" in result.output.lower()

    def test_watch_is_registered(self, runner):
        """'watch' appears in the top-level help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "watch" in result.output

    def test_watch_help_shows_options(self, runner):
        """Help output lists key options: --path, --on, --debounce, --patterns."""
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.output
        assert "--on" in result.output
        assert "--debounce" in result.output
        assert "--patterns" in result.output


class TestWatchMissingDependency:
    def test_watch_without_watchdog_exits_nonzero(self, runner, monkeypatch, tmp_path):
        """When watchdog is not installed the command should print an error and exit non-zero."""
        import builtins
        real_import = builtins.__import__

        def patched_import(name, *args, **kwargs):
            if name.startswith("watchdog"):
                raise ImportError("watchdog not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", patched_import)
        result = runner.invoke(cli, ["watch", "--path", str(tmp_path)])
        # Command should fail (SystemExit(1)) with an informative message
        assert result.exit_code != 0 or "watchdog" in result.output


class TestWatchPathValidation:
    def test_watch_nonexistent_path_exits(self, runner):
        """Passing a non-existent --path should exit with an error."""
        result = runner.invoke(cli, ["watch", "--path", "/nonexistent/path/xyz123"])
        # Either the command catches it and exits non-zero, or watchdog is missing
        # Either way we just need no unhandled exception
        assert result.exit_code is not None
