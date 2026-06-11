"""Tests for the Fabric platform expansion: items, workspaces, git, pipelines, jobs."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _token():
    return patch("pbi_cli.fabric_api.get_token", return_value="tok")


class TestItems:
    def test_item_list(self, runner):
        items = {"value": [
            {"id": "i1", "displayName": "SalesModel", "type": "SemanticModel"},
            {"id": "i2", "displayName": "SalesReport", "type": "Report"},
        ]}
        with _token(), patch("pbi_cli.fabric_api.get", return_value=items):
            result = runner.invoke(
                cli, ["--json", "fabric", "item", "list", "--workspace", "ws-1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert {d["type"] for d in data} == {"SemanticModel", "Report"}

    def test_item_create_uploads_definition_parts(self, runner, tmp_path):
        (tmp_path / "definition").mkdir()
        (tmp_path / "definition" / "model.tmdl").write_text("model Model", encoding="utf-8")
        captured: dict = {}

        def fake_post(url, token, payload=None, **kw):
            captured["url"] = url
            captured["payload"] = payload
            return {"id": "new-item", "displayName": "M"}

        with _token(), patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "--json", "fabric", "item", "create", "--workspace", "ws-1",
                "--name", "M", "--type", "SemanticModel", "--definition", str(tmp_path),
            ])
        assert result.exit_code == 0, result.output
        parts = captured["payload"]["definition"]["parts"]
        assert parts[0]["path"] == "definition/model.tmdl"
        assert base64.b64decode(parts[0]["payload"]).decode() == "model Model"

    def test_item_get_downloads_definition(self, runner, tmp_path):
        definition = {"definition": {"parts": [{
            "path": "definition/model.tmdl",
            "payload": base64.b64encode(b"model Model").decode(),
            "payloadType": "InlineBase64",
        }]}}
        out = tmp_path / "dl"
        with _token(), \
             patch("pbi_cli.fabric_api.get", return_value={"id": "i1"}), \
             patch("pbi_cli.fabric_api.post", return_value=definition):
            result = runner.invoke(cli, [
                "fabric", "item", "get", "--workspace", "ws-1", "--item", "i1",
                "--output", str(out),
            ])
        assert result.exit_code == 0, result.output
        assert (out / "definition" / "model.tmdl").read_text(encoding="utf-8") == "model Model"


class TestWorkspaceAndGit:
    def test_workspace_create(self, runner):
        with _token(), patch("pbi_cli.fabric_api.post",
                             return_value={"id": "ws-9", "displayName": "New"}):
            result = runner.invoke(cli, [
                "--json", "fabric", "workspace", "create", "--name", "New",
                "--capacity", "cap-1"])
        assert result.exit_code == 0
        assert json.loads(result.output)["id"] == "ws-9"

    def test_git_status_table(self, runner):
        status = {
            "remoteCommitHash": "abc123def456", "workspaceHead": "abc123def456",
            "changes": [{"itemMetadata": {"displayName": "Model", "itemType": "SemanticModel"},
                         "workspaceChange": "Modified", "remoteChange": None}],
        }
        with _token(), patch("pbi_cli.fabric_api.get", return_value=status):
            result = runner.invoke(cli, ["fabric", "git", "status", "--workspace", "ws-1"])
        assert result.exit_code == 0
        assert "Modified" in result.output

    def test_git_commit_sends_head(self, runner):
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["payload"] = payload
            return {"status": "Succeeded"}

        with _token(), \
             patch("pbi_cli.fabric_api.get", return_value={"workspaceHead": "h1"}), \
             patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "fabric", "git", "commit", "--workspace", "ws-1", "-m", "sync"])
        assert result.exit_code == 0
        assert captured["payload"]["workspaceHead"] == "h1"
        assert captured["payload"]["comment"] == "sync"


class TestPipelines:
    def test_deploy_resolves_stage_names(self, runner):
        stages = {"value": [
            {"id": "s1", "displayName": "Dev", "order": 0, "workspaceId": "w1"},
            {"id": "s2", "displayName": "Test", "order": 1, "workspaceId": "w2"},
        ]}
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["payload"] = payload
            return {"status": "Succeeded"}

        with _token(), patch("pbi_cli.fabric_api.get", return_value=stages), \
             patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "fabric", "pipeline", "deploy", "--pipeline", "p1",
                "--from", "Dev", "--to", "Test"])
        assert result.exit_code == 0, result.output
        assert captured["payload"]["sourceStageId"] == "s1"
        assert captured["payload"]["targetStageId"] == "s2"

    def test_deploy_unknown_stage_fails(self, runner):
        with _token(), patch("pbi_cli.fabric_api.get", return_value={"value": []}):
            result = runner.invoke(cli, [
                "fabric", "pipeline", "deploy", "--pipeline", "p1",
                "--from", "Nope", "--to", "Test"])
        assert result.exit_code != 0


class TestJobsAndDirectLake:
    def test_job_run(self, runner):
        with _token(), patch("pbi_cli.fabric_api.post",
                             return_value={"id": "job-1", "status": "NotStarted"}):
            result = runner.invoke(cli, [
                "--json", "fabric", "job", "run", "--workspace", "w", "--item", "i",
                "--type", "RunNotebook"])
        assert result.exit_code == 0
        assert json.loads(result.output)["id"] == "job-1"

    def test_directlake_status_detects_mode(self, runner):
        def fake_post(url, token, payload=None, **kw):
            q = payload["queries"][0]["query"]
            if "INFO.TABLES" in q:
                return {"results": [{"tables": [{"rows": [{"[ID]": 1, "[Name]": "Sales"}]}]}]}
            if "INFO.PARTITIONS" in q:
                return {"results": [{"tables": [{"rows": [
                    {"[TableID]": 1, "[Name]": "Sales-p1", "[Mode]": "directLake",
                     "[State]": "Ready"}]}]}]}
            raise AssertionError(q)

        with _token(), patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "--json", "fabric", "directlake", "status",
                "--workspace", "w", "--dataset", "d"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["directLake"] is True
