# pbi-enterprise-cli

**Full-stack Power BI enterprise automation from the command line.**

```bash
pip install pbi-enterprise-cli
pbi doctor          # verify setup
pbi model tables    # list tables in the connected model
pbi govern check    # run governance rules
```

## Feature highlights

- **25 command groups** covering every layer of Power BI development
- **32 visual types** — from cards to decomposition trees
- **3 backends** — Desktop (TOM via pythonnet), XMLA (Premium/Fabric), Mock (CI)
- **PBIR GA format** — read and write `.pbip` project files directly
- **Governance engine** — 5 built-in rules + custom plugin system + **BPA compatibility** (run Microsoft community BPA rules natively — no Tabular Editor required)
- **REST source profiling** — Bearer/API-key auth, OData pagination, star-schema scaffold
- **REPL mode** — interactive session with tab completion and persistent history
- **Custom visual SDK** — scaffold, build, package, import `.pbiviz`
- **AI measure generation** — Claude API integration (requires `[ai]` extra)
- **24 AI skills** — install Claude Code skills (`pbi skills install --all`)
- **547 unit tests** passing on Python 3.10–3.12

## Install options

```bash
pip install pbi-enterprise-cli             # base
pip install "pbi-enterprise-cli[ai]"       # + Claude AI
pip install "pbi-enterprise-cli[xmla]"     # + MSAL auth for XMLA
pip install "pbi-enterprise-cli[sources]"  # + SQL/Excel/REST profiling
pip install "pbi-enterprise-cli[all]"      # everything
```

## Requirements

- Python 3.10+
- Windows (for Desktop/XMLA backends using .NET AMO — AMO DLLs are bundled in the wheel)

## Links

- [GitHub Repository](https://github.com/mudassir09/pbi-enterprise-cli)
- [Full Documentation](https://github.com/mudassir09/pbi-enterprise-cli#readme)
- [Changelog](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/CHANGELOG.md)
- [Security Policy](https://github.com/mudassir09/pbi-enterprise-cli/blob/main/SECURITY.md)
