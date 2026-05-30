---
name: power-bi-report
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for creating, scaffolding, and managing Power BI report pages in .pbip
  projects. Triggers on: "create a report", "add a page", "scaffold report",
  "report pages", "page layout", "delete page", "clear page", "pbi report",
  "multi-page report", "executive dashboard page", "drill-through page".
version: "1.0"
---

# power-bi-report

## Quick Reference

```bash
# Prerequisites: save .pbix as .pbip first
# File → Save as → Power BI project (.pbip)

# List pages
pbi report pages --pbip "C:/Reports/MyReport"

# Add a blank page
pbi report page-add --pbip "C:/Reports/MyReport" --name "Executive Summary"

# Delete a page
pbi report page-delete --pbip "C:/Reports/MyReport" --name "Old Page"

# Clear all visuals from a page
pbi report clear-page --pbip "C:/Reports/MyReport" --page "Draft"

# Scaffold a complete 3-page report (Financials model)
pbi report scaffold --pbip "C:/Reports/MyReport" --model financials --pages 3 --replace

# After any scaffold/edit: reload in Power BI Desktop when prompted
```

---

## Report Scaffold Pages

`pbi report scaffold` creates 3 pages tailored for the Financials model:

| Page | Visuals |
|------|---------|
| **Executive Summary** | 4 KPI cards + Sales by Country bar + Year slicer + Sales by Month line |
| **Sales Analysis** | Sales by Segment bar + Sales by Product bar + Detail table |
| **Profit Analysis** | Profit by Country bar + Profit by Segment bar + P&L card + Profit by Month line |

For custom models, use `--model YourTableName`. The scaffold uses that table name for all field references.

---

## Page Design Patterns

### Executive Summary Page

Layout (1280×720 canvas):
```
Row 1 (y=16, h=120): [KPI Card] [KPI Card] [KPI Card] [KPI Card]
Row 2 (y=152, h=360): [Main Chart 600w] [Slicer 200w] [Secondary Chart 462w]
```

Use `pbi visual add` to populate each slot after `pbi report page-add`.

### Operations Dashboard Page

```
Row 1: [Line Chart — trend over time, full width 1248w, h=240]
Row 2: [Bar Chart — by category, 600w] [Table — detail, 632w]
```

### Drill-through Detail Page

```
Row 1: [Slicer — filter by category, 200w] [Table — full detail, 1048w]
```

Configure drill-through by editing the page's `page.json`:
```json
{
  "displayName": "Product Detail",
  "pageBinding": {
    "name": "drill-product",
    "type": "Drillthrough"
  }
}
```

### Tooltip Page

Small canvas (320×240) with a single visual:
```bash
pbi report page-add --pbip "..." --name "Tooltip Sales"
# Then edit page.json to set type: Tooltip and smaller canvas
```

---

## PBIR File Structure

After scaffolding, Power BI Desktop reads these files:

```
financials.Report/
  definition/
    pages/
      {pageGUID}/
        page.json          ← page metadata (displayName, width, height)
        visuals/
          {visualGUID}/
            visual.json    ← visual config (type, position, query)
    pages.json             ← page order and active page
    report.json            ← report-level theme and settings
```

**External editing** is supported — Power BI Desktop prompts to reload when files change.

---

## Reload Workflow

```
Edit PBIR files via pbi-cli
         ↓
Power BI Desktop detects change
         ↓
Prompt: "External changes detected — Reload?"
         ↓
Click Reload → Pages appear with new visuals
```

If no prompt appears: close and reopen the `.pbip` file.

---

## Page JSON Reference

Minimum valid `page.json`:
```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
  "name": "a1b2c3d4e5f6g7h8i9j0",
  "displayName": "Executive Summary",
  "displayOption": "FitToPage",
  "width": 1280,
  "height": 720
}
```

`displayOption` values: `"FitToPage"`, `"FitToWidth"`, `"ActualSize"`.

---

## Common Report Errors

| Error | Fix |
|-------|-----|
| `No *.Report folder found` | Save as .pbip first (File → Save as → Power BI project) |
| Page not appearing after scaffold | Click Reload in Desktop; or close/reopen .pbip |
| Visuals appear but show errors | Check field names match your model — use `pbi model columns` |
| Schema validation error on reload | Check visual.json `$schema` matches `visualContainer/2.7.0/schema.json` |
