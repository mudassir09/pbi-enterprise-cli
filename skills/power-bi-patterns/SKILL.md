---
name: power-bi-patterns
description: >
  Orchestration skill for common Power BI solution patterns: end-to-end workflows,
  multi-skill coordination, and architectural patterns. Triggers on: "build a full report",
  "end-to-end", "set up a complete", "from scratch", "full dashboard", "solution pattern",
  "best practice workflow", "complete Power BI project".
version: "1.0"
---

# power-bi-patterns

## Common Solution Patterns

This skill orchestrates multiple pbi-cli skills to build complete Power BI solutions.

---

## Pattern 1: Executive Dashboard (Financials Model)

### What You Get

- 3-page report (Executive Summary, Sales Analysis, Profit Analysis)
- 14 visuals auto-positioned
- Corporate theme applied
- Governance checked

### Steps

```bash
# 1. Save your .pbix as .pbip first (File → Save as → Power BI project)

# 2. Scaffold all 3 pages with visuals
pbi report scaffold --pbip "C:/Reports/financials" --model financials --pages 3 --replace

# 3. Apply corporate theme
pbi theme apply --pbip "C:/Reports/financials" --theme themes/corporate.json

# 4. Run governance check
pbi govern check --pbip "C:/Reports/financials"

# 5. Reload in Power BI Desktop (Ctrl+Z to dismiss, then reload)
```

### Skills Involved

`power-bi-report` → `power-bi-visuals` → `power-bi-themes` → `power-bi-governance`

---

## Pattern 2: Self-Service Analytics Model

### Architecture

```
Raw Data Source
      │
      ▼
Power Query (ETL)
      │
      ▼
Star Schema (Import mode)
  ├── Fact: Sales (transactions)
  ├── Dim: Date (calendar table)
  ├── Dim: Product (with hierarchy)
  ├── Dim: Customer (with RLS)
  └── Dim: Geography
      │
      ▼
DAX Measures (business logic)
      │
      ▼
Report Layer (visuals, pages)
```

### Steps

```bash
# 1. Validate model structure
pbi model tables
pbi model relationships

# 2. Add date table if missing
pbi measure add --table Date --name "IsWeekend" \
  --dax "IF(WEEKDAY(Date[Date], 2) >= 6, 1, 0)"

# 3. Create standard measures
pbi measure add --table Sales --name "Total Revenue" \
  --dax "SUM(Sales[Revenue])" --format "$#,0.00"
pbi measure add --table Sales --name "Revenue YTD" \
  --dax "CALCULATE([Total Revenue], DATESYTD(Date[Date]))" --format "$#,0.00"

# 4. Set up RLS for customer segmentation
pbi security role add --role "RegionManager" \
  --filter "Geography[Region] = USERPRINCIPALNAME()"

# 5. Govern
pbi govern check
```

### Skills Involved

`power-bi-modeling` → `power-bi-security` → `power-bi-governance`

---

## Pattern 3: Incremental Refresh for Large Tables

### When to Use

- Fact table > 10M rows
- Daily or intra-day refresh needed
- Refresh taking > 30 minutes

### Steps

```bash
# 1. Export current TMDL
pbi database export-tmdl ./tmdl/

# 2. Edit tmdl/tables/Sales.tmdl — add refresh policy
# (see power-bi-partitions skill for TMDL syntax)

# 3. Import updated TMDL
pbi database import-tmdl ./tmdl/

# 4. Deploy to workspace
pbi deploy push --workspace "Dev"

# 5. Trigger initial full refresh from Power BI Service
# (subsequent refreshes will be incremental)
```

### Skills Involved

`power-bi-partitions` → `power-bi-deployment`

---

## Pattern 4: Governed Report Release

### Full CI/CD Workflow

```bash
# Developer workflow
git checkout -b feature/add-profit-page
pbi report page-add --pbip "./financials" --name "Profit Analysis"
pbi visual add ... (add visuals)
pbi govern check   # must pass
pbi dax test       # must pass
git commit -am "feat: add Profit Analysis page"
git push && open PR

# CI runs automatically on PR:
# - pbi govern check --json
# - pbi dax test --junit test-results.xml
# - pbi deploy diff --workspace "Dev"

# On merge to main (CD):
# - pbi deploy push --workspace "Dev"

# On release tag (CD with approval):
# - pbi deploy promote --from "Dev" --to "Test"
# - pbi deploy promote --from "Test" --to "Prod"
```

### Skills Involved

`power-bi-governance` → `power-bi-testing` → `power-bi-deployment-pipeline`

---

## Pattern 5: Report Migration (PBIX to PBIR)

### Steps

```bash
# 1. Open .pbix in Power BI Desktop
# 2. File → Save as → Power BI project (.pbip)
#    This converts to PBIR GA format automatically

# 3. Verify PBIR structure
ls "C:/Reports/financials.Report/definition/"

# 4. Check all pages loaded correctly
pbi report pages --pbip "C:/Reports/financials"

# 5. Validate visuals render
# (Open in Desktop, check for reload prompt, verify all pages)

# 6. Add to version control
cd "C:/Reports/"
git init
git add financials.pbip financials.Report/
git commit -m "Initial PBIR migration"
```

---

## Pattern 6: Multi-Report Consistency

### Keep Reports Consistent Across a Team

```bash
# 1. Create and store shared design system
pbi design export-theme --system "corporate" --output themes/corporate.json
git add themes/corporate.json
git commit -m "Add corporate theme"

# 2. Apply to all reports
for report in reports/*/; do
  pbi theme apply --pbip "$report" --theme themes/corporate.json
done

# 3. Run governance on all reports
for report in reports/*/; do
  pbi govern check --pbip "$report" --json >> governance-all.json
done

# 4. Enforce via pre-commit hook
# .git/hooks/pre-commit:
#   pbi govern check --pbip "." || exit 1
```

### Skills Involved

`power-bi-themes` → `power-bi-design-system` → `power-bi-governance`

---

## Decision Matrix: Which Pattern to Use

| Situation | Pattern |
|-----------|---------|
| New report for stakeholders | Pattern 1 (Executive Dashboard) |
| Building analytics for a team | Pattern 2 (Self-Service Model) |
| Data volume > 10M rows | Pattern 3 (Incremental Refresh) |
| Production release needed | Pattern 4 (Governed Release) |
| Converting existing .pbix | Pattern 5 (PBIX Migration) |
| Maintaining multiple reports | Pattern 6 (Multi-Report Consistency) |
