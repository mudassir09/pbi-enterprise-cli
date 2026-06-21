"""Tests for `pbi notebook` commands."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli
from pbi_cli.commands.notebook_cmd import _parse_param


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


def _mock_token():
    return patch("pbi_cli.fabric_api.get_token", return_value="fake-token")


class TestParseParam:
    def test_infers_types(self):
        assert _parse_param("n=7") == ("n", {"value": 7, "type": "int"})
        assert _parse_param("r=true") == ("r", {"value": True, "type": "bool"})
        assert _parse_param("f=1.5") == ("f", {"value": 1.5, "type": "float"})
        assert _parse_param("s=hello") == ("s", {"value": "hello", "type": "string"})

    def test_missing_equals_errors(self):
        import click

        with pytest.raises(click.ClickException):
            _parse_param("bad")


class TestNotebookRun:
    def test_run_passes_parameters(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.run_item_job",
            return_value={"jobInstanceId": "j1", "status": "NotStarted"},
        ) as mock_job:
            result = _run(runner, "notebook", "run", "--workspace", "ws",
                          "--notebook", "nb", "--param", "window=7", "--param", "rebuild=true")
        assert result.exit_code == 0
        exec_data = mock_job.call_args.kwargs["execution_data"]
        assert exec_data["parameters"]["window"] == {"value": 7, "type": "int"}
        assert exec_data["parameters"]["rebuild"] == {"value": True, "type": "bool"}

    def test_run_no_params_sends_none(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.run_item_job", return_value={"status": "NotStarted"}
        ) as mock_job:
            _run(runner, "notebook", "run", "--workspace", "ws", "--notebook", "nb")
        assert mock_job.call_args.kwargs["execution_data"] is None

    def test_run_wait_reports_completion(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.run_item_job", return_value={"status": "Completed"}
        ):
            result = _run(runner, "notebook", "run", "--workspace", "ws",
                          "--notebook", "nb", "--wait")
        assert "Completed" in result.output

    def test_dry_run(self, runner):
        with patch("pbi_cli.fabric_api.run_item_job") as mock_job:
            result = _run(runner, "--dry-run", "notebook", "run", "--workspace", "ws",
                          "--notebook", "nb", "--param", "x=1")
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        mock_job.assert_not_called()


class TestNotebookStatus:
    def test_status(self, runner):
        with _mock_token(), patch(
            "pbi_cli.fabric_api.get", return_value={"status": "Completed", "id": "j1"}
        ):
            result = _run(runner, "--json", "notebook", "status", "--workspace", "ws",
                          "--notebook", "nb", "--job", "j1")
        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "Completed"


class TestNotebookExportImport:
    def test_export_writes_ipynb(self, runner, tmp_path):
        ipynb = b'{"cells": [], "nbformat": 4}'
        definition = {"definition": {"parts": [
            {"path": "notebook-content.ipynb",
             "payload": base64.b64encode(ipynb).decode(), "payloadType": "InlineBase64"}]}}
        out = tmp_path / "nb.ipynb"
        with _mock_token(), patch("pbi_cli.fabric_api.post", return_value={}), \
                patch("pbi_cli.fabric_api.poll_lro", return_value=definition):
            result = _run(runner, "notebook", "export", "--workspace", "ws",
                          "--notebook", "nb", "--output", str(out))
        assert result.exit_code == 0
        assert out.read_bytes() == ipynb

    def test_import_rejects_non_json(self, runner, tmp_path):
        bad = tmp_path / "bad.ipynb"
        bad.write_text("not json", encoding="utf-8")
        with _mock_token():
            result = _run(runner, "notebook", "import", "--workspace", "ws",
                          "--name", "N", "--file", str(bad))
        assert result.exit_code != 0
        assert "not valid JSON" in result.output

    def test_import_creates_from_ipynb(self, runner, tmp_path):
        good = tmp_path / "g.ipynb"
        good.write_text('{"cells": [], "nbformat": 4}', encoding="utf-8")
        with _mock_token(), patch(
            "pbi_cli.fabric_api.post", return_value={}
        ) as mock_post, patch(
            "pbi_cli.fabric_api.poll_lro", return_value={"id": "new-nb"}
        ):
            result = _run(runner, "notebook", "import", "--workspace", "ws",
                          "--name", "MyNb", "--file", str(good))
        assert result.exit_code == 0
        payload = mock_post.call_args.kwargs["payload"]
        assert payload["displayName"] == "MyNb"
        assert payload["definition"]["format"] == "ipynb"
