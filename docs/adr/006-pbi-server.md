# ADR-006: Expose pbi-cli commands as a local FastAPI REST server

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

GitHub Actions, Azure DevOps, and other pipeline tools call external processes via subprocess or HTTP. While subprocess works, it has overhead per call and no streaming support. Additionally, future browser extension and VS Code extension integrations need an HTTP API, not a CLI subprocess.

## Decision

Expose all pbi-cli commands as REST endpoints via a local FastAPI server: `pbi server start --port 7788`.

## Rationale

- **Pipeline integration without subprocess overhead:** GitHub Actions can call `http://localhost:7788/model/tables` rather than spawning a new Python process per command. This is especially significant for bulk operations.
- **Browser and editor extension surface:** A local HTTP server is the standard integration point for VS Code extensions, browser DevTools extensions, and similar tooling.
- **Same backend, different transport:** The server is a thin routing layer over the same command implementations. No logic duplication.
- **Restores remote-access use case from MCP (ADR-001):** Without the complexity of MCP protocol maintenance.

## Trade-offs

- **Security surface:** A listening HTTP server is a new attack surface. Mitigated by: (a) default bind to `127.0.0.1` (loopback only), (b) optional API key authentication, (c) documented that production use should bind behind a reverse proxy with auth.
- **Process lifecycle:** The server must be started before pipeline steps that use it. Documented in the GitHub Action integration guide.
- **Optional dependency:** FastAPI and uvicorn are not in the base install (see ADR-005 pattern). Requires `pip install pbi-cli-tool[server]`.

## Consequences

- `src/pbi_cli/server/api.py` is the FastAPI application.
- `src/pbi_cli/server/routes/` contains one router file per command group.
- `pbi server start` command launches uvicorn with the FastAPI app.
- Default port: 7788. Configurable via `--port` flag or `PBI_SERVER_PORT` environment variable.
- `pbi-cli-tool[server]` optional extra: `fastapi>=0.110, uvicorn>=0.29`.
- Targets v6.0 release alongside the XMLA backend.
