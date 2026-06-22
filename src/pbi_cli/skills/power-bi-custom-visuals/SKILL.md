---
name: power-bi-custom-visuals
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for working with Power BI custom visuals: AppSource marketplace visuals,
  organizational store, pbiviz files, and CustomVisuals folder in PBIR projects.
  Triggers on: "custom visual", "AppSource visual", "pbiviz", "org visual",
  "third-party visual", "custom chart", "certified visual", "import visual".
version: "1.0"
---

# power-bi-custom-visuals

## Quick Reference

```bash
# List custom visuals in a report
pbi visual list-custom --pbip "C:/Reports/MyReport"

# Import a .pbiviz file into a report
pbi visual import --pbip "C:/Reports/MyReport" --pbiviz "visuals/MyVisual.pbiviz"

# Use a custom visual on a page
pbi visual add --pbip "C:/Reports/MyReport" --page "Executive Summary" \
  --type custom --visual-guid "org.powerbi.custom.sankey" \
  --table financials --value Sales --category Country
```

---

## Custom Visual Types

| Source | Trust Level | How to Add |
|--------|-------------|-----------|
| AppSource (certified) | High — Microsoft-reviewed | Download .pbiviz from AppSource |
| AppSource (uncertified) | Medium | Download .pbiviz from AppSource |
| Organizational store | Admin-managed | Admin enables in tenant settings |
| Custom-built | Developer | `pbiviz package` → .pbiviz file |

---

## PBIR Storage for Custom Visuals

Custom visuals are stored inside the report folder:

```
financials.Report/
  CustomVisuals/
    SankeyChart1DC7E5C5A0E64.pbiviz    ← the visual package
  definition/
    pages/
      {pageGUID}/
        visuals/
          {visualGUID}/
            visual.json   ← references the visual GUID
```

The `visual.json` for a custom visual uses `visualType` set to the visual's GUID:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
  "name": "a1b2c3d4e5f6",
  "position": { "x": 16, "y": 16, "z": 0, "width": 600, "height": 400, "tabOrder": 0 },
  "visual": {
    "visualType": "SankeyChart1DC7E5C5A0E64",
    "query": {
      "queryState": {
        "Source": {
          "projections": [{
            "field": { "Column": { "Expression": { "SourceRef": { "Entity": "financials" } }, "Property": "Segment" } },
            "queryRef": "financials.Segment"
          }]
        },
        "Destination": {
          "projections": [{
            "field": { "Column": { "Expression": { "SourceRef": { "Entity": "financials" } }, "Property": "Country" } },
            "queryRef": "financials.Country"
          }]
        },
        "Weight": {
          "projections": [{
            "field": { "Aggregation": { "Expression": { "Column": { "Expression": { "SourceRef": { "Entity": "financials" } }, "Property": "Sales" } }, "Function": 0 } },
            "queryRef": "Sum(financials[Sales])"
          }]
        }
      }
    },
    "objects": {}
  }
}
```

---

## Popular AppSource Visuals

| Visual | GUID Pattern | Use Case |
|--------|-------------|----------|
| Sankey Chart | `SankeyChart...` | Flow between categories |
| Bullet Chart | `BulletChart...` | KPI vs. target |
| Hierarchical Tree | `HierarchySlicer...` | Hierarchical slicer |
| Scatter Chart Pro | `ScatterChart...` | Advanced scatter |
| Gantt Chart | `Gantt...` | Project timelines |
| Infographic Designer | `Infographic...` | Icon-based KPIs |

---

## Importing a .pbiviz File

A `.pbiviz` file is a ZIP containing:
- `package.json` — metadata (name, version, GUID)
- `resources/visual.js` — compiled visual code
- `resources/visual.css` — styling
- `resources/pbiviz.json` — manifest

To add to a PBIR project:
1. Copy the `.pbiviz` file to the `CustomVisuals/` folder in the Report directory.
2. The visual is now available in Power BI Desktop when you reload the report.

```bash
# Manual copy (until pbi visual import is implemented)
cp MyVisual.pbiviz "C:/Reports/financials.Report/CustomVisuals/"
```

---

## Custom Visual Capability Roles

Different visuals accept different data roles. Common roles and their `queryState` keys:

| Role Name | Key | Description |
|-----------|-----|-------------|
| Category | `Category` | Axis / grouping |
| Values | `Values` or `Y` | Numeric measures |
| Legend | `Legend` | Color split |
| Size | `Size` | Bubble/marker size |
| Source | `Source` | Flow origin (Sankey) |
| Destination | `Destination` | Flow target (Sankey) |
| Tooltips | `Tooltips` | Hover detail fields |

Find the correct role names by extracting the `.pbiviz` and reading `capabilities.json`.

---

## Certified vs. Uncertified Visuals

| Property | Certified | Uncertified |
|----------|-----------|-------------|
| Code review | Yes (Microsoft) | No |
| Works in email subscriptions | Yes | No |
| Works in Analyze in Excel | Yes | No |
| Can use external resources | No | Yes |
| Safe for government tenants | Yes | Restricted |

Tenant admins can restrict non-certified visuals in the Power BI Admin Portal.

---

## Building a Custom Visual (Developer)

```bash
# Install Power BI Custom Visual tools
npm install -g powerbi-visuals-tools

# Create new visual project
pbiviz new MyVisual --template barChart

# Start dev server (live preview in Desktop)
pbiviz start

# Package for distribution
pbiviz package
# Outputs: dist/MyVisual.pbiviz
```

---

## Common Custom Visual Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Visual shows "This visual isn't supported" | Visual not certified and tenant blocks it | Ask admin to enable uncertified visuals |
| Visual missing after reload | .pbiviz not in CustomVisuals/ folder | Copy .pbiviz to report's CustomVisuals/ |
| Data not rendering | Wrong role name mapping | Check visual's capabilities.json for correct role keys |
| Visual version conflict | Old .pbiviz cached | Delete from CustomVisuals/, re-import latest version |
