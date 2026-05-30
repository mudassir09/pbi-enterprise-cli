---
name: power-bi-filters
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for configuring filters in Power BI reports: visual-level, page-level, and
  report-level filters, filter pane setup, DAX filter patterns, cross-filtering,
  and filter context. Triggers on: "filter", "slicer", "cross-filter", "filter pane",
  "visual filter", "page filter", "report filter", "KEEPFILTERS", "REMOVEFILTERS".
version: "1.0"
---

# power-bi-filters

## Quick Reference

```bash
# Add a slicer visual (user-interactive filter)
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type slicer --table financials --value Year

# Add a slicer with multiple fields (hierarchy slicer)
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type slicer --table financials --value "Segment" --extra-columns "Country"

# Validate DAX filter expression
pbi dax validate "CALCULATE(SUM(Sales[Revenue]), Sales[Region] = \"East\")"
```

---

## Filter Scope

| Scope | Affects | Where to Set |
|-------|---------|--------------|
| Visual-level | Single visual only | visual.json `filters` array |
| Page-level | All visuals on page | page.json `filters` array |
| Report-level | All pages | report.json `filters` array |
| Slicer | All synced visuals | Interactive; stored in visual.json |

---

## Filter JSON in PBIR

### Visual-Level Filter

In `visual.json` inside the `visual` object:

```json
{
  "visual": {
    "visualType": "card",
    "filters": [
      {
        "name": "filter-abc",
        "type": "Categorical",
        "field": {
          "Column": {
            "Expression": { "SourceRef": { "Entity": "financials" } },
            "Property": "Segment"
          }
        },
        "filter": {
          "Version": 2,
          "From": [{ "Name": "f", "Entity": "financials", "Type": 0 }],
          "Where": [{
            "Condition": {
              "In": {
                "Expressions": [{ "Column": { "Expression": { "SourceRef": { "Source": "f" } }, "Property": "Segment" } }],
                "Values": [
                  [{ "Literal": { "Value": "'Government'" } }],
                  [{ "Literal": { "Value": "'Enterprise'" } }]
                ]
              }
            }
          }]
        }
      }
    ]
  }
}
```

### Date Range Filter

```json
{
  "type": "Advanced",
  "filter": {
    "Version": 2,
    "From": [{ "Name": "d", "Entity": "Date", "Type": 0 }],
    "Where": [{
      "Condition": {
        "Between": {
          "Expression": { "Column": { "Expression": { "SourceRef": { "Source": "d" } }, "Property": "Date" } },
          "LowerBound": { "Literal": { "Value": "datetime'2023-01-01T00:00:00'" } },
          "UpperBound": { "Literal": { "Value": "datetime'2023-12-31T00:00:00'" } }
        }
      }
    }]
  }
}
```

---

## DAX Filter Patterns

### Basic Filter

```dax
Revenue East = CALCULATE(SUM(Sales[Revenue]), Sales[Region] = "East")
```

### Multiple Values

```dax
Revenue EU = CALCULATE(
    SUM(Sales[Revenue]),
    Sales[Region] IN {"France", "Germany", "UK"}
)
```

### Remove All Filters (Total)

```dax
Total Revenue All = CALCULATE(SUM(Sales[Revenue]), ALL(Sales))
```

### Remove Specific Column Filter

```dax
Revenue All Regions = CALCULATE(SUM(Sales[Revenue]), ALL(Sales[Region]))
```

### Keep Context Filters + Add New

```dax
Revenue East Always = CALCULATE(
    SUM(Sales[Revenue]),
    KEEPFILTERS(Sales[Region] = "East")
)
```

### Time Intelligence Filters

```dax
Revenue YTD = CALCULATE(SUM(Sales[Revenue]), DATESYTD(Date[Date]))
Revenue PYTD = CALCULATE(SUM(Sales[Revenue]), DATESYTD(DATEADD(Date[Date], -1, YEAR)))
```

---

## Cross-Filter Direction

Controls which direction filter propagation flows across relationships:

| Direction | Effect | Use When |
|-----------|--------|----------|
| Single (→) | Filter flows from 1 to many side | Default; most relationships |
| Both (↔) | Filter flows both ways | Many-to-many; role-playing dims |

**Warning:** Bidirectional filters can cause unexpected results with multiple fact tables. Avoid unless necessary.

Set in TMDL:

```tmdl
relationship Sales_Date
    fromTable: Sales
    fromColumn: DateKey
    toTable: Date
    toColumn: DateKey
    crossFilteringBehavior: bothDirections  // or: oneDirection
```

---

## Slicer Configuration in PBIR

Slicer visual with list style:

```json
{
  "visual": {
    "visualType": "slicer",
    "query": {
      "queryState": {
        "Values": {
          "projections": [{
            "field": {
              "Column": {
                "Expression": { "SourceRef": { "Entity": "financials" } },
                "Property": "Year"
              }
            },
            "queryRef": "financials.Year"
          }]
        }
      }
    },
    "objects": {
      "data": [{ "properties": { "mode": { "expr": { "Literal": { "Value": "'Basic'" } } } } }],
      "selection": [{ "properties": { "selectAllCheckboxEnabled": { "expr": { "Literal": { "Value": "false" } } } } }]
    }
  }
}
```

Slicer style options for `data.mode`: `'Basic'` (list), `'Dropdown'`, `'Between'` (range), `'After'`, `'Before'`.

---

## Filter Pane Visibility

Control filter pane in `report.json`:

```json
{
  "settings": {
    "filterPaneEnabled": true,
    "defaultFilterPaneEnabled": false
  }
}
```

Hide filter pane per page in `page.json`:

```json
{
  "displayOption": "FitToPage",
  "filterConfig": {
    "filterStateEnabled": false
  }
}
```

---

## Common Filter Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Slicer not filtering visual | Visuals on different pages | Enable slicer sync across pages |
| Filter returns all rows | Filter on wrong column | Check relationship path with `pbi model relationships` |
| CALCULATE ignores slicer | Using ALL() too broadly | Use ALLEXCEPT() to preserve slicer context |
| Date slicer shows wrong range | Date table not marked | Mark Date table with `isHidden: false, dataCategory: "Time"` in TMDL |
| Cross-filter causes duplicates | Bidirectional on M2M | Use bridge table with single direction |
