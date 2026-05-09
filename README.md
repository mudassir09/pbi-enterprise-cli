# pbi-cli

> Full-stack Power BI automation from the command line — semantic model management, report authoring, governance enforcement, DAX testing, REST source profiling, and AI-powered measure generation.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-410%20passing-brightgreen)
![Version](https://img.shields.io/badge/version-4.0.0--dev-orange)

---

## What it does

`pbi-cli` gives you a single `pbi` command that covers every layer of Power BI development — no clicking through the Desktop UI, no manual file editing, no proprietary tooling dependencies.

| Area | Commands |
|---|---|
| **Semantic model** | `pbi model` — tables, columns, relationships, lint, lineage |
| **DAX measures** | `pbi measure` — add, update, delete, AI-generate |
| **DAX testing** | `pbi dax` — query, validate, YAML unit-test suites |
| **Source profiling** | `pbi source` — SQL, Excel, CSV, REST APIs → star-schema scaffold |
| **Report authoring** | `pbi report` — pages, bookmarks (PBIR GA format) |
| **Visuals** | `pbi visual` — 17 visual types, colour-scale & data-bar formatting |
| **Layout** | `pbi layout` — shelf-packing auto-layout, named templates |
| **Themes** | `pbi theme` — generate WCAG-compliant themes from a brand colour |
| **Filters** | `pbi filter` — relative-date, TopN, basic value filters |
| **Governance** | `pbi govern` — 5 built-in rules + custom plugin system, auto-fix |
| **Security (RLS)** | `pbi security` — role add/delete/test |
| **Partitions** | `pbi partition` — add, refresh, delete |
| **Deployment** | `pbi deploy` — snapshot, diff, push via XMLA |
| **TMDL** | `pbi database` — export / import TMDL snapshots |
| **Docs** | `pbi docs` — markdown/Confluence data dictionary, audit log |
| **Diagnostics** | `pbi doctor` — check pythonnet, optional deps, platform |
| **Watch mode** | `pbi watch` — re-run governance + DAX tests on file change |
| **REST API** | `pbi server` — FastAPI server for pipeline integration |

---

## Backends

The same CLI works against three backends — swap with `--backend`:

| Backend | When to use |
|---|---|
| `desktop` (default) | Local Power BI Desktop open with a `.pbip` project |
| `xmla` | Power BI Premium or Microsoft Fabric — no Desktop required |
| `mock` | CI pipelines, unit tests, demos — zero infrastructure |

---

## Installation

**Base install** (semantic model, governance, DAX, report authoring):
```bash
pip install pbi-cli-tool
```

**Optional feature groups:**
```bash
pip install "pbi-cli-tool[ai]"       # Claude AI measure generation
pip install "pbi-cli-tool[xmla]"     # XMLA auth (MSAL)
pip install "pbi-cli-tool[sources]"  # SQL / Excel / REST profiling
pip install "pbi-cli-tool[viz]"      # WCAG theme validation, screenshots
pip install "pbi-cli-tool[server]"   # FastAPI REST server
pip install "pbi-cli-tool[all]"      # Everything
```

> **Requirements:** Python 3.10+. The `desktop` and `xmla` backends require Windows and the AMO .NET assemblies (installed with Power BI Desktop).

---

## Quick Start

```bash
# Check your setup
pbi doctor

# Connect to open Power BI Desktop and inspect the model
pbi model tables
pbi model relationships
pbi measure list

# Run governance checks
pbi govern check

# Auto-fix safe violations (PascalCase, missing format strings, etc.)
pbi govern fix --auto

# Add a measure
pbi measure add \
  --table Sales \
  --name "Total Revenue" \
  --expression "SUM(Sales[Revenue])" \
  --format-string "#,0.00" \
  --description "Net revenue after discounts"

# Run DAX unit tests
pbi dax test --suite tests/fixtures/measures/sales_suite.yaml

# Profile a REST API and scaffold a star-schema model
pbi source profile --type rest \
  --url https://api.example.com/v1/orders \
  --bearer-token $MY_TOKEN \
  --output profile.json

pbi source scaffold --profile profile.json
```

---

## Report Authoring (PBIP / PBIR)

Write directly to the `.pbip` project files — no running Desktop required. Open Desktop after to see the changes.

```bash
# Pages
pbi report pages       --pbip ./Sales.Report
pbi report page-add    --pbip ./Sales.Report --name "Executive Summary"

# Visuals (17 types: card, bar, column, line, table, slicer, matrix, ...)
pbi visual add --pbip ./Sales.Report \
  --page "Executive Summary" \
  --type card \
  --table Sales --value "Total Revenue" --measure

# Bookmarks
pbi report bookmark-add --pbip ./Sales.Report --name "Q4 2024 View"

# Conditional formatting
pbi visual format-color-scale --pbip ./Sales.Report \
  --page "Executive Summary" \
  --visual-title "Sales by Product" \
  --table Sales --field Revenue \
  --min "#FF6B6B" --mid "#FFD93D" --max "#6BCB77"

# Auto-layout (shelf-packing)
pbi layout auto --pbip ./Sales.Report --page "Executive Summary"
```

---

## Governance

Five built-in rules run out of the box. Drop a `.py` file in `~/.pbi-cli/rules/` to add your own:

```python
# ~/.pbi-cli/rules/no_spaces_in_columns.py
RULE_ID = "custom.no_spaces_in_columns"

def check(backend):
    violations = []
    for table in backend.table_list():
        for col in backend.column_list(table["name"]):
            if " " in col["name"]:
                violations.append({
                    "rule": RULE_ID,
                    "object": f"{table['name']}.{col['name']}",
                    "message": "Column name contains a space.",
                    "severity": "warning",
                    "autoFixable": False,
                })
    return violations
```

```bash
pbi govern rules    # lists all built-in + plugin rules
pbi govern check    # exit code 1 on errors — use as a CI gate
pbi govern fix --auto
```

---

## XMLA Backend

Connect to Power BI Premium or Fabric — no Desktop required:

```python
from pbi_cli.backends.xmla_backend import XmlaBackend

b = XmlaBackend()
b.connect(
    "powerbi://api.powerbi.com/v1.0/myorg/MySalesWorkspace",
    catalog="MySalesDataset",
    auth_mode="service_principal",   # or "device_flow" / "token"
    client_id=..., client_secret=..., tenant_id=...,
)
print(b.table_list())
print(b.dax_query("EVALUATE TOPN(5, Sales)"))
```

Connection pooling is automatic — same `(endpoint, catalog)` pair reuses the live AMO Server object.

---

## CI / CD

```yaml
# .github/workflows/pbi-governance.yml
name: PBI Governance
on: [push, pull_request]
jobs:
  govern:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install "pbi-cli-tool[dev]"
      - run: pbi --backend mock govern check
      - run: pbi --backend mock dax test --suite tests/fixtures/
```

---

## Global Flags

These work with every command:

| Flag | Purpose |
|---|---|
| `--backend desktop\|xmla\|mock` | Select backend (default: `desktop`) |
| `--dry-run` | Preview changes without applying them |
| `--json` | Machine-readable JSON output |
| `--port 5000` | Desktop local server port |

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude AI for `pbi measure generate` |
| `PBI_REST_BEARER` | Default Bearer token for REST source profiling |
| `PBI_CLIENT_ID` | AAD app client ID for XMLA service principal auth |
| `PBI_CLIENT_SECRET` | AAD app client secret |
| `PBI_TENANT_ID` | AAD tenant ID |

---

## Development

```bash
git clone https://github.com/mudassir09/pbi-cli.git
cd pbi-cli
pip install -e ".[all]"

# Run the full test suite (410 tests, ~4 s)
python -m pytest

# Lint
ruff check src/ tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch strategy and coding standards.

---

## License

[MIT](LICENSE) — © 2026 Mudassir
