---
name: power-bi-themes
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for generating, applying, and validating Power BI report themes: brand color
  palettes, WCAG accessibility compliance, JSON theme files, and theme management.
  Triggers on: "theme", "colors", "branding", "accessibility", "WCAG", "color palette",
  "pbi theme", "report styling", "dark mode", "corporate colors".
version: "1.0"
---

# power-bi-themes

## Quick Reference

```bash
# Generate a theme from brand colors
pbi theme generate --primary "#0078D4" --secondary "#106EBE" --name "Corporate"

# Apply a theme to a report
pbi theme apply --pbip "C:/Reports/MyReport" --theme "themes/Corporate.json"

# Validate WCAG contrast compliance
pbi theme validate --theme "themes/Corporate.json" --wcag AA

# List available themes
pbi theme list --pbip "C:/Reports/MyReport"
```

---

## Theme JSON Structure

Power BI themes are JSON files applied at report level:

```json
{
  "name": "Corporate Theme",
  "dataColors": [
    "#0078D4", "#106EBE", "#2B88D8", "#71AFE5",
    "#C7E0F4", "#DEECF9", "#F3F9FD", "#0063B1"
  ],
  "background": "#FFFFFF",
  "foreground": "#252423",
  "tableAccent": "#0078D4",
  "visualStyles": {
    "*": {
      "*": {
        "background": [{ "color": { "solid": { "color": "#FFFFFF" } } }],
        "border": [{ "show": { "expr": { "Literal": { "Value": "false" } } } }]
      }
    },
    "card": {
      "*": {
        "labels": [{ "color": { "solid": { "color": "#0078D4" } }, "fontSize": 28 }]
      }
    }
  }
}
```

---

## Color Palette Generation

### From a Single Brand Color

Given a primary hex color, generate a full 8-color palette:

| Slot | Formula | Role |
|------|---------|------|
| 1 | Primary (100%) | Main accent |
| 2 | Primary + 15% darker | Hover/active |
| 3 | Primary + 40% lighter | Secondary |
| 4 | Primary + 65% lighter | Tertiary |
| 5 | Primary + 80% lighter | Background tint |
| 6 | Complementary hue | Contrast accent |
| 7 | Neutral warm gray | Text/borders |
| 8 | Near-white | Canvas background |

### Corporate Brand Example

```json
{
  "name": "Contoso Theme",
  "dataColors": [
    "#002050", "#0078D4", "#00B294", "#FFB900",
    "#E81123", "#8764B8", "#5D5A58", "#D2D0CE"
  ]
}
```

---

## WCAG Contrast Requirements

| Level | Ratio | Use |
|-------|-------|-----|
| AA (Normal text) | 4.5:1 | Body text, labels ≤ 18pt |
| AA (Large text) | 3:1 | Headings > 18pt or 14pt bold |
| AAA (Normal text) | 7:1 | Maximum accessibility |

### Checking Contrast

Text color vs. background must meet minimum ratio:
- Black (#000000) on white (#FFFFFF) = 21:1 ✓
- #0078D4 (blue) on white = 4.5:1 ✓ (barely AA)
- #71AFE5 (light blue) on white = 2.3:1 ✗ (fails AA)

**Rule:** Never use `dataColors[2]` through `dataColors[5]` (light shades) as text colors on light backgrounds.

---

## Applying Theme in PBIR

Theme is stored in `report.json` at the report root:

```json
{
  "$schema": "...",
  "themeCollection": {
    "baseTheme": {
      "name": "Corporate",
      "version": "5.52",
      "type": 2
    }
  },
  "settings": {}
}
```

To apply a custom theme, save the `.json` file and reference it via Power BI Desktop:
**View → Themes → Browse for themes**

Or place the theme file in the report folder and update `report.json`.

---

## Dark Mode Theme

```json
{
  "name": "Dark Theme",
  "dataColors": [
    "#36B1DB", "#F2C811", "#00B294", "#E96C51",
    "#8764B8", "#0078D4", "#C8C8C8", "#4C4C4C"
  ],
  "background": "#1A1A2E",
  "foreground": "#F0F0F0",
  "tableAccent": "#36B1DB",
  "visualStyles": {
    "*": {
      "*": {
        "background": [{ "color": { "solid": { "color": "#1A1A2E" } } }],
        "fontColor": [{ "color": { "solid": { "color": "#F0F0F0" } } }]
      }
    }
  }
}
```

---

## Theme Inheritance and Overrides

Specificity order (most specific wins):

```
Report theme (base)
    └── Page-level overrides
            └── Visual-level formatting (Format pane)
```

Visual-level formatting in the Format pane overrides the theme. To prevent drift:
- Set all formatting in the theme
- Avoid per-visual color overrides
- Use `"*": { "*": {...} }` wildcard for global defaults

---

## Common Theme Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Colors not applying | Wrong JSON key name | Use `dataColors` (not `colors`) |
| Font not available | Custom font not installed | Use system fonts (Segoe UI, Arial, Calibri) |
| Theme resets on save | Saved as .pbix not .pbip | Use .pbip format for external theme files |
| WCAG validation fails | Light color on light bg | Darken text color or use darker palette slot |
