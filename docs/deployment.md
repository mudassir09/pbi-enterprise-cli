# Deployment Guide

This document covers `pbi deploy` and `pbi snapshot` mechanics, safety model,
rollback procedures, and environment promotion workflows.

---

## Snapshot Format

Snapshots are TMDL directory exports stored under `.pbi/snapshots/`:

```
.pbi/snapshots/
  20260530_142300_before-refactor/
    .snapshot-meta.json        ← created_at, label
    tables/
      FactSales.tmdl
      DimProduct.tmdl
      _Measures.tmdl
    relationships.tmdl
    model.tmdl
    expressions.tmdl
```

TMDL (Tabular Model Definition Language) is the text-based format for Power BI
semantic models. Each `.tmdl` file is UTF-8 text and is safe to diff and commit.

---

## Diff Algorithm

`pbi snapshot diff <id>` and `pbi deploy diff --snapshot <path>` perform
**object-level diffing**:

| Object type | Added | Removed | Modified |
|-------------|-------|---------|---------|
| Tables | New tables in current model | Tables in snapshot not in current | Table properties changed |
| Columns | New columns | Removed columns | Type, format, visibility changed |
| Measures | New measures | Removed measures | Expression, format, folder changed |
| Relationships | New relationships | Removed relationships | Cross-filter, cardinality changed |
| Roles | New roles | Removed roles | Filter expressions changed |

---

## Diff Output

```
$ pbi snapshot diff 20260530_142300_before-refactor

── Schema Diff ─────────────────────────────────────────

TABLES (2 changes)
  [+] DimChannel
  [~] FactSales
      [+] column: ChannelKey (int64)
      [~] column: NetRevenue — format: "$#,##0" → "$#,##0.00"

MEASURES (3 changes)
  [+] Channel Revenue
  [~] Total Revenue — expression changed
  [-] Old Metric

RELATIONSHIPS (1 change)
  [+] FactSales[ChannelKey] → DimChannel[ChannelKey]

ROLES (no changes)
```

---

## Push Safety Model

`pbi deploy push` follows this sequence:

1. **Govern check** — if `require_govern_clean = true` in `pbi.config.toml`, blocks on errors.
2. **Auto-snapshot** — saves the current model state to `.pbi/snapshots/<timestamp>/`.
3. **XMLA push** — sends the TMDL to the target workspace.
4. **On failure** — prints the snapshot path and prompts to run `pbi snapshot restore`.

If the push partially completes (e.g., 3 of 5 tables deployed before a timeout),
the model may be in an inconsistent state. Always restore from snapshot in that case.

---

## Rollback Procedure

```bash
# 1. List available snapshots
pbi snapshot list

# 2. See what changed
pbi snapshot diff 20260530_142300_before-refactor

# 3. Restore
pbi snapshot restore 20260530_142300_before-refactor --confirm
```

---

## Environment Promotion Workflow

```bash
# Step 1: Export a snapshot from dev
pbi --connection fabric-dev deploy snapshot --output ./releases/v2.0

# Step 2: Diff against prod before pushing
pbi deploy diff --snapshot ./releases/v2.0 --connection fabric-prod

# Step 3: Push to prod (requires explicit workspace arg)
pbi --connection fabric-prod deploy push --workspace "Sales-PROD"
```

Or use the shorthand:

```bash
pbi env promote fabric-dev fabric-prod --confirm
```

---

## Fabric Git Integration

When using Fabric's native Git integration, prefer committing TMDL via the
Fabric UI or `git push` rather than using `pbi deploy push`. Use `pbi deploy`
when:

- You need to push to a workspace that is **not** Git-connected.
- You are running a CI/CD pipeline that promotes between environments.
- You need the impact analysis (`pbi deploy impact`) before pushing.

---

## Impact Analysis

```bash
pbi deploy impact --workspace "Sales-PROD"
```

Lists all downstream reports and dashboards that use the target dataset, so you
can assess the blast radius before pushing schema changes.

---

## Partition Refresh After Deploy

After a schema push, incremental refresh partitions may need processing:

```bash
pbi partition refresh --table FactSales --type full --connection fabric-prod
```

---

## deploy push Flags

| Flag | Description |
|------|-------------|
| `--workspace` | Target workspace name (required) |
| `--xmla` | Override XMLA endpoint URL |
| `--require-govern-clean` | Block if govern check has errors |
| `--dry-run` | Preview the push without applying |
