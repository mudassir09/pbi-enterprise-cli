---
name: power-bi-report-design
version: "3.0"
min_cli_version: "0.1.0"
description: >
  Use for report page management, visual authoring, bookmarks, drillthrough,
  auto-layout, tooltip pages, conditional formatting, filter pane configuration,
  design critique, chart archetype selection, anti-pattern detection, and WCAG
  accessibility audits.
  Triggers on: "add a visual", "create a page", "bookmark", "drillthrough",
  "tooltip page", "conditional formatting", "color scale", "data bar",
  "report layout", "pbi report", "pbi visual", "pbi page", "pbi layout",
  "pbi filter", "auto-layout", "page navigator", "mobile layout", "PBIR",
  "design review", "chart choice", "which visual should I use", "accessibility",
  "WCAG", "anti-pattern", "report critique", "review this report".
  Do NOT trigger for DAX measures (→ power-bi-dax), theme/brand colors
  (→ power-bi-design-system), or model schema (→ power-bi-modeling).
---

# power-bi-report-design

Report pages, visuals, bookmarks, drillthrough, auto-layout, and filter configuration.

## Quick Reference

```bash
# Page management (page-add takes --name only; no page type flag, no rename command)
pbi report pages --pbip <path>
pbi report page-add --pbip <path> --name "Executive Summary"
pbi report page-add --pbip <path> --name "Detail Tooltip"
pbi report page-delete --pbip <path> --name "Draft"
pbi report page-duplicate --pbip <path> --name "Overview"

# Visual management (32 visual types supported — all --pbip <path>)
pbi visual list --pbip <path> --page "Overview"
pbi visual list --pbip <path> --page "Overview" --json
# Chart: --table + --value (numeric) + --category (grouping); positions are integers
pbi visual add --pbip <path> --page "Overview" --type bar \
  --table Sales --value "Total Revenue" --measure --category MonthName \
  --x 40 --y 120 --width 600 --height 400
pbi visual add --pbip <path> --page "Overview" --type card --table Sales --value "Total Revenue" --measure
pbi visual add --pbip <path> --page "Overview" --type slicer --table Product --value Category
pbi visual delete --pbip <path> --page "Overview" --name "Old Chart"
pbi visual update --pbip <path> --page "Overview" --name "Revenue Chart" --title "Monthly Revenue"

# Conditional formatting (--type color-scale|data-bar|rules|icons)
pbi visual format --pbip <path> --page "Overview" --visual "Revenue Table" \
  --type color-scale --table Sales --measure Revenue
pbi visual format --pbip <path> --page "Overview" --visual "KPI Table" \
  --type rules --table Sales --measure Status \
  --rule ">=:90:#00AA00" --rule ">=:70:#FFFF00" --rule "<:70:#FF0000"

# Bookmarks
pbi report bookmark-add --pbip <path> --name "EMEA View" --page "Overview"
pbi report bookmark-list --pbip <path>
pbi report bookmark-set-visibility --pbip <path> --name "EMEA View" --visible
pbi report bookmark-delete --pbip <path> --name "EMEA View"

# Auto-layout
pbi layout auto --pbip <path> --page "Overview"
pbi layout template --name financial-report --page "Overview"

# Filters (add-value | add-relative-date | add-advanced — no generic 'filter add')
pbi filter add-relative-date --pbip <path> --page "Overview" --table Calendar --column Date --last 30 --unit Days
pbi filter add-value --pbip <path> --page "Overview" --table Region --column Name --values "EMEA,APAC"
pbi filter list --pbip <path> --page "Overview"
pbi filter clear --pbip <path> --page "Overview"
```

---

## Worked Example 1: Build an executive summary page from scratch

```bash
# 1 — add the page
pbi report page-add --pbip <path> --name "Executive Summary"

# 2 — KPI cards at the top (--measure marks --value as an explicit DAX measure)
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "Total Revenue" --measure --x 40 --y 40 --width 220 --height 100
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "Gross Margin %" --measure --x 280 --y 40 --width 220 --height 100
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "YTD Revenue" --measure --x 520 --y 40 --width 220 --height 100

# 3 — Revenue trend line chart (--series adds a legend/series field)
pbi visual add --pbip <path> --page "Executive Summary" --type line \
  --table Sales --value "Total Revenue" --measure --category MonthYear \
  --x 40 --y 160 --width 700 --height 300

# 4 — Page-level date slicer + relative-date filter
pbi visual add --pbip <path> --page "Executive Summary" --type slicer \
  --table Calendar --value Date --x 40 --y 480 --width 300 --height 80
pbi filter add-relative-date --pbip <path> --page "Executive Summary" \
  --table Calendar --column Date --last 1 --unit Years

# 5 — Auto-layout tidy-up
pbi layout auto --pbip <path> --page "Executive Summary"
```

---

## Worked Example 2: Drillthrough page with conditional formatting

```bash
# 1 — Create the detail page
pbi report page-add --pbip <path> --name "Customer Detail"

# 2 — Add a table visual (--value is the main measure, --extra-columns adds more fields)
pbi visual add --pbip <path> --page "Customer Detail" --type table \
  --table Sales --value Revenue --measure --extra-columns "OrderDate,Status" \
  --x 40 --y 40 --width 900 --height 500

# 3 — Conditional formatting: colour scale on the Revenue measure
pbi visual format --pbip <path> --page "Customer Detail" --visual "Table" \
  --type color-scale --table Sales --measure Revenue

# 4 — Rules-based colouring on a Status measure (first match wins)
pbi visual format --pbip <path> --page "Customer Detail" --visual "Table" \
  --type rules --table Sales --measure Status \
  --rule "=:1:#00AA00" --rule "=:2:#FFFF00" --rule "=:3:#FF0000"
```

---

## Worked Example 3: Bookmark-based navigation panel

```bash
# Create views for each region
pbi filter add-value --pbip <path> --page "Overview" --table Region --column Name --values "EMEA"
pbi report bookmark-add --pbip <path> --name "EMEA View" --page "Overview"

pbi filter add-value --pbip <path> --page "Overview" --table Region --column Name --values "APAC"
pbi report bookmark-add --pbip <path> --name "APAC View" --page "Overview"

pbi filter add-value --pbip <path> --page "Overview" --table Region --column Name --values "Americas"
pbi report bookmark-add --pbip <path> --name "Americas View" --page "Overview"

# List all bookmarks
pbi report bookmark-list --pbip <path> --json
```

---

## Supported Visual Types (32)

These are the exact `--type` values accepted by `pbi visual add`:

| Category | Types (`--type` values) |
|---|---|
| Charts | `bar`, `column`, `stackedbar`, `stackedcolumn`, `100percentbar`, `100percentcolumn`, `line`, `area`, `stackedarea`, `combo`, `scatter`, `bubble`, `waterfall`, `funnel`, `pie`, `donut`, `ribbon`, `treemap` |
| KPI / Single | `card`, `kpi`, `multirow`, `gauge` |
| Tables | `table`, `matrix` |
| Maps | `map`, `filledmap`, `azuremap` |
| Filters | `slicer` |
| AI | `decomptree`, `keyinfluencers`, `smartnarrative`, `qanda` |

Non-data elements (textbox, button, image, navigators) are added with
`pbi visual add-element`, not `pbi visual add`.

---

## PBIR File Format Notes

`pbi report` commands write PBIR GA format (`.pbip` projects). Key invariants:
- Bookmarks use `durableId` UUIDs — do not rename these in JSON directly
- Visual positions are in device-independent units (1 unit ≈ 1 px at 100% scale)
- Page type field values: `standard`, `tooltip`, `drillthrough`

---

## Edge Cases

**Visual add fails with "field not found":** The field path `Table[Column]` must exactly match the model. Run `pbi model columns --table <name>` to confirm.

**Auto-layout overlaps visuals:** `pbi layout auto` repacks all visuals on a page within the canvas (`--canvas-width`/`--canvas-height`, default 1280×720). For a fixed structured layout, use `pbi layout template --name <executive-dashboard|operational-monitor|financial-report|drill-through-detail> --page "<name>"` instead.

**Drillthrough page not appearing in report:** Configure the drillthrough target with `pbi report drillthrough-setup --pbip <path> --page "<name>" --table <table>`.

**Conditional formatting lost after model refresh:** Format rules reference column names; if the column is renamed in the model, re-apply the format rule.

---

## Cross-skill handoffs

- DAX measures displayed in visuals → **power-bi-dax**
- Theme colors and brand fonts → **power-bi-design-system**
- Report deployment to service → **power-bi-deployment**
- Governance check on report naming → **power-bi-governance**
- Performance profiling of slow visuals → **power-bi-performance**

---

## Implementing a Design Brief

**This skill is the IMPLEMENTER.** When `power-bi-report-planner` (the director)
hands over a `design-brief.md`, your job is to build it faithfully — not to
redesign it. Same coordinates, same titles, same display rules. The planner found
the story and laid the grid; you turn each spec row into commands and QA the result.

### Step 1 — Translate each Visual Spec row into a command

The brief's Visual Spec table maps directly to `pbi visual add`:

| Brief column | CLI flag |
|---|---|
| Type | `--type` (use the exact enum: `bar`, `line`, `column`, `card`…) |
| Table | `--table` |
| Value | `--value` (add `--measure` if the brief marks it "(measure)") |
| Category | `--category` |
| x / y / w / h | `--x` / `--y` / `--width` / `--height` (integers, exactly as specified) |
| Title | `--title` (copy the interpretive title verbatim) |

Header rows (type `textbox`) use `add-element`:

```bash
pbi visual add-element --pbip <path> --page "<page>" --type textbox \
  --text "Financial Performance Overview" --x 48 --y 24 --width 1184 --height 44
```

Build in spec order (header → KPI strip → row 2 → row 3) so list order matches reading order.

### Step 2 — Apply the display rules

The brief's "Display rules" column maps to `pbi visual set-format` (run after the
visual exists; get the visual name from `pbi visual list`):

```bash
# Data labels on
pbi visual set-format --pbip <path> --page "<page>" --name <id> \
  --object dataLabels --property show --value true --type bool

# Brand accent colour on the bars
pbi visual set-format --pbip <path> --page "<page>" --name <id> \
  --object dataPoint --property defaultColor --value "#118DFF" --type color

# Conditional formatting on a table measure
pbi visual format --pbip <path> --page "<page>" --visual <id> \
  --type color-scale --table <T> --measure <M>
```

Apply the theme last if the brief names one: `pbi theme apply --pbip <path> --theme <file>`.

### Step 3 — Design QA self-check (run before declaring done)

```bash
pbi report validate --pbip <path> --fail-on error
pbi report lint --pbip <path>
pbi report a11y --pbip <path>
```

Then verify against this checklist — fix anything that fails:

- [ ] **Aligned grid** — every visual's x/y/w/h matches the brief; left edges line up at 48, right edges at 1232
- [ ] **KPI strip present** — headline numbers across the top, equal width
- [ ] **Interpretive titles** — every chart title states a finding with a real number, not a field name
- [ ] **No redundancy** — no two visuals share the same dimension + measure
- [ ] **Reading order = story order** — header → KPIs → trend → driver → context
- [ ] **≤ 5 data visuals** plus the KPI strip
- [ ] **Numbers from the data** — titles cite figures pulled in the planner's Phase 3, not guesses
- [ ] **Validation clean** — `report validate` exits 0

Known limitation: descending bar **sort** and per-card label sizing aren't exposed
by the CLI today — note these as Desktop-side refinements rather than claiming them done.

---

## Chart Archetype Selection

Use this table when the user asks "which visual should I use?" or when reviewing a design:

| Business question | Data shape | Recommended visual | `--type` value | Avoid |
|---|---|---|---|---|
| How does X compare across categories? | 1 measure, N categories | Bar (horizontal) | `bar` | Pie with >5 slices |
| How has X changed over time? | 1+ measures, date axis | Line chart | `line` | Bar chart for time |
| What is the part-to-whole composition? | 1 measure, few categories (≤5) | Donut | `donut` | 3D pie (never use) |
| How does X rank? | 1 measure, ordered categories | Bar sorted descending | `bar` | Table for ranking |
| What is the distribution of X? | 1 measure, many points | Scatter chart | `scatter` | Grouped bar |
| Are X and Y correlated? | 2 measures per point | Scatter chart | `scatter` | Line (implies time) |
| What is the current value of a KPI? | 1 measure, optional target | Card or KPI visual | `card` or `kpi` | Gauge (uses ink badly) |
| How does X break down hierarchically? | 1 measure, 2+ dimension levels | Matrix or treemap | `matrix` or `treemap` | Nested tables |
| Where is X geographically? | 1 measure + location field | Filled map or Azure map | `filledmap` | Bubble map for choropleth |
| What drives X up or down? | 1 outcome + many factors | Key influencers | `keyinfluencers` | Manual correlation scatter |
| How does X flow through stages? | 1 measure, ordered stages | Funnel or waterfall | `funnel` or `waterfall` | Bar for stage conversion |
| What changed between periods? | 2 period measures | Waterfall chart | `waterfall` | Side-by-side bars |

### Anti-pattern quick reference

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Pie chart with >5 slices | Angles are hard to compare; "other" hides data | Use bar chart sorted descending |
| Dual-axis line chart with different scales | Misleads: trends appear correlated | Split into 2 charts or use combo with explicit scale labels |
| 100% stacked bar for comparison | Hard to compare non-baseline segments | Use clustered bar instead |
| Table as the primary visual on page 1 | No pre-attentive encoding; forces reading | Promote key metrics to cards, use table for drill-down page |
| More than 4 colors in a single visual | Color differentiation fails beyond 4 | Group small categories into "Other" |
| Gauge / speedometer visual | Wastes 50% of ink on the empty half | Use card with conditional formatting or KPI visual |
| Slicers on every page | Redundant; increases cognitive load | Use sync slicers from a single master page |
| Title = measure name | No context for the reader | Write interpretive titles: "Revenue grew 18% YoY" |

---

## Design Review Workflow

Run this sequence to produce a structured design review for any existing report:

```bash
# 1 — Lint: check structural rules (unnamed visuals, missing alt text markers, etc.)
pbi report lint --pbip <path> --json

# 2 — Accessibility audit: WCAG compliance check
pbi report a11y --pbip <path> --json

# 3 — Field usage: identify unused fields and over-used measures
pbi report field-usage --pbip <path>

# 4 — Validate: confirm PBIR JSON schema integrity
pbi report validate --pbip <path>
```

After collecting output, produce a **Design Review Report** in this structure:

```markdown
## Design Review: <Report Name>

### Critical Issues (must fix before publish)
- [lint/a11y findings at error severity]

### Warnings (should fix)
- [lint/a11y findings at warning severity]

### Design Recommendations
- [chart archetype improvements per the archetype table]
- [layout and visual density observations]

### Accessibility
- [WCAG findings with remediation steps]

### Field Hygiene
- [unused fields that should be removed]
- [measures used on many pages that might benefit from a visual group]
```

---

## Accessibility (WCAG AA) Guidance

Run `pbi report a11y --pbip <path>` to get a machine-readable audit. Common findings:

The CLI **detects** these issues (`pbi report a11y`) but alt text, font size, and
tab order are set in Power BI Desktop or via the theme JSON — there is no
`pbi visual` flag for them today. Detect with the CLI, remediate as noted:

| Finding | Severity | Remediation |
|---|---|---|
| Visual has no alt text | Error | Add alt text in Power BI Desktop (Format → General → Alt text) |
| Color is the only differentiator | Warning | Add data labels or marker shapes in addition to color |
| Slicer has no accessible label | Warning | Set a title: `pbi visual update --pbip <p> --page <pg> --name <v> --title "<Field Name>"` |
| Text below 10pt | Warning | Raise font sizes in the theme JSON, then `pbi theme apply` |
| Low contrast ratio (<4.5:1) | Error | Fix theme colors (`pbi theme generate` enforces WCAG AA), then `pbi theme apply` |
| Tab order not set | Info | Set reading/tab order in Power BI Desktop (Selection pane) |

**Rule of thumb:** every visual on the report must be understandable without color.
Use data labels, patterns, or shapes as secondary encodings wherever color is used to
distinguish series.

---

## Layout Principles

**Visual density:** 3–5 visuals per 1280×720 page is the sweet spot.
More than 7 visuals on a page creates cognitive overload.

**The F-pattern:** readers scan top-left first. Put the single most important number
(a KPI card) at position x=40, y=40. Put the trend chart (the "why") immediately below.

**Whitespace:** leave at least 20px margin on all sides and 16px gutter between visuals.
`pbi layout auto` handles this automatically.

**Hierarchy signals:**
- Primary KPI: card, size 220×120 minimum
- Supporting chart: 600×360 minimum
- Secondary detail: table below the fold (y > 480)

**Slicer placement:** slicers belong in a consistent location — top bar (y=0–60, full width)
or right rail (x=1060–1280). Never scatter slicers randomly across a page.

---

## Common Design Patterns

### KPI header row

Four cards across the top (y=40, h=100), each 280px wide with 20px gutters:

```bash
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value Revenue --measure --x 40 --y 40 --width 280 --height 100 --title "Revenue"
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "Gross Margin %" --measure --x 340 --y 40 --width 280 --height 100 --title "Margin"
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "Units Sold" --measure --x 640 --y 40 --width 280 --height 100 --title "Units"
pbi visual add --pbip <path> --page "Executive Summary" --type card \
  --table Sales --value "Customer Count" --measure --x 940 --y 40 --width 280 --height 100 --title "Customers"
```

### Trend + breakdown split

Left 65% for a line chart (trend over time), right 35% for a bar chart (breakdown by category):

```bash
pbi visual add --pbip <path> --page "Executive Summary" --type line \
  --table Sales --value Revenue --measure --category MonthYear \
  --x 40 --y 180 --width 780 --height 480
pbi visual add --pbip <path> --page "Executive Summary" --type bar \
  --table Sales --value Revenue --measure --category Category \
  --x 840 --y 180 --width 400 --height 480
```

### Drill-through detail page

```bash
pbi report page-add --pbip <path> --name "Product Detail"
pbi visual add --pbip <path> --page "Product Detail" --type table \
  --table Sales --value Revenue --measure --extra-columns "Units,Date" \
  --x 40 --y 40 --width 1200 --height 600
```
