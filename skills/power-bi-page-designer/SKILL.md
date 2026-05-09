---
name: power-bi-page-designer
description: >
  Use when the user asks to create or design a complete report page from scratch for
  a specific business domain. This skill plans the full page — what visuals, in what
  order, in what position — before executing a single command. It understands business
  context and applies UX principles to produce a page that makes sense to the end user.
  Triggers on: "create a page for", "build a dashboard for", "design a supply chain page",
  "design a finance page", "design a sales page", "design a HR page", "design a page",
  "what visuals do I need for", "plan a report page", "build me a report for".
  Do NOT trigger for: adding a single visual, changing an existing layout, or theming.
requires:
  - power-bi-report
  - power-bi-visuals
  - power-bi-layout
version: "1.0"
---

# power-bi-page-designer

This skill is an orchestrator. It **thinks before it acts**.

Other skills know *how* to add a visual. This skill decides *which* visuals to add,
*in what order*, and *where* — based on the business domain and end-user needs.

**Two mandatory phases. Never skip Phase 1.**

```
Phase 1: PLAN   →  Inspect data, choose visuals, design layout on paper
Phase 2: EXECUTE →  Run commands in the correct sequence
```

---

## Quick Reference

```bash
# 1. Inspect available data
pbi model columns --pbip "C:/Reports/MyReport"

# 2. Create the page
pbi report page-add --pbip "C:/Reports/MyReport" --name "Supply Chain"

# 3. Add slicers (patch to Dropdown immediately after)
pbi visual add --pbip "..." --page "Supply Chain" --type slicer --table orders --value Date --x 16 --y 16 --width 180 --height 56

# 4. Add KPI cards in domain-logical order
pbi visual add --pbip "..." --page "Supply Chain" --type card --table orders --value "Units Shipped" --agg sum --title "Units Shipped" --x 16 --y 88 --width 300 --height 130

# 5. Add charts (half-width, 624px each)
pbi visual add --pbip "..." --page "Supply Chain" --type line --table orders --value "On Time %" --category Date --title "Delivery Trend" --x 16 --y 234 --width 624 --height 240

# 6. Verify final layout
pbi --json visual list --pbip "C:/Reports/MyReport" --page "Supply Chain"
```

---

## Phase 1: Plan (always do this first)

### Step 1 — Inspect available data

```bash
pbi model tables --pbip "C:/Reports/MyReport"
pbi model columns --pbip "C:/Reports/MyReport"
```

Note every column and its data type. Identify:
- **Date/time columns** → candidates for time-axis (line charts) and date slicers
- **Categorical columns** (text) → candidates for bar chart axes and slicers
- **Numeric columns** → candidates for KPI cards and chart values
- **Existing measures** → prefer measures over raw column aggregates for KPI cards

### Step 2 — Identify the domain and its natural KPI sequence

Match the page subject to a domain pattern below.
The KPI card order is the P&L / logical flow — never alphabetical, never arbitrary.

#### Finance / P&L
```
Slicers:  Year | Period | Segment
Cards:    Gross Sales  →  Discounts  →  COGS  →  Net Profit  →  Profit Margin %
Charts:   Revenue trend (line, time axis)
          Profit by Segment (bar)
          Cost breakdown by Product (column)
          Discount by Band (bar)
Detail:   P&L summary table (Segment × Revenue / Cost / Profit)
```
*Story: "We made X, gave back Y in discounts, spent Z in costs, kept W."*

#### Sales
```
Slicers:  Date | Region | Product | Sales Rep
Cards:    Total Revenue  →  Units Sold  →  Avg Order Value  →  Win Rate
Charts:   Revenue by Region (bar)
          Sales trend over time (line)
          Top Products by Revenue (column)
          Sales Rep leaderboard (bar, sorted desc)
Detail:   Order detail table
```
*Story: "How much did we sell, where, and who drove it?"*

#### Supply Chain / Operations
```
Slicers:  Date | Supplier | Product Category | Region
Cards:    Units Ordered  →  Units Shipped  →  On-Time Delivery %  →  Stockout Rate  →  Inventory Turnover
Charts:   Delivery performance trend (line)
          On-Time % by Supplier (bar)
          Inventory by Category (column)
          Lead Time by Region (bar)
Detail:   Order / shipment detail table
```
*Story: "Did we get the right things, to the right place, on time?"*

#### HR / Workforce
```
Slicers:  Department | Employment Type | Time Period
Cards:    Total Headcount  →  Open Positions  →  Attrition Rate  →  Avg Tenure  →  Engagement Score
Charts:   Headcount by Department (column)
          Attrition trend (line)
          Tenure distribution (bar)
          Salary band breakdown (column)
Detail:   Employee roster table
```
*Story: "How many people do we have, are we keeping them, and are they growing?"*

#### Marketing
```
Slicers:  Campaign | Channel | Date
Cards:    Impressions  →  Clicks  →  Conversions  →  Cost per Acquisition  →  ROAS
Charts:   Conversion funnel by Channel (bar)
          Spend vs Revenue trend (line)
          Campaign performance (column)
          Audience breakdown (bar)
Detail:   Campaign detail table
```
*Story: "What did we spend, who did we reach, and what did we get back?"*

### Step 3 — Map available columns to the domain pattern

Cross-reference what the model actually has against the domain pattern.
Substitute or drop visuals for which no matching column exists.
If a key KPI is missing (e.g. no On-Time Delivery % column), note it and recommend
a DAX measure be created first via `pbi measure add`.

### Step 4 — Produce a written plan before touching the CLI

Write this out explicitly (in your response) before running any command:

```
PAGE: <name>
CANVAS: 1280 × 720

Row 1 — Slicers (y=16, h=56)
  [Year slicer, x=16, w=180]  [Segment slicer, x=212, w=240]
  → patch both to Dropdown after creation

Row 2 — KPI Cards (y=88, h=130)
  [Gross Sales, x=16, w=300]  [Discounts, x=332, w=300]
  [COGS, x=648, w=300]        [Net Profit, x=964, w=300]
  → P&L flow: top-line → deductions → costs → bottom-line

Row 3 — Primary Charts (y=234, h=240)
  [Discounts by Band bar, x=16, w=624]  [COGS by Product column, x=656, w=624]

Row 4 — Supporting Charts (y=490, h=214)
  [Revenue by Segment bar, x=16, w=624]  [Key Metrics multirow, x=656, w=624]

TOTAL HEIGHT: 490 + 214 = 704px  ✓ (within 720px)
TOTAL WIDTH:  656 + 624 = 1280px ✓
```

Check before executing:
- [ ] All rows reach x=1280 (full canvas width)
- [ ] Total height ≤ 720px
- [ ] KPI cards are in domain-logical order, not arbitrary
- [ ] No chart is narrower than 400px
- [ ] Slicers are flagged for Dropdown patch
- [ ] Each visual has a meaningful title

---

## Phase 2: Execute (follow this sequence exactly)

```
1. pbi report page-add          ← create the page
2. pbi visual add (slicers)     ← filters first, always
3. Patch slicers to Dropdown    ← immediately after, before anything else
4. pbi visual add (cards)       ← in domain-logical order
5. pbi visual add (charts row 3) ← primary analysis
6. pbi visual add (charts row 4) ← supporting / detail
7. pbi visual list --json       ← verify all positions are correct
```

### Slicer Dropdown patch (run for every slicer, every time)

```bash
# Find the visual.json for the slicer and change 'Basic' to 'Dropdown'
# Use the page GUID from the .Report/definition/pages/ directory

python3.13 -c "
import json, pathlib
vj = pathlib.Path('path/to/visual.json')
data = json.loads(vj.read_text(encoding='utf-8'))
data['visual']['objects']['data'][0]['properties']['mode'] = {
    'expr': {'Literal': {'Value': \"'Dropdown'\"}}
}
vj.write_text(json.dumps(data, indent=2), encoding='utf-8')
print('Patched to Dropdown')
"
```

### Standard grid coordinates (1280px canvas, 16px margin/gutter)

| Layout | x positions | Width each |
|--------|-------------|-----------|
| 2-col  | 16, 656 | 624 |
| 3-col  | 16, 448, 880 | 400 (approx) |
| 4-col cards | 16, 332, 648, 964 | 300 |

| Row | y start | Recommended height | Content |
|-----|---------|-------------------|---------|
| Slicers | 16 | 56 | Dropdown slicers |
| Cards | 88 | 130 | KPI cards |
| Charts (row 1) | 234 | 240 | Primary analysis |
| Charts (row 2) | 490 | 214 | Supporting / detail |

---

## Synergy with sibling skills

| Skill | Role in this workflow |
|-------|----------------------|
| `power-bi-report` | Create the page (`pbi report page-add`) |
| `power-bi-visuals` | Add each visual (`pbi visual add`) |
| `power-bi-layout` | Grid coordinates, sizes, UX rules, slicer patch |
| `power-bi-modeling` | If a required KPI column doesn't exist, create it as a measure first |
| `power-bi-dax` | Validate any new DAX measures before adding them to visuals |

This skill calls the others. It does not replace them.

---

## Quality checklist — verify before declaring done

Run `pbi --json visual list --pbip "..." --page "..."` and confirm:

- [ ] Slicer visualType is "slicer" and visual.json has `'Dropdown'` mode
- [ ] Cards are at consistent y and height values
- [ ] No chart width < 400px
- [ ] No visual extends beyond x=1280 or y=720
- [ ] KPI card x-positions match the 4-col grid (16, 332, 648, 964)
- [ ] Row 3 and Row 4 charts are at x=16 and x=656 (2-col grid)
- [ ] Every visual has a title set

If any check fails, fix it before asking the user to refresh the report.
