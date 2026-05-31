---
name: power-bi-governance
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for Power BI governance: built-in rules, BPA (Best Practice Analyzer),
  custom plugin authoring, auto-fix, CI/CD gate, severity filtering, naming
  conventions, sensitivity labels, and compliance checks.
  Triggers on: "governance", "naming convention", "audit", "compliance", "pbi govern",
  "BPA", "Best Practice Analyzer", "naming rules", "measure naming", "table naming",
  "auto-fix", "policy", "CI gate", "exit code 1", "governance plugin",
  "custom rule", "sensitivity label", "pbi govern bpa".
  Do NOT trigger for report visual issues (→ power-bi-report-design), DAX
  expression authoring (→ power-bi-dax), or RLS security (→ power-bi-security-and-docs).
---

# power-bi-governance

## Quick Reference

```bash
# Run governance checks
pbi govern check --pbip "C:/Reports/MyReport"

# Output as JSON for CI integration
pbi govern check --json

# Auto-fix safe violations
pbi govern fix --auto

# Initialize governance config
pbi govern init

# Check only specific rules
pbi govern check --rules naming,measures

# BPA (Best Practice Analyzer) — run community rules without Tabular Editor
pbi govern bpa check                                # fetch Microsoft community rules live
pbi govern bpa check --file ./BPARules.json         # local rule file
pbi govern bpa check --url https://example.com/BPARules.json  # custom URL
pbi govern bpa check --severity error               # filter by severity (info|warning|error)
pbi govern bpa check --category Performance         # filter by category name
pbi --backend mock --json govern bpa check --file ./BPARules.json  # JSON output for CI
```

---

## governance.json Configuration

Created by `pbi govern init` at the project root:

```json
{
  "version": "1.0",
  "rules": {
    "naming": {
      "tables": {
        "pattern": "^[A-Z][a-zA-Z0-9 ]+$",
        "examples": ["Sales", "Date", "Product"],
        "forbidden": ["tbl_", "Tbl", "fact_", "dim_"]
      },
      "measures": {
        "pattern": "^[A-Z][a-zA-Z0-9 %#$]+$",
        "examples": ["Total Sales", "Profit %", "Units Sold #"],
        "forbidden": ["Measure", "measure_", "_calc", "test"]
      },
      "columns": {
        "pattern": "^[A-Z][a-zA-Z0-9 ]+$",
        "forbidden": ["ID", "Key", "_id", "_key"]
      }
    },
    "measures": {
      "require_description": true,
      "max_complexity": 50,
      "forbid_hardcoded_dates": true,
      "require_format_string": true
    },
    "tables": {
      "require_description": true,
      "max_columns": 50,
      "forbid_calculated_columns": false
    },
    "relationships": {
      "forbid_inactive": false,
      "forbid_bidirectional": true,
      "warn_many_to_many": true
    }
  },
  "severity": {
    "naming": "error",
    "measures.require_description": "warning",
    "measures.max_complexity": "error",
    "relationships.forbid_bidirectional": "warning"
  }
}
```

---

## Naming Convention Standards

### Tables

| Pattern | Good | Bad |
|---------|------|-----|
| PascalCase, no prefix | `Sales`, `DateDim` | `tbl_Sales`, `fact_sales` |
| Spaces allowed for dim tables | `Product Category` | `ProductCategory_DIM` |
| Abbreviate sparingly | `HR` (well-known) | `Emp` (unclear) |

### Measures

| Pattern | Good | Bad |
|---------|------|-----|
| Title Case with context | `Total Sales`, `Profit Margin %` | `measure1`, `TotSales` |
| Use symbols for units | `Revenue $`, `Margin %`, `Count #` | `Revenue Dollars`, `Margin Percent` |
| Group with prefix | `YTD Sales`, `YTD Profit` | `SalesYTD`, `ytd_profit` |

### Columns

| Pattern | Good | Bad |
|---------|------|-----|
| Title Case | `Order Date`, `Product Name` | `order_date`, `productName` |
| Avoid redundancy | `Name` (in Products table) | `Product Name` (in Products table) |
| Key columns: full name | `Customer ID` | `CustID`, `ID` |

---

## Governance Check Output

```
pbi govern check

[ERROR] Table "tbl_Sales" violates naming rule: forbidden prefix "tbl_"
[ERROR] Measure "measure1" violates naming rule: forbidden word "measure"
[ERROR] Measure "Total Sales" has no description
[WARN]  Relationship Sales→Product is bidirectional (potential fan trap)
[WARN]  Measure "Complex Calc" has complexity score 72 (max: 50)
[OK]    All column names pass naming rules
[OK]    No hardcoded dates found in measures

5 issues found (2 errors, 2 warnings, 1 OK)
```

Exit code 1 if any errors found (for CI gate).

---

## Auto-Fix Capabilities

`pbi govern fix --auto` can fix:

| Fix | What It Does |
|-----|-------------|
| Strip forbidden prefixes | `tbl_Sales` → `Sales` |
| Capitalize first letter | `sales` → `Sales` |
| Add empty description placeholder | Sets `description: "TODO"` |
| Convert bidirectional to single | Edits TMDL relationship |

It cannot fix (requires manual review):
- Measure renaming (breaks all DAX references)
- Complexity reduction (requires DAX rewrite)
- Hardcoded dates (requires business context)

---

## CI/CD Integration

```yaml
# GitHub Actions governance gate
- name: Governance Check
  run: pbi govern check --json > governance-report.json
  continue-on-error: false

- name: Upload Report
  uses: actions/upload-artifact@v3
  with:
    name: governance-report
    path: governance-report.json
```

JSON output structure:

```json
{
  "status": "fail",
  "errors": 2,
  "warnings": 1,
  "violations": [
    {
      "rule": "naming.tables",
      "severity": "error",
      "object": "tbl_Sales",
      "message": "Forbidden prefix 'tbl_'",
      "autoFixable": true
    }
  ]
}
```

---

## Measure Audit

```bash
pbi measure audit --json
```

Returns complexity scores and metadata for all measures:

```json
[
  {
    "name": "Total Sales",
    "table": "financials",
    "complexity": 3,
    "hasDescription": true,
    "formatString": "$#,0.00",
    "references": ["Sales", "Gross Sales"],
    "referencedBy": ["Profit Margin %", "Revenue YTD"]
  }
]
```

Complexity scoring:
- `+1` per column reference
- `+3` per iterator function (SUMX, AVERAGEX)
- `+5` per nested CALCULATE
- `+10` per FILTER(ALL(...))

---

## Common Governance Violations

| Violation | Example | Fix |
|-----------|---------|-----|
| Prefix on table | `fact_Orders` | Rename to `Orders` |
| Measure no description | `Total Revenue` | Add description in TMDL |
| Hardcoded date | `FILTER(..., [Year] = 2023)` | Use `YEAR(TODAY())` or a parameter |
| No format string | Measure returns 1234567 | Add `formatString: "$#,0.00"` |
| Bidirectional relationship | `Sales ↔ Returns` | Change to single direction |
| Orphan measure | Measure not used in any visual | Review and delete or document |
