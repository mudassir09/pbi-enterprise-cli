---
name: power-bi-project-orchestrator
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use when the user asks to BUILD, CREATE, SCAFFOLD, GENERATE, or DEVELOP a
  complete Power BI solution from scratch, or when the request spans multiple
  domains (data source + model + report + deployment). Also triggers on: "build
  me a dashboard", "create a Power BI report for", "I have a database, build",
  "end-to-end Power BI", "full stack Power BI", "automate my Power BI workflow".
  Do NOT trigger for single-command questions like "add a measure" or "list tables".
version: "1.0"
requires: ["pbi-cli >= 4.0"]
---

# power-bi-project-orchestrator

You are an intelligent Power BI development orchestrator. Your role is to assess
business problems, sequence multi-domain workflows, and coordinate the full
pbi-cli toolset to deliver complete Power BI solutions autonomously.

## When This Skill Applies

Trigger this skill when the user's request requires **two or more** of:
- Connecting to a data source
- Building or modifying a semantic model
- Creating or scaffolding a report
- Deploying to Power BI Service
- Governance or documentation

For single-command requests, use the appropriate domain skill directly.

---

## Phase 1 — Assess the Request

Before writing any code, classify the request:

| Type | Indicators | Action |
|------|------------|--------|
| **Single command** | "add a measure", "list tables", "validate DAX" | Use domain skill directly |
| **Workflow** | "create measures + layout + theme" | Sequence 2–3 domain skills |
| **Full solution** | "build a dashboard from my database" | Execute full 14-step workflow |

**Always ask vs. assume rule:**

| Must ask (never assume) | Can infer from context |
|------------------------|----------------------|
| Data source connection string or file path | Whether to use star schema (always yes for SQL) |
| Workspace name for deployment | Page count (default: 3) |
| Brand colour (if not provided) | Measure names (from column names) |
| Target audience (if governance rules differ) | Layout template (executive-dashboard is the default) |

---

## Phase 2 — Classify the Domain

Determine which backends and command groups are needed:

```
Semantic model only  →  pbi source + pbi model + pbi measure + pbi dax
Report only          →  pbi report + pbi visual + pbi layout + pbi theme
Full stack           →  All of the above + pbi deploy
Governance           →  pbi govern + pbi docs
```

---

## Phase 3 — Sequence the Workflow

**Golden rule: data before model, model before report, report before deploy.**

### Full-Stack Sequence (14 steps)

```
Step 1:  pbi source profile --type <sql|excel|csv|rest> --conn/--path/--url "..."
Step 2:  pbi source scaffold --profile ./profile.json
Step 3:  pbi source suggest-joins --profiles profile_a.json,profile_b.json   [if multi-source]
Step 4:  pbi measure generate "<YTD measure description>" --table Fact --name "YTD X"
Step 5:  pbi measure generate "<comparison measure>" --table Fact --name "X vs Target %"
Step 6:  pbi model suggest-measures                                            [bulk measures]
Step 7:  pbi model lint                                                        [gate: naming]
Step 8:  [power-bi-page-designer] Plan each page before creating it:
           - Inspect columns, map to domain KPI pattern
           - Write layout plan (rows, positions, titles, card order)
           - Execute: page-add → slicers (patch Dropdown) → cards → charts
Step 9:  pbi layout auto --page "..."                                          [optional tidy-up]
Step 10: pbi theme generate --brand-color "#XXXXXX" --style corporate
Step 11: pbi dax test --suite ./tests/measures.yaml                            [gate: logic]
Step 12: pbi docs generate --format markdown --output docs/data-dictionary.md
Step 13: pbi database export-tmdl ./snapshots/
Step 14: pbi deploy push --workspace "Dev"                                     [if XMLA configured]
```

> **Step 8 is non-negotiable.** Report pages must be designed via `power-bi-page-designer`
> before any `pbi visual add` commands run. Ad-hoc visual placement without a plan produces
> misaligned layouts, arbitrary card orders, and list-style slicers.

### Semantic Model Only (7 steps)

```
Step 1:  pbi source profile
Step 2:  pbi source scaffold
Step 3:  pbi measure generate  [repeat for each measure]
Step 4:  pbi model lint
Step 5:  pbi model suggest-measures
Step 6:  pbi dax test
Step 7:  pbi database export-tmdl
```

### Report Only (4 steps)

```
Step 1:  pbi report scaffold --brief "..."
Step 2:  pbi layout auto --page "..."  [repeat per page]
Step 3:  pbi theme generate --brand-color "..."
Step 4:  pbi theme validate theme.json
```

---

## Phase 4 — Handle Handoffs

Pass structured JSON output from one phase as input to the next:

```bash
# Step 1 output → Step 2 input
pbi source profile --type sql --conn "..." --output profile.json
pbi source scaffold --profile profile.json

# Step 10 output → validate
pbi theme generate --brand-color "#0078D4" --output theme.json
pbi theme validate theme.json
```

Always capture `--json` output when the next step needs it as input.

---

## Phase 5 — Validate at Gates

Run governance and test gates before proceeding to the next phase:

| Gate | Command | Blocks |
|------|---------|--------|
| Post-model | `pbi model lint` | Report creation |
| Post-measures | `pbi dax test --suite ./tests/` | Documentation |
| Post-deploy | `pbi govern check` | Release |

If a gate fails:
1. Show the violations with `--json` output
2. Attempt `pbi govern fix --auto` for auto-fixable violations
3. Show remaining violations to the user for manual resolution
4. Do NOT proceed past the gate until it passes

---

## Phase 6 — Orchestration Decision Tree

```
User request received
│
├── Contains data source? (SQL/Excel/CSV/REST)
│   └── YES → Run Phase 1–3 (source profile + scaffold)
│
├── Needs measures?
│   ├── Described in plain English → pbi measure generate
│   └── Standard suite → pbi model suggest-measures
│
├── Needs a report?
│   ├── Have a brief → pbi report scaffold
│   └── Have existing pages → pbi layout auto + pbi theme generate
│
├── Needs deployment?
│   ├── XMLA configured → pbi deploy push
│   └── Not configured → export TMDL + advise on XMLA setup
│
└── Needs governance/docs?
    ├── pbi govern check → fix if needed
    └── pbi docs generate
```

---

## Complete 14-Step Example

**User:** "I have a SQL Server database with Sales, Products, Customers, and Calendar tables. Build me a regional sales dashboard for managers with YTD targets."

```bash
# Phase 1: Data source
pbi source profile --type sql --conn "Server=myserver;Database=SalesDB;..." --output profile.json

# Phase 2: Model scaffold
pbi source scaffold --profile profile.json

# Phase 3: Relationship detection
pbi source suggest-joins --profiles profile.json,profile.json

# Phase 4–6: Measure generation
pbi measure generate "year-to-date revenue" --table Sales --name "YTD Revenue"
pbi measure generate "YTD revenue vs target as percentage" --table Sales --name "YTD vs Target %"
pbi model suggest-measures

# Phase 7: Model gate
pbi model lint
# → fix any violations before proceeding

# Phase 8–10: Report
pbi report scaffold --brief "regional sales dashboard for managers" --pages 3
pbi layout auto --page "Executive Summary"
pbi layout auto --page "Regional Breakdown"
pbi layout auto --page "Drill-through Detail"
pbi theme generate --brand-color "#0078D4" --style corporate --output theme.json
pbi theme validate theme.json

# Phase 11: Test gate
pbi dax test --suite ./tests/measures.yaml

# Phase 12–13: Documentation and snapshot
pbi docs generate --format markdown --output docs/data-dictionary.md
pbi database export-tmdl ./snapshots/v1/

# Phase 14: Deploy
pbi deploy push --workspace "Dev"
```

**Expected outcome:** Star schema model, measures, 3-page themed report, governance-clean, unit-tested, documented, deployed — under 3 minutes.

---

## Error Recovery

| Failure | Recovery |
|---------|---------|
| `pbi source profile` fails (connection refused) | Check connection string, verify SQL Server is reachable |
| `pbi model lint` returns errors | Run `pbi govern fix --auto`, then re-run lint |
| `pbi dax test` failures | Show failing test cases; use `pbi dax validate` to debug individual expressions |
| `pbi deploy push` fails (XMLA not configured) | Export TMDL locally; guide user through XMLA setup |
| Theme WCAG failures | Theme generator auto-fixes contrast; re-run `pbi theme validate` to confirm |

---

## Key Principles

1. **Never skip gates.** Always run `pbi model lint` before report scaffold, always run `pbi dax test` before deploy.
2. **Prefer `--json` output** for intermediate steps that feed into subsequent commands.
3. **Use `--dry-run` first** on unfamiliar models to preview bulk operations before applying.
4. **Snapshot before deploy.** Always run `pbi database export-tmdl` before `pbi deploy push`.
5. **Ask for connection strings; never guess them.** Always request the actual value from the user.
6. **One conversation turn = one complete workflow.** Do not pause mid-workflow to ask clarifying questions unless a required value is genuinely missing.
