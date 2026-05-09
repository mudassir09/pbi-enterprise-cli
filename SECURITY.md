# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 4.x (current) | ✅ Active |
| 3.x | ⚠️ Security fixes only |
| < 3.0 | ❌ Not supported |

## Reporting a Vulnerability

**Please do not file public GitHub Issues for security vulnerabilities.**

Report security issues privately by emailing: **mir.mudassir1@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You will receive an acknowledgement within 48 hours and a full response within 7 days.

## Security Considerations

### Credentials
- **Never** pass secrets as CLI arguments in production — use environment variables:
  - `PBI_CLIENT_SECRET` instead of `--client-secret`
  - `PBI_REST_BEARER` instead of `--bearer-token`
- The `~/.pbi-cli/connections.json` file stores connection profiles. Client secrets are
  stored in plaintext — secure the file with appropriate OS permissions (`chmod 600`).
- The audit log at `~/.pbi-cli/audit.jsonl` may contain model metadata. Do not commit it.

### XMLA Connections
- Service principal credentials grant broad workspace access. Follow least-privilege:
  assign the SP as a **Contributor** (not Admin) unless Admin is required.
- Token-mode (`auth_mode="token"`) accepts pre-acquired tokens — ensure token rotation
  and short TTLs in production.

### Governance Plugin Rules
- Rules loaded from `~/.pbi-cli/rules/*.py` run as arbitrary Python in the CLI process.
  Only load rule files you trust or have reviewed.

### pythonnet / AMO
- The Desktop backend loads .NET assemblies via pythonnet. Only assemblies from trusted
  sources (Power BI Desktop installation, official NuGet packages) should be loaded.
