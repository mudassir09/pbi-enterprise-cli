---
name: power-bi-layout
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for auto-layout of visuals on Power BI report pages: shelf packing,
  grid systems, responsive layouts, visual sizing, applying layout templates,
  and enforcing UX best practices for end-user report quality.
  Triggers on: "auto layout", "arrange visuals", "grid layout", "visual positioning",
  "pbi layout", "pack visuals", "responsive", "layout template", "align visuals",
  "slicer dropdown", "layout quality", "layout review", "report UX".
  Do NOT trigger for DAX, data modelling, or theme colour changes.
version: "1.1"
---

# power-bi-layout

---

## UX Principles — Apply Before Placing Any Visual

These rules are mandatory, not optional. A page that violates them is not done.
The end user — not the data model, not the developer — is the primary stakeholder of every layout decision.
Ask: "Can a business user understand this page in under 10 seconds without reading a manual?"

### 1. Visual hierarchy (top → bottom)
```
Row 1  Filters / slicers        — user sets context first
Row 2  KPI cards                — instant answer to "how are we doing?"
Row 3  Primary charts           — explain the numbers
Row 4  Supporting / detail      — drill-down, tables, secondary charts
```
Never put a chart above a KPI card. Never put a slicer below charts.

### 2. KPI cards must follow a logical domain sequence — not alphabetical or arbitrary order

The order of KPI cards is the order in which the user's eye reads the story.
Choose an order that matches the domain's natural flow:

**Finance / P&L pages:**
```
Gross Sales  →  Discounts  →  COGS  →  Net Profit
```
This traces money from top-line revenue through deductions to the bottom line.
A user instantly understands: "We made X, gave away Y, spent Z, kept W."

**Sales pages:**
```
Total Orders  →  Revenue  →  Avg Order Value  →  Conversion Rate
```

**Operations pages:**
```
Volume / Units  →  On-Time %  →  Defect Rate  →  Cost per Unit
```

The rule: cards tell a cause-and-effect or flow story left-to-right.
Never sort cards by metric name or by which measure was added first.

### 3. Slicers must be dropdown style
`pbi visual add --type slicer` creates a **list slicer** by default.  
List slicers expand to show all values with checkboxes — they consume 200–400px of height and look unprofessional when collapsed.  
**Always patch slicers to dropdown after adding them:**

```python
# Find the visual.json for every slicer and set mode to Dropdown
import json, pathlib

def set_slicer_dropdown(pbip_path: str, page_name: str):
    from pbi_cli.backends.pbir_backend import PbirBackend
    b = PbirBackend(pbip_path)
    visuals = b.visual_list(page_name)
    vdir = b._ga_visuals_dir(page_name)
    for vd in vdir.iterdir():
        vj = vd / "visual.json"
        if not vj.exists(): continue
        data = json.loads(vj.read_text(encoding="utf-8"))
        if data.get("visual", {}).get("visualType") != "slicer": continue
        objs = data["visual"].setdefault("objects", {})
        objs.setdefault("data", [{}])
        objs["data"][0].setdefault("properties", {})["mode"] = {
            "expr": {"Literal": {"Value": "'Dropdown'"}}
        }
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

Or edit visual.json directly — find the `"mode"` property and change `'Basic'` to `'Dropdown'`.

### 4. Canvas coverage — use the full width
Standard canvas: **1280 × 720 px** (16:9).  
Visuals must span the full 1280px width. Leaving >200px of dead space on the right is a layout failure.  
Apply the 2-column or 4-column grid below to ensure full coverage.

### 5. No scrollbars in charts
A chart that needs a scrollbar is too small. Minimum widths:
- Bar/column chart with ≤6 categories: **400px**
- Bar/column chart with 7–12 categories: **600px**
- Bar/column chart with 13+ categories: **900px** or use a table instead

### 6. Cards must not clip their subtitle
Power BI cards render a value line + a subtitle line. Minimum height **120px**; recommended **130px**.  
Cards shorter than 110px will clip the subtitle.

### 7. Consistent row heights
All visuals in the same logical row should share the same `y` and `height`.  
Mismatched heights create a ragged, unprofessional appearance.

---

## Quick Reference

```bash
# Auto-layout all visuals on a page
pbi layout auto --pbip "C:/Reports/MyReport" --page "Executive Summary"

# Apply a named layout template
pbi layout apply --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --template executive-dashboard

# Preview layout without writing files
pbi layout auto --pbip "C:/Reports/MyReport" --page "Executive Summary" --dry-run

# List available layout templates
pbi layout templates
```

---

## Canvas Coordinate System

```
(0, 0) ─────────────────────── (1280, 0)
  │                                   │
  │         1280 × 720 canvas         │
  │         (16:9 default)            │
  │                                   │
(0, 720) ─────────────────────── (1280, 720)
```

- All units in pixels
- Origin at top-left
- Standard padding: `16px` from canvas edge, `16px` between visuals

---

## Standard Grid System

### 12-Column Grid (1280px canvas)

| Columns | Width (px) | Use |
|---------|-----------|-----|
| 12 (full) | 1248 | Full-width charts |
| 8 | 816 | Main chart with sidebar |
| 6 | 608 | Half-width charts |
| 4 | 400 | Triple-column cards |
| 3 | 296 | Quad-column KPI cards |
| 2 | 192 | Narrow sidebars, slicers |

Formula: `width = (cols × 104) - 16` (with 16px gutter)

---

## Layout Templates

### Executive Dashboard

```
Row 1 (y=16, h=120):  [Card 296w] [Card 296w] [Card 296w] [Card 296w]
                       x=16        x=328       x=640       x=952
Row 2 (y=152, h=360): [Bar 600w]  [Slicer 192w]  [Line 420w]
                       x=16        x=632           x=840
```

### Operations Dashboard

```
Row 1 (y=16, h=240):  [Line 1248w — full width trend]
                       x=16
Row 2 (y=272, h=432): [Bar 600w]  [Table 632w]
                       x=16        x=632
```

### Sales Analysis

```
Row 1 (y=16, h=120):  [Card 296w] [Card 296w] [Slicer 192w] [Slicer 192w]
                       x=16        x=328       x=640          x=848
Row 2 (y=152, h=280): [Bar 608w]  [Bar 608w]
                       x=16        x=640
Row 3 (y=448, h=256): [Table 1248w]
                       x=16
```

### Single KPI Focus

```
Row 1 (y=16, h=200):  [MultiRow 1248w — KPI strip]
                       x=16
Row 2 (y=232, h=472): [Main Visual 1248w]
                       x=16
```

---

## Shelf-Packing Algorithm

When `pbi layout auto` runs, it packs visuals using a shelf-first algorithm:

1. Sort visuals by height descending (tallest first)
2. Place each visual on the lowest available horizontal shelf
3. Start a new shelf when current shelf has no space for the next visual
4. Apply 16px padding on all sides

The algorithm preserves visual type groupings — cards stay together, charts stay together.

---

## Auto-Positioning Logic

When adding a visual without explicit `--x`/`--y`, the CLI finds the next available slot:

```python
# Simplified logic
existing = load_existing_visual_positions(page)
next_y = max(v.y + v.height for v in existing) + 16 if existing else 16
next_x = 16
```

For smarter placement, use `pbi layout auto` after adding all visuals.

---

## Visual Size Recommendations

| Visual Type | Minimum | Recommended | Notes |
|-------------|---------|-------------|-------|
| Card | 200×120 | 300×130 | Subtitle clips below 120px; use 300px width for 4-card row |
| MultiRow Card | 300×150 | 624×220 | Add 50px per extra column |
| Bar chart ≤6 cats | 400×200 | 624×236 | Always use full half-width (624px) for no scrollbar |
| Bar chart 7–12 cats | 600×220 | 900×280 | Fewer than 600px causes scrollbar |
| Column chart | 400×200 | 624×236 | Same rule as bar chart |
| Line Chart | 500×250 | 900×300 | Wide canvas reduces data-label overlap |
| Table | 600×250 | 900×400 | Min 80px width per column; spaced column names need explicit field binding |
| Slicer (list) | 150×200 | — | **Avoid** — use Dropdown instead |
| Slicer (dropdown) | 150×50 | 200×56 | **Preferred** — must be set in visual.json (CLI default is list) |

---

## Aligning Visuals to a Grid

To snap all visuals to a 16px grid:

```bash
pbi layout snap --pbip "C:/Reports/MyReport" --page "Executive Summary" --grid 16
```

This rounds each visual's x/y/width/height to the nearest multiple of 16.

---

## Common Layout Errors

| Issue | Cause | Fix |
|-------|-------|-----|
| Visuals overlap | Auto-position not run after bulk add | Run `pbi layout auto` |
| Chart labels cut off | Visual too narrow | Increase width or reduce font size in theme |
| Cards misaligned vertically | Different y values | Run `pbi layout snap` to align to grid |
| Table scrolls horizontally | Too many columns for width | Increase table width or reduce columns |
