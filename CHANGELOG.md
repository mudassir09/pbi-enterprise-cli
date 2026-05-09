# Changelog

All notable changes to pbi-cli-tool are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [4.0.0-dev] — 2026-05-09

### Added
- **32 visual types** (up from 16): added KPI, area, stacked bar/column, 100% stacked,
  combo, bubble, filled map, Azure map, decomposition tree, key influencers,
  smart narrative, Q&A
- **REPL mode** (`pbi repl`) — interactive session with tab completion, command history
  persisted to `~/.pbi-cli/repl_history`, and persistent backend connection
- **Custom visual SDK** (`pbi custom-visual scaffold/build/package/import`) — full
  TypeScript project scaffolding, `tsc --noEmit` type-checking, `.pbiviz` packaging,
  and report import
- **Query tracing** (`pbi trace start/stop/fetch/export`) — capture DAX execution events
- **Benchmarking** (`pbi benchmark`) — run a DAX expression N times and report avg/min/max/P95
- **Connection profiles** (`pbi connections list/last/add/remove/use`) — named connections
  persisted to `~/.pbi-cli/connections.json`
- **Skills management** (`pbi skills install/list/uninstall`) — install Claude Code skills
  from the bundled `skills/` directory into `~/.claude/skills/`; 24 skills available
- **Calendar generation** (`pbi calendar generate`) — DAX CALENDAR calculated table with
  fiscal year, weekends, relative month/year columns
- **Culture/locale** (`pbi culture set/show`) — model locale configuration
- **TMDL diff** (`database diff-tmdl`) — compare live model against a snapshot directory
- **Bookmark management** — added `bookmark-get` and `bookmark-set-visibility` commands
- **Model stats** (`pbi model stats`) — row counts, measure count, table count, relationship
  complexity score, and health indicators
- **XMLA backend** — full AMO/ADOMD implementation with MSAL auth (device_flow,
  service_principal, token) and thread-safe connection pooling
- **Governance plugin system** — drop `.py` files in `~/.pbi-cli/rules/` for custom rules
- **REST source profiling** — Bearer/API-key auth, OData pagination, nested JSON,
  type inference
- **AI measure generation** — Claude API integration (`pbi measure generate`)
- **CHANGELOG.md**, **SECURITY.md**, **README.pypi.md** added

### Changed
- Governance `measure-description-required` rule is now `autoFixable: True`
- `measure_update` in `MockTomBackend` handles `new_name` kwarg correctly
- PBIR bookmarks use flat file format (`{id}.bookmark.json`) at schema `2.1.0`
- Conditional formatting uses `backColor`, `FillRule`, `linearGradient3` (correct casing)
- `pyproject.toml` extras: added `[xmla]` and `[ai]` groups; `[all]` includes both

### Fixed
- PBIR bookmark index writes `items` not `bookmarkOrder`
- `explorationState.version` set to `"1.3"` (was `"0.0"`)
- Conditional formatting deduplication no longer leaves stale entries
- `_url_to_table_name` returns `SalesData` (proper PascalCase) not `Salesdata`
- `_extract_records({}, None)` returns `[]` not `[{}]`

---

## [3.0.0] — 2025-12-01

### Added
- PBIR GA format backend (`PbirBackend`) — reads/writes `.pbip` project files directly
- Visual builder with 16 chart types and conditional formatting
- Governance engine with 4 built-in rules
- Source profiling for SQL, Excel, CSV

---

## [2.0.0] — 2025-06-01

### Added
- XMLA backend stub
- DAX test suite (YAML fixtures)
- Mock backend for CI testing
- FastAPI REST server (`pbi server`)

---

## [1.0.0] — 2025-01-01

### Added
- Initial release with Desktop (TOM) backend
- `pbi model`, `pbi measure`, `pbi dax` command groups
- Basic governance lint (`pbi model lint`)
