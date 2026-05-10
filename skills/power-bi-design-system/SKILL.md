---
name: power-bi-design-system
description: >
  Use for Power BI report design standards: branding guidelines, color systems,
  typography, spacing, reusable visual components, and corporate style consistency.
  Triggers on: "design system", "branding", "brand guidelines", "typography",
  "spacing", "color system", "reusable components", "style guide", "corporate style".
version: "1.0"
---

# power-bi-design-system

## Quick Reference

```bash
# Apply the design system to a report
pbi design apply --pbip "C:/Reports/MyReport" --system "corporate"

# Generate a theme from the design system
pbi design export-theme --system "corporate" --output themes/corporate.json

# Validate report against design system
pbi design check --pbip "C:/Reports/MyReport" --system "corporate"

# List registered design systems
pbi design list
```

---

## Design System Components

A complete Power BI design system defines:

| Component | Purpose |
|-----------|---------|
| Color palette | 8+ data colors + semantic colors |
| Typography | Font family, sizes for title/body/label |
| Spacing grid | Padding, gutters, margins |
| Visual templates | Pre-configured visual styles |
| Page templates | Standard layout blueprints |
| Icon library | Conditional formatting icons |

---

## Color System

### Primary Palette (8 Data Colors)

Each color slot has a designated semantic role:

| Slot | Role | Don't Use For |
|------|------|--------------|
| 1 | Primary metric, positive trend | Negative values |
| 2 | Secondary metric | Same chart as slot 1 without contrast |
| 3 | Tertiary metric | Text on light backgrounds (may fail WCAG) |
| 4–6 | Supporting series | Never for critical data |
| 7 | Neutral / baseline | Grid lines, reference lines |
| 8 | Warning / negative | Only negative trends (red-green safe) |

### Semantic Colors

```json
{
  "semanticColors": {
    "positive": "#107C10",
    "negative": "#D83B01",
    "neutral": "#605E5C",
    "warning": "#FFB900",
    "info": "#0078D4"
  }
}
```

### Applying Semantic Colors in DAX (Conditional Formatting)

```dax
Profit Color =
VAR _profit = [Profit Margin %]
RETURN
    SWITCH(
        TRUE(),
        _profit >= 0.15, "#107C10",  -- positive
        _profit >= 0.05, "#FFB900",  -- warning
        "#D83B01"                     -- negative
    )
```

---

## Typography System

### Font Hierarchy

| Element | Font | Size | Weight | Color |
|---------|------|------|--------|-------|
| Page title | Segoe UI | 18pt | Bold | Brand primary |
| Visual title | Segoe UI | 11pt | Bold | Near-black |
| Axis labels | Segoe UI | 9pt | Regular | Gray #605E5C |
| Data labels | Segoe UI | 9pt | Regular | Inherits |
| Card KPI | Segoe UI | 28pt | Light | Brand primary |
| Card label | Segoe UI | 10pt | Regular | Gray #605E5C |
| Table header | Segoe UI | 10pt | Bold | White on brand |
| Table body | Segoe UI | 9pt | Regular | Near-black |

### Font Safety

Use system fonts only — custom fonts require installation on every client machine:
- **Segoe UI** — default Windows; matches Power BI Desktop UI
- **Arial** — universal fallback
- **Calibri** — common in Office environments

---

## Spacing System

### 8px Base Grid

All spacing is multiples of 8px:

| Token | Value | Use |
|-------|-------|-----|
| xs | 8px | Internal padding, icon gap |
| sm | 16px | Visual margin, cell padding |
| md | 24px | Section spacing |
| lg | 32px | Row spacing |
| xl | 48px | Page section headers |

### Canvas Margins

Standard canvas (1280×720):
- Page edge padding: **16px** (sm)
- Between visuals: **16px** (sm)
- KPI card row height: **120px** (15 × 8)
- Chart minimum height: **360px** (45 × 8)

---

## Visual Component Library

### KPI Card Component

```json
{
  "visualType": "card",
  "objects": {
    "labels": [{
      "properties": {
        "fontSize": { "expr": { "Literal": { "Value": "28D" } } },
        "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI Light'" } } },
        "color": { "solid": { "color": "#0078D4" } }
      }
    }],
    "categoryLabels": [{
      "properties": {
        "fontSize": { "expr": { "Literal": { "Value": "10D" } } },
        "color": { "solid": { "color": "#605E5C" } }
      }
    }]
  }
}
```

### Chart Component Defaults

```json
{
  "objects": {
    "dataPoint": [{ "properties": { "defaultColor": { "solid": { "color": "#0078D4" } } } }],
    "plotArea": [{ "properties": { "transparency": { "expr": { "Literal": { "Value": "0D" } } } } }],
    "categoryAxis": [{
      "properties": {
        "labelFontSize": { "expr": { "Literal": { "Value": "9D" } } },
        "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI'" } } }
      }
    }]
  }
}
```

---

## Design Consistency Rules

| Rule | Check |
|------|-------|
| All visuals use brand font | Segoe UI or Arial only |
| KPI cards on Row 1 only | y <= 140 for cards |
| Slicers right-aligned | x >= 1050 or dedicated slicer column |
| No visual overlaps | All bounding boxes non-intersecting |
| Chart titles use brand color | `#0078D4` or configured primary |
| Table headers use brand background | Header fill = primary color |
| Consistent padding | All x values multiples of 16 |

---

## Design System Configuration File

Save as `design-system.json` in project root:

```json
{
  "name": "Corporate Design System",
  "version": "2.0",
  "colors": {
    "primary": "#0078D4",
    "secondary": "#106EBE",
    "dataColors": ["#0078D4", "#106EBE", "#00B294", "#FFB900", "#E81123", "#8764B8", "#5D5A58", "#D2D0CE"],
    "semantic": {
      "positive": "#107C10",
      "negative": "#D83B01",
      "warning": "#FFB900"
    }
  },
  "typography": {
    "fontFamily": "Segoe UI",
    "kpiSize": 28,
    "titleSize": 11,
    "bodySize": 9
  },
  "spacing": {
    "base": 8,
    "pagePadding": 16,
    "visualGap": 16
  }
}
```

---

## Common Design System Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Inconsistent chart colors | Missing theme file | Apply corporate theme JSON |
| Font not rendering | Custom font not installed | Switch to Segoe UI or Arial |
| Visual sizes don't match | Manual sizing | Run `pbi layout snap --grid 8` |
| Semantic colors not applying | DAX color measure not bound | Add conditional formatting to visual |
