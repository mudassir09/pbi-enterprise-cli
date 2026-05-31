---
name: power-bi-dax
version: "2.0"
min_cli_version: "1.0.0"
description: >
  Use for DAX measure authoring, validation, YAML unit-test suites, filter context
  reasoning, Time Intelligence patterns, optimisation, and design patterns.
  Triggers on: "write a DAX", "create a measure", "CALCULATE", "SUMX", "Time Intelligence",
  "YTD", "DATEADD", "filter context", "DAX not working", "validate this DAX",
  "pbi measure", "pbi dax", "pbi testing", "dax test suite", "pbi filter",
  "filter context", "row context", "iterator", "DAX pattern".
  Do NOT trigger for report visual layout (→ power-bi-report-design), model schema
  design (→ power-bi-modeling), or governance naming rules (→ power-bi-governance).
---

# power-bi-dax

DAX authoring, testing, filter context, Time Intelligence, and design patterns.

## Quick Reference

```bash
# Measure management
pbi measure list
pbi measure list --table Sales --json
pbi measure add --table Sales --name "Total Revenue" --expression "SUM(Sales[Revenue])" \
  --format-string "#,0.00" --description "Net revenue after discounts"
pbi measure update --table Sales --name "Total Revenue" --expression "SUM(Sales[Net])"
pbi measure delete --table Sales --name "Old Measure"
pbi measure audit                     # complexity scores, missing descriptions
pbi measure generate "YTD revenue by product" --table Sales  # AI-assisted

# DAX query and validation
pbi dax validate "TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])"
pbi dax query "EVALUATE SUMMARIZE(Sales, Sales[Region], \"Revenue\", SUM(Sales[Revenue]))"
pbi dax query --file ./queries/topN.dax --json

# Unit test suites
pbi dax test --suite ./tests/measures/time_intelligence.yaml
pbi dax test --suite ./tests/ --fail-fast
pbi dax test --suite ./tests/measures/sales.yaml --json

# Filter management
pbi filter add --visual "Sales Chart" --type relative-date --period last-30-days
pbi filter add --visual "Top Products" --type topN --field Product[Name] --n 10
pbi filter add --page "Overview" --type basic --field Region[Name] --values "EMEA,APAC"
pbi filter list
pbi filter remove --visual "Sales Chart" --type relative-date
```

---

## Worked Example 1: Add and test a YTD measure

```bash
# Add measure
pbi measure add \
  --table Sales \
  --name "YTD Revenue" \
  --expression "TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])" \
  --format-string "#,0.00" \
  --description "Revenue accumulated from 1 Jan to current date"

# Validate expression
pbi dax validate "TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])"

# Write a unit test
cat > ./tests/ytd.yaml << 'EOF'
suite: YTD Revenue
measures:
  - name: YTD Revenue
    table: Sales
    tests:
      - description: "Full year 2024 = sum of all 2024 rows"
        filters:
          Calendar[Year]: 2024
          Calendar[Date]: "2024-12-31"
        expected: 4823991.50
        tolerance: 0.01
      - description: "January only"
        filters:
          Calendar[Year]: 2024
          Calendar[MonthNum]: 1
        expected: 341200.00
        tolerance: 0.01
EOF

pbi dax test --suite ./tests/ytd.yaml
```

---

## Worked Example 2: Audit all measures missing a format string and fix in batch

```bash
# Get all measures missing format strings as JSON
pbi measure audit --json | jq '[.[] | select(.formatString == null or .formatString == "")]'

# Fix each one (example loop)
pbi measure audit --json \
  | jq -r '.[] | select(.formatString == null) | [.table, .name] | @tsv' \
  | while IFS=$'\t' read table name; do
      pbi measure update --table "$table" --name "$name" --format-string "#,0.00"
    done
```

---

## Worked Example 3: CI-safe DAX test suite

```yaml
# .github/workflows/dax-tests.yml
- name: Run DAX unit tests
  run: pbi --backend mock dax test --suite ./tests/measures/ --json > dax-results.json
- name: Upload results
  uses: actions/upload-artifact@v4
  with:
    name: dax-test-results
    path: dax-results.json
```

Unit test YAML schema:
```yaml
suite: Sales Measures
measures:
  - name: Total Revenue
    table: Sales
    tests:
      - description: "Single row"
        context: {Sales[Revenue]: 100.00}
        expected: 100.00
      - description: "Zero when no rows"
        context: {}
        expected: 0
```

---

## Time Intelligence Pattern Library

All patterns require an active relationship between the fact table and a Calendar table with a contiguous date range.

```dax
-- Year-to-date
YTD Revenue = TOTALYTD(SUM(Sales[Revenue]), Calendar[Date])

-- Fiscal YTD (June year end)
Fiscal YTD = TOTALYTD(SUM(Sales[Revenue]), Calendar[Date], "06-30")

-- Prior year same period
PY Revenue = CALCULATE(SUM(Sales[Revenue]), SAMEPERIODLASTYEAR(Calendar[Date]))

-- Year-over-year growth %
YoY Growth % =
VAR _cy = SUM(Sales[Revenue])
VAR _py = CALCULATE(SUM(Sales[Revenue]), SAMEPERIODLASTYEAR(Calendar[Date]))
RETURN DIVIDE(_cy - _py, _py)

-- Rolling 12 months
R12M Revenue = CALCULATE(
    SUM(Sales[Revenue]),
    DATESINPERIOD(Calendar[Date], LASTDATE(Calendar[Date]), -12, MONTH)
)

-- Month-to-date
MTD Revenue = TOTALMTD(SUM(Sales[Revenue]), Calendar[Date])

-- Quarter-to-date
QTD Revenue = TOTALQTD(SUM(Sales[Revenue]), Calendar[Date])
```

---

## Filter Context Patterns

```dax
-- Remove all filters on a table
All Revenue = CALCULATE(SUM(Sales[Revenue]), ALL(Sales))

-- Remove filters on one column
Unfiltered Product Revenue = CALCULATE(SUM(Sales[Revenue]), ALL(Product[Category]))

-- Preserve context, add a filter
High Value Sales =
CALCULATE(SUM(Sales[Revenue]), Sales[Amount] > 1000)

-- ALLEXCEPT — remove all but selected columns
Region Total = CALCULATE(SUM(Sales[Revenue]), ALLEXCEPT(Sales, Sales[Region]))

-- KEEPFILTERS — don't override existing filters
Revenue (safe) = CALCULATE(SUM(Sales[Revenue]), KEEPFILTERS(Sales[Status] = "Active"))
```

---

## VAR / RETURN pattern (always prefer over repeated expressions)

```dax
Margin % =
VAR _revenue = SUM(Sales[Revenue])
VAR _cost    = SUM(Sales[Cost])
VAR _margin  = _revenue - _cost
RETURN
    DIVIDE(_margin, _revenue, 0)
```

---

## Anti-patterns to avoid

| Anti-pattern | Problem | Fix |
|---|---|---|
| `FILTER(ALL(Table), ...)` in CALCULATE | Scans entire table, ignores existing filters | Use `KEEPFILTERS` or column filter |
| Nested CALCULATE without purpose | Confusing, often redundant | Flatten into one CALCULATE |
| Hardcoded years: `[Year] = 2024` | Breaks in next calendar year | Use `YEAR(TODAY())` |
| `COUNTROWS(FILTER(...))` | Slow for large tables | Use `CALCULATE(COUNTROWS(...), ...)` |
| `IF(ISBLANK(x), 0, x)` | Verbose | Use `x + 0` or `COALESCE(x, 0)` |

---

## Edge Cases

**DAX validation returns "column not found":** The expression references a column name that doesn't match the model exactly — DAX is case-insensitive but the table/column must exist. Run `pbi model columns --table <name>` to confirm exact names.

**Unit test fails with "context mismatch":** The mock backend applies filter context differently from Desktop for complex CALCULATE chains. Add `--backend desktop` to run tests against the live model for verification.

**`pbi measure generate` (AI) produces wrong format string:** Pass `--format-string` explicitly to override the generated value. AI generation is a starting point, not a final answer.

---

## Cross-skill handoffs

- Model schema (adding tables, relationships) → **power-bi-modeling**
- Report-level and visual filters in the canvas → **power-bi-report-design**
- Governance check on measure naming and descriptions → **power-bi-governance**
- Performance profiling of slow DAX → **power-bi-performance**
