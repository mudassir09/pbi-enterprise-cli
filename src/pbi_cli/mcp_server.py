"""MCP server — expose pbi-enterprise-cli capabilities to any MCP client.

A dependency-free stdio implementation of the Model Context Protocol
(JSON-RPC 2.0 over stdin/stdout, protocol 2024-11-05). Cursor, VS Code
Copilot, Windsurf, Claude Desktop, and any other MCP client can call the
model, DAX, governance, lint, and test surface directly.

Note: ADR-001 removed MCP as an *internal* transport between the CLI and TOM.
This server is the opposite direction — an *outward-facing* integration layer
for third-party agents; the CLI still talks to TOM in-process.
"""

from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"


def _tool(name: str, description: str, properties: dict | None = None,
          required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool("model_info", "Get semantic model name and metadata."),
    _tool("list_tables", "List all tables in the model."),
    _tool("list_columns", "List columns, optionally for one table.",
          {"table": {"type": "string", "description": "Optional table name filter."}}),
    _tool("list_measures", "List all DAX measures with expressions.",
          {"table": {"type": "string", "description": "Optional table name filter."}}),
    _tool("list_relationships", "List model relationships."),
    _tool("run_dax", "Execute a DAX query and return rows (live backends only).",
          {"query": {"type": "string", "description": "A DAX query, e.g. EVALUATE ..."}},
          ["query"]),
    _tool("govern_check", "Run all governance rules; returns violations."),
    _tool("dax_lint", "Run the static DAX linter over all measures."),
    _tool("format_dax", "Format a DAX expression (DAX Formatter conventions).",
          {"expression": {"type": "string"}}, ["expression"]),
    _tool("add_measure", "Add a DAX measure to a table.",
          {"table": {"type": "string"}, "name": {"type": "string"},
           "expression": {"type": "string"},
           "format_string": {"type": "string"}},
          ["table", "name", "expression"]),
    # --- Full-CLI parity: discover and invoke every pbi command, not just the
    #     curated tools above (deploy, test, fabric, sql, tenant, ops, govern fix...).
    _tool("list_commands",
          "List every pbi CLI command with its help and parameters — the complete "
          "capability map. Use this to discover commands, then call run_cli to run them."),
    _tool("run_cli",
          "Run ANY pbi CLI command and return its exit code and output. Pass argv as a "
          "list, e.g. ['govern','check','--fail-on','error'] or ['sql','query','--server',"
          "'x','SELECT 1']. This exposes the full CLI surface beyond the curated tools. "
          "Add '--json' for machine-readable output. The server's --backend/--path are "
          "applied automatically.",
          {"args": {"type": "array", "items": {"type": "string"},
                    "description": "Command-line arguments, excluding the 'pbi' program name."}},
          ["args"]),
]


def _walk_commands(cmd: Any, path: list[str]) -> list[dict[str, Any]]:
    """Flatten the Click command tree into a machine-readable list (for list_commands)."""
    import click

    entries: list[dict[str, Any]] = [{
        "command": " ".join(path),
        "help": (getattr(cmd, "help", None) or getattr(cmd, "short_help", None)
                 or "").strip().split("\n")[0],
        "params": [
            {"name": p.name, "opts": list(getattr(p, "opts", [])),
             "required": bool(getattr(p, "required", False))}
            for p in getattr(cmd, "params", []) if p.name != "help"
        ],
    }]
    if isinstance(cmd, click.Group):
        for name, sub in sorted(cmd.commands.items()):
            entries.extend(_walk_commands(sub, [*path, name]))
    return entries


class McpServer:
    """Stdio JSON-RPC loop dispatching MCP requests to a pbi backend."""

    def __init__(self, backend: Any, cli_prefix: list[str] | None = None) -> None:
        self._backend = backend
        # Global flags (e.g. ["--backend", "file", "--path", "/repo"]) prepended to
        # every run_cli invocation so passthrough commands use the same backend.
        self._cli_prefix = list(cli_prefix or [])

    # --- Tool implementations ---

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        b = self._backend
        if name == "list_commands":
            from pbi_cli.cli import cli as root

            return _walk_commands(root, ["pbi"])
        if name == "run_cli":
            from click.testing import CliRunner

            from pbi_cli.cli import cli as root

            argv = self._cli_prefix + [str(a) for a in (args.get("args") or [])]
            result = CliRunner(mix_stderr=True).invoke(root, argv)
            return {"exit_code": result.exit_code, "output": result.output}
        if name == "model_info":
            return b.model_info()
        if name == "list_tables":
            return b.table_list()
        if name == "list_columns":
            return b.column_list(args.get("table"))
        if name == "list_measures":
            return b.measure_list(args.get("table"))
        if name == "list_relationships":
            return b.relationship_list()
        if name == "run_dax":
            return b.dax_query(args["query"])
        if name == "govern_check":
            from pbi_cli.governance.engine import GovernanceEngine

            return GovernanceEngine(b).run_all()
        if name == "dax_lint":
            from pbi_cli.dax_tools import lint_measures

            return lint_measures(b.measure_list())
        if name == "format_dax":
            from pbi_cli.dax_tools import format_dax

            return {"formatted": format_dax(args["expression"])}
        if name == "add_measure":
            kwargs = {}
            if args.get("format_string"):
                kwargs["formatString"] = args["format_string"]
            return b.measure_add(args["table"], args["name"], args["expression"], **kwargs)
        raise ValueError(f"Unknown tool: {name}")

    # --- JSON-RPC plumbing ---

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method", "")
        request_id = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            result: Any = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pbi-enterprise-cli", "version": _version()},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                payload = self.call_tool(params.get("name", ""), params.get("arguments") or {})
                result = {
                    "content": [{"type": "text",
                                 "text": json.dumps(payload, indent=2, default=str)}],
                    "isError": False,
                }
            except Exception as exc:
                result = {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                }
        elif method == "ping":
            result = {}
        else:
            if request_id is None:
                return None  # unknown notification — ignore
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}

        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def serve_forever(self, stdin: Any = None, stdout: Any = None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.handle(request)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def _version() -> str:
    from pbi_cli import __version__

    return __version__
