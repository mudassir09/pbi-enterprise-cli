---
name: power-bi-audit
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for auditing and snapshotting Power BI models: capturing model state at a point in
  time, diffing snapshots to detect drift, auditing measure usage, orphan detection, and
  producing audit reports for compliance. Triggers on: "audit", "snapshot", "model diff",
  "drift detection", "orphan measures", "unused visuals", "compliance report", "pbi audit",
  "pbi snapshot", "model change history".
version: "1.0"
---

# power-bi-audit

## Quick Reference

```bash
# Capture a snapshot of the current model state
pbi audit snapshot --output ./snapshots/2026-05-30.json

# Diff two snapshots to see what changed
pbi audit diff --before ./snapshots/baseline.json --after ./snapshots/2026-05-30.json

# Audit all measures for usage (finds orphans not referenced in any visual)
pbi audit measures

# Audit all visuals for referencing deprecated/deleted measures
pbi audit visuals

# Full audit report (measures + visuals + relationships + governance)
pbi audit report --output ./audit-report.json

# Schedule regular snapshots (via cron)
pbi audit snapshot --output "./snapshots/$(date +%Y-%m-%d).json"
```

---

## Snapshots

`pbi audit snapshot` captures a complete model state including:

- All tables, columns, and their metadata
- All measures (name, expression, format string, description)
- All relationships
- All report pages, visuals, and their measure bindings
- Governance rule results at time of snapshot

Snapshot format (excerpt):

```json
{
  "snapshotAt": "2026-05-30T10:15:00Z",
  "modelVersion": "4.0.0",
  "tables": [...],
  "measures": [
    {
      "table": "Sales",
      "name": "Total Revenue",
      "expression": "SUM(Sales[Revenue])",
      "formatString": "$#,0.00",
      "description": "Sum of all sales revenue",
      "usedInVisuals": ["Sales Overview / KPI", "Detail / Table"]
    }
  ],
  "governance": {
    "errors": 0,
    "warnings": 2
  }
}
```

---

## Model Diff

`pbi audit diff` compares two snapshots and produces a structured change report:

```
pbi audit diff --before ./snapshots/baseline.json --after ./snapshots/2026-05-30.json

Changes detected (8 total):

  ADDED measures (2):
    + Sales[Profit Margin %]    — new measure, no description
    + Sales[Units Returned #]   — new measure

  MODIFIED measures (3):
    ~ Sales[Total Revenue]
        expression changed:
          - SUM(Sales[Revenue])
          + SUMX(Sales, Sales[Quantity] * Sales[UnitPrice])
    ~ Sales[YTD Revenue]
        formatString changed: "$#,0" → "$#,0.00"
    ~ Products[Avg Price]
        description added: "Average unit price across all products"

  REMOVED measures (1):
    - Sales[Old Metric]         — was referenced in 0 visuals (safe to delete)

  RELATIONSHIP changes (1):
    ~ Sales → Returns: direction changed Single → Both (⚠️ potential fan trap)

  GOVERNANCE delta:
    errors:   0 → 0   (unchanged)
    warnings: 1 → 3   (+2 new warnings)
```

---

## Measure Usage Audit

```bash
pbi audit measures

┌─ Measure Usage Report ────────────────────────────────────────────────────┐
│ Status    │ Measure                  │ Visuals  │ Referenced By           │
│ ✓ Active  │ Sales[Total Revenue]     │ 8        │ YTD Revenue, MoM Change │
│ ✓ Active  │ Sales[YTD Revenue]       │ 3        │ (base measure)          │
│ ⚠ Unused  │ Sales[Old Metric]        │ 0        │ (none)                  │
│ ⚠ Unused  │ Products[Test Measure]   │ 0        │ (none)                  │
│ ✓ Active  │ Products[Avg Price]      │ 2        │ Margin %, Revenue check │
└───────────────────────────────────────────────────────────────────────────┘

2 orphan measures found. Remove with: pbi measure remove --name "Old Metric"
```

---

## Visual Audit

```bash
pbi audit visuals

Checking all visuals for broken measure references...

  ✓ Sales Overview / KPI "Revenue"         — OK
  ✓ Sales Overview / Bar Chart             — OK
  ✗ Detail Page / Matrix                   — references deleted measure "Revenue (OLD)"
  ✗ Exec Summary / Card                    — references deleted measure "Test Measure"

2 visuals have broken references. Open in Desktop to reassign measures.
```

---

## Full Audit Report

```bash
pbi audit report --output ./audit-report.json --format json
pbi audit report --format table    # terminal table output
```

The JSON report includes:
- Snapshot metadata (time, model version)
- Measure usage table (active / orphan)
- Visual health (OK / broken references)
- Relationship inventory
- Governance summary (errors, warnings, violations list)
- Recommended actions

---

## CI Integration — Drift Detection

```bash
# In CI: compare current model against the last released snapshot
pbi audit diff \
  --before ./snapshots/release-baseline.json \
  --after <(pbi audit snapshot --stdout) \
  --fail-on relationship-direction-change \
  --fail-on measure-removed
```

`--fail-on` accepts:
- `measure-removed` — exit 1 if any measure is removed
- `relationship-direction-change` — exit 1 on directionality change
- `governance-regression` — exit 1 if error count increases
- `orphan-added` — exit 1 if new orphan measures appear

Use in a PR gate to prevent accidental breaking changes from reaching production.
