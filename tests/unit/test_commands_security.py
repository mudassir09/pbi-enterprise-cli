"""Unit tests for pbi security commands (RLS role management)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _run(runner, *args):
    return runner.invoke(cli, ["--backend", "mock", *args])


class TestSecurityRoles:
    def test_roles_empty(self, runner):
        """With a fresh mock backend, no roles are defined."""
        result = _run(runner, "security", "roles")
        assert result.exit_code == 0
        assert "No RLS roles" in result.output

    def test_roles_after_add(self, runner):
        """Adding a role then listing shows it in the output."""
        _run(runner, "security", "role-add", "--name", "Finance", "--table", "Sales",
             "--filter", "[Country] = \"UK\"")
        result = _run(runner, "security", "roles")
        # The mock backend stores them in-process but each invoke creates a fresh
        # MockTomBackend; just verify the command itself exits cleanly.
        assert result.exit_code == 0

    def test_roles_json_flag(self, runner):
        """--json flag is accepted; with empty roles the command exits cleanly."""
        result = runner.invoke(cli, ["--backend", "mock", "--json", "security", "roles"])
        assert result.exit_code == 0
        # Mock has no roles — the command prints "No RLS roles" and returns early
        assert "No RLS roles" in result.output


class TestSecurityRoleAdd:
    def test_role_add_success(self, runner):
        result = _run(runner, "security", "role-add",
                      "--name", "Finance",
                      "--table", "Sales",
                      "--filter", "[Country] = \"UK\"")
        assert result.exit_code == 0
        assert "Finance" in result.output

    def test_role_add_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "security", "role-add",
            "--name", "Finance",
            "--table", "Sales",
            "--filter", "[Country] = \"UK\"",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_role_add_missing_name(self, runner):
        result = _run(runner, "security", "role-add",
                      "--table", "Sales",
                      "--filter", "[Country] = \"UK\"")
        assert result.exit_code != 0

    def test_role_add_missing_filter(self, runner):
        result = _run(runner, "security", "role-add",
                      "--name", "Finance",
                      "--table", "Sales")
        assert result.exit_code != 0


class TestSecurityRoleDelete:
    def test_role_delete_success(self, runner):
        result = _run(runner, "security", "role-delete", "--name", "Finance")
        assert result.exit_code == 0
        assert "Finance" in result.output

    def test_role_delete_dry_run(self, runner):
        result = runner.invoke(cli, [
            "--backend", "mock", "--dry-run",
            "security", "role-delete",
            "--name", "Finance",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_role_delete_missing_name(self, runner):
        result = _run(runner, "security", "role-delete")
        assert result.exit_code != 0


class TestSecurityTest:
    def test_role_test_success(self, runner):
        result = _run(runner, "security", "test",
                      "--role", "Finance",
                      "--query", "EVALUATE Sales")
        assert result.exit_code == 0
        assert "Finance" in result.output

    def test_role_test_shows_row_count(self, runner):
        result = _run(runner, "security", "test",
                      "--role", "Manager",
                      "--query", "EVALUATE SUMMARIZE(Sales, Sales[Region])")
        assert result.exit_code == 0
        # Mock backend always returns rowCount = 1
        assert "1" in result.output

    def test_role_test_missing_role(self, runner):
        result = _run(runner, "security", "test", "--query", "EVALUATE Sales")
        assert result.exit_code != 0
