<div align="center">
  <img src="docs/assets/banner.svg" alt="pbi-enterprise-cli" width="100%"/>
</div>

<div align="center">

[![CI](https://github.com/mudassir09/pbi-enterprise-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/mudassir09/pbi-enterprise-cli/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mudassir09/pbi-enterprise-cli/graph/badge.svg)](https://codecov.io/gh/mudassir09/pbi-enterprise-cli)
[![PyPI](https://img.shields.io/pypi/v/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![Python](https://img.shields.io/pypi/pyversions/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pbi-enterprise-cli)](https://pypi.org/project/pbi-enterprise-cli/)

</div>

---

### Treat Power BI like real software — version it, test it, govern it, ship it.

**`pbi-enterprise-cli` automates Power BI & Microsoft Fabric from the command line — model, govern, test, document, and deploy semantic models and reports, on any OS.**

It brings software-engineering discipline to BI: six backends (including a pure-Python TMDL reader that needs no Windows), the only Python-native BPA governance runner, full Fabric REST coverage, DAX testing + lint + format, PBIR report intelligence, a declarative test platform, an MCP server for AI agents, and 12 Claude Code skills.

**Key differentiators vs alternatives:**

- **Real artifacts on any OS** — the `file` backend reads TMDL/PBIP folders straight from your repo (pure Python, no .NET): governance, BPA, lint, docs, and semantic diff run against *real* models on `ubuntu-latest`
- **Live DAX on any OS** — the `rest` backend runs DAX against any published dataset via the `executeQueries` API; the `xmla` backend gives full read/write on Windows
- **Python-native BPA runner** — runs the Best Practice Analyzer `BPARules.json` format with no .NET tooling; safe AST evaluation (no `eval()`) with an honest evaluated/skipped tally per run
- **Full Fabric lifecycle** — items (CRUD via the Item Definition API), workspaces, git sync, deployment pipelines, OneLake, capacity pause/resume/scale, jobs, Direct Lake diagnostics
- **Quality platform** — DAX lint/format, report lint + field-usage analysis, dbt-style data tests, schema contracts, RLS matrices, drift detection — all CI-gateable with exit codes and SARIF
- **AI-agent native** — `pbi mcp serve` exposes every capability to Cursor/Copilot/Claude Desktop; `pbi ask` turns English into executed DAX; 12 Claude Code skills install in one step
- **One-step CI** — a published GitHub Action and pre-commit hooks: the governance gate is one `uses:` line

---

## Installation

**Recommended — [uv](https://docs.astral.sh/uv/) (fastest, manages Python automatically, no PATH issues on Windows):**
```bash
uv tool install pbi-enterprise-cli
uv tool install "pbi-enterprise-cli[all]"   # all optional features
```

**Alternative — [pipx](https://pipx.pypa.io/):**
```bash
pipx install pbi-enterprise-cli
```

**Fallback — pip:**
```bash
pip install pbi-enterprise-cli
```

**With specific extras:**
```bash
uv tool install "pbi-enterprise-cli[ai,xmla]"     # Claude AI + XMLA/Fabric
uv tool install "pbi-enterprise-cli[sources]"     # SQL / Excel / REST profiling
uv tool install "pbi-enterprise-cli[server]"      # FastAPI REST server
uv tool install "pbi-enterprise-cli[viz]"         # WCAG theme validation
```

> **Requirements:** Python 3.10–3.13. The `desktop` and `xmla` backends require Windows. The `file`, `rest`, and `mock` backends work on Linux and macOS — CI pipelines need no Windows runner for governance, BPA, lint, DAX tests, docs, or diff.

---

## 60-Second Quickstart

```bash
# 1. Verify setup
pbi doctor

# 2. Connect to open Power BI Desktop + install all 12 Claude Code skills
pbi connect

# 3. Explore the model
pbi model tables
pbi measure list

# 4. Run governance and BPA
pbi govern check --fail-on error
pbi govern bpa check --severity error

# 5. Fix safe violations automatically
pbi govern fix --auto

# 6. Run DAX unit tests + lint
pbi dax test --suite ./tests/measures/
pbi dax lint --fail-on error

# 7. Deploy to a workspace via XMLA (Windows) — or edit a live model from
#    any OS with `--backend fabric` (see the backend table below)
pbi deploy push --workspace "Production"
```

No Desktop open? Everything above also works straight off the repo files:

```bash
pbi --backend file --path . govern check       # governance on real TMDL, any OS
pbi --backend file --path . docs site          # data-dictionary site from the repo
pbi ask "top 10 customers by revenue"          # English → DAX → results (rest/xmla)
```

---

## Before vs After

<div align="center">
  <img src="docs/assets/before-after.svg" alt="Before and after pbi-enterprise-cli" width="100%"/>
</div>

---

## Command Reference

| Area | Commands |
|---|---|
| **Semantic model** | `pbi model` — tables, columns, relationships, lint, lineage |
| **DAX measures** | `pbi measure` — add, update, delete, AI-generate, audit |
| **DAX testing** | `pbi dax` — query, validate, YAML unit-test suites, coverage |
| **DAX tooling** | `pbi dax format` (offline formatter) + `pbi dax lint` (static rules) |
| **Report analysis** | `pbi report lint / field-usage / diff / a11y` — PBIR intelligence |
| **T-SQL** | `pbi sql query` — run T-SQL against a Fabric Warehouse / Lakehouse SQL endpoint |
| **Lakehouse** | `pbi lakehouse` — list, tables, load-to-table, maintenance (OPTIMIZE/V-Order/VACUUM) |
| **Notebooks** | `pbi notebook` — run with typed parameters (`--wait`), status, export/import `.ipynb` |
| **Source profiling** | `pbi source` — SQL, Excel, CSV, REST → star-schema scaffold |
| **Calendar** | `pbi calendar` — generate date tables, fiscal year, mark-as-date-table |
| **Report authoring** | `pbi report` — pages, bookmarks, drillthrough (PBIR GA format) |
| **Visuals** | `pbi visual` — 32 visual types, conditional formatting, data bars |
| **Layout** | `pbi layout` — shelf-packing auto-layout, named templates |
| **Themes** | `pbi theme` — generate WCAG-compliant themes from a brand colour |
| **Filters** | `pbi filter` — relative-date, TopN, basic value filters |
| **Governance** | `pbi govern` — built-in rules + BPA + plugins, SARIF, PR comments, tenant-wide scan, AI explain, AI-readiness audit |
| **Tenant admin** | `pbi tenant` — usage analytics, access review, stale datasets, sensitivity labels |
| **Security (RLS)** | `pbi security` — role add/delete/test, perspectives |
| **Testing** | `pbi test` — data quality (DAX-compiled), schema contracts, RLS matrix, synthetic seed |
| **Partitions** | `pbi partition` — add, refresh, delete, incremental refresh |
| **Deployment** | `pbi deploy` — snapshot, diff, push via XMLA |
| **Fabric** | `pbi fabric` — items (full CRUD), workspaces, git sync, deployment pipelines, OneLake, capacity ops, jobs, Direct Lake, Fabric IQ ontologies (preview) |
| **Snapshots** | `pbi snapshot` — create, list, restore, diff — model rollback |
| **Environments** | `pbi env` — named connections, use, diff, promote, drift detection |
| **Model diff** | `pbi diff` — semantic TMDL diff (paths or git refs) + release notes |
| **TMDL** | `pbi database` — export / import TMDL snapshots |
| **Power Query** | `pbi pquery` — list M queries, query-folding analysis, M lint |
| **Operations** | `pbi ops` — refresh orchestration, chains, health checks, webhooks |
| **Migration** | `pbi migrate` — Direct Lake readiness, PBIX extraction, dbt interop |
| **Docs** | `pbi docs` — data dictionary, lineage, Mermaid ERD, MkDocs site |
| **AI & agents** | `pbi ask` (NL→DAX), `pbi mcp serve` (MCP server — full-CLI parity via `run_cli`), `pbi introspect` |
| **Scaffolding** | `pbi init` — tests + CI workflow + pre-commit + config in one step |
| **Diagnostics** | `pbi doctor` — check pythonnet, optional deps, platform |
| **Watch mode** | `pbi watch` — re-run governance + DAX tests on file change |
| **REST API** | `pbi server` — authenticated FastAPI server for pipeline integration |
| **Skills** | `pbi skills` — install, list, check 12 Claude Code Power BI skills |

---

## Scope: what's deep vs. emerging

Honesty about coverage, so you can judge fit:

- **Deep today (the moat):** the semantic-model layer — modelling, DAX authoring/testing/lint, governance + BPA, RLS, report (PBIR) authoring & analysis, TMDL diff/snapshot, docs/lineage, and CI gating. This is production-grade and best-in-class. Live measure edits now work **from any OS** via the `fabric` backend (no Windows/XMLA).
- **Solid:** Fabric platform *lifecycle* — item CRUD (any type), workspaces, git sync, deployment pipelines, OneLake files, capacity ops, jobs; **T-SQL against Warehouse/Lakehouse SQL endpoints** (`pbi sql query`); **Lakehouse table ops** (`pbi lakehouse` — list/tables/load/maintenance); **notebook runs** (`pbi notebook` — parameterised run, status, `.ipynb` export/import).
- **Emerging (item-level only, ergonomics in progress):** data-pipeline (Data Factory) run monitoring and Dataflows Gen2 mashups — reachable via `pbi fabric item`/`pbi fabric job`, dedicated commands still being built.
- **Not yet:** Eventstream / Eventhouse / KQL / Real-Time Intelligence and Spark environments.

If your work is **Power BI semantic models, governance, and analytics**, this is a one-stop shop today. If it's **Fabric Spark/lakehouse data engineering**, it's a capable lifecycle manager that's deepening — see [RECOMMENDATIONS.md](RECOMMENDATIONS.md) for the roadmap.

---

## Six-Backend Architecture

<div align="center">
  <img src="docs/assets/architecture.svg" alt="Backend architecture" width="100%"/>
</div>

| Backend | When to use | Requires |
|---|---|---|
| `desktop` (default) | Local Power BI Desktop with a `.pbip` project open | Windows + Desktop |
| `xmla` | Power BI Premium or Microsoft Fabric — no Desktop | Windows + MSAL (`[xmla]` extra) |
| `file` | TMDL/PBIP folders straight from the repo — governance, lint, docs, diff | Nothing — works on Linux/macOS |
| `rest` | Live DAX against any published dataset (executeQueries API) | A token — works on Linux/macOS |
| `fabric` | **Edit measures on a live model from any OS** — TMDL round-trip via the Item Definition API (no Windows, no XMLA) | A token — works on Linux/macOS |
| `mock` | CI pipelines, unit tests, demos | Nothing — works on Linux/macOS |

```bash
# Swap with --backend
pbi --backend file --path . govern check --fail-on error          # real artifacts, any OS
pbi --backend rest dax query "EVALUATE TOPN(10, Sales)"            # live DAX, any OS
pbi --backend fabric --workspace <ws> --dataset <ds> \
    measure add --table Sales --name "Margin %" \
    --expression "DIVIDE([Profit],[Revenue])"                     # live WRITE, any OS
pbi --backend xmla model tables                                   # Fabric without Desktop
pbi --backend desktop measure list                                # local Desktop (default)
```

> **The `fabric` backend** downloads the model's TMDL definition, applies the edit
> with the pure-Python TMDL writer, and pushes it back via `updateDefinition` — so
> `measure add/update/delete` against a *published* model no longer needs Windows.
> Structural edits (tables, relationships, partitions) still use `desktop`/`xmla`.

---

## Python-Native BPA Runner

`pbi-enterprise-cli` includes a Python-native runner for the [Best Practice Analyzer](https://docs.tabulareditor.com/BPA/Best-Practice-Analyzer.html) rule format — load the same `BPARules.json` files Tabular Editor uses, with no .NET 6 and no Tabular Editor install.

Rule expressions are parsed into an AST and evaluated safely (no `eval()`). Rules whose expression — or a property it references — is outside the model surface we expose are reported as **skipped**, not silently mis-evaluated. Every run prints an `evaluated / skipped` tally so you always know how much of a ruleset actually ran. Coverage of the Microsoft community ruleset improves with the richer `file`/`xmla` backends over `mock`.

```bash
# Microsoft community BPA rules (fetched live)
pbi govern bpa check

# Filter to errors only — safe CI gate
pbi govern bpa check --severity error

# Local corporate rule file
pbi govern bpa check --file ./governance/CorpBPARules.json

# Also evaluate runtime-statistics rules (large tables, RI violations,
# high-cardinality columns) — collects VertiPaq stats from the live model
pbi --backend desktop govern bpa check --vertipaq

# JSON output for downstream tooling
pbi --json govern bpa check --severity error
```

> **Full ruleset coverage.** Against a live `desktop`/`xmla` model with
> `--vertipaq`, the runner evaluates **all** of the Microsoft community ruleset —
> including the DAX-dependency, object-metadata, and runtime-statistic rules.
> Rules that read runtime statistics via `GetAnnotation(...)` (row counts,
> cardinality, RI violations) need `--vertipaq` because those numbers exist only
> once the data is loaded into VertiPaq; without it (or on the static `file`
> backend) they skip honestly rather than guessing.

**GitHub Actions governance gate — works on `ubuntu-latest`, no Windows runner needed:**

```yaml
- name: BPA governance gate
  run: pbi --backend mock govern bpa check --severity error
```

**Custom governance plugin** — drop a `.py` file in `~/.pbi-cli/rules/`:

```python
from pbi_cli.governance.engine import GovernanceRule, Violation

class NoHardcodedDatesRule(GovernanceRule):
    id = "custom.no-hardcoded-dates"
    severity = "error"

    def check(self, model) -> list[Violation]:
        return [
            Violation(self, f"Measure '{m.name}' contains a hardcoded year")
            for m in model.measures
            if "2024" in m.expression or "2025" in m.expression
        ]
```

---

## Claude Code Skills

Run `pbi connect` to install all 12 skills into `~/.claude/skills/` in one step:

```bash
pbi connect    # connects to Desktop + installs skills + prints model summary
```

Or install manually:

```bash
pbi skills install --all
pbi skills check          # verify compatibility with installed CLI version
```

| Skill | Covers |
|---|---|
| `power-bi-modeling` | Star schema, source profiling, partitions, incremental refresh, calendar, M queries |
| `power-bi-dax` | DAX authoring, Time Intelligence, YAML unit tests, filter context, design patterns |
| `power-bi-performance` | Query tracing, benchmarking, VertiPaq, storage vs formula engine |
| `power-bi-report-design` | Pages, 32 visual types, bookmarks, drillthrough, auto-layout, conditional formatting |
| `power-bi-design-system` | WCAG themes, brand colours, typography, custom visual SDK |
| `power-bi-governance` | Built-in rules, BPA, custom plugins, auto-fix, CI gate |
| `power-bi-security-and-docs` | RLS, perspectives, role testing, data dictionary, lineage, audit logs |
| `power-bi-deployment` | XMLA deploy, TMDL snapshots, multi-environment promotion, auth setup |
| `power-bi-diagnostics` | `pbi doctor`, pythonnet/AMO resolution, error playbook, connection troubleshooting |
| `power-bi-project-orchestrator` | Coordinates multi-skill workflows: model → DAX → governance → report → deploy |
| `power-bi-report-management` | Publish/download/update/delete PBIR reports in Fabric: pull/push round-trip, binding verification |
| `power-bi-report-planner` | Guided end-to-end report build: requirements, design brief, approval-gated PBIR authoring & publish |

---

## CI/CD Integration

Full governance + BPA + DAX lint + tests run on `ubuntu-latest` against the **real TMDL artifacts in your repo** — no Windows runner, no Power BI infrastructure.

**One step with the published GitHub Action:**

```yaml
# .github/workflows/pbi-govern.yml
name: Power BI Governance
on: [push, pull_request]
permissions:
  pull-requests: write
  security-events: write

jobs:
  govern:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mudassir09/pbi-enterprise-cli@v1
        with:
          path: .
          fail-on: error
          comment-pr: "true"            # governance summary as a PR comment
          sarif: pbi-governance.sarif   # violations in the code-scanning UI
```

**Or hand-rolled, with SARIF + drift detection:**

```yaml
      - run: pip install pbi-enterprise-cli
      - run: pbi --backend file --path . govern check --fail-on error --sarif gov.sarif
      - run: pbi --backend file --path . dax lint --fail-on error
      - run: pbi --backend file --path . dax format --check
      - run: pbi --backend file --path . report lint --pbip . --fail-on error
      - run: pbi diff main . --git --release-notes model-changes.md
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: gov.sarif }
```

**Pre-commit hooks** (`.pre-commit-config.yaml`):

```yaml
repos:
  - repo: https://github.com/mudassir09/pbi-enterprise-cli
    rev: v1.1.1
    hooks:
      - id: pbi-govern
      - id: pbi-dax-lint
      - id: pbi-dax-format
```

Scaffold all of this in one command: **`pbi init`**.

---

## Global Flags

| Flag | Purpose |
|---|---|
| `--backend desktop\|xmla\|mock\|file\|rest\|fabric` | Select backend (default: `desktop`) |
| `--path <folder>` | TMDL/PBIP project folder (file backend) |
| `--workspace <id>` / `--dataset <id>` | Fabric workspace + semantic-model id (fabric backend) |
| `--dry-run` | Preview changes without applying them |
| `--json` / `--yaml` | Machine-readable output |
| `--port 5000` | Desktop local server port |

> **Named connections:** save and switch reusable connection profiles with
> `pbi connections add/use/list` (or environment profiles with `pbi env`), rather
> than passing endpoints on every command.

## Exit Code Contract

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | User error — bad args, missing flags |
| `2` | Connection error — Desktop not open, XMLA unreachable |
| `3` | Validation error — governance violation, schema error |
| `4` | Operation error — TOM write failed, partial completion |

## Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude AI for `pbi measure generate` |
| `PBI_SERVER_KEY` | API key for `pbi server start` |
| `PBI_CLIENT_SECRET` | Service principal secret for XMLA connections |
| `PBI_REST_BEARER` | Default Bearer token for REST source profiling |

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, branch strategy, and the PR process.

**Good First Issues** are labelled [`good first issue`](https://github.com/mudassir09/pbi-enterprise-cli/issues?q=label%3A%22good+first+issue%22) — these are self-contained tasks with clear acceptance criteria and no deep context required.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/SOP.md](docs/SOP.md) | **Standard Operating Procedure** — the recommended end-to-end workflow using every feature |
| [docs/auth/xmla-auth.md](docs/auth/xmla-auth.md) | XMLA auth: service principal, managed identity, device flow |
| [docs/deployment.md](docs/deployment.md) | Snapshot format, diff algorithm, push safety, rollback |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branch strategy, coding standards, PR guide |
| [STABILITY.md](STABILITY.md) | Stable command surface, exit code contract, deprecation policy |

---

## License

MIT © [Mudassir](https://github.com/mudassir09) — see [LICENSE](LICENSE).

The bundled AMO/ADOMD client libraries are licensed under the [Microsoft Software License Terms](https://go.microsoft.com/fwlink/?LinkId=2179979).
