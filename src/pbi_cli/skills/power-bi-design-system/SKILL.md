---
name: power-bi-design-system
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for WCAG-compliant theme generation, brand colour enforcement, typography
  and spacing consistency, and custom visual SDK workflows (scaffold, build, package,
  import .pbiviz).
  Triggers on: "theme", "brand colour", "WCAG", "accessibility", "color palette",
  "pbi theme", "pbi custom-visual", "pbiviz", "custom visual", "design system",
  "typography", "brand font", "contrast ratio", "color scale theme".
  Do NOT trigger for conditional formatting on individual visuals
  (→ power-bi-report-design) or report page layout (→ power-bi-report-design).
---

# power-bi-design-system

WCAG themes, brand colour enforcement, typography, and custom visual SDK.

## Quick Reference

```bash
# Theme generation from a brand colour
pbi theme generate --brand-color "#0078D4" --output ./themes/contoso.json
pbi theme generate --brand-color "#0078D4" --wcag AA --output ./themes/contoso.json
pbi theme generate --brand-color "#0078D4" \
  --font "Segoe UI" --secondary-font "Segoe UI Light" \
  --output ./themes/contoso-full.json

# Apply and validate
pbi theme apply --file ./themes/contoso.json
pbi theme validate --file ./themes/contoso.json          # WCAG contrast check
pbi theme validate --file ./themes/contoso.json --level AAA

# Theme diff
pbi theme diff ./themes/contoso-v1.json ./themes/contoso-v2.json

# Custom visual SDK
pbi custom-visual scaffold --name "WaterfallPlus" --output ./visuals/
pbi custom-visual build --dir ./visuals/WaterfallPlus/
pbi custom-visual package --dir ./visuals/WaterfallPlus/ --output ./dist/
pbi custom-visual import --file ./dist/WaterfallPlus.pbiviz
pbi custom-visual list
```

---

## Worked Example 1: Generate a WCAG AA-compliant theme from brand colours

```bash
# Generate theme with automatic palette derivation
pbi theme generate \
  --brand-color "#004E8C" \
  --secondary-color "#50E6FF" \
  --font "Segoe UI" \
  --wcag AA \
  --output ./themes/contoso.json

# Validate all colour pairs pass AA contrast (4.5:1 text, 3:1 UI)
pbi theme validate --file ./themes/contoso.json --level AA

# Apply to open report
pbi theme apply --file ./themes/contoso.json
```

Generated theme structure:
```json
{
  "name": "Contoso Brand",
  "dataColors": ["#004E8C", "#0078D4", "#50E6FF", "#B3E0FF", "#E8F4FD"],
  "background": "#FFFFFF",
  "foreground": "#252423",
  "tableAccent": "#004E8C",
  "visualStyles": {
    "*": {
      "*": {
        "fontSize": [{"value": 12}],
        "fontFamily": [{"value": "Segoe UI"}]
      }
    }
  }
}
```

---

## Worked Example 2: Scaffold and package a custom visual

```bash
# Create a new visual project
pbi custom-visual scaffold --name "RevenueGauge" --template gauge --output ./visuals/

# Develop the visual (TypeScript/D3)
cd ./visuals/RevenueGauge/
# ... edit src/visual.ts ...

# Build and validate
pbi custom-visual build --dir ./visuals/RevenueGauge/

# Package into .pbiviz
pbi custom-visual package --dir ./visuals/RevenueGauge/ --output ./dist/

# Import into the open report
pbi custom-visual import --file ./dist/RevenueGauge.pbiviz

# Verify it appears in visual list
pbi custom-visual list
```

---

## Worked Example 3: Enforce brand compliance across multiple report files

```bash
# Validate the current theme against brand guidelines
pbi theme validate --file ./themes/approved-brand.json --level AA

# Diff two theme versions to review changes before rollout
pbi theme diff ./themes/brand-2025.json ./themes/brand-2026.json

# Apply approved theme to all open reports (requires Desktop)
pbi theme apply --file ./themes/brand-2026.json
```

---

## WCAG Contrast Requirements

| Level | Minimum contrast | Applies to |
|---|---|---|
| AA (standard) | 4.5:1 | Normal text (< 18pt) |
| AA | 3:1 | Large text (≥ 18pt or 14pt bold), UI components |
| AAA (enhanced) | 7:1 | Normal text |
| AAA | 4.5:1 | Large text |

`pbi theme generate --wcag AA` ensures all generated colour pairs meet AA requirements. Use `--wcag AAA` for regulated industries (government, healthcare, financial).

---

## Custom Visual Project Structure

```
RevenueGauge/
├── package.json
├── pbiviz.json           # visual metadata and capabilities
├── src/
│   ├── visual.ts         # main visual class
│   └── settings.ts       # formatting settings
├── style/
│   └── visual.less
└── assets/
    └── icon.png
```

---

## Edge Cases

**`pbi theme validate` fails with contrast warning:** Increase the luminance difference between the flagged colour pair. The tool prints the exact pair and current ratio (e.g., `#0078D4 on #FFFFFF: 4.1:1 < 4.5:1 required`).

**`pbi custom-visual build` fails with TypeScript errors:** The SDK scaffolds a working stub — TypeScript errors come from edits to `visual.ts`. Run `npm run build` inside the visual directory to see the full tsc error output.

**Custom visual doesn't appear after import:** Power BI Desktop requires a report restart to register new visuals. Close and reopen the report file.

**Theme `dataColors` has fewer than 8 entries:** Power BI cycles through `dataColors` for series. Provide at least 8 entries to avoid colour repetition in multi-series charts.

---

## Cross-skill handoffs

- Applying conditional formatting to individual visuals → **power-bi-report-design**
- Report page layout and visual positioning → **power-bi-report-design**
- Governance check for brand naming conventions → **power-bi-governance**
