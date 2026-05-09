---
name: power-bi-deployment
description: >
  Use for deploying semantic models and reports to Power BI Service via XMLA,
  promoting between workspaces (Dev→Test→Prod), TMDL snapshots, and rollback
  procedures. Triggers on: "deploy", "publish", "push to service", "promote",
  "Dev to Prod", "XMLA endpoint", "pbi deploy", "pbi database export-tmdl",
  "workspace", "rollback", "release".
version: "1.0"
---

# power-bi-deployment

## Quick Reference

```bash
# Snapshot before any deploy
pbi database export-tmdl ./snapshots/$(date +%Y%m%d)/

# Deploy to a workspace
pbi deploy push --workspace "Dev"

# Compare local vs deployed (no changes applied)
pbi deploy diff --workspace "Dev"

# Promote between workspaces
pbi deploy promote --from "Dev" --to "Staging"
pbi deploy promote --from "Staging" --to "Production"

# Connect via XMLA (Premium/Fabric)
pbi connect --xmla "powerbi://api.powerbi.com/v1.0/myorg/WorkspaceName"
```

---

## Deployment Workflow (3-Environment)

```
Local Desktop  →  Dev Workspace  →  Staging Workspace  →  Production
   (edit)         (integration)        (UAT/testing)         (live)
```

### Pre-Deploy Checklist

```bash
# 1. Run all gates
pbi model lint               # Naming conventions pass
pbi govern check             # No error-severity violations
pbi dax test --suite ./tests/measures.yaml  # All assertions pass

# 2. Snapshot current state
pbi database export-tmdl ./snapshots/pre-deploy/

# 3. Diff against target
pbi deploy diff --workspace "Dev"

# 4. Deploy
pbi deploy push --workspace "Dev"
```

### Promotion Checklist

```bash
# Dev → Staging
pbi deploy diff --workspace "Staging"    # Review differences
pbi deploy promote --from "Dev" --to "Staging"

# Staging → Production (requires approval gate)
pbi deploy promote --from "Staging" --to "Production"
```

---

## XMLA Endpoint Setup

Power BI Premium (P-SKU) or Fabric capacity required.

**Connection string format:**
```
powerbi://api.powerbi.com/v1.0/myorg/{WorkspaceName}
```

**Authentication:** Service principal (recommended for CI/CD):
```bash
# Set environment variables
export PBI_TENANT_ID="..."
export PBI_CLIENT_ID="..."
export PBI_CLIENT_SECRET="..."

pbi deploy push --workspace "Production" \
  --service-principal \
  --tenant-id $PBI_TENANT_ID \
  --client-id $PBI_CLIENT_ID \
  --client-secret $PBI_CLIENT_SECRET
```

---

## TMDL Snapshot Strategy

```
snapshots/
  pre-deploy/           ← before each push
  v1.0.0/              ← tagged releases
  daily/               ← automated daily backup
    2025-01-15/
    2025-01-16/
```

```bash
# Tag a release
pbi database export-tmdl ./snapshots/v1.0.0/

# Rollback to a snapshot
pbi database import-tmdl ./snapshots/v1.0.0/
pbi deploy push --workspace "Production"
```

---

## Rollback Procedure

1. **Identify the last good snapshot:**
   ```bash
   ls ./snapshots/
   ```

2. **Import the snapshot:**
   ```bash
   pbi database import-tmdl ./snapshots/pre-deploy/
   ```

3. **Verify locally:**
   ```bash
   pbi model lint
   pbi dax test --suite ./tests/
   ```

4. **Push rollback:**
   ```bash
   pbi deploy push --workspace "Production"
   ```

---

## Deployment Diff Output Interpretation

`pbi deploy diff` returns a structured change list:

```json
{
  "added": ["measures/[New KPI]"],
  "modified": ["measures/[Total Revenue] (expression changed)"],
  "deleted": [],
  "breaking": ["relationships/Sales→CustomerHistory (removed)"]
}
```

**Breaking changes** (highlighted in red) require stakeholder sign-off before promotion.

---

## CI/CD Pipeline Integration (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
- name: Deploy to Dev
  run: |
    pip install pbi-cli-tool
    pbi model lint
    pbi dax test --suite ./tests/
    pbi database export-tmdl ./snapshots/pre-deploy/
    pbi deploy push --workspace "Dev"
  env:
    PBI_CLIENT_ID: ${{ secrets.PBI_CLIENT_ID }}
    PBI_CLIENT_SECRET: ${{ secrets.PBI_CLIENT_SECRET }}
    PBI_TENANT_ID: ${{ secrets.PBI_TENANT_ID }}
```

---

## Common Deployment Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `XMLA not configured` | Workspace isn't Premium/Fabric | Upgrade capacity or use TMDL file export |
| `Transaction conflict` | Another user is editing the model | Wait and retry; `pbi deploy push --force` as last resort |
| `Schema version mismatch` | Local TMDL uses newer compatibility level | Set `--compatibility-level 1550` to match target |
| `Circular dependency detected` | New measure creates a cycle | Run `pbi measure audit` to identify |
| `Authentication failed` | Service principal not granted workspace access | Add SP to workspace as Member |
