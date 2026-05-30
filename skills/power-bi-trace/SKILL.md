---
name: power-bi-trace
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for capturing and analysing Power BI query traces: DAX query profiling, storage
  engine vs formula engine breakdown, slow query identification, VertiPaq scan analysis,
  and query plan inspection. Triggers on: "trace", "query trace", "slow query", "DAX
  performance", "storage engine", "formula engine", "VertiPaq", "query plan", "pbi trace",
  "profile DAX", "query profiler".
version: "1.0"
---

# power-bi-trace

## Quick Reference

```bash
# Start a trace session (captures all DAX queries)
pbi trace start

# Start trace and filter to queries over 500ms
pbi trace start --min-duration 500

# Stop the trace and save results
pbi trace stop --output ./traces/session.json

# Analyse a saved trace file
pbi trace analyse --file ./traces/session.json

# Analyse and show the top 10 slowest queries
pbi trace analyse --file ./traces/session.json --top 10

# Live trace — stream results to the terminal
pbi trace live --min-duration 200
```

---

## Trace Session Lifecycle

```
pbi trace start   →   (run report / interact with visuals)   →   pbi trace stop
```

Traces connect to the local Power BI Desktop instance via the XMLA endpoint on the loopback
port. Use `--port` if Desktop is running on a non-default port.

```bash
pbi trace start --port 51234
```

---

## Reading Trace Output

Each trace event maps to one of three engine components:

| Component | Abbreviation | Role |
|-----------|-------------|------|
| Formula Engine | FE | Evaluates DAX; orchestrates SE requests |
| Storage Engine | SE | Reads VertiPaq compressed columns; parallelisable |
| DirectQuery | DQ | Sends SQL to source; latency = network + DB |

A well-performing DAX query has:
- High SE parallelism (multiple SE queries running concurrently)
- Low FE time relative to total duration
- No or few DQ round-trips (for Import models)

### Sample output

```
pbi trace analyse --file ./traces/session.json --top 5

┌─ Slowest Queries ──────────────────────────────────────────────────────────┐
│ #  Duration  FE      SE      Visual                   Measure              │
│ 1  3,241ms   312ms   2,929ms Sales Overview / Matrix  YTD Revenue          │
│ 2  1,876ms   1,541ms 335ms   Sales Overview / KPI     Profit Margin %      │
│ 3   923ms    88ms    835ms   Filters / Slicer          (none — table scan) │
│ 4   441ms    210ms   231ms   Detail Page / Table      Running Total        │
│ 5   389ms    22ms    367ms   Sales Overview / Bar     Total Revenue        │
└────────────────────────────────────────────────────────────────────────────┘

Query #2 warning: FE time (1,541ms) is 82% of total — likely a complex DAX expression.
  Recommendation: check for nested FILTER(ALL(...)) or RANKX in [Profit Margin %].
```

---

## VertiPaq Scan Analysis

```bash
# Scan the loaded model and report column statistics
pbi trace vertipaq --output ./traces/vertipaq.json

# Show top 10 columns by memory footprint
pbi trace vertipaq --top-columns 10

# Show tables ordered by row count
pbi trace vertipaq --by row-count
```

### Sample VertiPaq output

```
Top 10 columns by memory (MB):
  Sales[ProductKey]         412 MB  (Dict: 2 MB, Data: 410 MB)  Cardinality: 4,200,000
  Sales[OrderDate]          318 MB  (Dict: 0 MB, Data: 318 MB)  Cardinality: 1,826
  Sales[CustomerKey]        287 MB  ...
```

High-cardinality integer key columns with no dictionary compression are the most common
cause of large model sizes. Consider integer surrogate keys and hiding them from the report
surface.

---

## Interpreting Common Performance Patterns

| Pattern | Symptom | Fix |
|---------|---------|-----|
| FE-heavy query | FE >> SE time | Simplify DAX; avoid nested iterators |
| SE scan on large table | SE time >> 1s, low parallelism | Add `SUMMARIZE` or aggregation table |
| DQ latency | DQ events in trace; user sees spinner | Optimize source SQL; add query folding |
| Cold cache | First query slow, repeat fast | Expected — VertiPaq caches after first scan |
| Many small SE queries | >50 SE events per DAX query | Likely RANKX or unbounded iterator |

---

## CI Integration — Regression Guard

```bash
# Save a baseline trace
pbi trace baseline save --file ./traces/baseline.json

# Compare current performance against baseline
pbi trace baseline compare --file ./traces/baseline.json --threshold 20%
# Exits non-zero if any query degrades by more than 20%
```

Use in CI after model changes to catch performance regressions before they reach production.
