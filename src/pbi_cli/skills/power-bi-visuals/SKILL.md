---
name: power-bi-visuals
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for adding, configuring, and managing visuals on Power BI report pages in
  .pbip projects. Triggers on: "add a visual", "create a chart", "add a card",
  "bar chart", "line chart", "table visual", "slicer", "pbi visual add",
  "visual not showing data", "visual types", "PBIR visual".
version: "1.0"
---

# power-bi-visuals

## Quick Reference

```bash
# List visuals on a page
pbi visual list --pbip "C:/Reports/MyReport" --page "Executive Summary"

# Add a KPI card
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type card --table financials --value Sales --title "Total Sales"

# Add a bar chart (category + value)
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type bar --table financials --value Sales --category Country \
  --title "Sales by Country"

# Add a line chart (axis + value)
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type line --table financials --value Sales --category "Month Name" \
  --title "Sales Trend"

# Add a slicer
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type slicer --table financials --value Year

# Add a table with multiple columns
pbi visual add --pbip "C:/Reports/MyReport" --page "Sales Analysis" \
  --type table --table financials --value Sales \
  --extra-columns "Country,Segment,Profit"

# Use an explicit DAX measure (not an aggregate column)
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type card --table financials --value "Total Sales" --measure

# Delete a visual
pbi visual delete --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --name abc123def456
```

---

## Visual Type Reference

| `--type` | Power BI Type | Required Options | Notes |
|----------|--------------|-----------------|-------|
| `card` | Card | `--value` | Single KPI value |
| `bar` | Clustered bar | `--value`, `--category` | Horizontal bars |
| `column` | Clustered column | `--value`, `--category` | Vertical bars |
| `line` | Line chart | `--value`, `--category` | Trend over time |
| `table` | Table | `--value` | `--extra-columns` for more fields |
| `slicer` | Slicer | `--value` | List-style filter |
| `multirow` | Multi-row card | `--value` | `--extra-columns` for more |

---

## Aggregation Options (`--agg`)

| Value | Function | Use When |
|-------|----------|----------|
| `sum` (default) | SUM() | Revenue, quantity, amount |
| `avg` | AVERAGE() | Ratings, prices, rates |
| `count` | COUNT() | Number of records |
| `min` | MIN() | Earliest date, lowest value |
| `max` | MAX() | Latest date, highest value |
| `none` | No aggregation | Category columns (Country, Segment) |

Use `--measure` flag when the field is an explicit DAX measure (not a column aggregate).

---

## Positioning

By default, visuals are auto-positioned after existing visuals. Override with:

```bash
pbi visual add ... --x 16 --y 152 --width 600 --height 360
```

Canvas is 1280×720. Coordinates start at top-left (0,0).

### Default Sizes

| Type | Width | Height |
|------|-------|--------|
| card | 200 | 120 |
| bar / column / line | 600 | 400 |
| table | 900 | 500 |
| slicer | 200 | 400 |
| multirow | 300 | 200 |

---

## Visual JSON Format (PBIR GA)

Each visual is stored in `definition/pages/{pageId}/visuals/{visualId}/visual.json`:

```json
{
  "$schema": "https://developer.microsoft.com/.../visualContainer/2.9.0/schema.json",
  "name": "abc123def456",
  "position": { "x": 16, "y": 16, "z": 0, "width": 200, "height": 120, "tabOrder": 0 },
  "visual": {
    "visualType": "card",
    "query": {
      "queryState": {
        "Values": {
          "projections": [
            {
              "field": { "Aggregation": { "Expression": { "Column": { "Expression": { "SourceRef": { "Entity": "financials" } }, "Property": "Sales" } }, "Function": 0 } },
              "queryRef": "Sum(financials[Sales])"
            }
          ]
        }
      }
    },
    "objects": {},
    "visualContainerObjects": {
      "title": [{ "properties": { "show": { "expr": { "Literal": { "Value": "true" } } }, "text": { "expr": { "Literal": { "Value": "'Total Sales'" } } } } }]
    }
  }
}
```

---

## Visual Recommendation Guide

| Scenario | Recommended Visual |
|----------|--------------------|
| Single KPI value | card |
| Compare categories | bar (horizontal) or column (vertical) |
| Show trend over time | line |
| Show composition (% of total) | bar with % axis |
| Multi-value lookup | table or multirow card |
| Filter the page | slicer |
| Distribution | scatter (not yet in pbi-cli) |
| Geographic data | map (not yet in pbi-cli) |

Run `pbi visual recommend --measures "Total Sales,Profit,Units"` for AI-powered recommendations.

---

## Common Visual Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Visual appears empty after reload | Field name typo | Run `pbi model columns` to verify exact column name |
| Schema validation errors | Wrong `$schema` URL | Ensure `visualContainer/2.9.0/schema.json` |
| "Additional property" error | Old `projections` format | Use new `query.queryState` format (current pbi-cli version) |
| Title not showing | `visualContainerObjects` missing | Pass `--title` flag to `pbi visual add` |
| All visuals stack at same position | Auto-position bug | Use explicit `--x` and `--y` flags |
