---
name: power-bi-report-design
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for report page management, visual authoring, bookmarks, drillthrough,
  auto-layout, tooltip pages, conditional formatting, and filter pane configuration.
  Triggers on: "add a visual", "create a page", "bookmark", "drillthrough",
  "tooltip page", "conditional formatting", "color scale", "data bar",
  "report layout", "pbi report", "pbi visual", "pbi page", "pbi layout",
  "pbi filter", "auto-layout", "page navigator", "mobile layout", "PBIR".
  Do NOT trigger for DAX measures (→ power-bi-dax), theme/brand colors
  (→ power-bi-design-system), or model schema (→ power-bi-modeling).
---

# power-bi-report-design

Report pages, visuals, bookmarks, drillthrough, auto-layout, and filter configuration.

## Quick Reference

```bash
# Page management
pbi report pages
pbi report page-add --name "Executive Summary" --type standard
pbi report page-add --name "Detail Tooltip" --type tooltip
pbi report page-add --name "Drill Detail" --type drillthrough
pbi report page-delete --name "Draft"
pbi report page-rename --old "Page 1" --new "Overview"

# Visual management (32 visual types supported)
pbi visual list
pbi visual list --page "Overview" --json
pbi visual add --page "Overview" --type clustered-bar-chart \
  --x "Calendar[MonthName]" --y "Sales[Total Revenue]" \
  --position x=40,y=120 --size w=600,h=400
pbi visual add --page "Overview" --type card --field "Sales[Total Revenue]"
pbi visual add --page "Overview" --type slicer --field "Product[Category]"
pbi visual delete --page "Overview" --name "Old Chart"
pbi visual update --page "Overview" --name "Revenue Chart" --title "Monthly Revenue"

# Conditional formatting
pbi visual format color-scale --page "Overview" --visual "Revenue Table" \
  --column "Revenue" --min-color "#FF0000" --mid-color "#FFFF00" --max-color "#00AA00"
pbi visual format data-bar --page "Overview" --visual "Sales Table" \
  --column "Units Sold" --positive-color "#0078D4"
pbi visual format icon-set --page "Overview" --visual "KPI Table" \
  --column "Status" --rules ">=90:green-circle,>=70:yellow-circle,<70:red-circle"

# Bookmarks
pbi report bookmark-add --name "EMEA View" --page "Overview"
pbi report bookmark-list
pbi report bookmark-apply --name "EMEA View"
pbi report bookmark-delete --name "EMEA View"

# Auto-layout
pbi layout auto --page "Overview" --algorithm shelf-pack
pbi layout apply-template --template financial-dashboard --page "Overview"
pbi layout list-templates

# Filters
pbi filter add --visual "Revenue Chart" --type relative-date --period last-30-days
pbi filter add --visual "Top N" --type topN --field Product[Name] --n 10
pbi filter add --page "Overview" --type basic --field Region[Name] --values "EMEA,APAC"
pbi filter list --page "Overview"
pbi filter remove --visual "Revenue Chart" --field Calendar[Date]
```

---

## Worked Example 1: Build an executive summary page from scratch

```bash
# 1 — add the page
pbi report page-add --name "Executive Summary" --type standard

# 2 — KPI cards at the top
pbi visual add --page "Executive Summary" --type card \
  --field "Sales[Total Revenue]" --position x=40,y=40 --size w=220,h=100
pbi visual add --page "Executive Summary" --type card \
  --field "Sales[Gross Margin %]" --position x=280,y=40 --size w=220,h=100
pbi visual add --page "Executive Summary" --type card \
  --field "Sales[YTD Revenue]" --position x=520,y=40 --size w=220,h=100

# 3 — Revenue trend line chart
pbi visual add --page "Executive Summary" --type line-chart \
  --x "Calendar[MonthYear]" --y "Sales[Total Revenue]" \
  --legend "Product[Category]" \
  --position x=40,y=160 --size w=700,h=300

# 4 — Page-level date slicer
pbi visual add --page "Executive Summary" --type slicer \
  --field "Calendar[Date]" --position x=40,y=480 --size w=300,h=80
pbi filter add --page "Executive Summary" --type relative-date --period current-year

# 5 — Auto-layout tidy-up
pbi layout auto --page "Executive Summary" --algorithm shelf-pack
```

---

## Worked Example 2: Drillthrough page with conditional formatting

```bash
# 1 — Create drillthrough page
pbi report page-add --name "Customer Detail" --type drillthrough
pbi report page-rename --old "Customer Detail" --new "Customer Detail"

# 2 — Add drillthrough field
pbi visual add --page "Customer Detail" --type table \
  --columns "Customer[Name],Sales[OrderDate],Sales[Revenue],Sales[Status]" \
  --position x=40,y=40 --size w=900,h=500

# 3 — Conditional formatting on Revenue column
pbi visual format color-scale \
  --page "Customer Detail" \
  --visual "Table" \
  --column "Revenue" \
  --min-color "#FFF0F0" \
  --max-color "#00AA00"

# 4 — Status icon set
pbi visual format icon-set \
  --page "Customer Detail" \
  --visual "Table" \
  --column "Status" \
  --rules "Paid:green-circle,Pending:yellow-circle,Overdue:red-circle"
```

---

## Worked Example 3: Bookmark-based navigation panel

```bash
# Create views for each region
pbi filter add --page "Overview" --type basic --field Region[Name] --values "EMEA"
pbi report bookmark-add --name "EMEA View" --page "Overview"

pbi filter add --page "Overview" --type basic --field Region[Name] --values "APAC"
pbi report bookmark-add --name "APAC View" --page "Overview"

pbi filter add --page "Overview" --type basic --field Region[Name] --values "Americas"
pbi report bookmark-add --name "Americas View" --page "Overview"

# List all bookmarks
pbi report bookmark-list --json
```

---

## Supported Visual Types (32)

| Category | Types |
|---|---|
| Charts | `bar-chart`, `clustered-bar-chart`, `stacked-bar-chart`, `line-chart`, `area-chart`, `combo-chart`, `scatter-chart`, `bubble-chart`, `waterfall-chart`, `funnel`, `pie`, `donut`, `ribbon-chart`, `treemap` |
| KPI / Single | `card`, `multi-row-card`, `kpi`, `gauge` |
| Tables | `table`, `matrix` |
| Maps | `map`, `filled-map`, `azure-map`, `shape-map` |
| Filters | `slicer` |
| AI | `decomposition-tree`, `key-influencers`, `smart-narrative`, `q-and-a` |
| Other | `image`, `text-box`, `button`, `shape` |

---

## PBIR File Format Notes

`pbi report` commands write PBIR GA format (`.pbip` projects). Key invariants:
- Bookmarks use `durableId` UUIDs — do not rename these in JSON directly
- Visual positions are in device-independent units (1 unit ≈ 1 px at 100% scale)
- Page type field values: `standard`, `tooltip`, `drillthrough`

---

## Edge Cases

**Visual add fails with "field not found":** The field path `Table[Column]` must exactly match the model. Run `pbi model columns --table <name>` to confirm.

**Auto-layout overlaps visuals:** `shelf-pack` packs left-to-right top-to-bottom; run `--algorithm grid` for fixed-grid placement instead.

**Drillthrough page not appearing in report:** The page must have at least one field set as the drillthrough target. Use `pbi visual add --page "<name>" --type drillthrough-target --field <field>`.

**Conditional formatting lost after model refresh:** Format rules reference column names; if the column is renamed in the model, re-apply the format rule.

---

## Cross-skill handoffs

- DAX measures displayed in visuals → **power-bi-dax**
- Theme colors and brand fonts → **power-bi-design-system**
- Report deployment to service → **power-bi-deployment**
- Governance check on report naming → **power-bi-governance**
- Performance profiling of slow visuals → **power-bi-performance**
