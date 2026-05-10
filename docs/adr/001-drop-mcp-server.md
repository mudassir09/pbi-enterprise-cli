# ADR-001: Drop MCP Server in favour of direct pythonnet interop

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

pbi-cli v1.x used an MCP (Model Context Protocol) server as an intermediary layer between Claude Code and the Power BI TOM API. The MCP server ran as a separate subprocess, and Claude communicated with it over a network socket.

## Decision

Remove the MCP server layer entirely. Connect directly to the .NET TOM DLLs in-process via pythonnet.

## Rationale

- **Latency:** MCP adds a network hop (loopback, but still IPC overhead) and subprocess lifecycle management. Direct pythonnet interop executes TOM operations in sub-millisecond time within the same Python process.
- **Token cost:** Every MCP round-trip carries JSON serialisation overhead. Direct interop keeps the call surface minimal.
- **Complexity:** Maintaining a separate subprocess (start, monitor, restart on crash) is significant operational overhead for what is essentially a library call.
- **Reliability:** Eliminating the subprocess eliminates a class of race conditions around startup ordering and port conflicts.

## Trade-offs

- **Crash isolation is lower.** A .NET CLR crash can take down the Python process. Mitigated by: (a) TOM operations are generally safe and well-tested by Microsoft, (b) pbi-cli takes snapshots before every write operation so state can be recovered.
- **Windows-only constraint is locked in.** The MCP approach could theoretically run on a remote Windows host from a non-Windows client. Direct pythonnet requires Windows. Mitigated by: XMLA backend (ADR-004) removes the Windows constraint for CI/CD use cases.

## Consequences

- `src/pbi_cli/backends/tom_backend.py` connects via pythonnet directly.
- No subprocess management code anywhere in the codebase.
- The `pbi-server` (ADR-006) restores remote-access capability without the MCP complexity.
