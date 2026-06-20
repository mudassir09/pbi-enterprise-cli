---
name: power-bi-fabric
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for Microsoft Fabric platform: OneLake, Medallion architecture, Direct Lake
  mode, Fabric Pipelines, Dataflow Gen2, Real-Time Intelligence (RTI), KQL, Shortcuts,
  Mirroring, and migration from Synapse/Premium. Triggers on: "Fabric", "OneLake",
  "Direct Lake", "Medallion", "Lakehouse", "KQL", "Eventstream", "Real-Time
  Intelligence", "Fabric pipeline", "Dataflow Gen2". Do NOT trigger for standard
  Import or DirectQuery — use power-bi-data-modeling instead.
---

# power-bi-fabric

## Architecture: Medallion on OneLake

```
Bronze (raw)    → Lakehouse Tables / Files — raw ingested data
Silver (curated)→ Lakehouse Tables — cleaned, joined, typed
Gold (semantic) → Lakehouse Tables / Warehouse — star schema for Power BI
                  ↓
              Power BI Semantic Model (Direct Lake)
```

---

## Direct Lake Mode

Direct Lake reads Parquet files from OneLake directly — no import, no DirectQuery
overhead. It is the fastest query mode for Fabric-native data.

### Requirements
- Data must be in a Fabric **Lakehouse** (Delta/Parquet) or **Warehouse**.
- Workspace must be on a Fabric capacity (F-SKU) or Premium (P-SKU).
- The semantic model must use **Direct Lake** storage mode (not Import, not DQ).

### Setting up Direct Lake in TMDL

```tmdl
table FactSales
  partition FactSales = entity
    mode: directLake
    source
      entityName: 'FactSales'
      schemaName: 'dbo'
      expressionSource: DatabaseQuery
```

### Fallback behaviour
If a query cannot be served from Direct Lake (e.g., complex DAX patterns), Power BI
falls back to DirectQuery automatically. Monitor this with `pbi trace query-perf`.

---

## Fabric Lakehouse — PySpark Data Preparation

```python
# Notebook cell — Gold layer star schema
from pyspark.sql import functions as F

fact_sales = spark.table("silver.sales_orders") \
    .select("OrderID", "ProductKey", "CustomerKey", "OrderDate", "Revenue") \
    .filter(F.col("Revenue") > 0)

fact_sales.write.mode("overwrite").saveAsTable("gold.FactSales")
```

---

## Fabric Pipelines vs Dataflow Gen2

| Tool | Use for |
|------|---------|
| **Dataflow Gen2** | No-code ETL, Power Query M in the cloud |
| **Fabric Pipelines** | Orchestrating notebooks, stored procs, copy activities |
| **Notebooks (PySpark)** | Complex transformations, ML, large-scale data |

---

## Real-Time Intelligence (RTI)

### Eventstream → KQL Database

```kql
// KQL query in RTI — last 5 minutes of sensor data
SensorReadings
| where ingestion_time() > ago(5m)
| summarize avg(Temperature) by bin(ingestion_time(), 1m), DeviceID
| order by ingestion_time() desc
```

### Connecting KQL to Power BI

```bash
pbi source profile --source "kql://cluster.region.kusto.windows.net/MyDatabase"
```

Use **DirectQuery** mode for real-time KQL data (Direct Lake is not supported for KQL).

---

## OneLake Shortcuts

Shortcuts create virtual pointers to data in ADLS Gen2, S3, or GCS without copying it.

```
OneLake
  └─ MyLakehouse
       └─ Tables
            └─ SalesData (shortcut → s3://my-bucket/sales/)
```

Data stays in the external storage; OneLake reads it on demand.

---

## Mirroring

Mirror Azure SQL, Snowflake, or Azure Cosmos DB into OneLake in near real-time
without ETL pipelines. Once mirrored, data is available as Delta tables.

---

## Migration from Synapse / Premium

| From | To | Steps |
|------|----|-------|
| Synapse Analytics | Fabric Warehouse | Export as Parquet → import to Lakehouse |
| Premium Import model | Direct Lake | Re-platform to Fabric, switch storage mode |
| Azure Data Factory | Fabric Pipelines | Recreate pipelines in Fabric UI |
| Power BI Dataflows Gen1 | Dataflow Gen2 | Re-author in Fabric |

---

## CLI Commands for Fabric

```bash
# Profile a Fabric Lakehouse
pbi source profile --source "fabric://workspace-id/lakehouse-id" --output json

# Scaffold a Direct Lake model from the gold layer
pbi source scaffold --source "fabric://workspace-id/lakehouse-id" \
  --output ./SalesModel.SemanticModel/definition/ \
  --date-table-strategy generate

# Deploy to a Fabric workspace
pbi --connection fabric-prod deploy push --workspace "Sales-Analytics"
```
