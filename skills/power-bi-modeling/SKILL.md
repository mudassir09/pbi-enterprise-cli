---
name: power-bi-modeling
description: >
  Use for semantic model design: star schema, dimensional modeling, relationships,
  calculated columns, data types, model optimization, and scaffolding from source
  profiles. Triggers on: "design a model", "star schema", "fact table", "dimension",
  "relationship", "calculated column", "pbi model", "pbi source scaffold",
  "cardinality", "many-to-many", "role-playing dimension".
version: "1.0"
---

# power-bi-modeling

## Quick Reference: pbi model Commands

```bash
pbi model info
pbi model tables
pbi model columns --table Sales
pbi model relationships
pbi model lint
pbi model suggest-measures
pbi model lineage --format mermaid

pbi source profile --type sql --conn "Server=...;Database=...;" --output profile.json
pbi source scaffold --profile profile.json
pbi source suggest-joins --profiles fact.json,dim.json

pbi database export-tmdl ./tmdl/
pbi database import-tmdl ./tmdl/
```

---

## Star Schema Design Checklist

| Step | Action | CLI Command |
|------|--------|-------------|
| 1 | Profile source tables | `pbi source profile` |
| 2 | Identify fact table (highest row count) | `pbi source scaffold` |
| 3 | Identify dimensions (lookup tables) | `pbi source scaffold` |
| 4 | Detect join candidates | `pbi source suggest-joins` |
| 5 | Verify naming conventions | `pbi model lint` |
| 6 | Generate starter measures | `pbi model suggest-measures` |

---

## Dimensional Patterns

### Slowly Changing Dimension (SCD) Type 2

```dax
-- To query current records only
Current Customers = CALCULATE(
    COUNTROWS(Customers),
    Customers[IsCurrent] = TRUE()
)

-- Historical measure using bridge table
Revenue at Sale = CALCULATE(
    SUM(Sales[Revenue]),
    USERELATIONSHIP(Sales[CustomerKey], CustomerHistory[CustomerKey])
)
```

### Role-Playing Dimensions

When one dimension table (e.g. Calendar) is related to a fact table by multiple date columns:

```dax
-- Create inactive relationship, activate with USERELATIONSHIP
Revenue by Ship Date = CALCULATE(
    SUM(Sales[Revenue]),
    USERELATIONSHIP(Sales[ShipDate], Calendar[Date])
)

Revenue by Order Date = SUM(Sales[Revenue])  -- uses active relationship
```

### Many-to-Many via Bridge Table

```
Sales → SalesTerritories → Territories
         (bridge)
```

```dax
Revenue by Territory = CALCULATE(
    SUM(Sales[Revenue]),
    TREATAS(VALUES(Territories[TerritoryKey]), SalesTerritories[TerritoryKey])
)
```

### Junk Dimension

Combine low-cardinality flag columns into a single dimension:

```
Instead of: Sales[IsOnline], Sales[IsDiscounted], Sales[IsReturn]
Create:     JunkDim[OnlineFlag], JunkDim[DiscountFlag], JunkDim[ReturnFlag]
```

### Degenerate Dimension

Order numbers, invoice numbers — store directly in the fact table, no separate table needed.

---

## Relationship Cardinality Reference

| Cardinality | Direction | When to Use |
|-------------|-----------|-------------|
| Many-to-One (*:1) | Single | Standard fact→dimension (preferred) |
| One-to-One (1:1) | Single | Vertical table split |
| Many-to-Many (*:*) | Both | Role-playing, bridge tables |
| One-to-Many (1:*) | Single | Dimension→fact (avoid; use *:1 from fact side) |

**Rule:** Always model from fact (*) → dimension (1). Bidirectional filters are expensive — use CROSSFILTER() in DAX instead.

---

## Naming Conventions (`pbi model lint` enforces these)

| Object | Convention | Example |
|--------|-----------|---------|
| Tables | PascalCase, singular | `Sales`, `Customer`, `Calendar` |
| Columns | PascalCase | `OrderDate`, `UnitPrice` |
| Measures | `[Title Case in Brackets]` | `[Total Revenue]`, `[YTD Sales]` |
| Hidden columns | `_PascalCase` prefix | `_CustomerKey` |
| Calculated columns | PascalCase, no measure brackets | `FullName` |

---

## Calculated Column vs Measure Decision

| Use Calculated Column | Use Measure |
|----------------------|-------------|
| Value is per-row fixed | Value depends on filter context |
| Used as a slicer or axis | Used as a plotted value |
| Low cardinality result | Aggregation needed |
| Example: `FullName = CONCAT(First, " ", Last)` | Example: `Total Revenue = SUM(Sales[Revenue])` |

---

## Scaffold Output Interpretation

`pbi source scaffold` produces a JSON model spec:

```json
{
  "tables": [
    {
      "name": "Sales",
      "role": "fact",
      "columns": [...],
      "suggestedMeasures": [
        {"name": "Total Revenue", "expression": "SUM(Sales[Revenue])"},
        {"name": "Order Count", "expression": "COUNTROWS(Sales)"}
      ]
    },
    {
      "name": "Customer",
      "role": "dimension",
      "keyColumn": "CustomerKey"
    }
  ],
  "relationships": [
    {"from": "Sales[CustomerKey]", "to": "Customer[CustomerKey]", "cardinality": "*:1"}
  ]
}
```

Apply it: `pbi source scaffold --profile profile.json --apply`
