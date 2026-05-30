---
name: power-bi-watch
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for file-system watching of PBIP/PBIR projects: auto-reloading the model on TMDL/PBIR
  changes, live governance checks on save, hot-reload integration with Power BI Desktop, and
  change diffing. Triggers on: "watch", "auto reload", "live reload", "hot reload", "file
  watcher", "pbi watch", "watch for changes", "reload on save", "monitor changes".
version: "1.0"
---

# power-bi-watch

## Quick Reference

```bash
# Watch the current PBIP project — reload model on any TMDL/PBIR change
pbi watch

# Watch and run governance checks on every save
pbi watch --govern

# Watch with a specific path
pbi watch --path "C:/Reports/SalesReport.pbip"

# Watch and show a diff of changes on each reload
pbi watch --diff

# Watch with debounce (wait 500ms after last change before reloading)
pbi watch --debounce 500

# Watch and publish to Desktop on each reload (requires Desktop running)
pbi watch --push-to-desktop
```

---

## How Watch Works

```
File saved in editor
        ↓
  pbi watch detects change (inotify / ReadDirectoryChangesW)
        ↓
  Debounce window (default 300ms) — coalesces rapid saves
        ↓
  Parse changed files (TMDL / PBIR / visualContainer.json)
        ↓
  Reload in-memory model
        ↓
  Optional: run --govern check
  Optional: push to Desktop via local XMLA
  Optional: print --diff
        ↓
  Print status line: "✓ Reloaded [2 files changed] 142ms"
```

---

## Watched File Types

| Extension / Path | Triggers reload? | Notes |
|------------------|-----------------|-------|
| `*.tmdl` | Yes | Model table/measure changes |
| `*.pbir` | Yes | Report page layout changes |
| `visualContainer.json` | Yes | Visual config changes |
| `*.json` (theme files) | Yes | Theme changes |
| `*.yaml` (governance config) | Yes | Rule updates |
| `*.py`, `*.md` | No | Non-model files ignored |

---

## Governance on Save

```bash
pbi watch --govern
```

Runs `pbi govern check` against the changed files on every reload and prints inline results:

```
[14:32:01] ✓ Reloaded (measures/Sales.tmdl)
  [WARN] Measure "rev" violates naming rule: too short (min 3 chars)
  [OK]   All other governance checks passed
  1 warning — fix with: pbi govern fix --auto
```

Use `--govern-fail` to make the watcher exit with a non-zero code on governance errors
(useful when watch is driven from a CI pre-commit hook).

---

## Desktop Hot-Reload

```bash
pbi watch --push-to-desktop
```

After each reload, pushes the updated model to a running Power BI Desktop instance via the
local XMLA loopback endpoint. Visuals refresh automatically — no need to close and reopen
the `.pbix` file.

Requirements:
- Power BI Desktop must be running with the same `.pbip` project open.
- The XMLA loopback port must be enabled in Desktop options.

---

## Change Diffing

```bash
pbi watch --diff
```

Prints a human-readable diff of what changed on each reload:

```
[14:35:12] ✓ Reloaded (measures/Sales.tmdl) — 1 measure changed

  ~ [Measure] Sales[Total Revenue]
      expression:
    -   SUM(Sales[Revenue])
    +   SUMX(Sales, Sales[Quantity] * Sales[UnitPrice])
      formatString: (unchanged) "$#,0.00"
```

---

## Configuration File

Add a `watch.json` to your project root to persist watch settings:

```json
{
  "path": ".",
  "debounce": 300,
  "govern": true,
  "diff": false,
  "pushToDesktop": false,
  "ignore": ["*.tmp", ".git/**", "node_modules/**"]
}
```

`pbi watch` reads `watch.json` automatically if present; CLI flags override file settings.
