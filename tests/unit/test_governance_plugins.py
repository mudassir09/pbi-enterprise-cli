"""Unit tests for the custom governance rule plugin system."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


class TestPluginLoader:
    def test_builtin_rules_loaded(self):
        from pbi_cli.governance.rules import ALL_RULES, _BUILTIN_RULES
        for rule in _BUILTIN_RULES:
            assert rule in ALL_RULES

    def test_all_builtin_rules_have_check(self):
        from pbi_cli.governance.rules import _BUILTIN_RULES
        for rule in _BUILTIN_RULES:
            assert callable(getattr(rule, "check", None)), f"{rule} missing check()"

    def test_all_builtin_rules_have_rule_id(self):
        from pbi_cli.governance.rules import _BUILTIN_RULES
        for rule in _BUILTIN_RULES:
            assert hasattr(rule, "RULE_ID"), f"{rule} missing RULE_ID"
            assert isinstance(rule.RULE_ID, str)
            assert rule.RULE_ID

    def test_load_plugin_rules_empty_when_dir_missing(self, tmp_path, monkeypatch):
        """When ~/.pbi-cli/rules/ doesn't exist, no plugins loaded."""
        from pbi_cli.governance import rules as rules_module
        non_existent = tmp_path / "rules_no_exist"
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        loaded = rules_module._load_plugin_rules()
        assert loaded == []

    def test_load_valid_plugin(self, tmp_path, monkeypatch):
        """A valid plugin file is loaded and returned."""
        rules_dir = tmp_path / ".pbi-cli" / "rules"
        rules_dir.mkdir(parents=True)
        plugin = rules_dir / "my_custom_rule.py"
        plugin.write_text(
            'RULE_ID = "custom.my_rule"\n'
            'def check(backend):\n'
            '    return []\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from pbi_cli.governance import rules as rules_module
        loaded = rules_module._load_plugin_rules()
        assert len(loaded) == 1
        assert loaded[0].RULE_ID == "custom.my_rule"
        assert callable(loaded[0].check)

    def test_invalid_plugin_warns_but_does_not_crash(self, tmp_path, monkeypatch):
        """A plugin with a syntax error issues a warning but doesn't crash."""
        rules_dir = tmp_path / ".pbi-cli" / "rules"
        rules_dir.mkdir(parents=True)
        bad_plugin = rules_dir / "bad_rule.py"
        bad_plugin.write_text("this is not valid python !!!@##", encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from pbi_cli.governance import rules as rules_module
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            loaded = rules_module._load_plugin_rules()
        # Should return empty (bad plugin skipped) and warn
        assert loaded == []
        assert len(w) >= 1

    def test_plugin_without_check_is_skipped(self, tmp_path, monkeypatch):
        """A plugin file without check() is skipped silently."""
        rules_dir = tmp_path / ".pbi-cli" / "rules"
        rules_dir.mkdir(parents=True)
        plugin = rules_dir / "no_check.py"
        plugin.write_text(
            'RULE_ID = "custom.no_check"\n'
            '# no check function\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from pbi_cli.governance import rules as rules_module
        loaded = rules_module._load_plugin_rules()
        assert loaded == []

    def test_plugin_without_rule_id_is_skipped(self, tmp_path, monkeypatch):
        """A plugin file without RULE_ID is skipped silently."""
        rules_dir = tmp_path / ".pbi-cli" / "rules"
        rules_dir.mkdir(parents=True)
        plugin = rules_dir / "no_id.py"
        plugin.write_text(
            'def check(backend):\n'
            '    return []\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from pbi_cli.governance import rules as rules_module
        loaded = rules_module._load_plugin_rules()
        assert loaded == []


class TestEngineListRules:
    def test_list_rules_returns_list(self):
        from pbi_cli.governance.engine import GovernanceEngine
        rules = GovernanceEngine.list_rules()
        assert isinstance(rules, list)
        assert len(rules) >= 4  # at least the 4 built-in rules

    def test_list_rules_has_required_fields(self):
        from pbi_cli.governance.engine import GovernanceEngine
        for r in GovernanceEngine.list_rules():
            assert "rule_id" in r
            assert "source" in r
            assert "fixable" in r

    def test_builtin_rules_source_label(self):
        from pbi_cli.governance.engine import GovernanceEngine
        builtin_rules = [r for r in GovernanceEngine.list_rules() if r["source"] == "built-in"]
        assert len(builtin_rules) >= 4, "Expected at least 4 built-in rules"
        # Verify actual RULE_IDs from the modules
        rule_ids = {r["rule_id"] for r in builtin_rules}
        assert "table-pascal-case" in rule_ids
        assert "measure-brackets" in rule_ids


class TestGovernRulesCommand:
    def test_govern_rules_command(self):
        from click.testing import CliRunner
        from pbi_cli.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--backend", "mock", "govern", "rules"])
        assert result.exit_code == 0
        assert "built-in" in result.output

    def test_govern_rules_json(self):
        import json
        from click.testing import CliRunner
        from pbi_cli.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--backend", "mock", "--json", "govern", "rules"])
        assert result.exit_code == 0
        # Extract the JSON array from the output (may have trailing console lines)
        data = _extract_json_list(result.output)
        assert isinstance(data, list)
        assert len(data) >= 4


def _extract_json_list(output: str) -> list:
    """Extract the first complete JSON array from CLI output."""
    import json
    idx = output.find("[")
    if idx < 0:
        return json.loads(output)
    # Find matching closing bracket by tracking depth
    depth = 0
    for i, ch in enumerate(output[idx:], start=idx):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(output[idx:i + 1])
    return json.loads(output[idx:])
