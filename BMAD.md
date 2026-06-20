# BMAD — pbi-cli Gap Analysis & Implementation Plan

**Date:** 2026-05-30  
**Scope:** Missing skills + CI/CD infrastructure improvements  
**Status:** In progress

---

## 1. Context

`pbi-cli` is a Power BI one-stop-shop platform (v4.0.0) with 30 skills covering DAX, governance,
deployment, visuals, themes, security, etc. An audit surfaced six missing skills and nine
infrastructure gaps.

---

## 2. Missing Skills

| # | Skill | Source module | Priority |
|---|-------|---------------|----------|
| S1 | `power-bi-intelligence` | `src/pbi_cli/intelligence/` — measure generator, visual recommender, theme generator, layout engine | High — first-class AI subsystem with no skill |
| S2 | `power-bi-connections` | `src/pbi_cli/commands/connections.py` | Medium |
| S3 | `power-bi-trace` | `src/pbi_cli/commands/trace.py` | Medium |
| S4 | `power-bi-watch` | `src/pbi_cli/commands/watch.py` | Medium |
| S5 | `power-bi-calendar` | `src/pbi_cli/commands/calendar_cmd.py` | Medium |
| S6 | `power-bi-audit` | `src/pbi_cli/_audit.py` + `_snapshot.py` | Medium |

---

## 3. Infrastructure Gaps

| # | Gap | Severity | Fix |
|---|-----|----------|-----|
| I1 | No Windows CI job — TOM/XMLA backends untested | High | Add `windows-test` job to `ci.yml` |
| I2 | No pip caching in any workflow job | Medium | Add `cache: pip` to all `actions/setup-python` steps |
| I3 | Release publishes without pre-flight tests | High | Add test job as `needs:` gate in `release.yml` |
| I4 | Token-based PyPI auth (insecure pattern) | Medium | Switch to OIDC Trusted Publishing |
| I5 | PR check duplicates CI unit test run | Low | Remove redundant `pytest` call from `pr-check.yml` |
| I6 | No Dependabot config | Medium | Add `.github/dependabot.yml` |
| I7 | No security/supply-chain scanning | Medium | Add `pip-audit` step in CI |
| I8 | `azure-pipelines-govern.yml` is orphaned at repo root | Low | Add header comment clarifying status |
| I9 | Coverage gate at 65% — no trend tracking | Low | Add Codecov upload step |

---

## 4. Implementation Plan

### Phase 1 — Skills (S1–S6)
Create `src/pbi_cli/skills/<name>/SKILL.md` for each missing skill following the established frontmatter
format (`name`, `version`, `min_cli_version`, `description`).

### Phase 2 — Infrastructure
1. `ci.yml` — add pip caching, add `windows-test` job, add `pip-audit` security step
2. `release.yml` — add `needs: [test]` gate + switch to OIDC publishing
3. `pr-check.yml` — remove duplicate unit test run
4. `.github/dependabot.yml` — new file, pip + GitHub Actions ecosystems
5. `azure-pipelines-govern.yml` — add clarifying comment

---

## 5. Acceptance Criteria

- All 6 skill files pass the `pr-check.yml` SKILL.md frontmatter validator
- CI passes on both `ubuntu-latest` and `windows-latest`
- Release workflow requires green tests before publishing
- `dependabot.yml` covers both `pip` and `github-actions` ecosystems
- No duplicate test execution on PRs
