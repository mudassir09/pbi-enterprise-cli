# ADR-003: PBIR JSON as a second interaction surface alongside TOM

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

Power BI's TOM (Tabular Object Model) API covers the *semantic model*: tables, columns, measures, relationships, and partitions. It does not cover report-layer objects: pages, visuals, filters, bookmarks, and themes.

Report-layer objects are stored in the PBIR (Power BI Report) JSON format, inside `.pbip` project folders. These are separate files with a completely different schema.

## Decision

Add a `PbirBackend` class that reads and writes PBIR JSON report files directly, independent of the TOM backend.

## Rationale

- **Complete surface:** Without PBIR support, pbi-cli can only manipulate semantic models. The "one-stop-shop" vision (report scaffold, layout engine, theme generation) requires report-layer access.
- **File-based, no COM required:** PBIR is plain JSON. Operations can run without a running Power BI Desktop process, making them cross-platform and testable.
- **Clear separation of concerns:** TOM = semantic model; PBIR = report visuals. Keeping them as separate backends with separate command groups (`pbi model` vs `pbi report`, `pbi visual`, `pbi layout`) prevents API confusion.

## Trade-offs

- **Two backends to maintain.** The TOM and PBIR backends must be kept in sync with Microsoft's evolving formats. PBIR is still a relatively new format (introduced with `.pbip` projects) and Microsoft may make breaking changes.
- **Desktop format dependency.** PBIR JSON is a file format tied to Power BI Desktop's save format. It is not exposed via XMLA. This means report operations always require local file access.
- **No live preview.** Writing PBIR JSON does not immediately refresh the visual in Power BI Desktop (Desktop must reload the file). The `pbi visual screenshot` command (via Playwright) works around this for CI contexts.

## Consequences

- `src/pbi_cli/backends/pbir_backend.py` handles all report JSON operations.
- `pbi report`, `pbi visual`, `pbi layout`, `pbi theme` commands use the PBIR backend.
- PBIR backend is file-based; it requires a `.pbip` folder path, not a network connection.
- Tests for PBIR backend use fixture JSON files (no Power BI Desktop required).
