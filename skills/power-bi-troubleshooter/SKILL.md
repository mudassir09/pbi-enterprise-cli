---
name: power-bi-troubleshooter
description: >
  Orchestration skill for systematic Power BI troubleshooting. Use when the user
  describes any problem without specifying the cause. Triggers on: "not working",
  "help me fix", "something is wrong", "broken", "why is", "how do I fix",
  "error in my report", "can't connect", "visual is blank", "report won't load".
version: "1.0"
---

# power-bi-troubleshooter

## Triage Decision Tree

```
User reports a problem
         │
         ├─ Can't run pbi-cli at all?
         │   └── Run: pbi doctor
         │       See: power-bi-diagnostics skill
         │
         ├─ Can't connect to Power BI Desktop?
         │   ├── Is Desktop open with a .pbip file? → Open it first
         │   ├── Run: pbi connect (checks port/process)
         │   └── Run: pbi doctor --dlls (checks DLL versions)
         │
         ├─ Report page not showing in Desktop?
         │   ├── Click "Reload" in Desktop (external changes detected)
         │   ├── If no prompt: close/reopen .pbip file
         │   ├── Check: pbi report pages (does CLI see the page?)
         │   └── See: power-bi-report skill
         │
         ├─ Visual is blank or shows error?
         │   ├── Check field names: pbi model columns
         │   ├── Verify table name matches exactly (case-sensitive)
         │   ├── Check visual.json $schema URL
         │   └── See: power-bi-visuals skill → Common Visual Issues
         │
         ├─ DAX measure returns wrong value?
         │   ├── Run: pbi dax validate "EXPRESSION"
         │   ├── Run: pbi dax query "EVALUATE ROW(\"Test\", EXPRESSION)"
         │   └── See: power-bi-diagnostics skill → DAX Debugging Checklist
         │
         ├─ Report is slow?
         │   ├── Run: pbi measure audit --json
         │   ├── Check: bidirectional relationships
         │   └── See: power-bi-performance skill
         │
         ├─ Governance check failing?
         │   ├── Run: pbi govern check --json (see all violations)
         │   ├── Run: pbi govern fix --auto (fix safe violations)
         │   └── See: power-bi-governance skill
         │
         ├─ Deployment failing?
         │   ├── Check XMLA endpoint is enabled (Premium/Fabric required)
         │   ├── Run: pbi deploy diff --workspace "Target"
         │   └── See: power-bi-deployment-pipeline skill
         │
         └─ Data is stale / not refreshing?
             ├─ Small table: refresh in Desktop (Home → Refresh)
             ├─ Large table: check incremental refresh config
             └── See: power-bi-partitions skill
```

---

## Quick Diagnostic Commands

Run these first when anything seems wrong:

```bash
# 1. Check tool environment
pbi doctor

# 2. Verify Desktop connection
pbi connect

# 3. List model tables (proves model is accessible)
pbi model tables

# 4. List pages in report
pbi report pages --pbip "C:/Reports/MyReport"

# 5. Check for governance issues
pbi govern check
```

---

## Error Message Decoder

| Error Message | Root Cause | First Step |
|---------------|-----------|-----------|
| `No *.Report folder found` | Not a .pbip project | File → Save as → Power BI project |
| `No module named 'clr'` | pythonnet not installed | `pip install pythonnet` |
| `No running Power BI Desktop found` | Desktop not open | Open your .pbip file in Desktop |
| `Port 0 in netstat` | Model still loading | Wait 10s, run `pbi connect` again |
| `Access denied to MSMDSRV` | User mismatch | Run terminal as same user as Desktop |
| `$schema property did not match` | Wrong schema URL | Use `visualContainer/2.7.0/schema.json` |
| `Additional property ... not allowed` | Old visual format | Use `query.queryState` structure |
| `Column not found` | Field name typo | Run `pbi model columns` to check exact name |
| `XMLA endpoint not enabled` | Free/Pro workspace | Upgrade to Premium or Fabric |
| `UnicodeEncodeError: 'charmap'` | Windows cp1252 console | Avoid non-ASCII characters in output |

---

## Systematic Fix Protocol

When you don't know the cause:

### Step 1: Isolate
```bash
# Does the CLI work at all?
pbi --version

# Can it see the model?
pbi model tables

# Is the report structure valid?
pbi report pages --pbip "C:/Reports/MyReport"
```

### Step 2: Compare Working vs. Broken
```bash
# Show a working visual vs. broken visual
pbi visual list --pbip "C:/Reports/MyReport" --page "Working Page"
pbi visual list --pbip "C:/Reports/MyReport" --page "Broken Page"
```

### Step 3: Validate the File Directly
```bash
# Read the visual.json that Power BI rejected
cat "financials.Report/definition/pages/{pageGUID}/visuals/{visualGUID}/visual.json"
```

Check against the PBIR GA spec:
- `$schema`: must be `visualContainer/2.7.0/schema.json`
- `visual.visualType`: must be a valid type string
- `visual.query.queryState`: must use role keys (Values, Category, Y, etc.)
- No direct `projections` or `prototypeQuery` at `visual` level

### Step 4: Rollback and Retry
```bash
# Delete the broken visual
pbi visual delete --pbip "..." --page "..." --name {visualId}

# Re-add with explicit positioning
pbi visual add --pbip "..." --page "..." \
  --type card --table financials --value Sales --title "Total Sales" \
  --x 16 --y 16 --width 296 --height 120
```

---

## Skill Routing Guide

| Problem Type | Skill to Use |
|-------------|-------------|
| CLI not running, DLL errors | `power-bi-diagnostics` |
| Page management, page not showing | `power-bi-report`, `power-bi-pages` |
| Visual blank, wrong type, position | `power-bi-visuals`, `power-bi-layout` |
| DAX returning wrong value | `power-bi-diagnostics`, `power-bi-testing` |
| Slow report, performance | `power-bi-performance` |
| Naming violations, audit | `power-bi-governance` |
| Cannot deploy, workspace error | `power-bi-deployment-pipeline` |
| Refresh failing, stale data | `power-bi-partitions` |
| Security, RLS not working | `power-bi-security` |
| Theme, colors wrong | `power-bi-themes`, `power-bi-design-system` |
| Building full solution | `power-bi-patterns` |
