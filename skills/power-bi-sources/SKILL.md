---
name: power-bi-sources
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use when connecting to data sources, profiling schemas, scaffolding star-schema
  models, or suggesting joins. Triggers on: "connect to SQL", "profile my database",
  "scaffold a model", "I have an Excel file", "read from REST API",
  "pbi source profile", "pbi source scaffold", "pbi source suggest-joins",
  "auto-detect relationships", "star schema from my data".
  Do NOT trigger for report-only or measure-only requests.
version: "1.0"
requires: ["pbi-cli >= 4.0", "pbi-cli-tool[sources]"]
---

# power-bi-sources

## Quick Reference

```bash
# SQL Server
pbi source profile --type sql --conn "mssql+pyodbc://server/db?driver=ODBC+Driver+17+for+SQL+Server" --output profile.json

# Excel
pbi source profile --type excel --path ./data/sales.xlsx --output profile.json

# CSV
pbi source profile --type csv --path ./data/products.csv --output profile.json

# REST API
pbi source profile --type rest --url "https://api.example.com/data" --output profile.json

# Scaffold star schema from profile
pbi source scaffold --profile profile.json

# Suggest joins between two sources
pbi source suggest-joins --profiles profile_a.json,profile_b.json
```

## Source Profile Output Schema

```json
[
  {
    "tableName": "Sales",
    "rowCount": 1250000,
    "columns": [
      {
        "name": "SalesKey",
        "dataType": "Int64",
        "nullable": false,
        "nullRate": 0.0,
        "distinctCount": 1250000,
        "sampleValues": [1, 2, 3, 4, 5]
      }
    ]
  }
]
```

## Star Schema Scaffold Rules

1. **Fact table:** Largest row count. Contains numeric measure columns and foreign key columns.
2. **Dimension tables:** Smaller row counts. Contain descriptive attributes and a primary key.
3. **Key detection:** Columns ending in `Key`, `ID`, `Sk`, `Code` are treated as key columns.
4. **Relationship detection:** Fact column name matches dimension primary key → ManyToOne relationship.
5. **Starter measures:** SUM() of every numeric column in the fact table (first 5).

## Join Suggestion Algorithm

| Tier | Method | Confidence |
|------|--------|------------|
| 1 | Exact column name match across tables | High |
| 2 | Column name + matching data type | High |
| 3 | Column name substring match + cardinality | Medium |

Always review suggested joins before applying — the algorithm uses heuristics.

## Supported Connection Strings (SQLAlchemy format)

| Source | Format |
|--------|--------|
| SQL Server | `mssql+pyodbc://server/database?driver=ODBC+Driver+17+for+SQL+Server` |
| PostgreSQL | `postgresql+psycopg2://user:pass@host/database` |
| MySQL | `mysql+pymysql://user:pass@host/database` |
| SQLite | `sqlite:///path/to/file.db` |
| Azure SQL | `mssql+pyodbc://server.database.windows.net/db?driver=ODBC+Driver+17&Authentication=ActiveDirectoryInteractive` |

Requires: `pip install pbi-cli-tool[sources]`
