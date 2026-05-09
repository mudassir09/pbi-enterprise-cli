---
name: power-bi-security
description: >
  Use for Row-Level Security (RLS), Object-Level Security (OLS), workspace roles,
  sensitivity labels, and secure deployment patterns. Triggers on: "RLS", "row-level
  security", "restrict data by user", "dynamic security", "object-level security",
  "who can see what", "security roles", "USERNAME()", "USERPRINCIPALNAME()".
version: "1.0"
---

# power-bi-security

## Quick Reference

```bash
# Export model to inspect/edit RLS roles in TMDL
pbi database export-tmdl ./tmdl/

# After editing TMDL roles locally
pbi database import-tmdl ./tmdl/

# Validate model including security rules
pbi model lint
pbi govern check
```

---

## Row-Level Security Patterns

### Static RLS (simple, low maintenance)

```dax
-- Role: "Australia Only"
-- Table: Sales, filter expression:
Sales[Country] = "Australia"
```

Use when: small number of fixed regions, roles rarely change.

### Dynamic RLS (scales to thousands of users)

Requires a security mapping table (`UserSecurity`) with columns: `Email`, `Region`.

```dax
-- Role: "Dynamic Regional"
-- Table: Sales, filter expression:
Sales[Region] IN
    CALCULATETABLE(
        VALUES(UserSecurity[Region]),
        UserSecurity[Email] = USERPRINCIPALNAME()
    )
```

```dax
-- Simpler pattern using LOOKUPVALUE
Sales[Region] = LOOKUPVALUE(
    UserSecurity[Region],
    UserSecurity[Email], USERPRINCIPALNAME()
)
```

### Hierarchical RLS (managers see their team's data)

```dax
-- UserSecurity: Email, ManagerEmail, Region
-- Employees see their own data; managers see their reports' data
VAR CurrentUser = USERPRINCIPALNAME()
RETURN
    Sales[SalesRepEmail] = CurrentUser
    || Sales[SalesRepEmail] IN
        CALCULATETABLE(
            VALUES(UserSecurity[Email]),
            UserSecurity[ManagerEmail] = CurrentUser
        )
```

### Many-to-Many RLS (users belong to multiple groups)

```dax
-- UserGroups: Email, GroupKey
-- GroupPermissions: GroupKey, RegionKey
-- Filter on the fact table via bridge:
Sales[RegionKey] IN
    CALCULATETABLE(
        VALUES(GroupPermissions[RegionKey]),
        FILTER(UserGroups, UserGroups[Email] = USERPRINCIPALNAME())
    )
```

---

## Object-Level Security (OLS)

OLS hides entire tables or columns. Configure in TMDL:

```tmdl
table Payroll
    isHidden: true
    
    column Salary
        dataType: decimal
        isAvailableInMdx: false
```

OLS is enforced at the XMLA/AS layer — it cannot be bypassed by DAX.

---

## RLS Testing Pattern

```dax
-- Test in DAX Studio: impersonate a user
EVALUATE
CALCULATETABLE(
    SUMMARIZE(Sales, Sales[Region], "Revenue", SUM(Sales[Revenue])),
    USERELATIONSHIP(UserSecurity[Email], UserSecurity[Email])
)
-- (use Power BI Desktop "View as" → specific user for UI testing)
```

---

## Security Roles in TMDL

```tmdl
role SalesManager
    modelPermission: read
    
    tablePermission Sales
        filterExpression: >-
            Sales[Region] IN
                CALCULATETABLE(
                    VALUES(UserSecurity[Region]),
                    UserSecurity[Email] = USERPRINCIPALNAME()
                )
```

Export with `pbi database export-tmdl` to find and edit role definitions.

---

## Workspace Role Reference

| Role | Can Edit Model | Can Edit Reports | Can View | Can Share |
|------|--------------|-----------------|----------|-----------|
| Admin | Yes | Yes | Yes | Yes |
| Member | Yes | Yes | Yes | Yes |
| Contributor | No | Yes | Yes | No |
| Viewer | No | No | Yes | No |

---

## Common RLS Mistakes

| Mistake | Fix |
|---------|-----|
| Filtering on a dimension that doesn't directly join the fact | Apply filter to dimension table; propagate via relationship |
| USERPRINCIPALNAME() returns wrong value in Desktop | Use "View as role" in Desktop — UPN is only populated in Service |
| RLS slows report dramatically | Index the filter column in the source; reduce UserSecurity table size |
| Users see all data despite RLS | Check if user has Admin/Member workspace role (bypasses RLS) |

---

## Sensitivity Labels

Apply via Power BI Service Admin Portal or via REST API. Cannot be set via `pbi-cli` — note this to users asking for automation.

**Recommended label tiers:**
- `Public` — sample/demo data
- `Internal` — standard business reports
- `Confidential` — HR, payroll, PII
- `Highly Confidential` — executive comp, M&A
