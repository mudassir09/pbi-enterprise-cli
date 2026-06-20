# Standard Operating Procedure — pbi-enterprise-cli

**Version:** 1.1.0 · **Audience:** Power BI / Fabric developers, BI leads, platform admins, and CI engineers.

This SOP describes the recommended way to run a Power BI / Microsoft Fabric estate with
`pbi-enterprise-cli`, end to end: project setup, daily development, quality gates,
deployment, operations, tenant governance, and AI-assisted workflows. Every step is a
copy-pasteable command. Exit codes are contractual (`0` ok · `1` user error ·
`2` connection · `3` validation/governance · `4` operation), so every step here can be
scripted and gated.

---

## 0. Choosing a backend (read this first)

Every command runs against a backend selected with `--backend`. Pick by task:

| You are… | Use | Example |
|---|---|---|
| Editing a model open in Power BI Desktop | `desktop` (default) | `pbi measure list` |
| Working with the TMDL/PBIP files in a git repo (no Desktop needed, any OS) | `file` | `pbi --backend file --path . govern check` |
| Querying or auditing a **published** dataset from any OS | `rest` | `pbi --backend rest dax query "EVALUATE Sales"` |
| Writing to a Premium/Fabric model without Desktop (Windows) | `xmla` | `pbi --backend xmla --connection prod model tables` |
| Writing unit tests / demos | `mock` | `pbi --backend mock govern check` |

**Rules of thumb**
- CI always uses `file` (real artifacts) — never `mock` unless you're testing the CLI itself.
- `rest` needs `PBI_WORKSPACE_ID`, `PBI_DATASET_ID`, and a token (`PBI_REST_BEARER` or MSAL via the `[xmla]` extra).
- Add `--json` (or `--yaml`) to any command for scripting; add `--dry-run` before any write you're unsure about.

---

## 1. One-time setup

### 1.1 Developer workstation (Windows, full stack)

```bash
uv tool install "pbi-enterprise-cli[all]"
pbi doctor                       # verify pythonnet, DLLs, optional extras
pbi connect                      # attach to open Desktop + install 10 Claude Code skills
pbi completions                  # shell tab-completion setup instructions
```

### 1.2 Developer workstation (macOS/Linux)

```bash
uv tool install "pbi-enterprise-cli[ai,sources]"
pbi doctor
# Work file-based against the repo:
pbi --backend file --path . model tables
```

### 1.3 New or existing repo

```bash
cd my-pbip-repo
pbi init        # scaffolds: pbi.config.toml, tests/{measures,data,contracts},
                #            .github/workflows/pbi-govern.yml, .pre-commit-config.yaml
git add . && git commit -m "chore: pbi-enterprise-cli project scaffold"
```

### 1.4 Service principal for CI / automation

Set these as CI secrets (used by `rest`, `fabric`, `tenant`, `ops`, `govern scan`):

| Variable | Purpose |
|---|---|
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `PBI_CLIENT_SECRET` | Service principal (client-credentials) auth |
| `PBI_REST_BEARER` | Alternative: a pre-acquired bearer token |
| `PBI_WORKSPACE_ID`, `PBI_DATASET_ID` | Default target for the `rest` backend |
| `ANTHROPIC_API_KEY` | AI commands (`ask`, `measure generate`, `govern explain`) |

---

## 2. Daily development workflow

### 2.1 Explore and edit the model

```bash
pbi model tables                                   # what's in the model
pbi model relationships
pbi model stats                                    # size/complexity overview
pbi measure add Sales "Margin %" "DIVIDE([Profit], [Revenue])" --format "0.0%"
pbi measure list --table Sales
pbi undo                                           # every write is snapshotted — revert the last one
```

Before any risky change, check the blast radius:

```bash
pbi model impact --column "Sales[Amount]"          # what breaks if this changes
```

### 2.2 Keep DAX clean as you go

```bash
pbi dax lint                       # static analysis: DIVIDE, EARLIER, volatile fns, anti-patterns
pbi dax format --check             # is everything formatted? (exit 1 if not)
pbi dax format --all --write       # fix it
pbi dax validate "SUM(Sales[Revenue])"
pbi dax query "EVALUATE TOPN(10, Sales)"
```

### 2.3 Author the report layer

```bash
pbi report pages --pbip .
pbi visual add --pbip . --page Overview --type barChart --x Sales.Category --y "Sales.[Total Revenue]"
pbi layout auto --pbip . --page Overview           # shelf-packing auto-layout
pbi theme generate --brand "#0E7C61" --apply       # WCAG-compliant theme from a brand colour
pbi report lint --pbip .                           # density, hidden visuals, overlaps, alt text
pbi report a11y --pbip .                           # accessibility audit
```

### 2.4 Watch mode (tight feedback loop)

```bash
pbi watch          # re-runs governance + DAX tests on every file save
```

### 2.5 Commit hygiene (automatic via pre-commit)

`pbi init` wired these hooks; they run on every commit:
`pbi-govern` · `pbi-dax-lint` · `pbi-dax-format`.

---

## 3. Quality gates (the test pyramid)

Run the full pyramid locally before a PR; CI runs the same commands.

```bash
# 1. Governance — naming, metadata, model quality (+ BPA, Tabular Editor rule format)
pbi --backend file --path . govern check --fail-on error
pbi --backend file --path . govern bpa check --severity error
pbi --backend file --path . govern fix --auto          # apply safe auto-fixes

# 2. DAX unit tests (YAML suites) + coverage
pbi dax test --suite tests/measures/
pbi dax coverage --suite tests/measures/               # which measures lack tests

# 3. Data quality tests — compiled to DAX, run on a live backend (rest/xmla/desktop)
pbi --backend rest test data --suite tests/data/

# 4. Schema contracts — fail CI on accidental breaking changes
pbi --backend file --path . test schema --contract tests/contracts/schema.yaml

# 5. RLS persona matrix
pbi --backend xmla test rls --matrix tests/rls.yaml

# 6. Report layer
pbi report lint --pbip . --fail-on warning
pbi report field-usage --pbip . --unused-only          # dead columns/measures to remove

# 7. Power Query
pbi --backend file --path . pquery folding-check --fail-on-breaker
pbi --backend file --path . pquery lint                # hardcoded paths, credentials
```

**Suite formats** (created by `pbi init`, see `--help` on each command for full syntax):

```yaml
# tests/data/data_suite.yaml
tests:
  - {table: Sales, row_count: {min: 1}}
  - {type: not_null, table: Sales, column: Revenue}
  - {type: unique, table: Customers, column: CustomerKey}
  - {type: relationship, table: Sales, column: ProductKey,
     to_table: Products, to_column: ProductKey}
```

---

## 4. Pull requests and CI

### 4.1 The standard PR pipeline (one step)

```yaml
# .github/workflows/pbi-govern.yml
- uses: mudassir09/pbi-enterprise-cli@v1
  with:
    path: .
    fail-on: error
    comment-pr: "true"          # posts a governance summary on the PR
    sarif: pbi-governance.sarif # violations appear in GitHub code scanning
    test-suite: tests/measures/
```

### 4.2 Reviewable model diffs

Raw TMDL diffs are unreadable; give reviewers semantics:

```bash
pbi diff main . --git                          # branch vs working tree, object-level
pbi diff main . --git --release-notes CHANGES.md   # markdown for the PR description
pbi report diff path/to/main-checkout .        # visual-level report diff
```

### 4.3 Drift guard (catch direct prod edits)

Run nightly or per-deploy; fails if someone edited the live model outside git:

```bash
pbi --backend xmla --connection prod env drift --path . --fail-on-drift
```

---

## 5. Deployment

### 5.1 Git-driven (recommended)

```bash
# Option A — Fabric Item Definition API (works from any OS, including CI):
pbi fabric item update --workspace <ws-id> --item <model-id> --definition ./Sales.SemanticModel

# Option B — XMLA push with snapshot safety (Windows):
pbi snapshot create --label pre-deploy
pbi deploy push --connection fabric-prod
pbi snapshot restore --label pre-deploy        # rollback if needed

# Option C — workspace git integration (Fabric-native):
pbi fabric git status --workspace <ws-id>
pbi fabric git update --workspace <ws-id>      # repo → workspace
```

### 5.2 Stage promotion via deployment pipelines

```bash
pbi fabric pipeline stages --pipeline <pipeline-id>
pbi fabric pipeline deploy --pipeline <pipeline-id> --from Dev --to Test
```

### 5.3 Post-deploy verification

```bash
pbi --backend rest dax query "EVALUATE ROW(\"rows\", COUNTROWS(Sales))"
pbi --backend rest test data --suite tests/data/
pbi ops refresh --workspace <ws-id> --dataset <ds-id> --notify $TEAMS_WEBHOOK
```

---

## 6. Operations (run on a schedule)

```bash
# Ordered refreshes with short-circuit + Teams/Slack alerting
pbi ops refresh-chain --plan ops/refresh-plan.yaml --notify $TEAMS_WEBHOOK

# Workspace health: failed refreshes in the last 24h (exit 4 on problems)
pbi ops health --workspace <ws-id> --hours 24 --notify $TEAMS_WEBHOOK

# Direct Lake: check framing and reframe after lakehouse loads
pbi fabric directlake status --workspace <ws-id> --dataset <ds-id>
pbi fabric directlake reframe --workspace <ws-id> --dataset <ds-id>

# Capacity cost control (Azure ARM)
pbi fabric capacity pause  --subscription $SUB --resource-group rg-bi --name fab-dev   # evenings
pbi fabric capacity resume --subscription $SUB --resource-group rg-bi --name fab-dev
pbi fabric capacity scale  --subscription $SUB --resource-group rg-bi --name fab-prod --sku F64
```

---

## 7. Tenant governance (admin, monthly/quarterly)

```bash
# Governance across EVERY dataset in the org (Scanner API)
pbi govern scan --fail-on error --max-workspaces 200

# Adoption: top reports, top users, activity mix
pbi tenant usage --days 30

# Cleanup candidates: datasets with no refresh in 90 days
pbi tenant stale --days 90

# Access review for audits (flag guests)
pbi tenant access --external-only

# Sensitivity labels at scale
pbi tenant labels set --label-id <mip-guid> --dataset <id> --dataset <id>
```

---

## 8. Documentation (regenerate on every release)

```bash
pbi --backend file --path . docs generate --format markdown -o docs/dictionary.md
pbi --backend file --path . docs erd --output docs/model-erd.mmd     # Mermaid ERD
pbi --backend file --path . docs site --output docs-site             # full MkDocs site
mkdocs gh-deploy -f docs-site/mkdocs.yml                              # publish to Pages
```

---

## 9. AI and agent workflows

```bash
# English → DAX → executed results (requires [ai] + ANTHROPIC_API_KEY)
pbi ask "monthly revenue trend for 2026 by region"

# AI-generated measures and violation explanations
pbi measure generate "year over year revenue growth percent"
pbi govern explain

# Claude Code: 10 bundled skills
pbi skills install --all && pbi skills check

# Any other MCP client (Cursor, Copilot, Claude Desktop) — add to mcpServers:
#   { "pbi": { "command": "pbi",
#              "args": ["--backend", "file", "--path", "C:/repo", "mcp", "serve"] } }

# Give an agent the full command map as context
pbi introspect --format llms > llms.txt
```

---

## 10. Migration playbooks

```bash
# Import → Direct Lake: list every blocker with the required action
pbi --backend file --path . migrate direct-lake

# Legacy estate inventory: extract layout/metadata from .pbix at scale
pbi migrate pbix-extract legacy-report.pbix --output ./inventory/legacy-report

# dbt-driven models: map dbt models to tables, generate a schema contract
pbi migrate dbt --manifest target/manifest.json --contract-out tests/contracts/dbt.yaml
```

---

## 11. Troubleshooting quick reference

| Symptom | First command | Then |
|---|---|---|
| Anything at all | `pbi doctor` | Fix what it reports |
| "No running Power BI Desktop found" | Open the `.pbip` in Desktop | `pbi connect --port <n>` if multiple |
| XMLA auth failures | `pbi --backend xmla model tables` after setting SP env vars | See [docs/auth/xmla-auth.md](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/auth/xmla-auth.md) |
| `rest` backend "needs a workspace and dataset" | Set `PBI_WORKSPACE_ID` / `PBI_DATASET_ID` | Check token scope |
| A write went wrong | `pbi undo` | `pbi snapshot list` → `restore` |
| Slow report | `pbi trace start` → interact → `pbi trace stop` | `pbi report lint`, `pquery folding-check` |
| CI exit code 3 | Read the violations table | `pbi govern fix --auto` for fixable ones |

---

## 12. Cadence summary

| Frequency | Procedure |
|---|---|
| Every save | `pbi watch` (governance + tests on change) |
| Every commit | pre-commit hooks: govern, dax lint, dax format |
| Every PR | GitHub Action gate + `pbi diff --git` release notes |
| Every deploy | snapshot → push → `test data` → `ops refresh` |
| Nightly | `ops health`, `env drift --fail-on-drift`, `ops refresh-chain` |
| Monthly | `govern scan`, `tenant usage`, `tenant stale`, docs regen |
| Quarterly | `tenant access --external-only` review, capacity right-sizing |
