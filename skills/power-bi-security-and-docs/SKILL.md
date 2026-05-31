---
name: power-bi-security-and-docs
version: "2.0"
min_cli_version: "1.0.0"
description: >
  Use for RLS role management, DAX row-filter expressions, perspective management,
  role testing, data dictionary generation, audit logs, and lineage documentation.
  Triggers on: "RLS", "row-level security", "role", "row filter", "perspective",
  "data dictionary", "pbi security", "pbi docs", "audit log", "lineage",
  "Confluence", "markdown docs", "measure catalog", "OLS", "sensitivity label".
  Do NOT trigger for governance naming rules (→ power-bi-governance), report
  visuals (→ power-bi-report-design), or model schema (→ power-bi-modeling).
---

# power-bi-security-and-docs

RLS security, perspectives, role testing, data dictionary, audit logs, and lineage.

## Quick Reference

```bash
# RLS role management
pbi security roles list
pbi security role-add --name "EMEA Sales" \
  --table Sales --filter "Sales[Region] = USERNAME()"
pbi security role-add --name "Manager View" \
  --table Employee --filter "Employee[ManagerEmail] = USERPRINCIPALNAME()"
pbi security role-delete --name "Old Role"
pbi security role-test --role "EMEA Sales" --user "alice@contoso.com"
pbi security role-test --role "EMEA Sales" --user "alice@contoso.com" --json

# Perspectives
pbi security perspective-add --name "Finance View" \
  --include-tables "Sales,Calendar,Finance" \
  --include-measures "Total Revenue,Gross Margin %"
pbi security perspective-list
pbi security perspective-delete --name "Draft"

# Documentation generation
pbi docs generate --format markdown --output ./docs/data-dictionary.md
pbi docs generate --format confluence --output ./docs/confluence-export.json
pbi docs generate --format markdown --include-measures --include-lineage
pbi docs generate --table Sales --format markdown   # single table
pbi docs lineage --format mermaid --output ./docs/lineage.md
pbi docs lineage --format json --output ./docs/lineage.json

# Audit log
pbi docs audit-log --last 30d --format json
pbi docs audit-log --user "alice@contoso.com" --format markdown
```

---

## Worked Example 1: Dynamic RLS with USERNAME()

```bash
# Role: each user sees only their region's data
pbi security role-add \
  --name "Regional Sales Rep" \
  --table Sales \
  --filter "Sales[Region] = LOOKUPVALUE(Employee[Region], Employee[Email], USERNAME())"

# Test as two different users
pbi security role-test --role "Regional Sales Rep" --user "emea.rep@contoso.com" --json
pbi security role-test --role "Regional Sales Rep" --user "apac.rep@contoso.com" --json
```

Expected JSON output:
```json
{
  "role": "Regional Sales Rep",
  "user": "emea.rep@contoso.com",
  "rowsVisible": {
    "Sales": 142000,
    "Customer": 8400
  },
  "filterExpression": "Sales[Region] = \"EMEA\""
}
```

---

## Worked Example 2: Manager hierarchy RLS

```bash
# Each manager sees their direct reports' data
pbi security role-add \
  --name "Manager Hierarchy" \
  --table Employee \
  --filter "Employee[ManagerEmail] = USERPRINCIPALNAME() || Employee[Email] = USERPRINCIPALNAME()"

# Test — manager should see their own row + direct reports
pbi security role-test --role "Manager Hierarchy" --user "manager@contoso.com"
```

---

## Worked Example 3: Generate a full data dictionary and lineage doc

```bash
# Generate markdown data dictionary (measures + columns + descriptions)
pbi docs generate \
  --format markdown \
  --include-measures \
  --include-lineage \
  --output ./docs/data-dictionary.md

# Generate Mermaid lineage diagram
pbi docs lineage --format mermaid --output ./docs/lineage.md

# Generate Confluence-ready JSON export
pbi docs generate --format confluence --output ./confluence/model-docs.json
```

Markdown output structure:
```markdown
# Data Dictionary — Sales Model

## Tables

### Sales
| Column | Type | Description |
|--------|------|-------------|
| OrderDate | DateTime | Date the order was placed |
| Revenue | Decimal | Net revenue after discounts |

## Measures

### [Total Revenue]
**Expression:** `SUM(Sales[Revenue])`
**Format:** `#,0.00`
**Description:** Net revenue after all discounts applied
```

---

## RLS Filter Expression Reference

| Pattern | Expression |
|---|---|
| Static value | `Sales[Region] = "EMEA"` |
| Current user (email) | `Employee[Email] = USERNAME()` |
| UPN-based (Azure AD) | `Employee[UPN] = USERPRINCIPALNAME()` |
| Lookup from user table | `LOOKUPVALUE(Employee[Region], Employee[Email], USERNAME())` |
| Manager hierarchy | `Employee[ManagerUPN] = USERPRINCIPALNAME() \|\| Employee[UPN] = USERPRINCIPALNAME()` |
| Parameterised | `Sales[SensitivityLevel] <= LOOKUPVALUE(UserAccess[Level], UserAccess[UPN], USERNAME())` |

---

## Perspective Use Cases

Perspectives do not enforce security — they only control visibility in client tools.

| Use case | What to include |
|---|---|
| Finance team | Finance tables + all financial measures |
| Operations | Ops tables; exclude HR and Finance |
| Executive | Pre-calculated KPI measures only; hide source tables |

```bash
pbi security perspective-add \
  --name "Executive KPIs" \
  --include-measures "Total Revenue,Gross Margin %,YTD Revenue,Headcount" \
  --exclude-tables "Sales,HR,Finance"
```

---

## Audit Log Schema

```json
[
  {
    "timestamp": "2026-05-31T14:23:00Z",
    "user": "alice@contoso.com",
    "action": "measure.add",
    "target": "Sales.[Total Revenue]",
    "backend": "desktop",
    "result": "success"
  }
]
```

---

## Edge Cases

**Role test returns 0 rows unexpectedly:** Check whether the DAX filter expression references the correct table/column names. `USERNAME()` returns `DOMAIN\user` on Desktop but UPN format in the cloud — test both.

**Data dictionary missing descriptions:** Descriptions are sourced from the model's `description` properties on columns and measures. Add them with `pbi measure update --name X --description "..."`.

**Lineage shows "unknown source":** REST and custom connector sources may not expose lineage metadata. Document these sources manually.

---

## Cross-skill handoffs

- Model schema (tables, columns, relationships) → **power-bi-modeling**
- Governance checks including sensitivity labels → **power-bi-governance**
- DAX filter expression syntax → **power-bi-dax**
- Deployment with security roles intact → **power-bi-deployment**
