# pbi-enterprise-cli

**Full-stack Power BI automation from the command line.**

```bash
pip install pbi-enterprise-cli
pbi doctor          # verify setup
pbi model tables    # list tables in the connected model
pbi govern check    # run governance rules (exit 3 on violations)
```

## Feature highlights

- **22 command groups** covering every layer of Power BI development
- **3 backends** — Desktop (TOM via pythonnet), XMLA (Premium/Fabric), Mock (CI)
- **PBIR GA format** — read and write `.pbip` project files directly
- **Governance engine** — built-in rules + BPA + custom plugin system, `--fail-on` CI gate
- **Model snapshots** — create/list/restore/diff with `pbi snapshot`
- **Multi-environment** — named connections, `pbi env promote dev→prod`
- **Authenticated REST server** — API key auth, localhost-only default
- **Source profiling** — SQL, Excel, CSV, REST → star-schema scaffold
- **30 Claude Code skills** — install with `pbi skills install --all`
- **575 unit tests** passing on Python 3.10–3.12, coverage gate enforced

## Install options

```bash
pip install pbi-enterprise-cli             # base
pip install "pbi-enterprise-cli[ai]"       # + Claude AI measure generation
pip install "pbi-enterprise-cli[xmla]"     # + MSAL auth for XMLA
pip install "pbi-enterprise-cli[sources]"  # + SQL/Excel/REST profiling
pip install "pbi-enterprise-cli[server]"   # + authenticated FastAPI REST server
pip install "pbi-enterprise-cli[all]"      # everything
```

## Requirements

- Python 3.10+
- Windows (for Desktop/XMLA backends using .NET AMO)
- Power BI Desktop (for the `desktop` backend)

## Links

- [GitHub Repository](https://github.com/mudassir09/pbi-enterprise-cli)
- [Full Documentation](https://github.com/mudassir09/pbi-enterprise-cli#readme)
- [XMLA Auth Guide](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/auth/xmla-auth.md)
- [Deployment Guide](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/docs/deployment.md)
- [Stability Policy](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/STABILITY.md)
- [Changelog](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/CHANGELOG.md)
- [Security Policy](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/SECURITY.md)
