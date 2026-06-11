# pbi-enterprise-cli — Capability Roadmap Recommendations

**Date:** 2026-06-11
**Goal:** identify every area that can be implemented to make this the most powerful tool for Power BI and Microsoft Fabric users.

> **Implementation status (2026-06-11):** the recommendations below have been implemented.
>
> - ✅ **§1 Fabric depth** — `pbi fabric item/workspace/git/pipeline/onelake/capacity/job/directlake` (dataflows run through the job scheduler)
> - ✅ **§2 Cross-platform** — `file` backend (TMDL/PBIP) + `rest` backend (executeQueries); pure-Python XMLA client remains future work
> - ✅ **§3 Performance** — Direct Lake diagnostics (`fabric directlake`); VertiPaq/benchmark harness still ride on existing `pbi trace`/`benchmark`
> - ✅ **§4 DAX tooling** — `dax format`, `dax lint`, `dax coverage` (impact analysis already existed as `model impact`)
> - ✅ **§5 Power Query** — `pbi pquery list/get/folding-check/lint`
> - ✅ **§6 Report intelligence** — `report lint/field-usage/diff/a11y`; visual screenshot regression remains future work (needs `[viz]` + a renderer)
> - ✅ **§7 Testing** — `pbi test data/schema/rls/seed`
> - ✅ **§8 Governance/tenant** — SARIF + PR comments, `govern scan` (Scanner API), `govern explain`, `pbi tenant usage/access/stale/labels`; endorsement automation is blocked on a public API
> - ✅ **§9 CI/CD** — `action.yml` GitHub Action, `.pre-commit-hooks.yaml`, `pbi init`, `pbi diff` (+ `--git`, release notes), `env drift`
> - ✅ **§10 AI & agents** — `pbi mcp serve` (outward-facing MCP), `pbi ask`, `govern explain`, `pbi introspect --format llms`
> - ✅ **§11 DX** — `pbi init`, completions (already shipped), introspection; TUI/VS Code extension remain future work
> - ✅ **§12 Migration** — `migrate direct-lake/pbix-extract/dbt`; full AAS migration guide remains future work
> - ✅ **§13 Ops** — `pbi ops refresh/refresh-chain/health` with Teams/Slack webhooks
> - ✅ **§14 Docs** — `docs erd` (Mermaid), `docs site` (MkDocs)

This document is grounded in the current codebase (v1.0.2 + unreleased `pbi fabric`, `pbi govern plugins`, `--yaml`). Each section states what exists today, what's missing, and a sketch of the command surface. A prioritised matrix and suggested release sequencing are at the end.

---

## 1. Fabric Platform Depth — from "datasets" to the whole platform

**Today:** `pbi fabric` covers `workspaces`, `capacities`, `datasets`, `refresh`, `lineage` — read-mostly, semantic-model-centric.

Fabric is now lakehouses, warehouses, pipelines, notebooks, and OneLake. The CLI that manages *all* Fabric items from one terminal has no real competitor today.

| Recommendation | Sketch |
|---|---|
| **Fabric item CRUD via the Item Definition API** — create/get/update any Fabric item (semantic models, reports, notebooks, pipelines) as base64 definition parts. This is the single most strategic feature: it enables deploying models and reports **from Linux/macOS with no XMLA and no Windows** | `pbi fabric item list/get/create/update --type SemanticModel` |
| **Workspace management** — create workspaces, assign capacity, manage role assignments | `pbi fabric workspace create/assign-capacity/users add` |
| **Fabric Git integration API** — connect a workspace to a repo, get status, commit workspace → git, update git → workspace | `pbi fabric git status/commit/update` |
| **Fabric deployment pipelines API** — list pipelines, deploy stage→stage with deployment rules (today `pbi deploy` is XMLA-only) | `pbi fabric pipeline deploy --from Dev --to Test` |
| **OneLake operations** — list/upload/download files, manage shortcuts (ADLS-compatible API) | `pbi onelake ls/cp/shortcut add` |
| **Capacity operations** — pause/resume/scale (Azure ARM API), CU consumption summary from Capacity Metrics | `pbi fabric capacity pause/resume/scale/usage` |
| **Job scheduler API** — run/schedule/monitor item jobs (pipeline runs, notebook runs, refreshes) uniformly | `pbi fabric job run/status/cancel` |
| **Dataflows Gen2** — export/import mashup definitions, trigger refresh | `pbi fabric dataflow export/refresh` |

## 2. Cross-Platform Live Connectivity — kill the Windows constraint

**Today:** `desktop` and `xmla` backends require Windows (pythonnet + bundled AMO DLLs). Linux/macOS users only get `mock`.

This is the #1 adoption ceiling. Two complementary paths, neither requiring .NET:

- **REST execute-queries backend** — the Power BI `executeQueries` REST endpoint runs DAX against any published dataset from any OS. A fourth backend (`rest`) would light up `pbi dax query`, `pbi dax test`, `pbi measure list` (via INFO functions), and read-only governance against live Fabric models on `ubuntu-latest` — i.e. **live BPA in CI without Windows**.
- **TMDL/PBIP file backend** — parse the `.pbip` / TMDL folder directly (pure Python, no Desktop). Governance, BPA, lint, docs, and diff run against the files in the repo — exactly what CI wants, with no live connection at all. The mock backend already proves the interface; this makes it real.
- Longer term: a **pure-Python XMLA client** (XMLA-over-HTTP is SOAP/XML) for full read/write from any OS — large effort, huge payoff.

## 3. Performance & Optimization Tooling

**Today:** `pbi trace` (start/stop/fetch/export/clear) and the `power-bi-performance` skill.

| Recommendation | Why |
|---|---|
| **VertiPaq Analyzer equivalent** — DMV-based model size report: per-column cardinality, dictionary/hierarchy size, encoding, % of model size | The single most-used optimization tool in the ecosystem; trivially scriptable: `pbi analyze vertipaq --top 20` |
| **DAX benchmark harness** — run a query N times, warm/cold cache, FE/SE breakdown, compare two model versions | `pbi dax bench --query q.dax --baseline main` — enables perf regression gates in CI |
| **Performance regression CI gate** — store baseline timings as JSON, fail PR if a measure regresses > X% | Natural extension of snapshots + trace |
| **Refresh analysis** — parse refresh history (REST), longest partitions, failure patterns | `pbi partition analyze` |
| **Aggregation advisor** — suggest aggregation tables from trace data (most-hit column groups) | High-end differentiator |
| **Direct Lake diagnostics** — framing status, fallback-to-DirectQuery detection and *why*, reframe command | Direct Lake is the Fabric default; nobody has good CLI tooling for it |

## 4. DAX Developer Tooling

**Today:** `pbi dax query/validate/test` (YAML suites), AI measure generation, measure audit.

| Recommendation | Why |
|---|---|
| **DAX formatter** — `pbi dax format` (daxformatter.com API, plus offline best-effort) | Table-stakes for a DAX toolchain; enables format-check in CI |
| **DAX linter** — static rules: unqualified column refs, `FILTER` over a table where a predicate works, missing `DIVIDE`, iterator misuse | Complements BPA (model-level) with expression-level analysis: `pbi dax lint` |
| **Measure dependency graph & impact analysis** — "what breaks if I rename/delete column X" across measures, calc columns, RLS, and (with PBIR parsing) report visuals | `pbi model impact --column 'Sales[Amount]'` — enterprise teams ask for this constantly |
| **Calculation group support** — list/add/edit calculation groups and items | Gap in the current model surface |
| **Field parameters support** — scaffold field parameter tables | Common modern pattern, fiddly by hand |
| **DAX test coverage report** — which measures have YAML tests, which don't | `pbi dax test --coverage` rounds out the testing story |
| **NL→DAX query** — `pbi ask "top 10 customers by sales"` translating to an EVALUATE and showing results | Showcases the AI extra beyond measure generation |

## 5. Power Query / M Layer

**Today:** source profiling → star-schema scaffold; the `power-bi-power-query` skill exists, but no `pbi pquery` commands.

- **M query list/export/import** — round-trip M expressions from the model/TMDL: `pbi pquery list/get/set`.
- **Query folding analyzer** — static detection of folding-breaking steps (e.g. `Table.AddIndexColumn` before a filter); the most common silent performance killer.
- **M linter/formatter** — naming, hardcoded credentials/paths detection (also a governance rule).
- **Source migration assist** — rewrite source steps (SQL Server → Fabric Lakehouse/Warehouse) with a dry-run diff; pairs with the Import → Direct Lake migration in §12.

## 6. Report-Layer Intelligence (PBIR)

**Today:** strong authoring (`report`, `visual`, `layout`, `theme`, `filter`), but little *analysis* of existing reports.

| Recommendation | Why |
|---|---|
| **Report linter** — too many visuals per page, hidden visuals, unused bookmarks, missing alt text, inconsistent fonts/themes | `pbi report lint` mirrors `govern check` for the report layer |
| **Field usage analysis** — cross-reference PBIR visuals with the model: which columns/measures are used by *no* visual → safe-to-remove list | Closes the loop between model governance and reports; the killer feature of third-party tools like Measure Killer |
| **Report semantic diff** — human-readable visual-level diff between two PBIR versions ("Page 'Sales': visual X moved, measure Y swapped") | PR reviews of report changes are unreadable JSON today |
| **Visual regression testing** — render pages (Playwright is already in the `viz` extra) and compare screenshots against baselines | `pbi report snapshot --pages all`; unique CI capability |
| **Accessibility audit** — tab order, alt text, WCAG contrast against the applied theme (extends existing theme validation) | `pbi report a11y` |
| **Cross-report theme rollout** — apply/validate a corporate theme across many reports at once | Enterprise design-system enforcement |

## 7. Testing Expansion — toward "dbt for Power BI"

**Today:** DAX YAML unit tests, snapshot/rollback, mock backend.

- **Data quality tests** — declarative YAML: row counts, null checks, uniqueness, referential integrity (orphaned fact keys), accepted values — executed as generated DAX. `pbi test data --suite tests/data/`.
- **Schema contract tests** — assert tables/columns/types exist with expected properties; fail CI on accidental breaking changes. `pbi test schema --contract schema.yml`.
- **RLS test matrix** — declare personas × expected row counts in YAML, execute via XMLA `EffectiveUserName`/role impersonation. Extends `pbi security test` into CI.
- **Synthetic data generation** — generate realistic mock data from the schema so the mock backend (and demos) have meaningful rows: `pbi mock seed`.
- **Cross-version test runs** — run the same suite against dev and prod connections and diff results (catches environment drift in numbers, not just metadata).

## 8. Governance, Compliance & Tenant Administration

**Today:** rule engine + BPA + plugin marketplace + auto-fix — best-in-class for one model. The next tier is *tenant-wide*.

| Recommendation | Why |
|---|---|
| **Scanner API integration** — tenant/workspace-wide metadata scan; run governance rules across *every* dataset in the org, output a fleet report | Turns the tool from per-model to organization-grade: `pbi govern scan --all-workspaces` |
| **Activity events / usage metrics** — pull the Activity Log: unused reports, stale datasets (no refresh/views in N days), top users | `pbi audit usage --days 90`; feeds "delete candidates" reports |
| **Sensitivity labels** — read/apply MIP labels via API | Compliance teams require it |
| **Endorsement automation** — certify/promote datasets that pass the governance gate | Connects CI quality to catalog trust: `pbi govern endorse --on-pass` |
| **Access review** — who has access to what, flag external users, export for audits | `pbi security access-report` |
| **SARIF output for `govern check`** — violations appear natively in the GitHub code-scanning / PR annotations UI | Cheap, high-visibility CI win |
| **Rule pack ecosystem** — versioned, signed community rule packs; org-internal registries (the `plugins search/install` scaffolding already exists) | Network effects |

## 9. CI/CD & DevOps Ecosystem

**Today:** great YAML examples in the README; users still hand-roll workflows.

- **Official GitHub Action** (`mudassir09/pbi-govern-action@v1`) and **Azure DevOps extension** — wraps install + govern + BPA + DAX tests + artifact upload. Marketplace presence is also a discovery channel.
- **PR comment bot mode** — `pbi govern check --comment-pr` posts a formatted summary (violations, model diff, test results) on the PR via `GITHUB_TOKEN`.
- **`pbi init`** — scaffold a complete project: `.pbip` layout, `tests/measures/`, `pbi.config.toml`, governance config, GitHub workflow, pre-commit config. Time-to-first-value for new repos.
- **pre-commit hooks** — publish a `.pre-commit-hooks.yaml` (govern, dax lint/format, report lint on changed files).
- **TMDL semantic diff for PRs** — `pbi diff --git main` producing "Measure [Total Sales] expression changed; Column [Date] deleted" instead of raw text diffs; also feeds release-notes generation (`pbi docs changelog`).
- **Drift detection** — compare git TMDL vs the published workspace; fail or auto-open an issue when someone edited prod directly. `pbi env drift --connection prod`.
- **Deployment rules** — declarative per-environment parameter/connection-string rewrites applied during `deploy push` (parity with Microsoft deployment pipelines, but git-driven).

## 10. AI & Agent Integration

**Today:** AI measure generation, theme/layout/visual-recommender intelligence modules, 10 Claude Code skills.

- **Broaden AI verbs:** model documentation drafting (`pbi docs generate --ai`), star-schema design proposals from `pbi source profile` output, AI explanations of BPA violations with suggested fixes (`pbi govern explain`), DAX→English and English→DAX, report page generation from a prompt (the intelligence modules are already in place to compose this).
- **Reconsider an MCP server — for *other* agents.** ADR-001 dropped MCP as an internal transport, which was right. But an *outward-facing* MCP server (`pbi mcp serve`) is a different proposition: it makes every CLI capability available to Cursor, VS Code Copilot, Windsurf, and any MCP client — not just Claude Code skill users. The existing FastAPI server shares most of the plumbing. This is likely the single biggest reach-multiplier available.
- **Agent-friendly output contract** — `--json` everywhere is already strong; add stable schemas (publish JSON Schema files), an `llms.txt`/`pbi --agent-help` machine-readable command map, and idempotent/dry-run guarantees documented per command.
- **Skill auto-update channel** — `pbi skills update` pulling the latest skill versions matched to the CLI version (the `min_cli_version` check already exists).

## 11. Developer Experience

- **Shell completions** — bash/zsh/PowerShell via Click's native support: `pbi completions install`. Cheap, expected.
- **TUI explorer** — a Textual-based `pbi ui`: browse tables/measures/relationships, run DAX with results grid, view governance status. The REPL (`repl.py`) is the seed.
- **DAX REPL mode** — multi-line editing, history, table-formatted EVALUATE results inside `pbi repl`.
- **Better errors with playbooks** — error codes linking to a docs page per failure mode (`pbi doctor` already has the diagnostic data).
- **`pbi.config.toml` first-class** — per-repo defaults (backend, connection, fail-on level, rule excludes); the example file exists but configuration precedence should be documented and complete.
- **VS Code extension (thin)** — surface govern/test/diff results in the Problems panel by shelling out to the CLI; the SARIF output from §8 makes this nearly free.

## 12. Migration & Interoperability

- **PBIX read-only extraction** — parse `.pbix` (DataModel via offline analysis, layout JSON) so legacy reports can be inventoried, linted, and converted to PBIP: `pbi convert pbix-to-pbip`.
- **Import → Direct Lake migration advisor** — analyze an Import model and report blockers (calc columns, unsupported types), generate the Direct Lake variant: `pbi migrate direct-lake --analyze`.
- **AAS → Fabric migration** — Azure Analysis Services models are TOM-compatible; a guided `pbi migrate aas` is a timely enterprise magnet (AAS retirement pressure).
- **Tabular Editor interop** — already reads BPA rule files; add C# script → governance-plugin conversion notes and TE3 folder-format compatibility for TMDL.
- **dbt interop** — read dbt `manifest.json` to map lakehouse tables → semantic model lineage; generate semantic model scaffolds from dbt models/exposures.

## 13. Operations & Monitoring

- **Refresh orchestration** — `pbi fabric refresh` exists; add wait/poll with timeout, retry policy, and chained refreshes (dataflow → dataset) with failure short-circuit: `pbi ops refresh-chain plan.yml`.
- **Notifications** — Teams/Slack webhooks on refresh failure, governance regression, drift detection: `--notify teams:<url>`.
- **Scheduled health checks** — `pbi ops monitor` as a daemon or cron-friendly one-shot: capacity throttling, gateway status, failed refreshes since last run; pairs with the `server` extra for a `/health` dashboard.
- **Audit log persistence** — append-only JSONL of every write operation the CLI performs (who/when/what/before-after), exportable for SOC compliance.

## 14. Documentation & Lineage Outputs

**Today:** markdown/Confluence data dictionary, lineage, audit log.

- **Model ERD generation** — relationships → Mermaid/SVG diagram embedded in docs output: `pbi docs erd`.
- **Static docs site** — `pbi docs site` generating a browsable MkDocs site (dictionary + ERD + measure catalog with formatted DAX + test coverage), publishable to GitHub Pages from CI.
- **Column-level lineage** — source query → table/column → measure → (with §6 field usage) report visual. End-to-end lineage is something even Microsoft doesn't surface in one view.
- **More export targets** — SharePoint pages, Notion, static HTML; plus `docs diff` to show documentation drift in PRs.

---

## Priority Matrix

| # | Recommendation | Impact | Effort | Tier |
|---|---|---|---|---|
| 2 | TMDL/PBIP file backend (live-file governance, no Windows) | Very high | Medium | **Now** |
| 1 | Fabric Item Definition API (deploy from any OS) | Very high | Medium | **Now** |
| 2 | REST execute-queries backend | High | Low-Med | **Now** |
| 9 | Official GitHub Action + PR comment bot + SARIF | High | Low | **Now** |
| 4 | DAX formatter + linter | High | Low-Med | **Now** |
| 3 | VertiPaq analyzer | High | Low-Med | **Now** |
| 11 | Shell completions, `pbi init` | Medium | Low | **Now** |
| 10 | Outward-facing MCP server | Very high | Medium | **Next** |
| 6 | Field usage analysis + report linter | High | Medium | **Next** |
| 4 | Impact analysis / dependency graph | High | Medium | **Next** |
| 7 | Data quality + schema contract tests | High | Medium | **Next** |
| 1 | Fabric git integration + deployment pipelines API | High | Medium | **Next** |
| 8 | Scanner API tenant-wide governance | Very high | High | **Next** |
| 9 | TMDL semantic diff + drift detection | High | Medium | **Next** |
| 3 | Direct Lake diagnostics | High | Medium | **Next** |
| 6 | Visual regression testing | Medium | High | Later |
| 12 | PBIX extraction, AAS/Direct Lake migration | High | High | Later |
| 2 | Pure-Python XMLA client | Very high | Very high | Later |
| 11 | TUI explorer, VS Code extension | Medium | High | Later |
| 13 | Ops monitoring + notifications | Medium | Medium | Later |
| 5 | Query folding analyzer, M tooling | Medium | Medium | Later |
| 14 | Docs site + ERD | Medium | Low-Med | Later |

## Suggested Release Sequencing

- **v1.1 (in flight):** `pbi fabric` basics, plugin marketplace, `--yaml` — already in the Unreleased changelog.
- **v1.2 — "CI anywhere":** TMDL file backend, REST execute-queries backend, SARIF output, GitHub Action, DAX format/lint, `pbi init`, completions. *Theme: every core workflow works on Linux against real artifacts.*
- **v1.3 — "Fabric native":** Item Definition CRUD, workspace management, git integration, deployment pipelines, OneLake basics, Direct Lake diagnostics. *Theme: full Fabric lifecycle from the terminal.*
- **v1.4 — "Analysis & trust":** VertiPaq analyzer, impact analysis, field usage, report linter, data/schema/RLS test suites, semantic diff + drift. *Theme: the quality platform.*
- **v2.0 — "Org scale + agents":** MCP server, Scanner API fleet governance, usage analytics, endorsement automation, docs site. *Theme: tenant-wide, agent-first.*

### Strategic throughline

The moat is the combination no one else has: **git-native artifacts (TMDL/PBIR) + live connectivity (XMLA/REST/Fabric API) + a governance engine + an AI/agent surface, in one installable tool.** Every tier above deepens at least two of those four pillars. The two highest-leverage single moves are (1) the file/REST backends that remove the Windows ceiling, and (2) the MCP server that makes every existing command available to every AI agent, not only Claude Code.
