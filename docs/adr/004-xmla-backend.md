# ADR-004: Add XMLA Backend for headless operation

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

The TOM backend (ADR-001) requires a running Power BI Desktop process and Windows. This blocks CI/CD adoption: GitHub Actions and Azure DevOps runners are typically Linux, and even Windows runners cannot run Power BI Desktop without a display.

Power BI Premium and Microsoft Fabric expose an XMLA endpoint that accepts the same AMO/TOM API calls over HTTPS, without requiring Desktop.

## Decision

Implement an `XmlaBackend` class that connects to the Power BI Service or Fabric XMLA endpoint instead of Desktop, while exposing the same command surface as the `TomBackend`.

## Rationale

- **Breaks the Windows-only constraint for CI/CD.** XMLA connections use standard HTTPS, so they work from any OS.
- **~80% code reuse.** The AMO API surface is identical for Desktop and XMLA connections. Only the connection initialisation code differs. All command implementations (`pbi measure add`, `pbi model lint`, etc.) work unchanged.
- **Enables production deploy workflows.** `pbi deploy push` (Epic E) requires XMLA to apply model changes to the Power BI Service.

## Trade-offs

- **Requires Premium or Fabric licence.** XMLA write access requires a Power BI Premium Per User (PPU), Premium Per Capacity (P/EM SKU), or Microsoft Fabric licence. Desktop backend remains the default for non-Premium users.
- **Read operations may have slight latency.** Remote XMLA calls are slower than in-process Desktop connections (~100–500ms vs <1ms). For interactive use this is acceptable; for bulk operations, batching is recommended.
- **Authentication complexity.** XMLA requires Azure AD authentication (service principal or interactive). This adds configuration steps documented in `pbi connect --xmla` help text.

## Consequences

- `src/pbi_cli/backends/xmla_backend.py` implements XMLA connection and all TOM operations.
- `--backend xmla` flag on the CLI selects the XMLA backend.
- `pbi connect --xmla "powerbi://..."` is the primary entry point for XMLA.
- `XMLA_ENDPOINT`, `XMLA_CLIENT_ID`, `XMLA_CLIENT_SECRET` environment variables supported for CI/CD authentication.
- Desktop backend remains default; XMLA backend is opt-in.
- Targets v6.0 release.
