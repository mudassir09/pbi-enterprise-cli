---
name: power-bi-visual-selection
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use when the user needs guidance on which visual to use for a specific data
  question. Triggers on: "which chart", "what visual", "best chart for", "how to
  show", "compare X and Y", "trend over time", "part of whole", "KPI visual",
  "should I use a bar or column", "table vs matrix". Do NOT trigger when the user
  already knows which visual and wants to add it — use power-bi-visuals instead.
---

# power-bi-visual-selection

## The Five Data Questions

Every data question falls into one of five categories:

| Question | Best visual family |
|----------|-------------------|
| How much? (magnitude) | Bar, Column, Waterfall |
| How did it change over time? (trend) | Line, Area, Combo |
| What is the proportion? (part of whole) | Donut, Treemap, 100% Stacked |
| How do things compare? (ranking) | Bar (sorted), Bullet |
| What is the relationship? (correlation) | Scatter, Bubble |

---

## Decision Guide

### Comparison over time → Line Chart
```
Use when: Date is on X-axis, one or more metrics on Y.
Avoid:    When fewer than 3 data points — use a Card or KPI instead.
```

### Category comparison → Bar Chart (horizontal)
```
Use when: Comparing named items (products, regions, people).
Prefer horizontal over column when category labels are long.
Sort by value descending unless chronological order matters.
```

### Column Chart
```
Use when: X-axis is time or an ordinal category with ≤ 12 items.
Avoid:    More than 15 categories on X — switch to bar or table.
```

### KPI / Card
```
Use when: Single number is the primary communication.
KPI:      Single number + trend indicator + target.
Card:     Single number only (no target or trend).
Multi-row Card: Several KPIs in a compact grid.
```

### Table vs Matrix
```
Table:   Flat list of records. Use when rows are independent entities.
Matrix:  Pivot/cross-tab. Use when you need row + column grouping.
         Never use a matrix when a bar chart communicates the same insight faster.
```

### Scatter Chart
```
Use when: Showing correlation between two numeric measures.
Add a third measure as bubble size for three-variable analysis.
Avoid:    When one axis is categorical — use bar instead.
```

### Waterfall
```
Use when: Showing how a total is built up (e.g., revenue bridge, variance).
Requires: A category axis with items that sum to a total.
```

### Treemap
```
Use when: Showing hierarchy + proportions simultaneously (e.g., product category → SKU).
Avoid:    More than 20 leaf nodes — too small to read.
```

---

## Visuals to Avoid (and why)

| Visual | Problem | Use instead |
|--------|---------|------------|
| Pie chart with > 5 slices | Angles are hard to compare | Bar chart |
| 3D bar / 3D pie | Distorts proportions | 2D equivalent |
| Gauge (speedometer) | Wastes space, one number | Card + conditional formatting |
| Radar / Spider | Difficult to read accurately | Table or small multiples |
| Clustered bar with > 4 series | Cognitive overload | Small multiples or filter |

---

## AppSource Recommendations

| Use case | AppSource visual |
|----------|-----------------|
| Gantt / timeline | Timeline by OKViz |
| Bullet charts | Bullet Chart by OKViz |
| Small multiples | Small Multiples by OKViz |
| Sankey / flow | Sankey Chart |
| Advanced KPI | KPI Ticker |
| Word cloud | Word Cloud |
| Chord diagram | Chord by Microsoft |

---

## CLI Command

Once you've decided on a visual:
```bash
pbi visual add --type barChart --title "Revenue by Region" --page "Overview"
```

Supported visual types: `barChart`, `columnChart`, `lineChart`, `areaChart`,
`scatterChart`, `pieChart`, `donutChart`, `treemap`, `waterfall`, `funnel`,
`card`, `multiRowCard`, `kpiVisual`, `tableEx`, `matrix`, `slicer`.
