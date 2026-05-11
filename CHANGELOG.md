# Changelog

All notable changes to pbi-enterprise-cli are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0.dev1] — 2026-05-11

### Added
- **BPA (Best Practice Analyzer) compatibility** (`pbi govern bpa check`) — run the Microsoft
  community BPA rule set (or any local `BPARules.json`) without .NET tooling. Supports
  `--file`, `--url`, `--severity`, and `--category` filters. First Python-native BPA runner.
- **AMO DLLs bundled in wheel** — `Microsoft.AnalysisServices.*.dll` now shipped inside the
  package under `pbi_cli/dlls/`; the `desktop` backend works immediately after `pip install`
  on Windows without a separate Desktop installation.

### Fixed
- `pbi doctor` no longer crashes on Linux/macOS — `import clr` raises `RuntimeError` (not
  just `ImportError`) when Mono is absent; both exception types now caught gracefully.
- `PyYAML` added to core dependencies — `pbi dax test --suite` no longer fails with
  `ModuleNotFoundError: No module named 'yaml'` on a base install.
- Coverage gate adjusted to 65% (platform-specific files `tom_backend.py` and `server/api.py`
  excluded from measurement).

---

## [0.1.0-dev] — 2026-05-10

> First public release. Prior development (v1–v3) was internal only.

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

