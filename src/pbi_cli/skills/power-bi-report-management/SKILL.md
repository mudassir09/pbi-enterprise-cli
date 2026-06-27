---
name: power-bi-report-management
version: "1.1"
min_cli_version: "0.1.0"
description: >
  Use for publishing, downloading, updating, and deleting Power BI reports in
  Microsoft Fabric workspaces via the Fabric REST API. Triggers on:
  "publish to Fabric", "upload PBIR", "deploy report to workspace",
  "download report definition", "update report in Fabric", "delete report",
  "pbi fabric report", "push report", "pull report", "report CRUD".
  Do NOT trigger for local PBIR authoring (→ power-bi-report-design),
  theme or visual changes (→ power-bi-report-design),
  or semantic model deployment (→ power-bi-deployment).
---

# power-bi-report-management

Fabric REST API transport for Power BI report items — PBIR-aware CRUD with
LRO support, binding verification, and smart create-vs-update detection.

## Quick Reference

```bash
# List all reports in a workspace
pbi fabric report list --workspace <workspace-id>
pbi fabric report list --workspace <workspace-id> --json

# Get report metadata
pbi fabric report get --workspace <workspace-id> --report "Sales Dashboard"
pbi fabric report get --workspace <workspace-id> --report <report-id>

# Download PBIR definition to local folder (pull)
pbi fabric report pull --workspace <workspace-id> --report "Sales Dashboard"
pbi fabric report pull --workspace <workspace-id> --report "Sales Dashboard" \
  --output ./local/Sales.Report

# Publish local PBIR folder to Fabric (push — create or update)
# New report (create) — --dataset-id rebinds the local byPath model to the Fabric model:
pbi fabric report push --workspace <workspace-id> --report "Sales Dashboard" \
  --definition ./Sales.Report --dataset-id <semantic-model-id>

# Existing report (update definition in-place):
pbi fabric report push --workspace <workspace-id> --report "Sales Dashboard" \
  --definition ./Sales.Report

# Publish with binding verification (recommended before first publish):
pbi fabric report push --workspace <workspace-id> --report "Sales Dashboard" \
  --definition ./Sales.Report --dataset-id <semantic-model-id> --bind-verify

# Publish with a table rename (migration where the target model renamed a table):
pbi fabric report push --workspace <workspace-id> --report "Sales Dashboard" \
  --definition ./Sales.Report --dataset-id <semantic-model-id> \
  --bind-verify --remap "Sales Data=Sales"

# Update display name or description only
pbi fabric report update --workspace <workspace-id> --report "Sales Dashboard" \
  --name "Sales Executive Dashboard"

# Delete a report
pbi fabric report delete --workspace <workspace-id> --report "Sales Dashboard" --yes
```

---

## Round-Trip Workflow

The standard pattern for editing a Fabric-hosted report locally:

```
1. pull        Download PBIR definition to local folder
       ↓
2. edit        Use pbi report / pbi visual / pbi filter / pbi theme commands
               (or directly edit visual.json / page.json files)
       ↓
3. validate    pbi report validate --pbip <folder>
               pbi report lint --pbip <folder>
       ↓
4. push        Upload edited definition back to Fabric (auto-detects update)
```

```bash
# Step 1 — pull
pbi fabric report pull --workspace <id> --report "Sales Dashboard" --output ./Sales.Report

# Step 2 — edit locally
pbi visual add --pbip ./Sales.Report --page "Overview" --type card --table Sales --value Revenue --measure
pbi report bookmark-add --pbip ./Sales.Report --name "EMEA Filter" --page "Overview"

# Step 3 — validate
pbi report validate --pbip ./Sales.Report
pbi report lint --pbip ./Sales.Report

# Step 4 — push
pbi fabric report push --workspace <id> --report "Sales Dashboard" --definition ./Sales.Report
```

---

## Binding Verification

Before publishing to a new workspace or rebinding to a different semantic model,
run binding verification to catch entity name mismatches early:

```bash
pbi fabric report push --workspace <target-workspace-id> \
  --report "Sales Dashboard" \
  --definition ./Sales.Report \
  --dataset-id <target-semantic-model-id> \
  --bind-verify
```

What it checks: every **table** (`Entity`), **column** (`table[column]`) and
**measure** reference in the report's visuals is compared against the target
semantic model's actual tables, columns and measures (read live via the
`executeQueries` `INFO.*` functions). Report-level measures (in
`reportExtensions.json`) are recognised as valid. Any mismatches are listed by
kind with a clear error before any upload begins. If the model cannot be queried
the push **fails closed** — it never silently reports "passed".

Common mismatch causes:
- Source model uses `'Sales Data'`, target uses `'Sales'` (rename during migration)
- Development model has staging prefix (`stg_Orders`), production doesn't
- Entity casing differs (`FactSales` vs `factSales`)
- A column or measure was renamed/removed in the target model

**Fixing a rename:** pass `--remap "Old Name=New Name"` (repeatable) to rewrite
table references on a temp copy before push — your local files are not modified.

**Binding mode:** when `--dataset-id` is given, `push` rewrites the report's
`definition.pbir` from a local `byPath` model reference to a Fabric `byConnection`
reference automatically. This is required for first-time publish of a
locally-authored `.pbip` — without it the report uploads unbound and every visual
renders empty.

---

## Format Rules

- Always use PBIR format (not PBIR-Legacy). The `pull` command requests
  `?format=PBIR` automatically.
- If a pull returns no parts or the definition contains `"format": "PBIR-Legacy"`,
  the report was saved in an older format — open in Power BI Desktop, save as
  `.pbip`, then use `pbi fabric item create` to re-publish in PBIR format.

---

## LRO (Long-Running Operations)

`pull`, `push` (create and update), all run asynchronous Fabric API operations
that may return `202 Accepted`. The CLI polls automatically until the operation
completes or times out (default 300 s). No manual polling needed.

---

## Authentication

The CLI uses the same token resolution as all `pbi fabric` commands:

1. `PBI_REST_BEARER` or `FABRIC_TOKEN` environment variable (recommended for CI)
2. MSAL device-flow interactive login (requires `pip install 'pbi-enterprise-cli[xmla]'`)

```bash
export PBI_REST_BEARER="eyJ0eXAiOiJKV1Q..."
pbi fabric report list --workspace <id>
```

---

## Workspace and Report ID Resolution

All `--workspace` and `--report` options accept either a GUID or a display name:

```bash
# By name (resolved via list API):
pbi fabric report pull --workspace "My Analytics Workspace" --report "Sales Dashboard"

# By GUID (direct, no extra API call):
pbi fabric report pull \
  --workspace 12345678-abcd-... \
  --report 87654321-dcba-...
```

Use `pbi fabric workspaces --filter "Analytics"` to look up workspace IDs.

---

## Integration with Report Planner

When using the `power-bi-report-planner` skill, the management skill handles
the final publish step automatically after local authoring completes:

```
powerbi-report-planner  →  powerbi-report-design  →  powerbi-report-management
(requirements + plan)      (local PBIR authoring)     (Fabric publish)
```
