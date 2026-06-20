---
name: power-bi-deployment-pipeline
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for CI/CD deployment pipelines for Power BI: Git integration, Fabric
  deployment pipelines, environment promotion (Dev→Test→Prod), XMLA publishing,
  and automated release workflows. Triggers on: "deployment pipeline", "CI/CD",
  "promote", "publish to workspace", "dev test prod", "XMLA deploy", "Fabric pipeline",
  "git integration", "automated deploy", "release pipeline".
version: "1.0"
---

# power-bi-deployment-pipeline

## Quick Reference

```bash
# Push model to a workspace
pbi deploy push --workspace "Dev"

# Compare local vs. workspace
pbi deploy diff --workspace "Dev"

# Promote from Dev to Test
pbi deploy promote --from "Dev" --to "Test"

# Promote from Test to Prod (with confirmation)
pbi deploy promote --from "Test" --to "Prod" --confirm
```

---

## Deployment Environments

Standard 3-environment setup:

| Environment | Workspace | Refresh Schedule | Who Deploys |
|-------------|-----------|-----------------|-------------|
| Dev | `MyReport-Dev` | Manual | Developers |
| Test | `MyReport-Test` | Daily | CI/CD on merge to main |
| Prod | `MyReport-Prod` | Business hours | CD on release tag |

---

## XMLA Endpoint Setup

XMLA endpoint is required for programmatic deployment (requires Power BI Premium or Fabric):

1. Enable in Admin Portal: **Tenant settings → XMLA Endpoints → Enabled**
2. Set workspace connection string:
   ```
   powerbi://api.powerbi.com/v1.0/myorg/{WorkspaceName}
   ```
3. Authenticate with service principal or user credentials

```bash
# Configure XMLA endpoint
pbi config set xmla-endpoint "powerbi://api.powerbi.com/v1.0/myorg/Dev"
pbi config set service-principal-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
pbi config set service-principal-secret "$(cat sp-secret.txt)"
```

---

## Deployment Workflow (Git-based)

```
Developer pushes branch
         │
         ▼
CI: pbi govern check    ←── Fail = block merge
         │
         ▼
CI: pbi dax test        ←── Fail = block merge
         │
         ▼
Merge to main
         │
         ▼
CD: pbi deploy push --workspace "Dev"
         │
         ▼
Manual QA in Dev workspace
         │
         ▼
CD: pbi deploy promote --from "Dev" --to "Test"
         │
         ▼
UAT sign-off
         │
         ▼
Release tag → CD: pbi deploy promote --from "Test" --to "Prod"
```

---

## GitHub Actions CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Power BI Deploy

on:
  push:
    branches: [main]
  release:
    types: [published]

env:
  PBIP_PATH: ./financials.pbip

jobs:
  validate:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install pbi-cli
        run: pip install pbi-cli
      - name: Governance check
        run: pbi govern check --json
      - name: TMDL snapshot
        run: pbi database export-tmdl ./tmdl/

  deploy-dev:
    needs: validate
    runs-on: windows-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to Dev
        run: pbi deploy push --workspace "MyReport-Dev"
        env:
          PBI_SP_ID: ${{ secrets.SERVICE_PRINCIPAL_ID }}
          PBI_SP_SECRET: ${{ secrets.SERVICE_PRINCIPAL_SECRET }}
          PBI_TENANT_ID: ${{ secrets.TENANT_ID }}

  deploy-prod:
    needs: deploy-dev
    runs-on: windows-latest
    if: github.event_name == 'release'
    environment: production  # requires manual approval in GitHub
    steps:
      - name: Promote Test to Prod
        run: pbi deploy promote --from "MyReport-Test" --to "MyReport-Prod"
```

---

## TMDL Snapshots for Version Control

Store TMDL (Tabular Model Definition Language) snapshots in Git for full change history:

```bash
# Export current model state
pbi database export-tmdl ./tmdl/

# Compare TMDL changes since last export
git diff ./tmdl/
```

TMDL files are human-readable and diff-friendly:

```tmdl
// tmdl/tables/Sales.tmdl
table Sales
    lineageTag: abc-123

    column OrderDate
        dataType: dateTime
        lineageTag: def-456
        summarizeBy: none

    measure 'Total Revenue' = SUM(Sales[Revenue])
        formatString: "$#,0.00"
        description: "Sum of all revenue including returns"
```

---

## Deployment diff Output

```
pbi deploy diff --workspace "Dev"

  Model: financials
  Workspace: MyReport-Dev

  Tables:
    ~ Sales (modified)
        + column: DiscountAmount
        ~ measure: 'Total Revenue' (formatString changed)
    + Returns (new table)

  Relationships:
    + Sales[OrderID] → Returns[OrderID]

  3 changes pending
```

---

## Rollback Strategy

```bash
# List recent TMDL snapshots
pbi database snapshots

# Restore a previous snapshot
pbi database restore-tmdl --snapshot 2024-01-15_10-30-00

# Or restore from Git
git checkout main~1 -- tmdl/
pbi database import-tmdl ./tmdl/
pbi deploy push --workspace "Dev"
```

---

## Fabric Deployment Pipelines (GUI alternative)

Fabric has built-in deployment pipelines (Settings → Deployment pipelines):

1. Create pipeline → assign Dev/Test/Prod workspaces
2. Compare: shows schema differences between stages
3. Deploy: promotes all items or selected items

The `pbi deploy promote` command automates what the GUI pipeline does via XMLA.

---

## Common Deployment Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `XMLA endpoint not enabled` | Free/Pro workspace | Upgrade to Premium or Fabric |
| `Access denied` | SP not added to workspace | Add service principal as workspace member |
| `Schema version mismatch` | Desktop version differs from service | Update Power BI Desktop |
| `Dataset not found` | First deploy to new workspace | Use `--create` flag for initial push |
| `Merge conflict in TMDL` | Two developers modified same table | Resolve conflict in Git, re-export |
