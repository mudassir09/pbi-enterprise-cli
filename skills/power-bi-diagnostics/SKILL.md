---
name: power-bi-diagnostics
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for diagnosing Power BI performance issues, DAX query problems, model errors,
  connection failures, and pbi-cli setup issues. Triggers on: "slow", "performance",
  "not working", "error", "connection failed", "timeout", "pbi doctor", "diagnose",
  "debug", "why is my report slow", "measure returns wrong value", "blank visual".
version: "1.0"
---

# power-bi-diagnostics

## Quick Reference

```bash
# Setup and connectivity diagnosis
pbi doctor

# Model health checks
pbi model lint
pbi govern check
pbi measure audit

# DAX debugging
pbi dax validate "YOUR_EXPRESSION"
pbi dax query "EVALUATE SUMMARIZE(Sales, Sales[Region], \"Rev\", SUM(Sales[Revenue]))"

# Connection
pbi connect
```

---

## Diagnostic Decision Tree

```
Problem reported
│
├── Cannot connect to Power BI Desktop
│   └── Run: pbi doctor
│       ├── pythonnet not installed → pip install pythonnet
│       ├── DLL load failure → check DLL directory, run pbi doctor --dlls
│       └── No PBI process → open a .pbix file first
│
├── DAX measure returns blank/wrong value
│   ├── Run: pbi dax validate "EXPRESSION"
│   ├── Check: filter context (is CALCULATE needed?)
│   ├── Check: relationship active? (use USERELATIONSHIP)
│   └── Check: DIVIDE instead of "/" (avoids divide-by-zero blank)
│
├── Report is slow to load
│   ├── Run: pbi measure audit (find high-complexity measures)
│   ├── Check: bidirectional relationships (disable where possible)
│   ├── Check: calculated columns vs. measures (move to measures)
│   └── See Performance section below
│
├── Governance violation blocking pipeline
│   ├── Run: pbi govern check --json
│   ├── Auto-fix: pbi govern fix --auto
│   └── Manual: review remaining violations
│
└── Deploy fails
    ├── Run: pbi deploy diff --workspace "Target"
    ├── Check: XMLA endpoint configured
    └── Check: service principal permissions
```

---

## `pbi doctor` Output Interpretation

```
[OK]  pythonnet 3.0.3 loaded
[OK]  Microsoft.AnalysisServices.Tabular.dll found
[OK]  msmdsrv.exe running on port 52714
[OK]  Connected to model: AdventureWorks (CompatibilityLevel 1565)
[WARN] ADOMD DLL version mismatch: expected 19.x, found 18.x
[FAIL] Cannot load Microsoft.AnalysisServices.Core.dll
```

| Status | Meaning | Action |
|--------|---------|--------|
| OK | Component healthy | None needed |
| WARN | Functional but suboptimal | Review recommendation |
| FAIL | Blocking issue | Follow fix instructions |

---

## DAX Measure Debugging Checklist

**Step 1:** Validate syntax
```bash
pbi dax validate "[Total Revenue] = SUM(Sales[Revenue])"
```

**Step 2:** Test in isolation
```bash
pbi dax query "EVALUATE ROW(\"Test\", SUM(Sales[Revenue]))"
```

**Step 3:** Test with context
```bash
pbi dax query "EVALUATE CALCULATETABLE(ROW(\"Test\", SUM(Sales[Revenue])), Sales[Region] = \"East\")"
```

**Step 4:** Check dependencies
```bash
pbi model lineage --measure "[Total Revenue]"
```

**Step 5:** Run full audit
```bash
pbi measure audit --json
```

---

## Common DAX Return Values and Their Meaning

| Returns | Likely Cause |
|---------|-------------|
| BLANK() | No matching rows; check filter context |
| 0 | Aggregation returned zero (not blank) — may be correct |
| Same value everywhere | Filter context not applied; missing CALCULATE |
| Error: Circular dependency | Measure references itself directly or indirectly |
| Error: Column not found | Typo in table or column name; check with `pbi model columns` |
| #ERROR in visual | DAX evaluation error; use `pbi dax validate` |

---

## Performance Diagnosis

### Measure Complexity
```bash
pbi measure audit --json | jq '.[] | select(.complexityScore > 50)'
```

High complexity (> 50) measures are the primary cause of slow visuals.

### Expensive Patterns to Detect

```dax
-- AVOID: FILTER(ALL()) on large tables
Revenue Filtered = CALCULATE(SUM(Sales[Revenue]), FILTER(ALL(Sales), Sales[Region] = "East"))
-- PREFER:
Revenue East = CALCULATE(SUM(Sales[Revenue]), Sales[Region] = "East")

-- AVOID: Nested iterators
= SUMX(Products, SUMX(RELATEDTABLE(Sales), Sales[Revenue]))
-- PREFER: Pre-aggregate with SUMMARIZE

-- AVOID: COUNT(column) on non-key column
= COUNT(Sales[OrderID])  -- scans all rows
-- PREFER:
= COUNTROWS(Sales)  -- same result, faster
```

### Relationship Issues

```bash
pbi model relationships --json | jq '.[] | select(.isActive == false)'
```

Inactive relationships with bidirectional filter direction cause fan traps.

---

## Setup Issues Reference

| Issue | Fix |
|-------|-----|
| `No module named 'clr'` | `pip install pythonnet` |
| `Could not load type System.ComponentModel` | Use net45 DLLs (not netcoreapp) — run `pbi doctor --dlls` |
| `No running Power BI Desktop found` | Open a .pbix file first, then retry |
| `Port 0 in netstat` | PBI not finished loading; wait 10 seconds and retry |
| `Access denied to MSMDSRV` | Run terminal as same user who opened Power BI Desktop |
| `ADOMD connection refused` | Ensure model is loaded (not just Desktop window, but file is open) |
