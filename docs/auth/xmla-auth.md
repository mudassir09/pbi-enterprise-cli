# XMLA Authentication Guide

## Overview

The `--backend xmla` flag (or `"backend": "xmla"` in a named connection) connects
to Power BI Premium or Microsoft Fabric via XMLA. Three authentication methods are
supported, configured via environment variables or `~/.pbi-cli/connections.json`.

---

## Method 1: Service Principal (Recommended for CI/CD)

### Azure AD App Registration

1. **Register the app:** Azure Portal → App Registrations → New registration
2. **Note:** Application (client) ID, Directory (tenant) ID
3. **Create a secret:** Certificates & secrets → New client secret → copy the value
4. **Grant Power BI API permission:**
   - API permissions → Add a permission → Power BI Service
   - Select `Tenant.ReadWrite.All` (admin) or `Dataset.ReadWrite.All` (dataset-only)
   - Click "Grant admin consent"
5. **Enable service principal access:**
   - Power BI Admin Portal → Tenant Settings
   - Enable "Allow service principals to use Power BI APIs"
6. **Add to workspace:**
   - Workspace → Access → add the service principal as **Member** or **Admin**

### Connection config

```json
{
  "name": "fabric-prod",
  "backend": "xmla",
  "xmla_endpoint": "powerbi://api.powerbi.com/v1.0/myorg/YourWorkspace",
  "auth": "service_principal",
  "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_secret_env": "PBI_CLIENT_SECRET"
}
```

```bash
export PBI_CLIENT_SECRET="your-secret-value"
pbi --connection fabric-prod model tables
```

> **Security:** The secret value is never stored in `connections.json`. Only the
> environment variable **name** (`client_secret_env`) is stored.

---

## Method 2: Managed Identity (Azure-hosted runners)

```json
{
  "name": "fabric-ci",
  "backend": "xmla",
  "xmla_endpoint": "powerbi://api.powerbi.com/v1.0/myorg/YourWorkspace",
  "auth": "managed_identity"
}
```

No credentials required. Works on:
- Azure Virtual Machines (system-assigned identity)
- Azure DevOps hosted agents (with workload identity federation)
- GitHub Actions with the `azure/login` action

---

## Method 3: Interactive (Developer workstations)

```json
{
  "name": "fabric-dev",
  "backend": "xmla",
  "xmla_endpoint": "powerbi://api.powerbi.com/v1.0/myorg/YourWorkspace",
  "auth": "interactive"
}
```

Opens a browser window for Azure AD login. The token is cached in the OS credential
store and reused on subsequent commands until it expires.

---

## GitHub Actions Example

```yaml
name: Power BI Governance Check
on: [pull_request]

jobs:
  govern:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli
      - name: Run governance check
        env:
          PBI_CLIENT_SECRET: ${{ secrets.PBI_CLIENT_SECRET }}
        run: |
          pbi --connection fabric-prod --json govern check --fail-on error
```

Add these GitHub secrets:
- `PBI_CLIENT_SECRET` — the service principal secret value

---

## Azure DevOps Example

```yaml
variables:
  - group: pbi-credentials   # variable group containing PBI_CLIENT_SECRET

steps:
  - script: pip install pbi-enterprise-cli
  - script: |
      pbi --connection fabric-prod --json govern check --fail-on error
    env:
      PBI_CLIENT_SECRET: $(PBI_CLIENT_SECRET)
    displayName: Governance Check
```

---

## Add a Named Connection

```bash
pbi connections add
```

The wizard prompts for all required fields and tests the connection before saving.
Secrets are stored by **env var name only** — never in plain text.

---

## Troubleshooting

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `AADSTS700016` | App not found in tenant | Check tenant_id matches the app registration |
| `403 Forbidden` | Missing workspace access | Add service principal to workspace as Member |
| `AADSTS50011` | Reply URL mismatch | Not applicable for service principal flow |
| `Token expired` | Interactive token stale | Delete token cache and re-run |
