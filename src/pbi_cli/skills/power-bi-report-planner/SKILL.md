---
name: power-bi-report-planner
version: "1.1"
min_cli_version: "0.1.0"
description: >
  Use for end-to-end guided report building: requirements gathering, semantic
  model inspection, locked design brief, approval-gated PBIR authoring, and
  optional Fabric publishing. Triggers on: "create a new Power BI report",
  "build me a report", "plan and build a report", "help me define a report",
  "report from this semantic model", "guided report workflow", "report planner".
  Do NOT trigger for: editing an existing report page (→ power-bi-report-design),
  DAX measure work (→ power-bi-dax), or Fabric publish only (→ power-bi-report-management).
---

# power-bi-report-planner

**This is the DIRECTOR skill.** It decides *what to build, where to place it, and
how to display it* — then hands a locked, concrete design brief to the
`power-bi-report-design` skill, which IMPLEMENTS it with the CLI. The planner does
not run `pbi visual add` itself; it produces the spec. Think: architect (planner)
vs. builder (report-design).

The planner gathers requirements, inspects the model, **finds the story in the
data**, designs a professional page on a fixed grid, waits for approval, then hands
off to the implementer.

**Division of labour:**

```
power-bi-report-planner  (DIRECTOR)        power-bi-report-design  (IMPLEMENTER)
─────────────────────────────────────      ──────────────────────────────────────
Requirements + model inventory             Reads the design brief
Finds the story (queries the data)    →    Maps each spec row to a pbi command
Designs the page (grid + visual spec)      Runs pbi visual add / set-format / format
Writes interpretive titles                 Applies display rules + header
Locks the brief, gets approval             Runs design QA self-check
```

**Workflow summary:**

```
Phase 1 — Define     Clarification questions (3-5 rounds)
     ↓
Phase 2 — Inspect    Semantic model inventory via pbi commands
     ↓
Phase 3 — Find the   Query the data to discover the actual narrative / headline /
          Story      tension — design follows the story, not the other way round
     ↓
Phase 4 — Design     Lay the page on the grid; write the visual-spec table with
          the Page   interpretive titles and display rules (the locked brief)
     ↓
Phase 5 — Approve    STOP — do not build anything until the user says "approve"
     ↓
Phase 6 — Hand off   power-bi-report-design implements the brief, then QA-checks it
     ↓
Phase 7 — Publish    (Optional) pbi fabric report push to Fabric workspace
```

---

## Phase 1 — Define

Ask these questions in up to 3 rounds. Only ask what hasn't been answered already.
Do NOT ask all questions at once — group into at most 2 questions per round.

**Required answers before proceeding to Phase 2:**

| # | Question | Why it matters |
|---|---|---|
| 1 | Who is the audience? (executives, analysts, ops team…) | Drives visual complexity and page count |
| 2 | What is the primary business question the report must answer? | Sets the north-star KPI and page 1 layout |
| 3 | Which semantic model / .pbip project should this be based on? | Needed for model inspection |
| 4 | How many pages? Any named sections? | Determines scaffold structure |
| 5 | Is there a design system / theme to apply? (e.g. corporate colours) | Applied in Phase 5 |
| 6 | Delivery target: local .pbip only, or publish to a Fabric workspace? | Determines whether Phase 6 runs |

If the user says "just build something reasonable", use sensible defaults:
- 3 pages: Executive Summary, Detail Analysis, Reference
- Standard layout: KPI cards row + main chart + slicer column
- Default theme (no custom colours)
- Local only (no Fabric publish unless workspace id provided)

---

## Phase 2 — Inspect

Run these commands to inventory the semantic model. Use `--json` for machine-readable output.

```bash
# List all tables
pbi model tables --json

# List all measures (with expressions)
pbi measure list --json

# List columns for key tables
pbi model columns --table <TableName> --json

# Check existing report structure (if a .pbip already exists)
pbi report pages --pbip <path>
pbi report field-usage --pbip <path>

# Run governance check to surface issues early
pbi govern check --json
```

Produce a **Model Summary** section in your response:

```
## Model Summary
Tables: [list with row-count hint if visible]
Key measures: [top 5-10 measures with brief descriptions]
Likely dimensions: [date, category, geography tables]
Likely facts: [sales, inventory, events tables]
Potential KPIs: [measures well-suited for cards on page 1]
Field validation: [any measure or column names you'll reference in the brief]
```

**Field validation is critical:** before writing the design brief, confirm that
every field you plan to use actually exists with the exact name returned by
`pbi model columns` and `pbi measure list`. Mismatched names cause build failures.

---

## Phase 3 — Find the Story

**A professional report argues a point. Find that point in the data BEFORE
designing.** Do not design a page and then drop in whatever fields exist — query
the model, find the headline and the tension, and let those drive the layout.

Run targeted DAX/measure queries to discover:

```bash
# Headline totals (the KPI numbers)
pbi --backend desktop dax query "EVALUATE ROW(\"Sales\", SUM(T[Sales]), \"Profit\", SUM(T[Profit]), \"Margin\", [Profit Margin %])"

# Ranking by a dimension (who/where leads)
pbi --backend desktop dax query "EVALUATE SUMMARIZECOLUMNS(T[Segment], \"Profit\", SUM(T[Profit]), \"Margin\", [Profit Margin %]) ORDER BY [Profit] DESC"

# Trend over time (momentum)
pbi --backend desktop dax query "EVALUATE SUMMARIZECOLUMNS(T[Month], \"Sales\", SUM(T[Sales])) ORDER BY T[Month]"
```

From the results, write a **Narrative** of 3–4 beats. A good narrative has a
*tension* — two facts that pull against each other. Example from the Financials data:

```
Headline: $965K sales at a healthy 39.9% margin.
Beat 1 (when):  Sales build steadily to a December peak.
Beat 2 (who):   Channel drives the most profit ($106K)…
Beat 3 (twist): …but Enterprise earns the richest margin (45%) on the least volume.
Beat 4 (where): Germany is the largest market ($295K).
```

Every visual on the page must serve one beat. If a visual doesn't advance the
story, cut it. **Two visuals on the same dimension with the same measure are
redundant — never do that** (e.g. "Sales by Segment" + "Profit by Segment" tells
one story badly; "Profit by Segment" + "Margin % by Segment" tells volume-vs-
efficiency, which is a real story).

---

## Phase 4 — Design the Page

Lay every page on the **standard grid** so visuals align by default:

```
Canvas:      1280 × 720
Margins:     48 px on all four sides   (content lives in x 48–1232, y 48–680)
Gutter:      16 px between visuals
4-col width: (1184 − 3·16) / 4 = 284   → x = 48, 348, 648, 948
2-col split: left 720 + gutter + right 448, OR left 580 + gutter + right 588
Rows:        Header y24 h44 · KPI strip y88 h104 · Row2 y208 h232 · Row3 y456 h224
```

**Reading order = story order (F-pattern).** Top-left is read first, so put the
headline there:

| Zone | y | Purpose | Visual pattern |
|---|---|---|---|
| Header | 24 | Page title (textbox) | `add-element textbox` |
| KPI strip | 88 | The headline numbers | 3–4 `card`, equal width, aligned |
| Row 2 — hero + driver | 208 | The trend (wide, left) + the main breakdown (right) | `line` + `bar` |
| Row 3 — context + twist | 456 | Geography / detail (left) + the efficiency angle (right) | `column` + `bar`/`table` |

Then write the **locked design brief** — this is the contract the implementer follows.
Save as `design-brief.md`:

```markdown
# Design Brief — <Page Name>

## Narrative
<the 3–4 beats from Phase 3, with the headline takeaway>

## Theme
<theme JSON file, or brand accent colour e.g. #118DFF, or "default">

## Visual Spec
| # | Story beat | Type | Table | Value | Category | x | y | w | h | Title (states the finding) | Display rules |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | header | textbox | — | — | — | 48 | 24 | 1184 | 44 | "Financial Performance Overview" | — |
| 2 | KPI | card | Financials | Sales | — | 48 | 88 | 284 | 104 | "Total Sales" | — |
| 3 | KPI | card | Financials | Profit | — | 348 | 88 | 284 | 104 | "Total Profit" | — |
| 4 | KPI | card | Financials | Profit Margin % (measure) | — | 648 | 88 | 284 | 104 | "Profit Margin" | — |
| 5 | KPI | card | Financials | Units Sold | — | 948 | 88 | 284 | 104 | "Units Sold" | — |
| 6 | when | line | Financials | Sales | Month | 48 | 208 | 720 | 232 | "Sales build through the year to a December peak" | data labels off |
| 7 | who | bar | Financials | Profit | Segment | 784 | 208 | 448 | 232 | "Channel leads profit at $106K" | data labels on; accent #118DFF |
| 8 | where | column | Financials | Sales | Country | 48 | 456 | 580 | 224 | "Germany is the top market — $295K" | — |
| 9 | twist | bar | Financials | Profit Margin % (measure) | Segment | 644 | 456 | 588 | 224 | "Yet Enterprise earns the richest margin — 45%" | data labels on |

## Title rules
- Every chart title STATES THE FINDING, not the field name. "Channel leads profit
  at $106K", never "Profit by Segment". Use real numbers pulled in Phase 3.
- The textbox header names the page; the KPI cards are labelled by what they show.

## Filters / slicers
| Scope | Field | Type | Value |
|---|---|---|---|
| <page/report> | <Table[Col]> | <relative-date/value> | <e.g. last 1 Years> |
```

---

## Phase 5 — Approve

**STOP HERE.** Do not build anything until the user explicitly approves.

Present `requirements.md` + `design-brief.md` and ask:

> "The narrative and design brief are ready. Review the visual spec above — type
> **approve** (or **proceed**) to build it, or request changes before I start."

Accept: "approve", "proceed", "yes", "go ahead", "build it", "looks good", "lgtm".
Do not interpret silence or partial answers as approval.

---

## Phase 6 — Hand off to the implementer

The design brief is now executed by the **`power-bi-report-design`** skill, which
maps each Visual Spec row to a `pbi visual add` command, applies the display rules
with `pbi visual set-format`, adds the header with `pbi visual add-element`, then
runs its design QA self-check. See that skill's "Implementing a Design Brief"
section. The planner's job is done once the brief is approved and handed over.

If you are operating both roles in one session, simply proceed to build the brief
exactly as written — same grid coordinates, same interpretive titles, same display
rules — then run the QA checklist before declaring done.

The mechanical command sequence (scaffold → `visual add` per spec row → `set-format`
→ filters → theme → validate/lint/a11y) lives in **`power-bi-report-design` →
"Implementing a Design Brief."** Greenfield: `pbi project new --out <dir> --name <name>`
first; `pbi report scaffold` only adds pages to an existing `.Report`.

**Visual `--type` values:** `card`, `kpi`, `multirow`, `bar`, `column`, `stackedbar`,
`stackedcolumn`, `100percentbar`, `100percentcolumn`, `line`, `area`, `stackedarea`,
`combo`, `scatter`, `bubble`, `pie`, `donut`, `gauge`, `waterfall`, `funnel`, `ribbon`,
`treemap`, `table`, `matrix`, `slicer`, `map`, `filledmap`, `azuremap`, `decomptree`,
`keyinfluencers`, `smartnarrative`, `qanda`.

**Filter commands:** `filter add-value` (categorical), `filter add-relative-date`,
`filter add-advanced` (numeric). There is no generic `filter add`.

---

## Phase 7 — Publish (conditional)

Run only if the user specified a Fabric workspace as the delivery target.

```bash
# Get workspace id if only name was given
pbi fabric workspaces --filter "<workspace name>" --json

# Push with binding verification
pbi fabric report push \
  --workspace <workspace-id> \
  --report "<report name>" \
  --definition ./MySales.Report \
  --dataset-id <semantic-model-id> \
  --bind-verify

# Confirm it's live
pbi fabric report list --workspace <workspace-id>
```

---

## Design Defaults

When the user hasn't specified visual choices, default to these story-shaped
layouts — all on the standard grid from Phase 4:

| Page role | Narrative shape | Layout |
|---|---|---|
| Executive Summary | Headline → trend → driver → context | 4 KPI cards (y88) + hero line (y208 left) + driver bar (y208 right) + context column/bar (y456) |
| Detail Analysis | Compare → rank → inspect | Ranked bar (left) + breakdown column (right) + detail table (full-width, below) |
| Reference / Appendix | Look up | Full-width table + page-nav buttons |

Never exceed ~5 data visuals per page plus the KPI strip — density above that
reads as clutter, not insight.

---

## Dependency Checks

Before starting Phase 2, verify the user has:
- A `.pbip` project file. For greenfield, `pbi project new --out <dir> --name <name>`
  creates a complete openable PBIP (offline model + report). `pbi report scaffold`
  requires an existing `.Report` folder — it adds pages, it does not create the project.
- Access to the semantic model (local TMDL or live XMLA connection)
- For Fabric publish: `PBI_REST_BEARER` or `FABRIC_TOKEN` set, and workspace access

If anything is missing, surface it clearly with the fix command before proceeding.
