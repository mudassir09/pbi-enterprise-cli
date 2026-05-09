"""CliRunner tests for pbi docs commands."""

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


# ── docs generate ─────────────────────────────────────────────────────────────

class TestDocsGenerate:
    def test_markdown_outputs_to_console(self, runner):
        result = _run(runner, "docs", "generate", "--format", "markdown")
        assert result.exit_code == 0
        assert "# Data Dictionary" in result.output

    def test_markdown_includes_table_names(self, runner):
        result = _run(runner, "docs", "generate", "--format", "markdown")
        assert "Sales" in result.output

    def test_markdown_write_to_file(self, runner, tmp_path):
        out = str(tmp_path / "dict.md")
        result = _run(runner, "docs", "generate", "--format", "markdown", "--output", out)
        assert result.exit_code == 0
        assert "Written" in result.output
        content = (tmp_path / "dict.md").read_text(encoding="utf-8")
        assert "Data Dictionary" in content

    def test_confluence_format(self, runner):
        result = _run(runner, "docs", "generate", "--format", "confluence")
        assert result.exit_code == 0


# ── docs audit-log ────────────────────────────────────────────────────────────

class TestDocsAuditLog:
    def test_empty_audit_log_message(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("pbi_cli._audit._AUDIT_FILE", tmp_path / "audit.jsonl")
        result = _run(runner, "docs", "audit-log")
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_audit_log_with_entries(self, runner, tmp_path, monkeypatch):
        audit_file = tmp_path / "audit.jsonl"
        audit_file.write_text(
            json.dumps({"timestamp": "2025-01-01T00:00:00", "command": "measure add",
                        "user": "test"}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli._audit._AUDIT_FILE", audit_file)
        result = _run(runner, "docs", "audit-log")
        assert result.exit_code == 0

    def test_audit_log_limit(self, runner, tmp_path, monkeypatch):
        audit_file = tmp_path / "audit.jsonl"
        lines = [
            json.dumps({"timestamp": f"2025-01-{i:02d}T00:00:00", "command": "x", "user": "u"})
            for i in range(1, 11)
        ]
        audit_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr("pbi_cli._audit._AUDIT_FILE", audit_file)
        result = _run(runner, "docs", "audit-log", "--limit", "3")
        assert result.exit_code == 0
