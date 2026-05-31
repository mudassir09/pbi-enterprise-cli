---
name: power-bi-deployment
version: "2.0"
min_cli_version: "1.0.0"
description: >
  Use for TMDL snapshot/diff/restore, XMLA push to Premium/Fabric, multi-stage
  pipeline orchestration, service principal and device-flow auth, and
  environment promotion workflows.
  Triggers on: "deploy", "promote", "push to service", "XMLA", "Fabric",
  "Premium", "pbi deploy", "pbi snapshot", "pbi env", "pbi database",
  "deployment pipeline", "dev to prod", "rollback", "TMDL diff",
  "service principal", "managed identity", "environment promotion".
  Do NOT trigger for local Desktop model editing (→ power-bi-modeling) or
  governance gate setup (→ power-bi-governance).
---

# power-bi-deployment

XMLA deployment, model snapshots, multi-environment promotion, and CI/CD pipelines.

## Quick Reference

```bash
# Snapshot and rollback
pbi snapshot create --label before-refactor
pbi snapshot list
pbi snapshot diff 20260531_142300_before-refactor
pbi snapshot restore 20260531_142300_before-refactor --confirm

# XMLA deployment
pbi deploy push --workspace "Sales-PROD" --dataset "Sales Model"
pbi deploy push --connection fabric-prod --dry-run
pbi deploy status --workspace "Sales-PROD"

# TMDL export/import
pbi database export-tmdl ./tmdl/
pbi database import-tmdl ./tmdl/

# Environment management
pbi connections add                              # interactive wizard
pbi env list
pbi env use fabric-dev
pbi env diff fabric-dev fabric-prod             # compare two environments
pbi env promote fabric-dev fabric-prod --confirm

# Auth setup
pbi connections add --type xmla \
  --endpoint "powerbi://api.powerbi.com/v1.0/myorg/SalesPROD" \
  --auth service-principal \
  --tenant-id "$TENANT_ID" \
  --client-id "$CLIENT_ID" \
  --client-secret "$CLIENT_SECRET"
```

---

## Worked Example 1: Safe deploy with snapshot and rollback guard

```bash
# 1 — Snapshot before any changes
pbi snapshot create --label pre-deploy-$(date +%Y%m%d)

# 2 — Validate governance before push
pbi --backend mock govern check --fail-on error

# 3 — Dry-run deployment
pbi deploy push --connection fabric-prod --dry-run

# 4 — Real deployment
pbi deploy push --connection fabric-prod

# 5 — Verify model is live
pbi --connection fabric-prod model tables

# Rollback if needed
pbi snapshot list
pbi snapshot restore pre-deploy-20260531 --confirm
```

---

## Worked Example 2: Multi-stage CI/CD pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Fabric
on:
  push:
    branches: [main]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli
      - run: pbi --backend mock govern check --fail-on error

  deploy-staging:
    needs: governance
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli
      - name: Deploy to Staging
        env:
          TENANT_ID: ${{ secrets.TENANT_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          CLIENT_SECRET: ${{ secrets.CLIENT_SECRET }}
        run: |
          pbi connections add --type xmla `
            --endpoint "${{ vars.STAGING_ENDPOINT }}" `
            --auth service-principal `
            --tenant-id $env:TENANT_ID `
            --client-id $env:CLIENT_ID `
            --client-secret $env:CLIENT_SECRET `
            --name fabric-staging
          pbi deploy push --connection fabric-staging

  deploy-prod:
    needs: deploy-staging
    environment: production
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli
      - name: Deploy to Production
        env:
          TENANT_ID: ${{ secrets.TENANT_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          CLIENT_SECRET: ${{ secrets.CLIENT_SECRET }}
        run: |
          pbi connections add --type xmla `
            --endpoint "${{ vars.PROD_ENDPOINT }}" `
            --auth service-principal `
            --tenant-id $env:TENANT_ID `
            --client-id $env:CLIENT_ID `
            --client-secret $env:CLIENT_SECRET `
            --name fabric-prod
          pbi deploy push --connection fabric-prod
```

---

## Worked Example 3: TMDL-based Git workflow

```bash
# On feature branch: export TMDL, edit, import, review diff
pbi database export-tmdl ./tmdl/
git add ./tmdl/ && git commit -m "model: add Sales[Margin %] column"

# On PR: show TMDL diff as review artifact
git diff main...HEAD ./tmdl/

# On merge to main: deploy
pbi database import-tmdl ./tmdl/
pbi deploy push --connection fabric-dev
```

---

## Authentication Modes

| Mode | When to use | Setup |
|---|---|---|
| `interactive` | Personal dev, one-off tasks | Browser popup, no config needed |
| `device-flow` | CI with no browser, shared accounts | Code printed to terminal |
| `service-principal` | Production CI/CD, automation | App registration + secret/cert |
| `managed-identity` | Azure-hosted runners | No secrets needed — IMDS automatic |

### Service principal setup (one-time)

```bash
# Register an app in Entra ID, grant "Dataset.ReadWrite.All" + "Workspace.ReadWrite.All"
pbi connections add \
  --type xmla \
  --endpoint "powerbi://api.powerbi.com/v1.0/myorg/MyWorkspace" \
  --auth service-principal \
  --tenant-id "00000000-0000-0000-0000-000000000000" \
  --client-id "00000000-0000-0000-0000-000000000000" \
  --client-secret "your-secret" \
  --name prod-xmla
```

---

## Edge Cases

**XMLA push fails with 403:** The service principal is not a Workspace Member or Admin — add it in the Power BI service under Workspace → Access.

**`pbi deploy push` hangs:** Large models (>1 GB) can take 10–30 minutes over XMLA. Use `--timeout 3600` to extend the default 5-minute timeout.

**Snapshot restore fails after compatibility level change:** The snapshot was taken at a different compatibility level. Restore is blocked — inspect the TMDL diff and apply changes selectively.

**Device-flow in GitHub Actions:** Not supported in non-interactive runners. Use `service-principal` or `managed-identity` in CI.

---

## Cross-skill handoffs

- Model schema changes before deploying → **power-bi-modeling**
- Governance gate before deploy → **power-bi-governance**
- RLS roles and security validation → **power-bi-security-and-docs**
- End-to-end project orchestration → **power-bi-project-orchestrator**
