---
name: power-bi-intelligence
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for AI-driven Power BI assistance: auto-generating DAX measures from plain English,
  recommending visuals for a given dataset shape, generating WCAG-compliant themes, and
  auto-arranging report layouts. Triggers on: "generate a measure", "suggest a visual",
  "recommend a chart", "auto layout", "generate theme", "AI measure", "pbi measure generate",
  "pbi visual recommend", "pbi theme generate", "layout engine", "intelligent layout".
version: "1.0"
---

# power-bi-intelligence

## Quick Reference

```bash
# Generate a DAX measure from plain English
pbi measure generate "year-to-date revenue by region" --table Sales --name "YTD Revenue"

# Recommend the best visual type for your data shape
pbi visual recommend --table Sales --columns "Region,Revenue,Date"

# Auto-generate a WCAG AA-compliant theme from a base colour
pbi theme generate --base-color "#0078D4" --output ./themes/corporate.json

# Auto-arrange all visuals on a report page using the layout engine
pbi layout arrange --page "Sales Overview" --strategy grid
pbi layout arrange --page "Sales Overview" --strategy flow
pbi layout arrange --page "Sales Overview" --strategy focus --focus-visual KPI_Revenue
```

---

## Measure Generator

`pbi measure generate` translates natural language into a DAX measure and writes it to the model.

### Supported intent patterns

| Intent phrase | Generated pattern |
|---------------|-------------------|
| "year-to-date X" | `TOTALYTD(SUM(...), Calendar[Date])` |
| "same period last year" | `CALCULATE(..., SAMEPERIODLASTYEAR(...))` |
| "% of total" | `DIVIDE([Measure], CALCULATE([Measure], ALL(Table)))` |
| "running total" | `CALCULATE(..., FILTER(ALL(Calendar[Date]), ...))` |
| "average X per Y" | `AVERAGEX(VALUES(Table[Y]), [X])` |
| "count distinct X" | `DISTINCTCOUNT(Table[X])` |
| "rank X by Y" | `RANKX(ALL(Table), [Y])` |

### Example

```bash
pbi measure generate "profit margin percentage" --table Sales --name "Profit Margin %"
# Writes to model:
# Profit Margin % = DIVIDE(SUM(Sales[Profit]), SUM(Sales[Revenue]))
# Format string: "0.00%"
```

### Flags

| Flag | Description |
|------|-------------|
| `--table` | Target table for the new measure |
| `--name` | Measure name (auto-inferred if omitted) |
| `--format-string` | Override auto-detected format string |
| `--dry-run` | Print DAX without writing to model |
| `--backend` | `mock` (default), `tom`, `pbir`, `xmla` |

---

## Visual Recommender

`pbi visual recommend` inspects column types and cardinality to suggest the most appropriate
visual type.

### Recommendation logic

| Data shape | Recommended visual | Reason |
|------------|--------------------|--------|
| 1 measure, 1 date column | Line chart | Trend over time |
| 1 measure, 1 low-cardinality category (≤10) | Bar/Column chart | Comparison |
| 1 measure, 1 high-cardinality category (>10) | Table or Treemap | Too many bars |
| 2 measures, 1 category | Clustered bar | Side-by-side comparison |
| 1 measure (single value) | Card | KPI at a glance |
| 1 measure + target | KPI visual | Progress toward goal |
| 2 numeric measures | Scatter chart | Correlation |
| Geo column + measure | Map or Filled Map | Spatial distribution |

### Example output

```
pbi visual recommend --table Sales --columns "Region,Revenue,Date"

Recommendation: Line chart (confidence: 92%)
  Reason: Revenue is a continuous numeric measure; Date is a time axis.
  Alternative: Column chart (if comparing discrete periods, not trends)

pbi visual recommend --table Sales --columns "Region,Revenue"

Recommendation: Bar chart (confidence: 87%)
  Reason: Region has 8 distinct values (low cardinality). Revenue is a measure.
  Alternative: Treemap (if hierarchy within Region exists)
```

---

## Theme Generator

`pbi theme generate` produces a Power BI theme JSON file that passes WCAG AA contrast
requirements (4.5:1 for text, 3:1 for large text and UI elements).

```bash
pbi theme generate --base-color "#0078D4" --output ./themes/corporate.json
pbi theme generate --base-color "#107C10" --name "Green Corporate" --output ./themes/green.json
pbi theme generate --base-color "#D83B01" --palette-size 8 --output ./themes/orange.json
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--base-color` | required | Hex colour — anchor of the palette |
| `--palette-size` | `6` | Number of data colours to generate |
| `--name` | derived from base colour | Theme display name |
| `--output` | `./theme.json` | Output file path |
| `--wcag-level` | `AA` | `AA` (4.5:1) or `AAA` (7:1) |

### Output format (excerpt)

```json
{
  "name": "Corporate Blue",
  "dataColors": ["#0078D4", "#004578", "#2B88D8", "#71AFE5", "#C7E0F4", "#DEECF9"],
  "background": "#FFFFFF",
  "foreground": "#323130",
  "tableAccent": "#0078D4"
}
```

---

## Layout Engine

`pbi layout arrange` repositions all visuals on a page using one of three strategies.

### Strategies

| Strategy | Description | Best for |
|----------|-------------|----------|
| `grid` | Uniform grid, all visuals equal size | Dashboards with many tiles |
| `flow` | Left-to-right, top-to-bottom, respecting visual proportions | Report pages |
| `focus` | One large focal visual + supporting tiles arranged around it | Executive summaries |

```bash
# Grid layout — 3-column grid
pbi layout arrange --page "Sales Overview" --strategy grid --columns 3

# Flow layout
pbi layout arrange --page "Sales Overview" --strategy flow

# Focus layout — Revenue KPI takes centre stage
pbi layout arrange --page "Sales Overview" --strategy focus --focus-visual KPI_Revenue

# Preview without writing changes
pbi layout arrange --page "Sales Overview" --strategy grid --dry-run
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--page` | required | Page name to rearrange |
| `--strategy` | `flow` | `grid`, `flow`, or `focus` |
| `--columns` | `3` | Column count (grid strategy only) |
| `--focus-visual` | required for `focus` | Visual name to centre |
| `--padding` | `10` | Pixel padding between visuals |
| `--dry-run` | `false` | Print new positions without writing |
