---
name: power-bi-pages
description: >
  Use for managing report pages: adding, deleting, ordering, configuring drillthrough,
  tooltip pages, and mobile layouts. Triggers on: "add a page", "delete page",
  "page order", "drill-through", "tooltip page", "mobile layout", "pbi report pages",
  "page navigation", "hidden page", "report sections".
version: "1.0"
---

# power-bi-pages

## Quick Reference

```bash
pbi report pages --pbip "C:/Reports/MyReport"
pbi report page-add --pbip "C:/Reports/MyReport" --name "New Page"
pbi report page-delete --pbip "C:/Reports/MyReport" --name "Draft"
pbi report clear-page --pbip "C:/Reports/MyReport" --page "Executive Summary"
```

---

## Page Types

| Type | `displayOption` | Use |
|------|----------------|-----|
| Standard | `"FitToPage"` | Regular report page |
| Wide | `"FitToWidth"` | Long tables, horizontal scroll |
| Actual Size | `"ActualSize"` | Pixel-precise layouts |
| Tooltip | set via `pageBinding` | Small hover card (320×240) |
| Drill-through | set via `pageBinding` | Detail page with context filter |

---

## Page Order

`pages.json` controls the tab order in Power BI Desktop:

```json
{
  "pageOrder": [
    "e9acc75405694aba86b528eb44575368",
    "5cf6109e285f49c9aa81655ed960f66f",
    "342b8f6b49ca46f6b0f63a24517462f9"
  ],
  "activePageName": "e9acc75405694aba86b528eb44575368"
}
```

To reorder pages, edit `pages.json` and reorder the GUIDs, then reload in Desktop.

---

## Drill-through Page Setup

1. Add the page:
```bash
pbi report page-add --pbip "..." --name "Product Detail"
```

2. Edit the page's `page.json` to add `pageBinding`:
```json
{
  "name": "abc123...",
  "displayName": "Product Detail",
  "displayOption": "FitToPage",
  "width": 1280,
  "height": 720,
  "pageBinding": {
    "name": "drillthrough-product",
    "type": "Drillthrough"
  }
}
```

3. Add a drill-through anchor visual (the field users right-click on):
```bash
pbi visual add --pbip "..." --page "Product Detail" \
  --type slicer --table financials --value Product
```

---

## Tooltip Page Setup

1. Add a small page:
```bash
pbi report page-add --pbip "..." --name "Sales Tooltip"
```

2. Edit `page.json` — set small canvas and tooltip binding:
```json
{
  "displayName": "Sales Tooltip",
  "width": 320,
  "height": 240,
  "pageBinding": {
    "name": "tooltip-sales",
    "type": "Tooltip"
  }
}
```

3. Add a single visual:
```bash
pbi visual add --pbip "..." --page "Sales Tooltip" \
  --type card --table financials --value Sales --x 8 --y 8 --width 304 --height 224
```

---

## Hidden Pages

To hide a page (used for drill-through/tooltip targets):

Edit `page.json`:
```json
{
  "visibility": "HiddenInViewMode"
}
```

`visibility` options: `"Visible"` (default), `"HiddenInViewMode"`.

---

## Page Canvas Sizes

| Canvas | Width | Height | Use |
|--------|-------|--------|-----|
| 16:9 (default) | 1280 | 720 | Standard dashboards |
| 4:3 | 960 | 720 | Presentations |
| Custom | any | any | Branded reports |
| Tooltip | 320 | 240 | Hover cards |
| Mobile | 320 | 568 | Phone layout |

---

## Copying Pages Between Reports

PBIR GA makes this straightforward:

```bash
# Copy a page folder from one report to another
cp -r "ReportA.Report/definition/pages/{pageGUID}" \
      "ReportB.Report/definition/pages/{pageGUID}"

# Update ReportB's pages.json to include the new page GUID
# Then reload ReportB in Desktop
```

**Note:** Visual field references must match the target report's semantic model table and column names.
