---
name: power-bi-connections
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for managing Power BI data source connections: listing, testing, updating, and
  switching connection strings across PBIP/PBIR projects, DirectQuery vs Import mode
  changes, and service principal credential management. Triggers on: "connection string",
  "data source", "pbi connections", "switch data source", "update credentials",
  "DirectQuery", "Import mode", "gateway", "pbi connect".
version: "1.0"
---

# power-bi-connections

## Quick Reference

```bash
# List all data source connections in the model
pbi connections list

# Test connectivity to all configured data sources
pbi connections test

# Show connection details for a specific source
pbi connections show --source "SQL_Prod"

# Update a connection string
pbi connections set --source "SQL_Prod" --server "prod-sql.database.windows.net" --database "SalesDB"

# Switch all connections from dev to prod environment
pbi connections switch --env prod

# Export connections to JSON for review
pbi connections export --output ./connections.json

# Import connections from a saved profile
pbi connections import --file ./connections.json
```

---

## Connection Types

| Type | Backend | Notes |
|------|---------|-------|
| SQL Server | DirectQuery / Import | Windows auth or SQL auth |
| Azure SQL | DirectQuery / Import | Service principal or managed identity |
| SharePoint | Import | OAuth2, requires tenant ID |
| Excel / CSV | Import | File path or URL |
| OData | DirectQuery / Import | Feed URL + optional auth |
| REST API | Import | Custom connector — see `pbi sources` |
| Fabric Lakehouse | DirectQuery | Workspace + lakehouse name |

---

## Connection Profiles (Environment Switching)

Define named profiles in `connections.json` at project root:

```json
{
  "profiles": {
    "dev": {
      "SQL_Main": {
        "server": "dev-sql.internal",
        "database": "SalesDB_Dev",
        "authMode": "windows"
      }
    },
    "prod": {
      "SQL_Main": {
        "server": "prod-sql.database.windows.net",
        "database": "SalesDB",
        "authMode": "servicePrincipal",
        "tenantId": "$env:AZURE_TENANT_ID",
        "clientId": "$env:AZURE_CLIENT_ID",
        "clientSecret": "$env:AZURE_CLIENT_SECRET"
      }
    }
  }
}
```

`$env:VAR` placeholders are resolved from environment variables at runtime — never store
secrets in the file directly.

Switch profiles:

```bash
pbi connections switch --env prod   # applies prod profile to model
pbi connections switch --env dev    # reverts to dev profile
```

---

## Service Principal Authentication

```bash
# Configure service principal for a source
pbi connections set --source "SQL_Prod" \
  --auth service-principal \
  --tenant-id $env:AZURE_TENANT_ID \
  --client-id $env:AZURE_CLIENT_ID \
  --client-secret $env:AZURE_CLIENT_SECRET
```

For CI/CD, pass credentials via environment variables — `pbi connections switch --env prod`
will resolve `$env:` placeholders automatically.

---

## DirectQuery vs Import Mode

```bash
# Check current storage mode for each table
pbi connections mode list

# Switch a table from Import to DirectQuery
pbi connections mode set --table Sales --mode DirectQuery

# Switch entire model to Import (where supported)
pbi connections mode set --all --mode Import
```

| Mode | When to use | Trade-off |
|------|-------------|-----------|
| Import | Default; data cached in model | Fast visuals; data not real-time |
| DirectQuery | Large tables, real-time data | Slower queries; DB must be online |
| Dual | Tables queried both ways | Flexible; complex to manage |
| Streaming | Real-time push datasets | No history; specialised use |

---

## Gateway Configuration

```bash
# List configured on-premises data gateways
pbi connections gateway list

# Associate a connection with a gateway
pbi connections gateway set --source "SQL_OnPrem" --gateway "Corp-Gateway-01"

# Test gateway connectivity
pbi connections gateway test --gateway "Corp-Gateway-01"
```

Gateways are required for on-premises sources when publishing to the Power BI service.
Use the Power BI Service admin portal to register gateway clusters; `pbi connections gateway`
manages the association within the PBIP project file.
