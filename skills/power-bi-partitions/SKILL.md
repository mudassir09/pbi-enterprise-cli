---
name: power-bi-partitions
description: >
  Use for managing table partitions in Power BI semantic models: incremental
  refresh configuration, partition strategy, processing individual partitions,
  and large table optimization. Triggers on: "partitions", "incremental refresh",
  "large table", "partition strategy", "partial refresh", "RangeStart", "RangeEnd",
  "refresh policy", "historical data", "rolling window".
version: "1.0"
---

# power-bi-partitions

## Quick Reference

```bash
# Export model TMDL to inspect partition definitions
pbi database export-tmdl ./tmdl/

# After editing partition config in TMDL
pbi database import-tmdl ./tmdl/

# Push updated partition config to workspace
pbi deploy push --workspace "Dev"
```

Partition management is done via TMDL editing — there are no dedicated `pbi partitions` CLI commands yet. Export, edit, import.

---

## Incremental Refresh Setup

### Step 1: Define Parameters in Power Query

Create two parameters in your data source query:
- `RangeStart` (Date/Time, type: Date/Time)
- `RangeEnd` (Date/Time, type: Date/Time)

```powerquery
// Filter your query using these parameters
Table.SelectRows(Source, each [OrderDate] >= RangeStart and [OrderDate] < RangeEnd)
```

### Step 2: Configure Refresh Policy in TMDL

```tmdl
table Sales
    refreshPolicy: auto
    
    refreshPolicy
        incrementalGranularity: day
        rollingWindowGranularity: year
        rollingWindowPeriods: 3
        incrementalPeriods: 10
        incrementalPeriodsOffset: 0
        sourceExpression: >-
            let
                Source = Sql.Database("server", "db"),
                Sales = Source{[Schema="dbo", Item="Sales"]}[Data],
                Filtered = Table.SelectRows(Sales, each [OrderDate] >= RangeStart and [OrderDate] < RangeEnd)
            in
                Filtered
```

### Step 3: Publish and Refresh

```bash
pbi database export-tmdl ./tmdl/   # Capture partition config
pbi deploy push --workspace "Dev"
# Then trigger refresh from Power BI Service
```

---

## Partition Strategies

| Strategy | When to Use | Partition By |
|----------|-------------|-------------|
| Rolling Window | Live transactional data (3yr window) | Day/Month |
| Historical + Current | Mixed archive + live | Year (archive) + Month (current) |
| Fixed Archive | Immutable historical data | Year |
| Single Partition | Small tables (< 1M rows) | None needed |

---

## Manual Partition Definitions in TMDL

```tmdl
table Sales

    partition Sales-2023 = m
        mode: import
        source = >-
            let Source = ... in Table.SelectRows(Source, each Date.Year([Date]) = 2023)
    
    partition Sales-2024 = m
        mode: import
        source = >-
            let Source = ... in Table.SelectRows(Source, each Date.Year([Date]) = 2024)
    
    partition Sales-Current = m
        mode: import
        source = >-
            let Source = ... in Table.SelectRows(Source, each Date.Year([Date]) = Date.Year(DateTime.LocalNow()))
```

---

## Partition Sizing Guidelines

| Row Count | Recommended Partition Size | Notes |
|-----------|---------------------------|-------|
| < 1M | Single partition | No partitioning needed |
| 1M – 50M | Monthly | Good balance of refresh time vs. granularity |
| 50M – 500M | Weekly or Daily | Reduces per-refresh scope |
| > 500M | Daily + DirectQuery for current | Hybrid mode |

---

## Processing Partitions

With XMLA endpoint (Premium/Fabric):

```bash
# Export current partition state
pbi database export-tmdl ./tmdl/

# After manually updating a partition's source expression:
pbi database import-tmdl ./tmdl/
pbi deploy push --workspace "Production"

# The service then processes only modified partitions
```

---

## Common Partition Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Full refresh despite incremental config | RangeStart/RangeEnd not defined in query | Add parameter filter to Power Query step |
| Partition count explodes | Daily granularity on 10yr history | Use monthly for archive, daily for rolling window only |
| Historical partition keeps refreshing | `incrementalPeriodsOffset` too high | Set offset to 0 for complete historical freeze |
| Merge failure on publish | Partition name collision | Ensure partition names are unique in TMDL |
