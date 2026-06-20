# pbi-enterprise-cli

**Enterprise-grade Power BI & Microsoft Fabric automation CLI — TMDL/XMLA/REST backends, Python-native BPA governance, DAX testing & lint, PBIR report intelligence, an MCP server for AI agents, and AI-powered measures.**

[![PyPI](https://img.shields.io/pypi/v/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![Python](https://img.shields.io/pypi/pyversions/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![License](https://img.shields.io/github/license/mudassir09/pbi-enterprise-cli)](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pbi-enterprise-cli)](https://pypi.org/project/pbi-enterprise-cli/)
[![codecov](https://codecov.io/gh/mudassir09/pbi-enterprise-cli/graph/badge.svg)](https://codecov.io/gh/mudassir09/pbi-enterprise-cli)

```bash
uv tool install pbi-enterprise-cli
pbi doctor                                   # verify setup
pbi --backend file --path . govern check     # governance on your repo's TMDL — any OS
pbi dax lint --fail-on error                 # static DAX analysis
pbi ask "top 10 customers by revenue"        # English → DAX → results
```

## Key differentiators

- **Real artifacts on any OS** — the `file` backend reads TMDL/PBIP folders straight from your repo (pure Python, no .NET): governance, BPA, lint, docs, and semantic diff on `ubuntu-latest`
- **Live DAX on any OS** — the `rest` backend runs DAX against published datasets via the `executeQueries` API; `xmla` gives full read/write on Windows
- **Python-native BPA runner** — runs the Best Practice Analyzer `BPARules.json` format with no .NET; safe AST evaluation with an honest evaluated/skipped tally per run
- **Full Fabric lifecycle** — item CRUD (Item Definition API), workspaces, git sync, deployment pipelines, OneLake, capacity ops, jobs, Direct Lake diagnostics
- **Quality platform** — DAX lint/format, report lint + unused-field analysis, dbt-style data tests, schema contracts, RLS matrices, drift detection — all CI-gateable with SARIF output
- **AI-agent native** — `pbi mcp serve` exposes everything to Cursor/Copilot/Claude Desktop; 10 bundled Claude Code skills install with `pbi connect`
- **One-step CI** — published GitHub Action + pre-commit hooks; scaffold a full project with `pbi init`

## Five backends, one API

| Backend | Use for | OS |
|---|---|---|
| `desktop` | Local Power BI Desktop (.pbip) | Windows |
| `xmla` | Premium / Fabric read-write | Windows |
| `file` | TMDL/PBIP repo artifacts — governance, lint, docs, diff | Any |
| `rest` | Live DAX via executeQueries | Any |
| `mock` | Unit tests, demos | Any |

## Command surface

`model` · `measure` · `dax` (query/test/lint/format/coverage) · `report` (authoring + lint/field-usage/diff/a11y) · `visual` · `layout` · `theme` · `filter` · `govern` (rules/BPA/plugins/SARIF/tenant scan) · `tenant` (usage/access/labels) · `security` · `test` (data/schema/rls/seed) · `partition` · `deploy` · `snapshot` · `env` (incl. drift) · `diff` · `fabric` (items/workspaces/git/pipelines/onelake/capacity/jobs/directlake) · `pquery` (M folding/lint) · `ops` (refresh chains/health) · `migrate` (direct-lake/pbix/dbt) · `docs` (dictionary/ERD/site) · `mcp` · `ask` · `introspect` · `init` · `watch` · `server` · `skills`

## Install options

```bash
# Recommended
uv tool install pbi-enterprise-cli
uv tool install "pbi-enterprise-cli[all]"   # everything

# Alternative
pipx install pbi-enterprise-cli

# Fallback
pip install pbi-enterprise-cli
```

| Extra | Adds |
|---|---|
| `[ai]` | Claude AI: `pbi ask`, `measure generate`, `govern explain` |
| `[xmla]` | MSAL auth for XMLA/Fabric + device flow |
| `[sources]` | SQL / Excel / REST source profiling |
| `[server]` | FastAPI REST server |
| `[viz]` | WCAG theme validation |

## Requirements

- Python 3.10–3.13
- Windows for the `desktop` and `xmla` backends (.NET AMO, DLLs bundled)
- Linux/macOS fully supported via the `file`, `rest`, and `mock` backends

## Links

- [GitHub Repository](https://github.com/mudassir09/pbi-enterprise-cli)
- [Full Documentation](https://github.com/mudassir09/pbi-enterprise-cli#readme)
- [Standard Operating Procedure](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/SOP.md)
- [XMLA Auth Guide](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/auth/xmla-auth.md)
- [Changelog](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/CHANGELOG.md)
- [Security Policy](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/SECURITY.md)
- [Issues](https://github.com/mudassir09/pbi-enterprise-cli/issues)
