# Changelog

All notable changes to pbi-enterprise-cli are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.0.2] — 2026-05-31

### Fixed
- `pyyaml>=6.0` promoted from `dev` extra to core dependency — `pbi_cli.commands.dax`
  imports `yaml` at module level, causing `ModuleNotFoundError` on base installs

[1.0.2]: https://github.com/mudassir09/pbi-enterprise-cli/compare/v1.0.1...v1.0.2

---

## [1.0.1] — 2026-05-31

### Fixed
- `pythonnet` constraint reverted to `>=3.0` — pinning to `==3.1.0rc0` (a pre-release)
  blocked `uv tool install` and any resolver that refuses pre-releases by default
- Release smoke-test rewritten to use `pip install` (not `uv tool install`) and target
  the mock backend — avoids .NET dependency on ubuntu-latest CI runners

[1.0.1]: https://github.com/mudassir09/pbi-enterprise-cli/compare/v1.0.0...v1.0.1

---

## [1.0.0] — 2026-05-31

First stable release. Earns the 1.0.0 number: all credibility issues resolved, live CI,
10-skill architecture shipped, visual README, and community infrastructure in place.

### Added
- **Skills: 24 → 10 consolidated** — every original topic preserved and deepened inside
  broader category-based skills; each skill now has command reference, 3+ worked examples,
  edge cases, cross-skill handoffs, and enterprise CI/CD patterns
  - New: `power-bi-report-design` (absorbs report, visuals, pages, layout, page-designer, filters)
  - New: `power-bi-security-and-docs` (absorbs security, docs)
  - Rewritten: modeling, dax, performance, design-system, governance, deployment, diagnostics,
    project-orchestrator
- **`pbi connect` auto-setup** — detects open Desktop session, installs all 10 skills to
  `~/.claude/skills/`, prints Rich model summary (name, tables, measures, port), shows next
  steps; target <60 s time-to-first-value
- **SVG visual assets** — `docs/assets/banner.svg`, `architecture.svg`, `before-after.svg`
- **README overhaul** — banner, differentiators, quickstart, before/after diagram,
  architecture diagram, BPA marketing section, consolidated skills table, CI/CD gate YAML
- **GitHub community files** — structured issue templates (bug, feature, skill idea),
  PR template with skill-change checklist, CODEOWNERS
- **GitHub Discussions** — three seeded threads: Getting started Q&A, Show and tell,
  Feature requests & roadmap

### Changed
- `pyproject.toml` version: `0.1.0.dev2` → `1.0.0`
- Classifier: `3 - Alpha` → `4 - Beta`
- `pythonnet` pinned: `>=3.0` → `==3.1.0rc0`
- Python 3.13 added to CI matrix and classifiers
- `release.yml`: added `workflow_dispatch`, Trusted Publishing (OIDC), post-release smoke-test
- Install docs: uv-first three-tier block (uv → pipx → pip)
- All 10 skill `min_cli_version` set to `0.1.0` (was `4.0.0`)

### Fixed
- Static hardcoded badges (`547 passing`, `65%+`) replaced with live GitHub Actions /
  Codecov / shields.io badges
- `__version__` now matches `pyproject.toml` (was `4.0.0.dev0`)
- Release pipeline previously published `dev0` but not `dev1`/`dev2` — fixed trigger
  and added smoke-test job

### Notes
- Versions 4.0.0 and 4.0.1 were yanked — version history jumps from 0.1.0.dev2 to 1.0.0
- Next release will be 1.1.0 (minor): `pbi connect` XMLA auto-detection, governance plugin
  marketplace, Fabric REST API commands

[1.0.0]: https://github.com/mudassir09/pbi-enterprise-cli/compare/v0.1.0.dev2...v1.0.0

---

## [4.0.1] — 2026-05-30

### Changed
- PyPI metadata: added author, classifiers, project URLs, switched readme to README.pypi.md
- Added keywords: powerbi, pbip, xmla, fabric

## [4.0.0] — 2026-05-30 (Enterprise Readiness release)

### Added — Skills Gap Fill
- **`skills/power-bi-intelligence/`** — AI-driven measure generation, visual recommendation, WCAG theme generation, and layout engine
- **`skills/power-bi-connections/`** — connection string management, environment switching, service principal auth, DirectQuery/Import modes, gateway config
- **`skills/power-bi-trace/`** — DAX query profiling, FE/SE/DQ breakdown, VertiPaq scan analysis, CI performance regression guard
- **`skills/power-bi-watch/`** — file-system watcher, hot-reload to Desktop, governance-on-save, change diffing
- **`skills/power-bi-calendar/`** — calendar table generation (standard + fiscal year), mark-as-date-table, validation against fact tables
- **`skills/power-bi-audit/`** — model snapshots, drift detection diff, orphan measure detection, CI change guard

### Changed — CI/CD Infrastructure
- **Pip caching** added to all workflow jobs (`cache: pip`) — faster installs across lint, test, contract, pbir-format, release
- **Windows CI job** (`windows-test`) added to `ci.yml` — TOM/XMLA backends now tested on `windows-latest` with pythonnet
- **Security scan** (`pip-audit`) added to `ci.yml` as a dedicated `security` job
- **Release workflow** now requires a passing test job (`needs: test`) before publishing to PyPI
- **PyPI publishing** switched from token-based `twine` to OIDC Trusted Publishing (`pypa/gh-action-pypi-publish`) — no long-lived secrets
- **PR check** no longer duplicates the full unit test run (handled by `ci.yml`)
- **`azure-pipelines-govern.yml`** clarified with header comment — purpose vs. GitHub Actions equivalent is now explicit

### Added — Repository Hygiene
- **`.github/dependabot.yml`** — weekly automated dependency updates for both `pip` and `github-actions` ecosystems, grouped by concern
- **`BMAD.md`** — gap analysis and implementation plan document



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
