---
name: power-bi-performance
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for Power BI performance optimization: query optimization, aggregations,
  VertiPaq engine, DirectQuery tuning, composite models, and slow visual diagnosis.
  Triggers on: "performance", "slow", "aggregation", "VertiPaq", "DirectQuery",
  "composite model", "query folding", "pre-aggregation", "report takes long to load".
version: "1.0"
---

# power-bi-performance

## Quick Reference

```bash
# Audit measure complexity
pbi measure audit --json | jq '.[] | select(.complexityScore > 30)'

# Check relationships for performance issues
pbi model relationships --json

# Validate a DAX query execution plan
pbi dax query "EVALUATE ROW(\"Total\", [Total Sales])"

# Run performance diagnostics
pbi doctor --performance
```

---

## VertiPaq Storage Engine

Power BI uses VertiPaq (xVelocity in-memory columnar storage):

| Characteristic | Detail |
|----------------|--------|
| Storage | Columnar, dictionary-encoded |
| Compression | Run-length encoding (RLE) per column |
| Cardinality | High-cardinality columns compress poorly |
| Best for | < 200M rows; < 100 columns per table |

### Column Cardinality Impact

| Column Type | Cardinality | Compression | Action |
|------------|-------------|-------------|--------|
| Status (Low/Med/High) | 3 | Excellent | Keep |
| Country | 50 | Very good | Keep |
| Product SKU | 50,000 | Good | Keep if needed |
| Order ID | 10,000,000 | Poor | Remove if not needed |
| Timestamp (seconds) | Very high | Very poor | Round to day/hour |

---

## Import vs. DirectQuery vs. Composite

| Mode | Pros | Cons | Use When |
|------|------|------|----------|
| Import | Fast queries; full DAX | Data is stale until refresh; size limit | < 1GB model; batch analytics |
| DirectQuery | Always current; no size limit | Slow queries; limited DAX | Real-time; very large data |
| Dual | Both — auto-selects best | Complex setup | Dimensions in DQ models |
| Composite | Mix Import + DQ | Complex; relationship limits | Large DQ fact + Import dims |

---

## DAX Performance Patterns

### Fast Patterns

```dax
-- PREFER: Simple filter argument
Revenue East = CALCULATE(SUM(Sales[Revenue]), Sales[Region] = "East")

-- PREFER: COUNTROWS over COUNT
Row Count = COUNTROWS(Sales)

-- PREFER: DISTINCTCOUNT directly
Unique Customers = DISTINCTCOUNT(Sales[CustomerID])

-- PREFER: Pre-calculated date boundaries
Last 12 Months Revenue = CALCULATE(
    SUM(Sales[Revenue]),
    DATESINPERIOD(Date[Date], MAX(Date[Date]), -12, MONTH)
)
```

### Slow Patterns to Avoid

```dax
-- AVOID: FILTER(ALL()) iterates full table
Revenue East SLOW = CALCULATE(
    SUM(Sales[Revenue]),
    FILTER(ALL(Sales), Sales[Region] = "East")
)

-- AVOID: Nested row-by-row iterators
Complex = SUMX(Products, SUMX(RELATEDTABLE(Sales), Sales[Revenue]))
-- PREFER: SUMMARIZE then aggregate

-- AVOID: COUNT on non-key column (scans all rows)
Order Count = COUNT(Sales[OrderDate])
-- PREFER:
Order Count = COUNTROWS(Sales)

-- AVOID: IF with complex both-branch evaluation
Bad Metric = IF([Profit] > 0, SUMX(...), SUMX(...))
-- PREFER: Store branching result in variable
Good Metric = VAR _profit = [Profit]
              VAR _if_positive = SUMX(...)
              VAR _if_negative = SUMX(...)
              RETURN IF(_profit > 0, _if_positive, _if_negative)
```

---

## Aggregations (Pre-aggregated Tables)

For tables > 50M rows, create an aggregation table:

### Source Table (Detail)
```
Sales: 50M rows — DateKey, ProductKey, CustomerKey, Revenue, Quantity
```

### Aggregation Table
```
Sales_Agg: 50K rows — DateKey, ProductKey, SUM(Revenue), SUM(Quantity), COUNT(*)
```

### TMDL Configuration

```tmdl
table Sales_Agg
    column DateKey
        dataType: int64
    column ProductKey
        dataType: int64
    column Revenue_SUM
        dataType: double
        summarizeBy: sum

    aggregation
        groupBy: DateKey
        groupBy: ProductKey
        measure: Revenue_SUM → SUM(Sales[Revenue])
        measure: Row_Count → COUNTROWS(Sales)
```

Power BI automatically routes queries: if the query can be answered from `Sales_Agg`, it uses that; otherwise falls back to `Sales`.

---

## Query Folding (DirectQuery)

Query folding = pushing transformations to the source database (not run in Power BI).

### Foldable Operations

```powerquery
// These fold to SQL WHERE clause
Table.SelectRows(source, each [Region] = "East")
Table.SelectColumns(source, {"DateKey", "Revenue"})
Table.Group(source, {"DateKey"}, {{"Revenue", List.Sum, type number}})
```

### Non-Foldable (breaks folding)

```powerquery
// These break query folding — avoid in large tables
Table.AddColumn(source, "Custom", each Text.Upper([Region]))  // custom function
Table.Buffer(source)
Table.Distinct(source)
```

Check if folding is active: right-click a step in Power Query → "View Native Query". If grayed out, folding is broken.

---

## Relationship Performance

### Single-direction (recommended)

```
Date[DateKey] → Sales[DateKey]   -- filter from Date to Sales
```

### Avoid Bidirectional

Bidirectional relationships cause:
- Fan trap issues with multiple fact tables
- Slower query performance (double filter propagation)
- Unexpected DISTINCTCOUNT results

```bash
# Find all bidirectional relationships
pbi model relationships --json | jq '.[] | select(.crossFilteringBehavior == "bothDirections")'
```

---

## Partition Strategy for Performance

Large tables should be partitioned — queries that target a date range skip irrelevant partitions:

| Table Size | Partition By | Estimated Speedup |
|------------|-------------|-------------------|
| 1M–50M rows | Monthly | 10–12× |
| 50M–500M rows | Weekly or Daily | 30–50× |
| > 500M rows | Daily + DirectQuery current | 100×+ |

---

## Performance Monitoring

```bash
# Find high-complexity measures (primary slow-query cause)
pbi measure audit --json

# Check for inactive relationships being used
pbi model relationships --json | jq '.[] | select(.isActive == false)'

# List large tables by row count
pbi model tables --json | jq 'sort_by(-.rowCount)'
```

---

## Common Performance Fixes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| All visuals slow | High-cardinality column | Remove or reduce precision (round timestamps) |
| Single visual slow | Complex DAX measure | Refactor to remove nested iterators |
| First load slow | No aggregation table | Add agg table for large fact tables |
| DirectQuery timeouts | Source query not folding | Check for non-foldable Power Query steps |
| Refresh takes hours | No incremental refresh | Configure RangeStart/RangeEnd partition |
| Filter propagation wrong | Bidirectional relationship | Switch to single direction |
