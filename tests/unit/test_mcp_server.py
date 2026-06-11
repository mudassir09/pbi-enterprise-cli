"""Tests for the MCP server, ask, and introspect commands."""

from __future__ import annotations

import io
import json

import pytest
from click.testing import CliRunner

from pbi_cli.backends.mock_backend import MockTomBackend
from pbi_cli.cli import cli
from pbi_cli.mcp_server import TOOLS, McpServer


@pytest.fixture()
def server():
    backend = MockTomBackend()
    backend.connect()
    return McpServer(backend)


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


class TestMcpProtocol:
    def test_initialize(self, server):
        resp = server.handle(_rpc("initialize"))
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "pbi-enterprise-cli"

    def test_tools_list(self, server):
        resp = server.handle(_rpc("tools/list"))
        names = {t["name"] for t in resp["result"]["tools"]}
        assert {"list_tables", "run_dax", "govern_check", "add_measure"} <= names

    def test_tools_call_list_tables(self, server):
        resp = server.handle(_rpc("tools/call", {"name": "list_tables", "arguments": {}}))
        assert resp["result"]["isError"] is False
        tables = json.loads(resp["result"]["content"][0]["text"])
        assert {"name": "Sales", "isHidden": False} in tables

    def test_tools_call_add_measure_writes(self, server):
        server.handle(_rpc("tools/call", {
            "name": "add_measure",
            "arguments": {"table": "Sales", "name": "M1", "expression": "1"}}))
        assert any(m["name"] == "M1" for m in server._backend.measure_list())

    def test_tools_call_unknown_is_error(self, server):
        resp = server.handle(_rpc("tools/call", {"name": "nope", "arguments": {}}))
        assert resp["result"]["isError"] is True

    def test_unknown_method_error(self, server):
        resp = server.handle(_rpc("bogus/method"))
        assert resp["error"]["code"] == -32601

    def test_notification_returns_none(self, server):
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        assert server.handle(note) is None

    def test_serve_loop_round_trip(self, server):
        stdin = io.StringIO(json.dumps(_rpc("tools/list")) + "\n")
        stdout = io.StringIO()
        server.serve_forever(stdin=stdin, stdout=stdout)
        resp = json.loads(stdout.getvalue())
        assert len(resp["result"]["tools"]) == len(TOOLS)


class TestCli:
    def test_mcp_tools_listing(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "mcp", "tools"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(t["tool"] == "run_dax" for t in data)

    def test_introspect_json(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["introspect"])
        assert result.exit_code == 0
        entries = json.loads(result.output)
        commands = {e["command"] for e in entries}
        assert "pbi govern check" in commands
        assert "pbi fabric item create" in commands
        assert "pbi test data" in commands

    def test_introspect_llms(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["introspect", "--format", "llms"])
        assert result.exit_code == 0
        assert result.output.startswith("# pbi-enterprise-cli")
        assert "`pbi dax lint`" in result.output

    def test_ask_requires_ai_extra_or_key(self, monkeypatch):
        # Without a key the anthropic client raises; with no extra it's a clean error.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["--backend", "mock", "ask", "total revenue"])
        assert result.exit_code != 0
