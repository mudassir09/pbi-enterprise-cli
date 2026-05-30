# Source Profiling Guide

`pbi source profile` introspects a data source and returns a structured schema
description. `pbi source scaffold` then generates TMDL files from that profile.

---

## Supported Source Types

### SQL Server / Azure SQL

```bash
pbi source profile \
  --source "mssql://server.database.windows.net/SalesDW" \
  --output json
```

Uses `INFORMATION_SCHEMA.COLUMNS` and `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`
to enumerate tables, columns, primary keys, and foreign keys.

### Fabric Lakehouse / Warehouse

```bash
pbi source profile \
  --source "fabric://workspace-id/lakehouse-id" \
  --output json
```

Uses the Fabric REST API (`/v1/workspaces/{id}/lakehouses/{id}/tables`).

### Snowflake

```bash
pbi source profile \
  --source "snowflake://account/SALES_DW/PUBLIC" \
  --output json
```

Uses `INFORMATION_SCHEMA.COLUMNS` via the Snowflake Python connector.

### Excel / CSV

```bash
pbi source profile --source ./data/sales.xlsx --output json
pbi source profile --source ./data/sales.csv  --output json
```

Reads the file with `openpyxl` / `csv` and infers column types.

### REST API (JSON)

```bash
pbi source profile \
  --source "https://api.example.com/orders" \
  --output json
```

Fetches a sample page and infers schema from the JSON response shape.

---

## Classification Logic

Tables are classified as **fact** or **dimension** using this heuristic:

| Rule | Result |
|------|--------|
| Row count > 10,000 AND has FK to ≥ 2 other tables | `fact` |
| Name starts with `Fact` or `fact_` | `fact` |
| Contains only lookup/reference columns | `dimension` |
| Everything else | `dimension` (conservative default) |

### Overriding classification

```bash
pbi source profile \
  --source "mssql://server/db" \
  --override-fact "OrderLines,Returns" \
  --override-dim "Calendar"
```

---

## Output Format

```json
{
  "source": "mssql://server/SalesDW",
  "profiled_at": "2026-05-30T10:00:00Z",
  "tables": [
    {
      "schema": "dbo",
      "name": "SalesOrderDetail",
      "estimated_rows": 121317,
      "classification": "fact",
      "classification_reason": "row_count > 10000 AND has_fk_to_3_tables",
      "columns": [
        {
          "name": "SalesOrderID",
          "sql_type": "int",
          "nullable": false,
          "is_pk": true,
          "is_fk": true,
          "fk_refs": "dbo.SalesOrderHeader"
        },
        {
          "name": "NetRevenue",
          "sql_type": "money",
          "nullable": false,
          "is_pk": false,
          "is_fk": false,
          "suggested_measure": "SUM"
        }
      ],
      "suggested_name": "FactSalesOrderDetail",
      "suggested_grain": "one row = one order line item"
    }
  ],
  "suggested_star_schema": {
    "facts": ["FactSalesOrderDetail"],
    "dimensions": ["DimProduct", "DimCustomer", "DimDate"]
  }
}
```

---

## Scaffold Command

Generates ready-to-use TMDL files from a live source profile:

```bash
pbi source scaffold \
  --source "mssql://server/SalesDW" \
  --output ./MyReport.SemanticModel/definition/ \
  --date-table-strategy generate
```

`--date-table-strategy` options:

| Value | Behaviour |
|-------|-----------|
| `generate` | Creates a DimDate table with standard columns + fiscal year |
| `existing` | Maps to an existing date table detected in the source |
| `none` | Skips date table generation |

### Output structure

```
definition/
  tables/
    FactSalesOrderDetail.tmdl
    DimProduct.tmdl
    DimCustomer.tmdl
    DimDate.tmdl              ← generated if --date-table-strategy generate
  relationships.tmdl
  expressions.tmdl            ← ServerName, DatabaseName parameters
```

---

## Composite Keys

When a table has a composite primary key, `pbi source profile` creates a
surrogate key column recommendation in the output:

```json
{
  "composite_pk": ["OrderID", "LineNumber"],
  "surrogate_key_suggestion": "SalesOrderLineKey"
}
```

---

## Views vs Tables

By default, both tables and views are profiled. To exclude views:

```bash
pbi source profile --source "mssql://server/db" --no-views
```

Views are flagged with `"object_type": "view"` in the output.
