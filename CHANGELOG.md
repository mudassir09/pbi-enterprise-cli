# Changelog

All notable changes to pbi-cli-tool are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [4.0.0-dev] — 2026-05-30 (Enterprise Readiness update)

### Added — W-12 Server Security
- **`pbi server generate-key`** — generates a 64-char cryptographically random API key
- **API key authentication** on all `/api/*` endpoints via `X-PBI-API-Key` header
- **`src/pbi_cli/server/auth.py`** — `verify_api_key`, `generate_key`, `get_configured_key`
- Server refuses to start if `PBI_SERVER_KEY` env var is not set
- Warning printed when binding to non-localhost address

### Added — W-05 Governance CI/CD
- **`--fail-on [error|warning|info]`** flag on `pbi govern check` (default: `error`)
- **Exit code 3** on governance violations (was 1) — matches the exit code contract
- **JSON output envelope** — `{summary: {errors, warnings, infos, total}, violations: [...]}`
- **`.github/workflows/pbi-govern.yml`** — PR governance workflow with PR comment
- **`azure-pipelines-govern.yml`** — Azure DevOps equivalent

### Added — W-10 Skill Versioning
- `version` and `min_cli_version` frontmatter on all 24 SKILL.md files
- **`pbi skills check`** — validates each skill against the installed CLI version; exits 1 on incompatible

### Added — W-07 Multi-Environment
- **`pbi env`** command group: `list`, `use`, `diff`, `promote --confirm`
- **`pbi.config.toml.example`** — project-level environment/governance/deploy config

### Added — W-03 Snapshots & Rollback
- **`pbi snapshot`** command group: `create --label`, `list`, `restore --confirm`, `diff`
- Snapshots stored in `.pbi/snapshots/<timestamp>/` with metadata JSON

### Added — W-01/W-09 Community & Stability
- **`STABILITY.md`** — stable command surface, exit code contract, deprecation policy
- **`MAINTAINERS.md`** — team, support SLAs, release process
- **`.github/ISSUE_TEMPLATE/`** — bug, feature, governance rule, skill contribution templates

### Added — Documentation (W-04/W-08/W-11)
- **`docs/auth/xmla-auth.md`** — service principal, managed identity, interactive; GitHub Actions + Azure DevOps examples
- **`docs/source-profiling.md`** — all source types, classification logic, output format, scaffold
- **`docs/deployment.md`** — snapshot format, diff algorithm, push safety model, rollback, Fabric Git

### Added — 6 New Skills (Skills Gap)
- **`power-bi-advisor`** — master orchestrator, 12-phase build order, licensing guide, 3 worked examples
- **`power-bi-power-query`** — M language, ETL patterns, REST API pagination, incremental refresh
- **`power-bi-visual-selection`** — five data questions framework, visual decision guide, AppSource recommendations
- **`power-bi-fabric`** — OneLake, Medallion architecture, Direct Lake, RTI, KQL, Fabric Pipelines
- **`power-bi-copilot`** — Copilot setup, Q&A synonyms, linguistic schema, Smart Narratives, AI visuals
- **`power-bi-templates`** — Sales, Finance, HR, Operations, Marketing starter templates with measures
- Skills registry expanded from 24 → 30 skills

### Changed
- `pbi govern check` JSON output is now an envelope object (not a bare list) — see W-05
- `pbi govern check` exits 3 on violations (was 1) — see STABILITY.md
- All server API endpoints now require auth (breaking change for unauthenticated callers)
- Test suite updated to match new govern JSON contract and server auth

### Fixed
- Server API tests now correctly pass `X-PBI-API-Key` header
- `pbi skills list` count updated to 30 (was 24)

### Tests
- 25 new tests in `tests/unit/test_new_commands.py`
- 575 total passing (was 550), 26 skipped, 0 failures
- Coverage gate enforced: `--cov-fail-under=70` in `pyproject.toml`

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
