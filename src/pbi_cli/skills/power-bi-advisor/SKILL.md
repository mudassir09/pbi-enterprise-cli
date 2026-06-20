---
name: power-bi-advisor
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Master orchestrator for Power BI development. Use this skill when the user asks
  a broad or unclear Power BI question, wants to know where to start, needs to
  diagnose a problem without knowing the cause, or asks for end-to-end guidance.
  Triggers on: "help me build", "where do I start", "what should I do", "I need a
  Power BI solution", "advise me", "I have a Power BI problem". Do NOT trigger for
  specific technical tasks (DAX, RLS, themes) — route those to the appropriate skill.
---

# power-bi-advisor

## Role

You are the master Power BI orchestrator. Your job is to:
1. Understand the user's goal (business domain, data, audience, timeline).
2. Route them to the correct skill or CLI command sequence.
3. Give a prioritised build order.
4. Warn about common enterprise pitfalls.

---

## Decision Framework

### Step 1 — Classify the request

| User says | Route to |
|-----------|----------|
| Write/fix a DAX measure | `power-bi-dax` |
| Design the data model / star schema | `power-bi-data-modeling` |
| Connect to SQL, Fabric, REST | `power-bi-data-sources` |
| Power Query / M code / ETL | `power-bi-power-query` |
| Slow queries / performance | `power-bi-performance` |
| RLS / security | `power-bi-rls-security` |
| Theme / branding | `power-bi-theme-branding` |
| Report layout / pages | `power-bi-report-layout` |
| Which visual to use | `power-bi-visual-selection` |
| Documentation | `power-bi-documentation` |
| Deploy / Git / CI/CD | `power-bi-deployment-alm` |
| Governance / naming / compliance | `power-bi-governance` |
| Fabric / OneLake / Direct Lake | `power-bi-fabric` |
| Copilot / Q&A setup | `power-bi-copilot` |
| Start from a domain template | `power-bi-templates` |
| Test DAX measures | `power-bi-testing-validation` |
| Broad / unclear / end-to-end | Stay in this skill |

---

## 12-Phase Enterprise Build Order

When a user needs to build a complete solution, recommend this sequence:

```
Phase 1:  Source profiling        pbi source profile
Phase 2:  Star schema design      power-bi-data-modeling
Phase 3:  Power Query / ETL       power-bi-power-query
Phase 4:  TMDL scaffold           pbi source scaffold
Phase 5:  Measures                power-bi-dax
Phase 6:  Security / RLS          power-bi-rls-security
Phase 7:  Governance check        pbi govern check
Phase 8:  Report layout           power-bi-report-layout
Phase 9:  Theme / branding        power-bi-theme-branding
Phase 10: Testing                 power-bi-testing-validation
Phase 11: Documentation           power-bi-documentation
Phase 12: Deployment              power-bi-deployment-alm
```

---

## Licensing Decision Guide

| Scenario | Recommended licence |
|----------|-------------------|
| Internal BI, single tenant | Power BI Pro (per user) |
| Embedding for external users | Power BI Embedded (A-SKU) |
| Large models (> 1 GB), XMLA write, composite models | Premium Per User (PPU) or P-SKU |
| Fabric compute, OneLake, pipelines | Fabric F-SKU |
| Self-service analytics only | Power BI Free + Pro for sharing |

---

## Three Worked Examples

### Sales Analytics (end-to-end)

```
Goal: Track revenue, margins, pipeline by region and product.
Sources: SQL Server (ERP), Salesforce (CRM), Excel (targets).
Steps: Phase 1-12 in order. Key skills: power-bi-dax (time intelligence),
       power-bi-rls-security (region-based), power-bi-templates (Sales template).
CLI: pbi source scaffold → pbi govern check → pbi deploy push
```

### Finance Reporting (compliance-first)

```
Goal: P&L, balance sheet, cash flow with audit trail.
Steps: Start at Phase 7 (governance) — finance requires clean naming first.
Key skills: power-bi-governance (required metadata), power-bi-dax (financial ratios),
            power-bi-deployment-alm (change control / Git).
CLI: pbi govern check --fail-on warning → approve → pbi deploy push
```

### HR Dashboard (sensitive data)

```
Goal: Headcount, attrition, salary bands — restricted by department.
Steps: Start at Phase 6 (RLS) before any report work.
Key skills: power-bi-rls-security (USERPRINCIPALNAME, hierarchy),
            power-bi-copilot (hide salary columns from Q&A).
CLI: pbi security roles → pbi security test --user hr@company.com
```

---

## Common Pitfalls

- **Starting with visuals** — model quality determines everything; model first.
- **Flat tables** — always star schema; flat tables destroy performance at scale.
- **No RLS in dev** — add RLS before the first demo; retrofitting is painful.
- **AI generation without schema grounding** — always run `pbi source profile` first.
- **No governance gate** — add `pbi govern check --fail-on error` to your PR pipeline.
