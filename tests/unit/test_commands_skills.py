"""CliRunner tests for pbi skills commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def tmp_skills_target(tmp_path) -> Path:
    """A temporary directory to use as the skills install target."""
    target = tmp_path / "claude_skills"
    target.mkdir(parents=True)
    return target


@pytest.fixture()
def skills_source(tmp_path) -> Path:
    """Create a fake bundled skills source directory with a few skill subdirs."""
    source = tmp_path / "skills"
    source.mkdir()
    # Create mock skill directories matching names in _BUNDLED_SKILLS
    for name in ["power-bi-dax", "power-bi-modeling", "power-bi-governance"]:
        skill_dir = source / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"# {name} skill", encoding="utf-8")
    return source


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, [*args])


# ── skills list ───────────────────────────────────────────────────────────────


class TestSkillsList:
    def test_list_exits_cleanly(self, runner):
        result = _run(runner, "skills", "list")
        assert result.exit_code == 0

    def test_list_shows_12_skills(self, runner):
        """_BUNDLED_SKILLS has 12 entries (10 original + report-management + report-planner)."""
        from pbi_cli.commands.skills_cmd import _BUNDLED_SKILLS
        assert len(_BUNDLED_SKILLS) == 12

    def test_list_output_contains_skill_names(self, runner):
        result = _run(runner, "skills", "list")
        assert result.exit_code == 0
        assert "power-bi-dax" in result.output

    def test_list_shows_not_installed_by_default(self, runner, tmp_path, monkeypatch):
        """Skills show as not-installed when the target dir does not exist."""
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_claude_skills_dir", lambda: tmp_path / "nonexistent")
        result = _run(runner, "skills", "list")
        assert result.exit_code == 0
        # The dim "–" marker appears for not-installed skills
        assert "power-bi-dax" in result.output

    def test_list_installed_flag_with_none_installed(self, runner, tmp_path, monkeypatch):
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_claude_skills_dir", lambda: tmp_path / "empty")
        result = _run(runner, "skills", "list", "--installed")
        assert result.exit_code == 0

    def test_list_shows_installed_skill(self, runner, tmp_path, monkeypatch):
        import pbi_cli.commands.skills_cmd as skills_mod
        target = tmp_path / "skills"
        target.mkdir()
        (target / "power-bi-dax").mkdir()
        monkeypatch.setattr(skills_mod, "_claude_skills_dir", lambda: target)
        result = _run(runner, "skills", "list")
        assert result.exit_code == 0
        assert "power-bi-dax" in result.output


# ── skills install ────────────────────────────────────────────────────────────


class TestSkillsInstall:
    def test_install_no_args_prints_help(self, runner, tmp_skills_target):
        result = _run(runner, "skills", "install", "--target", str(tmp_skills_target))
        assert result.exit_code == 0
        assert "Specify skill names" in result.output or "--all" in result.output

    def test_install_single_skill(self, runner, tmp_skills_target, skills_source, monkeypatch):
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        result = _run(
            runner, "skills", "install", "power-bi-dax",
            "--target", str(tmp_skills_target)
        )
        assert result.exit_code == 0
        assert (tmp_skills_target / "power-bi-dax").exists()

    def test_install_all_copies_available_skills(self, runner, tmp_skills_target, skills_source, monkeypatch):  # noqa: E501
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        result = _run(
            runner, "skills", "install", "--all",
            "--target", str(tmp_skills_target)
        )
        assert result.exit_code == 0
        # The 3 fake skills in skills_source should be copied
        assert (tmp_skills_target / "power-bi-dax").exists()

    def test_install_missing_skill_prints_not_found(self, runner, tmp_skills_target, skills_source, monkeypatch):  # noqa: E501
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        result = _run(
            runner, "skills", "install", "nonexistent-skill",
            "--target", str(tmp_skills_target)
        )
        assert result.exit_code == 0
        assert "Not found" in result.output

    def test_install_overwrites_existing(self, runner, tmp_skills_target, skills_source, monkeypatch):  # noqa: E501
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        # Install once
        _run(runner, "skills", "install", "power-bi-dax", "--target", str(tmp_skills_target))
        # Install again - should overwrite without error
        result = _run(runner, "skills", "install", "power-bi-dax", "--target", str(tmp_skills_target))  # noqa: E501
        assert result.exit_code == 0


# ── skills uninstall ──────────────────────────────────────────────────────────


class TestSkillsUninstall:
    def test_uninstall_no_args_prints_help(self, runner, tmp_skills_target):
        result = _run(runner, "skills", "uninstall", "--target", str(tmp_skills_target))
        assert result.exit_code == 0
        assert "Specify skill names" in result.output or "--all" in result.output

    def test_uninstall_installed_skill(self, runner, tmp_skills_target, skills_source, monkeypatch):
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        # First install
        _run(runner, "skills", "install", "power-bi-dax", "--target", str(tmp_skills_target))
        assert (tmp_skills_target / "power-bi-dax").exists()
        # Then uninstall
        result = _run(runner, "skills", "uninstall", "power-bi-dax", "--target", str(tmp_skills_target))  # noqa: E501
        assert result.exit_code == 0
        assert not (tmp_skills_target / "power-bi-dax").exists()

    def test_uninstall_not_installed_prints_message(self, runner, tmp_skills_target):
        result = _run(runner, "skills", "uninstall", "power-bi-dax", "--target", str(tmp_skills_target))  # noqa: E501
        assert result.exit_code == 0
        assert "Not installed" in result.output

    def test_uninstall_prints_removed_count(self, runner, tmp_skills_target, skills_source, monkeypatch):  # noqa: E501
        import pbi_cli.commands.skills_cmd as skills_mod
        monkeypatch.setattr(skills_mod, "_skills_source_dir", lambda: skills_source)
        _run(runner, "skills", "install", "power-bi-dax", "--target", str(tmp_skills_target))
        result = _run(runner, "skills", "uninstall", "power-bi-dax", "--target", str(tmp_skills_target))  # noqa: E501
        assert "removed" in result.output.lower()
