---
name: power-bi-modeling
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for semantic model design, data source profiling, partition management,
  incremental refresh, calendar table generation, and locale/culture settings.
  Triggers on: "star schema", "dimensional model", "fact table", "dimension",
  "relationship", "calculated column", "pbi model", "pbi source", "pbi partition",
  "incremental refresh", "pbi calendar", "pbi culture", "scaffold", "cardinality",
  "many-to-many", "role-playing dimension", "source profiling", "M query".
  Do NOT trigger for DAX measure writing (→ power-bi-dax), report visuals
  (→ power-bi-report-design), or governance rules (→ power-bi-governance).
---

# power-bi-modeling

Data modelling: star schema design, source profiling, partitions, incremental refresh, calendar generation, and locale settings.

## Quick Reference

```bash
# Model inspection
pbi model info
pbi model tables
pbi model columns --table Sales
pbi model relationships
pbi model lint
pbi model suggest-measures
pbi model lineage --format mermaid

# Source profiling and scaffolding
pbi source profile --type sql --conn "Server=prod;Database=SalesDW;" --output profile.json
pbi source profile --type excel --file ./data/source.xlsx --output profile.json
pbi source profile --type rest --url https://api.example.com/sales --output profile.json
pbi source scaffold --profile profile.json
pbi source scaffold --profile profile.json --apply    # write directly to open model
pbi source suggest-joins --profiles fact.json,dim.json

# Partition management
pbi partition list --table Sales
pbi partition add --table Sales --name "Sales_2025" --filter "Year = 2025"
pbi partition refresh --table Sales --name "Sales_2025"
pbi partition delete --table Sales --name "Sales_2024"

# Incremental refresh
pbi partition incremental --table Sales \
  --range-start 2020-01-01 --range-end TODAY \
  --incremental-window 30d --full-window 3y

# Calendar table
pbi calendar create --start 2020-01-01 --end 2027-12-31 --table-name Calendar
pbi calendar create --fiscal-year-end 06-30    # June fiscal year
pbi calendar mark-as-date-table --table Calendar --date-column Date

# Locale / culture
pbi culture set --locale en-US
pbi culture set --locale en-GB --decimal "." --thousands ","
pbi culture list

# TMDL snapshots
pbi database export-tmdl ./tmdl/
pbi database import-tmdl ./tmdl/
```

---

## Worked Example 1: Profile a SQL source and scaffold a star schema

```bash
# Step 1 — profile the source (works against mock backend for schema discovery)
pbi source profile \
  --type sql \
  --conn "Server=prod-sql;Database=SalesDW;Trusted_Connection=True;" \
  --output ./profiles/salesdw.json

# Step 2 — review suggested relationships
pbi source suggest-joins --profiles ./profiles/salesdw.json

# Step 3 — apply the scaffold to the open Desktop model
pbi source scaffold --profile ./profiles/salesdw.json --apply

# Step 4 — lint the resulting model
pbi model lint
```

Expected output after scaffold:
```json
{
  "tables": [
    {"name": "Sales", "role": "fact", "rowCount": 4200000},
    {"name": "Customer", "role": "dimension", "keyColumn": "CustomerKey"},
    {"name": "Product",  "role": "dimension", "keyColumn": "ProductKey"}
  ],
  "relationships": [
    {"from": "Sales[CustomerKey]", "to": "Customer[CustomerKey]", "cardinality": "*:1"},
    {"from": "Sales[ProductKey]",  "to": "Product[ProductKey]",   "cardinality": "*:1"}
  ]
}
```

---

## Worked Example 2: Set up incremental refresh for a large fact table

```bash
# Configure incremental refresh — keeps 3 years full, refreshes last 30 days
pbi partition incremental \
  --table Sales \
  --range-start 2022-01-01 \
  --range-end TODAY \
  --incremental-window 30d \
  --full-window 3y

# Verify partition plan
pbi partition list --table Sales

# Trigger a refresh of the incremental partition only
pbi partition refresh --table Sales --name "Sales_incremental"
```

---

## Worked Example 3: Generate a fiscal-year calendar and mark as date table

```bash
# UK fiscal year (April to March)
pbi calendar create \
  --start 2020-01-01 \
  --end 2027-12-31 \
  --table-name FiscalCalendar \
  --fiscal-year-end 03-31

pbi calendar mark-as-date-table --table FiscalCalendar --date-column Date

# Verify the model sees it as a date table
pbi model tables --json | jq '.[] | select(.isDateTable)'
```

---

## Dimensional Patterns

### Star Schema (preferred)
```
        Customer ─┐
        Product  ─┤
        Calendar ─┼─→ Sales (fact)
        Territory─┤
        Promotion─┘
```

### Role-Playing Dimensions
```dax
-- Calendar related to Sales on three date columns
-- Active: OrderDate; inactive: ShipDate, DueDate
Revenue by Ship Date = CALCULATE(
    SUM(Sales[Revenue]),
    USERELATIONSHIP(Sales[ShipDate], Calendar[Date])
)
```

### Many-to-Many via Bridge Table
```
Sales → SalesTerritories (bridge) → Territories
```

Use `TREATAS` in DAX for best performance over bidirectional filters.

---

## Relationship Cardinality Reference

| Cardinality | When to use |
|---|---|
| `*:1` fact → dimension | Standard; always prefer this direction |
| `1:1` | Vertical table split (large wide table) |
| `*:*` | Bridge tables, role-playing; minimize bidirectional |

---

## Edge Cases

**Desktop not running:** `pbi model tables` exits with code 2 and message "No running Power BI Desktop found." Open a `.pbip` file before running model commands.

**Source profile on REST API with auth:** Add `--auth bearer` and set `PBI_REST_TOKEN` env var. Device-flow OAuth: `--auth device-flow`.

**Partition refresh on XMLA:** Requires Premium/Fabric workspace. Set `--backend xmla` and ensure a connection is configured (`pbi connections add`).

**Calendar already exists:** `pbi calendar create` exits 1 if the table name already exists. Use `--replace` to overwrite.

---

## Cross-skill handoffs

- Writing DAX measures for the modelled tables → **power-bi-dax**
- Governance checks on naming conventions → **power-bi-governance**
- Deploying the model to Premium/Fabric → **power-bi-deployment**
- Report visuals using the model → **power-bi-report-design**

---

## Enterprise Patterns

### CI/CD schema drift detection
```yaml
- name: Export TMDL snapshot
  run: pbi --backend mock database export-tmdl ./tmdl/

- name: Diff against main branch snapshot
  run: git diff --exit-code ./tmdl/
```

### Automated source scaffold on schema change
```bash
# In a data pipeline step after ETL completes:
pbi source profile --type sql --conn "$CONN_STR" --output profile.json
pbi source scaffold --profile profile.json --apply --dry-run   # preview
pbi source scaffold --profile profile.json --apply             # apply
pbi govern check --fail-on error                               # gate
```
