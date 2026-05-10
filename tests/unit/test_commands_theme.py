"""CliRunner tests for pbi theme commands."""

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


class TestThemeGenerate:
    def test_generates_theme_file(self, runner, tmp_path):
        out = str(tmp_path / "theme.json")
        result = _run(runner, "theme", "generate", "--brand-color", "#0078D4", "--output", out)
        assert result.exit_code == 0
        assert "Theme written" in result.output
        data = json.loads((tmp_path / "theme.json").read_text())
        assert isinstance(data, dict)

    def test_dry_run_skips_write(self, runner, tmp_path):
        out = str(tmp_path / "theme.json")
        result = runner.invoke(
            cli,
            [
                "--backend",
                "mock",
                "--dry-run",
                "theme",
                "generate",
                "--brand-color",
                "#FF0000",
                "--output",
                out,
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert not (tmp_path / "theme.json").exists()

    def test_corporate_style(self, runner, tmp_path):
        out = str(tmp_path / "corp.json")
        result = _run(
            runner,
            "theme",
            "generate",
            "--brand-color",
            "#003366",
            "--style",
            "corporate",
            "--output",
            out,
        )
        assert result.exit_code == 0

    def test_dark_style(self, runner, tmp_path):
        out = str(tmp_path / "dark.json")
        result = _run(
            runner,
            "theme",
            "generate",
            "--brand-color",
            "#222222",
            "--style",
            "dark",
            "--output",
            out,
        )
        assert result.exit_code == 0


class TestThemeValidate:
    def test_validates_theme_file(self, runner, tmp_path):
        theme_file = tmp_path / "t.json"
        theme_file.write_text(
            json.dumps(
                {
                    "name": "TestTheme",
                    "dataColors": ["#0078D4", "#FFFFFF"],
                    "background": "#FFFFFF",
                    "foreground": "#000000",
                }
            ),
            encoding="utf-8",
        )
        result = _run(runner, "theme", "validate", str(theme_file))
        assert result.exit_code == 0

    def test_validate_json_output(self, runner, tmp_path):
        theme_file = tmp_path / "t.json"
        theme_file.write_text(json.dumps({"name": "T", "dataColors": []}), encoding="utf-8")
        result = runner.invoke(
            cli, ["--backend", "mock", "--json", "theme", "validate", str(theme_file)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "passes" in data
