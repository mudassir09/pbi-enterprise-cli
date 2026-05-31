---
name: power-bi-project-orchestrator
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use to coordinate multi-skill Power BI workflows: model design → DAX authoring
  → governance → report → deploy. Handles cross-skill handoffs, resolves conflicts
  between skill recommendations, and provides end-to-end workflow patterns.
  Triggers on: "full project", "end-to-end", "where do I start", "what order",
  "build a complete report", "set up a new model", "migrate to Fabric",
  "enterprise workflow", "orchestrate", "full pipeline".
  Do NOT trigger for single-skill questions — route to the specific skill directly.
---

# power-bi-project-orchestrator

Coordinates multi-skill workflows. Routes questions to the right skill. Handles handoffs.

## Skill Map — Route by Topic

| User question type | → Skill |
|---|---|
| Star schema, source profiling, partitions, calendar, M queries | **power-bi-modeling** |
| DAX measures, Time Intelligence, unit tests, filter context | **power-bi-dax** |
| Slow queries, VertiPaq, benchmarking, storage engine | **power-bi-performance** |
| Report pages, visuals, bookmarks, drillthrough, auto-layout | **power-bi-report-design** |
| Themes, brand colours, WCAG, custom visuals | **power-bi-design-system** |
| Governance rules, BPA, naming conventions, auto-fix, CI gate | **power-bi-governance** |
| RLS, security roles, data dictionary, lineage, audit logs | **power-bi-security-and-docs** |
| XMLA deploy, snapshots, environments, CI/CD, auth | **power-bi-deployment** |
| pbi doctor, pythonnet errors, connection issues, error codes | **power-bi-diagnostics** |

---

## End-to-End Workflow: New Enterprise Model from Scratch

```bash
# Phase 1: Model
pbi source profile --type sql --conn "$CONN_STR" --output profile.json
pbi source scaffold --profile profile.json --apply
pbi calendar create --start 2020-01-01 --end 2027-12-31
pbi calendar mark-as-date-table --table Calendar --date-column Date
pbi model lint

# Phase 2: DAX
pbi measure generate "total revenue, gross margin %, YTD revenue" --table Sales
pbi measure audit                         # check descriptions and format strings
pbi dax test --suite ./tests/measures/

# Phase 3: Governance gate
pbi govern check --fail-on error
pbi govern bpa check --severity error
pbi govern fix --auto

# Phase 4: Security
pbi security role-add --name "Regional" --table Sales \
  --filter "Sales[Region] = LOOKUPVALUE(Employee[Region], Employee[Email], USERNAME())"
pbi security role-test --role "Regional" --user "test@contoso.com"

# Phase 5: Report
pbi report page-add --name "Executive Summary"
pbi visual add --page "Executive Summary" --type card --field "Sales[Total Revenue]"
pbi layout auto --page "Executive Summary"
pbi theme generate --brand-color "#0078D4" --wcag AA --output ./themes/brand.json
pbi theme apply --file ./themes/brand.json

# Phase 6: Deploy
pbi snapshot create --label pre-production
pbi deploy push --connection fabric-prod
```

---

## End-to-End Workflow: Migrate Existing Model to Fabric

```bash
# 1 — Export current model
pbi database export-tmdl ./tmdl-backup/
pbi snapshot create --label pre-migration

# 2 — Governance baseline
pbi --backend mock govern check --json > governance-baseline.json

# 3 — Set up Fabric XMLA connection
pbi connections add --type xmla \
  --endpoint "powerbi://api.powerbi.com/v1.0/myorg/FabricWS" \
  --auth service-principal \
  --name fabric-prod

# 4 — Push to Fabric
pbi deploy push --connection fabric-prod

# 5 — Verify
pbi --connection fabric-prod model tables
pbi --connection fabric-prod govern check --fail-on error

# 6 — Document
pbi docs generate --format markdown --output ./docs/data-dictionary.md
```

---

## End-to-End Workflow: CI/CD Pipeline for a Git-Managed Model

```yaml
# .github/workflows/pbi-ci.yml
name: Power BI CI

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli

      - name: Governance gate
        run: pbi --backend mock govern check --fail-on error

      - name: BPA check
        run: pbi --backend mock govern bpa check --severity error

      - name: DAX unit tests
        run: pbi --backend mock dax test --suite ./tests/measures/

      - name: JSON contract tests
        run: pytest tests/unit/test_json_contracts.py

  deploy:
    needs: validate
    if: github.ref == 'refs/heads/main'
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pbi-enterprise-cli
      - name: Deploy to Fabric
        env:
          TENANT_ID: ${{ secrets.TENANT_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          CLIENT_SECRET: ${{ secrets.CLIENT_SECRET }}
        run: |
          pbi connections add --type xmla `
            --endpoint "${{ vars.FABRIC_ENDPOINT }}" `
            --auth service-principal `
            --tenant-id $env:TENANT_ID --client-id $env:CLIENT_ID `
            --client-secret $env:CLIENT_SECRET --name fabric-prod
          pbi deploy push --connection fabric-prod
```

---

## Conflict Resolution

**Governance says rename a measure that DAX references:** Rename in the model first (`pbi measure update --name "Old" --new-name "New"`), then verify no broken DAX expressions (`pbi dax validate` on dependent measures).

**Design system theme conflicts with conditional formatting colours:** Theme sets default data colours; conditional formatting overrides them per-visual. Set conditional formatting *after* applying the theme.

**Performance fix requires model restructuring:** Route to **power-bi-modeling** for schema changes (column removal, aggregation tables), then back to **power-bi-performance** to verify the fix improved the trace.

**RLS role blocks a test user from seeing expected data:** Route to **power-bi-security-and-docs** for `pbi security role-test`. If the filter DAX is wrong, route to **power-bi-dax** for expression help.

---

## Skill Invocation Cheat Sheet

```bash
# When you don't know which skill handles X:
pbi --help           # lists all command groups
pbi <group> --help   # lists commands in that group

# To orchestrate a full check before any PR merge:
pbi --backend mock govern check --fail-on error && \
pbi --backend mock dax test --suite ./tests/ && \
echo "All checks passed"
```
