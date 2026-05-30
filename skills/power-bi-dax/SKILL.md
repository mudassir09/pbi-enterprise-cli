---
name: power-bi-dax
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for DAX measure creation, validation, testing, Time Intelligence patterns,
  CALCULATE modifiers, filter context reasoning, anti-pattern detection, and
  measure complexity analysis. Triggers on: "write a DAX", "create a measure",
  "CALCULATE", "SUMX", "Time Intelligence", "YTD", "DATEADD", "filter context",
  "DAX not working", "validate this DAX", "pbi measure", "pbi dax".
version: "1.0"
---

# power-bi-dax

## Quick Reference: pbi dax Commands

```bash
pbi dax validate "TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])"
pbi dax query "EVALUATE SUMMARIZE(Sales, Sales[Region], \"Revenue\", SUM(Sales[Revenue]))"
pbi dax test --suite ./tests/measures/time_intelligence.yaml

pbi measure add --table Sales --name "Total Revenue" --expression "SUM(Sales[Revenue])" --format-string "#,0.00"
pbi measure generate "year-to-date revenue" --table Sales --name "YTD Revenue"
pbi measure audit
pbi measure list --table Sales
```

---

## Time Intelligence Pattern Library

All Time Intelligence patterns require an active relationship between the fact table and a Calendar/Date table with a contiguous date range.

### Year-to-Date

```dax
YTD Revenue = TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])

-- With custom fiscal year end (e.g., 30 June)
YTD Revenue (FY) = TOTALYTD(SUM(Sales[Revenue]), Calendar[Date], "06/30")
```

### Same Period Last Year

```dax
Revenue LY = CALCULATE(SUM(Sales[Revenue]), SAMEPERIODLASTYEAR(Calendar[Date]))

YoY Growth % = DIVIDE([Total Revenue] - [Revenue LY], [Revenue LY])
```

### Month-over-Month

```dax
Revenue PM = CALCULATE(SUM(Sales[Revenue]), DATEADD(Calendar[Date], -1, MONTH))

MoM Change % = DIVIDE([Total Revenue] - [Revenue PM], [Revenue PM])
```

### Running Total

```dax
Running Revenue = CALCULATE(
    SUM(Sales[Revenue]),
    FILTER(ALL(Calendar[Date]), Calendar[Date] <= MAX(Calendar[Date]))
)
```

### Parallel Period (same period, prior year)

```dax
Revenue PP = CALCULATE(SUM(Sales[Revenue]), PARALLELPERIOD(Calendar[Date], -1, YEAR))
```

---

## CALCULATE Modifier Reference

| Modifier | Effect | Use When |
|----------|--------|----------|
| `ALL(Table)` | Removes all filters on table | Total, % of grand total |
| `ALL(Table[Column])` | Removes filters on one column | Rank, running total |
| `ALLEXCEPT(Table, Col1, Col2)` | Keeps only specified filters | Subtotals with context |
| `KEEPFILTERS(expr)` | Intersects rather than replaces filters | Additive filtering |
| `REMOVEFILTERS(Table)` | Alias for ALL — removes filters | Clear, explicit intent |
| `CROSSFILTER(col1, col2, dir)` | Changes relationship filter direction | Many-to-many workarounds |

---

## Filter Context Reasoning Guide

**Row context** is created by iterators (SUMX, FILTER, ADDCOLUMNS). It applies to the current row.

**Filter context** is created by slicers, visual filters, and CALCULATE. It filters the table.

```dax
-- SUMX creates row context; the inner expression sees each row
Revenue with Tax = SUMX(Sales, Sales[Revenue] * 1.1)

-- CALCULATE changes filter context; SUM sees filtered rows
East Revenue = CALCULATE(SUM(Sales[Revenue]), Sales[Region] = "East")

-- Context transition: CALCULATE inside SUMX converts row context to filter context
Sales[Revenue by Category] = SUMX(Sales, CALCULATE(SUM(Sales[Revenue])))
```

**When FILTER(ALL(...)) is needed vs. CALCULATE:**

```dax
-- This is WRONG for running totals (filters out future dates):
CALCULATE(SUM(Sales[Revenue]), Calendar[Date] <= MAX(Calendar[Date]))

-- This is CORRECT (ALL removes existing date filter first):
CALCULATE(SUM(Sales[Revenue]), FILTER(ALL(Calendar[Date]), Calendar[Date] <= MAX(Calendar[Date])))
```

---

## Common DAX Anti-Patterns

### 1. Expensive SUMX over large tables

```dax
-- AVOID: iterates every row, slow on millions of rows
Revenue = SUMX(Sales, Sales[Quantity] * Sales[Unit Price])

-- PREFER: if the calculated column already exists
Revenue = SUM(Sales[Revenue])

-- If column doesn't exist, SUMX is fine — just be aware of cardinality
```

### 2. Hardcoded dates

```dax
-- AVOID: breaks when new year arrives
YTD = CALCULATE(SUM(Sales[Revenue]), YEAR(Sales[Date]) = 2024)

-- PREFER: dynamic
YTD = TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])
```

### 3. Circular dependency

```dax
-- AVOID: Measure A references Measure B which references Measure A
[Measure A] = [Measure B] + 1
[Measure B] = [Measure A] - 1  -- circular!

-- FIX: break the cycle by referencing base columns directly
[Measure B] = SUM(Sales[Revenue]) - 1
```

### 4. Ambiguous relationship without USERELATIONSHIP

```dax
-- When Sales has both OrderDate and ShipDate relating to Calendar:
Revenue by Ship Date = CALCULATE(
    SUM(Sales[Revenue]),
    USERELATIONSHIP(Sales[ShipDate], Calendar[Date])
)
```

---

## Measure Complexity Scoring

Complexity score estimates cognitive load and execution cost. Target: < 50 per measure.

| Factor | Points |
|--------|--------|
| Each nested iterator (SUMX, FILTER, ADDCOLUMNS) | +10 |
| Each CALCULATE | +5 |
| Each ALL/ALLEXCEPT | +5 |
| Expression length > 200 chars | +10 |
| Expression length > 400 chars | +20 |
| Time Intelligence function | +5 |
| DIVIDE (safe division) | 0 (encouraged) |

Run `pbi measure audit` to compute scores for all measures.

---

## DAX Test YAML Format

```yaml
suite: "Time Intelligence Measures"
connection: mock   # or "desktop" for live tests
tests:
  - name: "YTD Revenue returns correct value for Dec 2024"
    measure: "Sales[YTD Revenue]"
    filters:
      - table: Calendar
        column: Year
        value: 2024
      - table: Calendar
        column: Month
        value: 12
    expected: 1250000
    tolerance: 0.01   # 1% tolerance for floating point

  - name: "Revenue LY is null for earliest year"
    measure: "Sales[Revenue LY]"
    filters:
      - table: Calendar
        column: Year
        value: 2020
    expected: null
```

Run: `pbi dax test --suite ./tests/measures/time_intelligence.yaml`
