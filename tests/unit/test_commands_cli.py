"""CliRunner tests for top-level pbi CLI commands (doctor, undo, skill-validate, completions)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ── doctor ────────────────────────────────────────────────────────────────────

class TestDoctor:
    def test_doctor_runs(self, runner):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_json_output(self, runner):
        result = runner.invoke(cli, ["--json", "doctor"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        checks = {c["check"] for c in data}
        assert "Python version" in checks

    def test_doctor_includes_platform_check(self, runner):
        result = runner.invoke(cli, ["--json", "doctor"])
        data = json.loads(result.output)
        platform_check = next((c for c in data if c["check"] == "Platform"), None)
        assert platform_check is not None


# ── undo ──────────────────────────────────────────────────────────────────────

class TestUndo:
    def test_undo_no_snapshots_exits_cleanly(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("pbi_cli._snapshot._SNAPSHOT_DIR", tmp_path / "snapshots")
        result = runner.invoke(cli, ["--backend", "mock", "undo"])
        assert result.exit_code == 0
        assert "No snapshots" in result.output

    def test_undo_with_snapshot_and_no_pbi_desktop(self, runner, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        snap_file = snap_dir / "20250101T000000000000.json"
        snap_file.write_text(
            json.dumps({"measures": [], "tables": [], "columns": [], "relationships": [], "model": {}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli._snapshot._SNAPSHOT_DIR", snap_dir)
        monkeypatch.setattr("pbi_cli.backends.tom_backend.find_pbi_port", lambda: None)
        result = runner.invoke(cli, ["--backend", "mock", "undo", "--yes"])
        assert result.exit_code in (0, 1)
        assert "No running Power BI" in result.output


# ── skill-validate ────────────────────────────────────────────────────────────

class TestSkillValidate:
    def _write_skill(self, tmp_path, content: str) -> str:
        f = tmp_path / "SKILL.md"
        f.write_text(content, encoding="utf-8")
        return str(tmp_path)

    VALID_SKILL = """\
---
name: test-skill
description: |
  Use when user asks about testing. Do NOT trigger on unrelated topics.
  triggers on: test requests
version: "1.0"
requires: []
---

## Quick Reference

```bash
pbi measure list
```
"""

    def test_valid_skill_passes(self, runner, tmp_path):
        path = self._write_skill(tmp_path, self.VALID_SKILL)
        result = runner.invoke(cli, ["skill-validate", path])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_missing_frontmatter_is_error(self, runner, tmp_path):
        path = self._write_skill(tmp_path, "# No frontmatter here\n\nJust content.")
        result = runner.invoke(cli, ["skill-validate", path])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_missing_required_field_is_error(self, runner, tmp_path):
        content = """\
---
name: incomplete
description: Use when testing.
---

## Quick Reference
```bash
pbi
```
"""
        path = self._write_skill(tmp_path, content)
        result = runner.invoke(cli, ["skill-validate", path])
        assert result.exit_code == 1
        assert "version" in result.output or "requires" in result.output

    def test_no_code_block_is_warning(self, runner, tmp_path):
        content = """\
---
name: nocode
description: |
  Use when testing. Do NOT trigger otherwise.
  triggers on: test
version: "1.0"
requires: []
---

## Quick Reference

No code examples here.
"""
        path = self._write_skill(tmp_path, content)
        result = runner.invoke(cli, ["skill-validate", path])
        # warnings don't cause exit 1
        assert result.exit_code == 0

    def test_file_path_directly(self, runner, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(self.VALID_SKILL, encoding="utf-8")
        result = runner.invoke(cli, ["skill-validate", str(f)])
        assert result.exit_code == 0


# ── completions ───────────────────────────────────────────────────────────────

class TestCompletions:
    def test_completions_bash(self, runner):
        result = runner.invoke(cli, ["completions", "--shell", "bash"])
        assert result.exit_code == 0
        # Either prints the completion script or the instructions
        assert result.output.strip() != ""

    def test_completions_powershell(self, runner):
        result = runner.invoke(cli, ["completions", "--shell", "powershell"])
        assert result.exit_code == 0
        assert result.output.strip() != ""

    def test_completions_zsh(self, runner):
        result = runner.invoke(cli, ["completions", "--shell", "zsh"])
        assert result.exit_code == 0

    def test_completions_fish(self, runner):
        result = runner.invoke(cli, ["completions", "--shell", "fish"])
        assert result.exit_code == 0


# ── version ───────────────────────────────────────────────────────────────────

class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "pbi" in result.output.lower()
