---
name: power-bi-performance
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for query performance tracing, benchmarking, VertiPaq Analyzer diagnostics,
  storage engine vs formula engine analysis, and slow DAX investigation.
  Triggers on: "slow query", "performance", "VertiPaq", "trace", "benchmark",
  "storage engine", "formula engine", "DirectQuery slow", "cardinality",
  "pbi trace", "pbi benchmark", "DAX Studio equivalent", "query plan",
  "memory pressure", "model size".
  Do NOT trigger for DAX expression authoring (→ power-bi-dax) or model
  schema redesign (→ power-bi-modeling).
---

# power-bi-performance

Query tracing, benchmarking, VertiPaq analysis, and storage/formula engine diagnostics.

## Quick Reference

```bash
# Trace a DAX query
pbi trace start --query "EVALUATE SUMMARIZE(Sales, Calendar[Year], \"Rev\", SUM(Sales[Revenue]))"
pbi trace start --measure "Total Revenue" --duration 30s
pbi trace start --query-file ./queries/slow.dax --output ./traces/slow-trace.json

# Benchmark a measure
pbi benchmark --measure "Total Revenue" --iterations 10
pbi benchmark --measure "YTD Revenue" --iterations 20 --json

# VertiPaq / model size analysis
pbi trace model-stats
pbi trace model-stats --json | jq '.tables | sort_by(.sizeBytes) | reverse | .[0:5]'
```

---

## Worked Example 1: Profile a slow visual

```bash
# 1 — Capture a trace while the slow visual refreshes
pbi trace start --duration 60s --output ./traces/dashboard-trace.json

# (manually refresh the slow visual in Desktop during the 60s window)

# 2 — Inspect the trace
cat ./traces/dashboard-trace.json | jq '.events[] | select(.durationMs > 500)'

# 3 — Benchmark the suspected measure
pbi benchmark --measure "Complex KPI" --iterations 20 --json
```

---

## Worked Example 2: VertiPaq table size analysis

```bash
pbi trace model-stats --json > model-stats.json

# Top 5 tables by size
jq '.tables | sort_by(.sizeBytes) | reverse | .[0:5] | 
    .[] | {name: .name, sizeMB: (.sizeBytes / 1048576 | round), 
           rows: .rowCount, cardinality: .columnCardinality}' model-stats.json
```

Expected output:
```json
{"name": "Sales", "sizeMB": 842, "rows": 42000000, "cardinality": 450000}
{"name": "WebEvents", "sizeMB": 214, "rows": 180000000, "cardinality": 98000}
```

High cardinality on a column that isn't used in relationships or slicers is a top candidate for removal.

---

## Worked Example 3: Identify formula engine vs storage engine bottleneck

```bash
pbi trace start --measure "Expensive KPI" --duration 10s --output ./traces/kpi.json

# Formula engine time > 80% of total → DAX rewrite needed
# Storage engine time > 80% → data model restructuring needed
jq '{
  totalMs: .summary.durationMs,
  formulaEngineMs: .summary.formulaEngineMs,
  storageEngineMs: .summary.storageEngineMs,
  fePercent: (.summary.formulaEngineMs / .summary.durationMs * 100 | round)
}' ./traces/kpi.json
```

---

## Storage vs Formula Engine Decision Guide

| Symptom | Engine | Diagnosis |
|---|---|---|
| Query fast in cache, slow on cold start | Storage engine | Compression issue or high cardinality |
| Query always slow regardless of cache | Formula engine | Inefficient DAX — iterators, nested CALCULATE |
| DirectQuery slow | Storage engine | SQL query sent to source; add indexes |
| `SUMMARIZE` slow | Formula engine | Replace with `SUMMARIZECOLUMNS` |
| `FILTER(ALL(Table), ...)` slow | Formula engine | Use column filter in CALCULATE instead |

---

## Common DAX Performance Fixes

| Anti-pattern | Problem | Fix |
|---|---|---|
| `FILTER(ALL(Sales), Sales[Region] = "EMEA")` | Full table scan | `CALCULATE(SUM(...), Sales[Region] = "EMEA")` |
| `SUMX(Sales, Sales[Qty] * Sales[Price])` | Row-by-row iteration | Pre-calculate in a column if static |
| Nested `CALCULATE` with multiple `FILTER` | Multiple passes | Merge filters into one `CALCULATE` |
| `RELATED()` inside iterators | Expensive lookup per row | Denormalize the column to the fact table |
| Many-to-many with bidirectional filter | Cross-filter overhead | Use `CROSSFILTER(column, column, BOTH)` only where needed |

---

## VertiPaq Optimization Targets

| Metric | Warning threshold | Action |
|---|---|---|
| Column cardinality | > 1M distinct values | Hide or remove if not used in filters/relationships |
| Table row count | > 100M rows | Consider aggregations or DirectQuery |
| Model size | > 1 GB | Apply column removal, aggregations, or Fabric DirectLake |
| String column size | > 200 MB | Replace with integer key and a lookup dimension |

---

## Edge Cases

**`pbi trace start` captures nothing:** The Desktop model must be actively running a query during the trace window. Trigger the slow visual manually during the capture period.

**Benchmark returns inconsistent results:** The first 1–2 iterations include cold-cache overhead. Discard outliers and use the median of iterations 3–N. Use `--iterations 20` for stable results.

**Model stats show unexpectedly large "hidden" columns:** Power BI creates internal date tables for each date column. Use `pbi model columns --hidden` to identify and consider disabling auto-date tables.

---

## Cross-skill handoffs

- DAX expression rewriting for performance → **power-bi-dax**
- Model schema changes (removing high-cardinality columns) → **power-bi-modeling**
- Connection/backend errors during trace → **power-bi-diagnostics**
