"""Tests for pbi govern plugins command group."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


_SAMPLE_REGISTRY = {
    "plugins": [
        {
            "name": "require-sensitivity-labels",
            "rule_id": "custom.require-sensitivity-labels",
            "description": "Flags tables without a sensitivity label set",
            "tags": ["governance", "security", "sensitivity"],
            "url": "https://raw.githubusercontent.com/example/rules/main/sensitivity.py",
        },
        {
            "name": "no-hardcoded-dates",
            "rule_id": "custom.no-hardcoded-dates",
            "description": "Detects hardcoded year values in DAX measures",
            "tags": ["dax", "governance"],
            "url": "https://raw.githubusercontent.com/example/rules/main/dates.py",
        },
    ]
}

_SAMPLE_PLUGIN_PY = (
    'RULE_ID = "custom.require-sensitivity-labels"\n\n'
    "def check(backend):\n    return []\n"
)


class TestPluginsList:
    def test_list_empty_dir(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", tmp_path / "rules")
        result = _run(runner, "govern", "plugins", "list")
        assert result.exit_code == 0
        assert "No plugins installed" in result.output

    def test_list_shows_installed_plugin(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "my_rule.py").write_text(
            'RULE_ID = "custom.my-rule"\n\ndef check(backend):\n    return []\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)
        result = _run(runner, "govern", "plugins", "list")
        assert result.exit_code == 0
        assert "my_rule.py" in result.output
        assert "custom.my-rule" in result.output

    def test_list_multiple_plugins(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        for name, rule_id in [("rule_a.py", "custom.rule-a"), ("rule_b.py", "custom.rule-b")]:
            (rules_dir / name).write_text(f'RULE_ID = "{rule_id}"\ndef check(b): return []\n')
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)
        result = _run(runner, "govern", "plugins", "list")
        assert result.exit_code == 0
        assert "rule_a.py" in result.output
        assert "rule_b.py" in result.output


class TestPluginsSearch:
    def _mock_registry(self):
        import io

        body = json.dumps(_SAMPLE_REGISTRY).encode()

        class FakeResponse:
            def __init__(self):
                self._data = io.BytesIO(body)

            def read(self):
                return self._data.read()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return FakeResponse()

    def test_search_lists_all(self, runner):
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_registry(),
        ):
            result = _run(runner, "govern", "plugins", "search", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [p["name"] for p in data]
        assert "require-sensitivity-labels" in names
        assert "no-hardcoded-dates" in names

    def test_search_filters_by_keyword(self, runner):
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_registry(),
        ):
            result = _run(runner, "govern", "plugins", "search", "sensitivity", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [p["name"] for p in data]
        assert "require-sensitivity-labels" in names
        assert "no-hardcoded-dates" not in names

    def test_search_no_results(self, runner):
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_registry(),
        ):
            result = _run(runner, "govern", "plugins", "search", "nonexistent-xyz", "--json")
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    def test_search_registry_unavailable(self, runner):
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = _run(runner, "govern", "plugins", "search")
        assert result.exit_code != 0
        assert "Could not fetch registry" in result.output or "registry" in result.output.lower()


class TestPluginsInstall:
    def _make_mocks(self, registry=_SAMPLE_REGISTRY, plugin_content=_SAMPLE_PLUGIN_PY):
        """Return context managers that mock both registry fetch and plugin download."""

        class FakeRegistryResp:
            def read(self):
                return json.dumps(registry).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        class FakePluginResp:
            def read(self):
                return plugin_content.encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        responses = iter([FakeRegistryResp(), FakePluginResp()])
        return patch(
            "urllib.request.urlopen",
            side_effect=lambda *a, **kw: next(responses),
        )

    def test_install_by_name(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)
        with self._make_mocks():
            result = _run(runner, "govern", "plugins", "install", "require-sensitivity-labels")
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert (rules_dir / "require-sensitivity-labels.py").exists()

    def test_install_by_url(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)


        class FakeResp:
            def read(self): return _SAMPLE_PLUGIN_PY.encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = _run(
                runner, "govern", "plugins", "install", "my-rule",
                "--url", "https://example.com/my_rule.py",
            )
        assert result.exit_code == 0
        assert (rules_dir / "my-rule.py").exists()

    def test_install_unknown_name(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)


        class FakeResp:
            def read(self): return json.dumps(_SAMPLE_REGISTRY).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = _run(runner, "govern", "plugins", "install", "does-not-exist")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_install_creates_plugin_dir(self, runner, tmp_path, monkeypatch):
        rules_dir = tmp_path / "deep" / "rules"
        monkeypatch.setattr("pbi_cli.commands.govern._PLUGIN_DIR", rules_dir)
        with self._make_mocks():
            _run(runner, "govern", "plugins", "install", "require-sensitivity-labels")
        assert rules_dir.exists()
