# pbi-enterprise-cli

**Enterprise-grade Power BI automation CLI — XMLA/Fabric connectivity without Desktop, Python-native BPA governance, and AI-powered measures.**

[![PyPI](https://img.shields.io/pypi/v/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![Python](https://img.shields.io/pypi/pyversions/pbi-enterprise-cli?cacheSeconds=300)](https://pypi.org/project/pbi-enterprise-cli/)
[![License](https://img.shields.io/github/license/mudassir09/pbi-enterprise-cli)](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pbi-enterprise-cli)](https://pypi.org/project/pbi-enterprise-cli/)
[![codecov](https://codecov.io/gh/mudassir09/pbi-enterprise-cli/graph/badge.svg)](https://codecov.io/gh/mudassir09/pbi-enterprise-cli)

```bash
uv tool install pbi-enterprise-cli
pbi doctor          # verify setup
pbi model tables    # list tables in the connected model
pbi govern check    # run governance rules (exit 3 on violations)
```

## Key differentiators

- **XMLA/Fabric backend** — connect to Power BI Premium or Microsoft Fabric without Desktop
- **Python-native BPA runner** — the only Python implementation of Best Practice Analyzer rules
- **Three backends** — Desktop (TOM via pythonnet), XMLA (Premium/Fabric), Mock (CI/CD with zero infrastructure)
- **AMO DLLs bundled** — works after `pip install` without a separate Desktop installation
- **Governance engine** — built-in rules + BPA + custom plugin system, `--fail-on` CI gate
- **10 Claude Code skills** — install with `pbi connect` for AI-assisted development in < 60 s
- **CI-ready mock backend** — full test suite runs on Linux without Power BI infrastructure

## Install options

```bash
# Recommended
uv tool install pbi-enterprise-cli
uv tool install "pbi-enterprise-cli[all]"   # everything

# Alternative
pipx install pbi-enterprise-cli

# Fallback
pip install pbi-enterprise-cli

# With specific extras
uv tool install "pbi-enterprise-cli[ai,xmla]"     # Claude AI + XMLA/Fabric
uv tool install "pbi-enterprise-cli[sources]"     # SQL/Excel/REST profiling
uv tool install "pbi-enterprise-cli[server]"      # FastAPI REST server
```

## Requirements

- Python 3.10–3.13
- Windows (for `desktop` and `xmla` backends — require .NET AMO)
- Linux/macOS supported for CI using the `mock` backend

## Links

- [GitHub Repository](https://github.com/mudassir09/pbi-enterprise-cli)
- [Full Documentation](https://github.com/mudassir09/pbi-enterprise-cli#readme)
- [XMLA Auth Guide](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/auth/xmla-auth.md)
- [Changelog](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/CHANGELOG.md)
- [Security Policy](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/SECURITY.md)
- [Issues](https://github.com/mudassir09/pbi-enterprise-cli/issues)
