"""Tests for `pbi fabric ontology` — Fabric IQ ontology (preview) item management."""

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


class TestOntologyList:
    def test_list_hits_ontologies_endpoint(self, runner):
        captured = {}

        def fake_get(url, token, **kw):
            captured["url"] = url
            return {"value": [
                {"id": "o1", "displayName": "Enterprise Ontology", "description": "Core"},
            ]}

        with _token(), patch("pbi_cli.fabric_api.get", side_effect=fake_get):
            result = runner.invoke(
                cli, ["--json", "fabric", "ontology", "list", "--workspace", "ws-1"])
        assert result.exit_code == 0, result.output
        assert captured["url"].endswith("/workspaces/ws-1/ontologies")
        data = json.loads(result.output)
        assert data[0]["name"] == "Enterprise Ontology"


class TestOntologyGet:
    def test_get_without_output_shows_item(self, runner):
        with _token(), patch("pbi_cli.fabric_api.get",
                             return_value={"id": "o1", "displayName": "Ont"}):
            result = runner.invoke(cli, [
                "--json", "fabric", "ontology", "get",
                "--workspace", "ws-1", "--ontology", "o1"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["id"] == "o1"

    def test_get_with_output_downloads_definition(self, runner, tmp_path):
        definition = {"definition": {"parts": [{
            "path": "ontology.json",
            "payload": base64.b64encode(b'{"entityTypes": []}').decode(),
            "payloadType": "InlineBase64",
        }]}}
        out = tmp_path / "dl"
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["url"] = url
            return definition

        with _token(), \
             patch("pbi_cli.fabric_api.get", return_value={"id": "o1"}), \
             patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "fabric", "ontology", "get", "--workspace", "ws-1",
                "--ontology", "o1", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert captured["url"].endswith("/ontologies/o1/getDefinition")
        assert (out / "ontology.json").read_text(encoding="utf-8") == '{"entityTypes": []}'


class TestOntologyCreate:
    def test_create_posts_to_ontologies(self, runner):
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["url"] = url
            captured["payload"] = payload
            return {"id": "o-new", "displayName": "Sales Ontology"}

        with _token(), patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "--json", "fabric", "ontology", "create", "--workspace", "ws-1",
                "--name", "Sales Ontology", "--description", "Sales domain"])
        assert result.exit_code == 0, result.output
        assert captured["url"].endswith("/workspaces/ws-1/ontologies")
        assert captured["payload"] == {
            "displayName": "Sales Ontology", "description": "Sales domain"}

    def test_create_uploads_definition_parts(self, runner, tmp_path):
        (tmp_path / "ontology.json").write_text('{"entityTypes": []}', encoding="utf-8")
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["payload"] = payload
            return {"id": "o-new"}

        with _token(), patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "--json", "fabric", "ontology", "create", "--workspace", "ws-1",
                "--name", "O", "--definition", str(tmp_path)])
        assert result.exit_code == 0, result.output
        parts = captured["payload"]["definition"]["parts"]
        assert parts[0]["path"] == "ontology.json"
        assert base64.b64decode(parts[0]["payload"]).decode() == '{"entityTypes": []}'


class TestOntologyUpdateDelete:
    def test_update_posts_update_definition(self, runner, tmp_path):
        (tmp_path / "ontology.json").write_text("{}", encoding="utf-8")
        captured = {}

        def fake_post(url, token, payload=None, **kw):
            captured["url"] = url
            return {"status": "Succeeded"}

        with _token(), patch("pbi_cli.fabric_api.post", side_effect=fake_post):
            result = runner.invoke(cli, [
                "fabric", "ontology", "update", "--workspace", "ws-1",
                "--ontology", "o1", "--definition", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "/ontologies/o1/updateDefinition" in captured["url"]

    def test_delete_requires_confirmation(self, runner):
        with _token(), patch("pbi_cli.fabric_api.delete") as mock_delete:
            result = runner.invoke(cli, [
                "fabric", "ontology", "delete", "--workspace", "ws-1",
                "--ontology", "o1"], input="n\n")
        assert result.exit_code != 0
        mock_delete.assert_not_called()

    def test_delete_with_yes(self, runner):
        captured = {}

        def fake_delete(url, token, **kw):
            captured["url"] = url
            return {}

        with _token(), patch("pbi_cli.fabric_api.delete", side_effect=fake_delete):
            result = runner.invoke(cli, [
                "fabric", "ontology", "delete", "--workspace", "ws-1",
                "--ontology", "o1", "--yes"])
        assert result.exit_code == 0, result.output
        assert captured["url"].endswith("/workspaces/ws-1/ontologies/o1")
