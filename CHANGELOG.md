# Changelog

All notable changes to pbi-enterprise-cli are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added — `pbi lakehouse`: first-class Lakehouse table operations
- `pbi lakehouse list` — list lakehouses in a workspace.
- `pbi lakehouse tables` — list Delta tables (handles the `data`-keyed, paged response).
- `pbi lakehouse load` — load a OneLake file/folder into a Delta table (loadTable LRO),
  with `--format Csv|Parquet`, `--mode Overwrite|Append`, folder/recursive loads, `--wait`.
- `pbi lakehouse maintenance` — run table maintenance via the job scheduler:
  OPTIMIZE + V-Order (`--z-order col,col`) and/or VACUUM (`--vacuum-retention`), `--wait`.

### Added — `pbi notebook`: run notebooks + round-trip .ipynb
- `pbi notebook run` — run a notebook on demand with typed `--param name=value`
  (int/float/bool/string inferred), optional `--wait` for final status.
- `pbi notebook status` — get a run's status by job-instance id.
- `pbi notebook export` / `import` — export a notebook to a local `.ipynb`, or create
  a notebook in a workspace from an `.ipynb` file (validated as JSON first).
- New `fabric_api.run_item_job()` helper extracts the job-instance id from the LRO
  `Location` header and optionally polls to a terminal state — shared by lakehouse
  maintenance and notebook runs (and an improvement over the bare-202 `fabric job run`).

### Added — `pbi sql query`: T-SQL against Fabric Warehouse / Lakehouse SQL endpoints
- The data-engineering counterpart to `pbi dax query`. Run T-SQL against a Fabric
  Warehouse or Lakehouse SQL analytics endpoint, the first first-class DE primitive:
  - `pbi sql query --workspace <ws> --item <wh> "SELECT TOP 10 * FROM dbo.Sales"`
    discovers the server FQDN from the Fabric item via REST.
  - `pbi sql query --server <fqdn> --database <db> --file report.sql` connects directly.
  - `--json`/`--yaml` output, `--dry-run`, and AAD-token auth via the existing
    `fabric_api` ladder (env token / service principal / device flow).
- New `sql_endpoint.py` (endpoint discovery is pure REST and unit-tested; the TDS
  query runs over pyodbc). New `[sql]` extra (`pyodbc`); requires a Microsoft ODBC
  driver, with an actionable error if either is missing.

### Added — MCP server full-CLI parity
- `pbi mcp serve` now exposes two tools that cover the **entire** CLI, not just the
  10 curated tools: `list_commands` (machine-readable map of every command) and
  `run_cli` (invoke any `pbi` command and get exit code + output). The server's
  `--backend`/`--path` are propagated to passthrough invocations. Agents can now
  deploy, test, govern-fix, run Fabric ops, and run T-SQL through MCP.

### Added — `fabric_api` contract tests
- Recorded-response tests for the shared REST client (paging, LRO polling, error
  mapping, auth resolution) — the plumbing every `pbi fabric`/`tenant`/`ops`
  command depends on, previously live-only and untested.

### Added — VertiPaq statistics for runtime BPA rules
- `pbi govern bpa check --vertipaq` collects runtime statistics from a **live**
  model (desktop/xmla) and feeds them to the evaluator so the BPA rules that read
  `GetAnnotation(...)` evaluate instead of skipping:
  - `Vertipaq_RowCount` (table) — large-table-should-be-partitioned
  - `DateTimeWithHourMinSec` (column) — split date and time
  - `LongLengthRowCount` (column) — long-length high-cardinality columns
  - `Vertipaq_Cardinality` (column) — bidirectional-vs-high-cardinality
  - `Vertipaq_RIViolationInvalidRows` (relationship) — referential-integrity
- New `governance/vertipaq.py` collector: one batched DAX query per table
  (row count + per-column cardinality/scan stats), plus a best-effort RI check
  per relationship; results are returned as annotations keyed by object.
- Evaluator gained `GetAnnotation(...)`, `Convert.ToInt64/ToInt32/ToDouble/
  ToString`, the `char(n)` function, and bare-function-call parsing. Without
  `--vertipaq` (or on a static `file` backend) these rules skip honestly —
  `GetAnnotation` raises rather than guessing.
- Evaluator also gained `string.IsNullOrEmpty`/`IsNullOrWhiteSpace`, collection
  indexing (`Partitions[0]`), enabling the description/format-string/source-column
  and single-partition-name rules.
- Net effect: on a live model the community-ruleset coverage reaches **71 of
  71** (from 5 originally), with no false positives.

### Added — Full BPA community-ruleset coverage
- **Model metadata**: the desktop/xmla and file backends now surface `IsKey`,
  `SortByColumn`, `IsAvailableInMDX`, `DataCategory`, column `Type`, `SourceColumn`,
  `SummarizeBy`, table `ObjectTypeName`, and partition `SourceType`/`Query`/
  `DataSource`. BPA now also sees hidden objects (rules reason about `IsHidden`).
- **Type-aware scoping**: `DataColumn` / `CalculatedColumn` / `CalculatedTableColumn`
  and `Table` / `CalculatedTable` are distinct scopes, so a rule scoped to one
  sub-type no longer fires on the others (eliminated a class of false positives).
- **DAX dependency graph**: a static reference extractor powers `DependsOn`,
  `ReferencedBy`, and `DaxObjectName` — qualified/unqualified column and measure
  reference rules now evaluate.
- **New object-type scopes**: `CalculationGroup`/`CalculationItem`, `ModelRole`
  (members), `Perspective`, `TablePermission`/RowLevelSecurity, and `DataSource`.
- **Evaluator additions**: predicate closures (`current` at top level, `outerit`),
  object identity (`it <> outerit`), collection indexing, `AllMeasures`/`AllColumns`
  filters, `char.*`/`Math.*`/`string.*` statics, `ToCharArray`, `Substring`,
  enum constants, and C#-style `""` quote escapes.
- Integration tests (`tests/integration/test_tom_backend.py`) are now
  model-agnostic — they assert structure rather than a hard-coded "Financial
  Sample" schema, so they pass against any model open in Desktop.
- Note: the desktop/xmla `column_list` excludes hidden columns, so VertiPaq
  column stats are collected only for visible columns; table row counts and RI
  are unaffected.

### Fixed — Packaging (wheel shipped no data files)
- **The wheel previously contained only `.py` files** — no AMO/ADOMD DLLs, no
  skills, no server static UI. On a clean `pip install` this broke the
  `xmla`/`desktop` backends (missing DLLs), `pbi skills install` / `pbi connect`
  (no skills to copy), and `pbi server` (no UI). Added
  `[tool.setuptools.package-data]` declaring `dlls/*.dll`, `skills/**/*.md`, and
  `server/static/*`
- Skills now live inside the package (`src/pbi_cli/skills/`) so they ship in the
  wheel; `_skills_source_dir()` resolves the packaged copy with a repo-root
  fallback for source checkouts
- Added packaging regression tests (`tests/unit/test_packaging.py`)

### Fixed — BPA runner (most rules were silently skipped; unsafe eval)
- **Compound TOM scopes are now honoured.** The Microsoft community ruleset
  scopes rules to type lists like `"DataColumn, CalculatedColumn,
  CalculatedTableColumn"`, which never matched the old exact-name check — so
  ~93% of the community rules were silently skipped. Scope tokens now map to the
  evaluated object families (≈4× more community rules run)
- **Expressions are parsed into an AST and evaluated safely** — the old
  implementation regex-translated rule text and ran `eval()` on it. New module
  `governance/bpa_expr.py`; no `eval`/`exec`
- **LINQ-style collection methods now evaluate** (`Columns.Any(...)`, `.All`,
  `.Where`, `.Count`), plus `RegEx.IsMatch` and string methods — these were
  rejected outright before
- **.NET regex inline flags** (`(?i)` mid-pattern) are relocated to Python
  compile flags instead of erroring, and string-literal backslash sequences
  (`\s`, `\d`, `\t`) are preserved verbatim instead of being mangled by escape
  decoding — both previously corrupted or skipped regex-based rules
- **Enum constants** (`DataType.Int64`, `CrossFilteringBehavior.BothDirections`)
  and `Substring`/`ToString` are now supported
- **Relationship graph + predicate closures.** Columns and tables expose
  `UsedInRelationships`; relationships are navigable (`FromColumn.Name`,
  `ToTable.Name`, `FromCardinality`, `CrossFilteringBehavior`, …); predicates
  resolve the `current`/`it`/`outerit` iteration variables; and every object
  carries a `Model` back-reference (`Model.AllColumns`, `Model.AllMeasures`).
  This lights up the relationship-hygiene rules — foreign-key hiding, integer
  key types, tables-without-relationships, snowflake detection, duplicate
  columns. The `file` backend now also captures `toCardinality` and
  `crossFilteringBehavior`. Net effect on the Microsoft community ruleset
  (sparse `mock` backend): **5 → 36 of 71** rules evaluated vs the original
  implementation. The remainder need runtime VertiPaq statistics, a DAX
  dependency graph, or object types a static reader does not model — and are
  honestly reported as skipped
- **Honest skips** — a rule referencing a property we don't model is reported as
  skipped (with the evaluated/skipped tally) rather than defaulted to empty and
  mis-evaluated. Added `Model` and `Partition` rule scopes
- Docs no longer claim "same ruleset as Tabular Editor" — clarified to the BPA
  *rule format* with a transparent coverage tally

### Added — Fabric IQ & AI readiness
- `pbi fabric ontology` — manage Fabric IQ ontology (preview) items via the
  REST API: list, get (with `--output` definition download), create (with
  `--definition` upload), update, delete
- `pbi govern ai-readiness` — audit a semantic model's readiness for Copilot,
  Q&A, and Fabric IQ ontology generation: measure/column descriptions, hidden
  technical key columns, marked date table, auto date/time tables, Decimal
  columns (unsupported by the Fabric IQ graph), and relationship coverage;
  `--fail-on` for CI gating
- `file` backend now surfaces `dataCategory` on tables (date-table detection)

---

## [1.1.0] — 2026-06-12

The platform release: five backends, the full Fabric REST surface, DAX tooling,
report intelligence, a declarative test platform, tenant administration, an MCP
server for AI agents, and a one-step CI gate. 130+ new tests; coverage 78%.

### Added — Backends (CI anywhere)
- **`file` backend** — reads TMDL/PBIP folders directly (pure Python, any OS):
  governance, BPA, lint, docs, diff, and impact analysis against git artifacts
  with no Desktop, no Windows, no .NET; measure writes persist back to TMDL
- **`rest` backend** — live DAX via the Power BI `executeQueries` REST endpoint
  (any OS): `dax query/test`, metadata via INFO functions, read-only governance
  against published datasets from `ubuntu-latest`
- `--path` global flag — TMDL/PBIP folder for the file backend

### Added — Fabric platform
- `pbi fabric` command group — REST API basics: `workspaces`, `capacities`,
  `datasets`, `refresh`, `lineage` (Bearer token or MSAL device flow auth)
- `pbi fabric item` — full Item Definition API CRUD: list/get/create/update/delete
  any Fabric item; deploy semantic models and reports from any OS, no XMLA
- `pbi fabric workspace` — create, assign-capacity, role assignments
- `pbi fabric git` — workspace git integration: status, commit, update
- `pbi fabric pipeline` — deployment pipelines: list, stages, deploy stage→stage
- `pbi fabric onelake` — ls, download, upload, shortcuts (ADLS DFS API)
- `pbi fabric capacity` — pause/resume/scale via Azure ARM
- `pbi fabric job` — run/status/cancel item jobs (notebooks, pipelines, refreshes)
- `pbi fabric directlake` — partition-mode status and reframe

### Added — DAX tooling
- `pbi dax format` — offline DAX formatter (uppercase functions, long-line style),
  `--check` mode for CI/pre-commit, `--write` to persist
- `pbi dax lint` — static expression rules: DIVIDE, IFERROR, EARLIER, nested IF,
  volatile functions, hardcoded years, qualified measure refs, filter anti-patterns
- `pbi dax coverage` — which measures are covered by YAML test suites

### Added — Governance & tenant administration
- `pbi govern check --sarif/--markdown/--comment-pr` — SARIF 2.1.0 for GitHub code
  scanning, markdown summaries, automatic PR comments
- `pbi govern scan` — tenant-wide governance via the Scanner (admin) API
- `pbi govern explain` — AI explanations of violations with fixes ([ai] extra)
- `pbi tenant` command group — `usage` (activity-log adoption report), `access`
  (workspace access review), `stale` (datasets without recent refresh),
  `labels set/remove` (sensitivity labels, admin information-protection API)

### Added — Report intelligence (PBIR)
- `pbi report lint` — visual density, hidden visuals, alt text, overlap detection
- `pbi report field-usage` — cross-reference model columns/measures vs visuals;
  find unused fields safe to remove
- `pbi report diff` — semantic visual-level diff between two report versions
- `pbi report a11y` — accessibility audit: alt text, titles, tab order

### Added — Testing platform
- `pbi test data` — dbt-style data quality tests compiled to DAX: row counts,
  not-null, uniqueness, accepted values, referential integrity
- `pbi test schema` — schema contract tests (tables/columns/types/measures)
- `pbi test rls` — RLS persona matrix (role × query × expected rows)
- `pbi test seed` — synthetic fixture generation from the model schema

### Added — DevOps
- `pbi init` — project scaffolding: config, test suites, CI workflow, pre-commit
- `pbi diff` — semantic TMDL model diff (paths or `--git` refs), `--release-notes`
- `pbi env drift` — repo TMDL vs live model drift detection, `--fail-on-drift`
- `action.yml` — composite GitHub Action: governance gate on any repo in one step
- `.pre-commit-hooks.yaml` — pbi-govern, pbi-dax-lint, pbi-dax-format hooks

### Added — AI & agents
- `pbi mcp serve` — stdio MCP server: model/DAX/governance tools for Cursor,
  VS Code Copilot, Claude Desktop, and any MCP client (no extra dependency)
- `pbi ask` — natural language → DAX with optional execution ([ai] extra)
- `pbi introspect` — machine-readable command map (JSON or llms.txt format)

### Added — Power Query, ops, migration, docs
- `pbi pquery` — list M queries, static query-folding analysis, M lint
  (hardcoded paths, embedded credentials)
- `pbi ops` — `refresh` (wait + webhook notify), `refresh-chain` (ordered,
  short-circuit), `health` (failed refreshes across a workspace)
- `pbi migrate direct-lake` — Import → Direct Lake blocker analysis
- `pbi migrate pbix-extract` — legacy PBIX layout/metadata extraction
- `pbi migrate dbt` — dbt manifest → table mapping + generated schema contract
- `pbi docs erd` — Mermaid entity-relationship diagram
- `pbi docs site` — MkDocs data-dictionary site generator (formatted DAX included)

### Added — Misc
- `pbi govern plugins` command group — governance plugin marketplace:
  `list` (installed), `search` (community registry), `install` (by name or URL)
- `--yaml` global flag — YAML output alternative to `--json` on all commands
- Tests: 130+ new test cases across 10 new test modules; coverage 78%

### Changed
- Coverage gate raised: 67% → 75% (actual: 78%)
- `--backend` choices extended: `desktop | xmla | mock | file | rest`

[1.1.0]: https://github.com/mudassir09/pbi-enterprise-cli/compare/v1.0.2...v1.1.0

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
