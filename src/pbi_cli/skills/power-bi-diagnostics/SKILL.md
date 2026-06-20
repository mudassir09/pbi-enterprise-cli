---
name: power-bi-diagnostics
version: "2.0"
min_cli_version: "0.1.0"
description: >
  Use for pbi doctor interpretation, pythonnet/AMO resolution, platform detection,
  connection troubleshooting, error taxonomy, and guided fix playbooks.
  Triggers on: "pbi doctor", "not connecting", "pythonnet error", "AMO",
  "Desktop not found", "XMLA auth failed", "connection refused", "DLL error",
  "pbi diagnostics", "troubleshoot", "error code", "setup problem",
  "install issue", "port scan", "backend error".
  Do NOT trigger for DAX expression errors (→ power-bi-dax), governance
  violations (→ power-bi-governance), or deployment auth setup (→ power-bi-deployment).
---

# power-bi-diagnostics

`pbi doctor`, connection troubleshooting, pythonnet/AMO resolution, and error playbooks.

## Quick Reference

```bash
# Full setup check
pbi doctor
pbi --backend mock doctor          # test CLI works without Desktop
pbi --json doctor                  # machine-readable output for CI

# Port and connection scanning
pbi connect                        # auto-detect Desktop, show model info
pbi connect --port 52697           # explicit port

# Trace and benchmark (performance sub-commands)
pbi trace start --query "EVALUATE Sales" --duration 30s
pbi benchmark --measure "Total Revenue" --iterations 10
```

---

## Worked Example 1: Interpret pbi doctor output

```
pbi doctor

┌─────────────────────────┬──────────┬──────────────────────────────────────────┐
│ Check                   │ Status   │ Detail                                   │
├─────────────────────────┼──────────┼──────────────────────────────────────────┤
│ Python version          │ pass     │ 3.11.9                                   │
│ pythonnet               │ warn     │ Not installed (Windows only)             │
│ sqlalchemy [sources]    │ warn     │ Not installed (optional)                 │
│ fastapi [server]        │ pass     │ 0.136.3                                  │
│ Platform                │ warn     │ linux (TOM backend requires Windows)     │
└─────────────────────────┴──────────┴──────────────────────────────────────────┘
```

**Reading the output:**
- `pass` — dependency present and working
- `warn` — optional dependency missing or non-Windows platform; mock backend still works
- `fail` — required dependency broken; CLI may not function

**Linux/macOS CI environment:** `warn` on pythonnet and Platform is expected and correct. The mock backend works on all platforms; Desktop/XMLA backends require Windows.

---

## Worked Example 2: Fix "No running Power BI Desktop found"

```
pbi connect
Error: No running Power BI Desktop found.
```

**Diagnosis steps:**
```bash
# 1 — Confirm a .pbip or .pbix file is open in Desktop
#     (pbi requires an open model, not just the Desktop app)

# 2 — Check which port Desktop is using (Windows only)
netstat -ano | findstr "LISTEN" | findstr "5269"

# 3 — Try explicit port if auto-detection fails
pbi connect --port 52697

# 4 — If Desktop is open but port scan finds nothing,
#     restart Desktop and reopen the file
```

---

## Worked Example 3: Resolve pythonnet import error on Windows

```
ImportError: No module named 'clr'
```

**Fix:**
```bash
# Uninstall generic pythonnet and install the pinned version
pip uninstall pythonnet -y
pip install pythonnet==3.1.0rc0

# Verify
python -c "import clr; print('OK')"

# If still failing — .NET Framework 4.7.2+ required on Windows
# Check:
dotnet --list-runtimes
# Must show "Microsoft.NETFramework.App 4.7.2" or higher
```

---

## Error Code Reference

| Exit code | Meaning | Common cause |
|---|---|---|
| 0 | Success | — |
| 1 | User error | Missing required flag, invalid argument |
| 2 | Connection error | Desktop not running, XMLA unreachable, port wrong |
| 3 | Validation error | Governance violation, schema error, DAX invalid |
| 4 | Operation error | TOM write failed, partial completion, DLL exception |

---

## Common Error Playbook

| Error message | Root cause | Fix |
|---|---|---|
| `No running Power BI Desktop found` | Desktop not open or no model loaded | Open a `.pbip` file in Desktop |
| `pythonnet.Runtime.PythonException: clr` | pythonnet version mismatch | `pip install pythonnet==3.1.0rc0` |
| `ADOMD: Connection refused` | XMLA endpoint wrong or firewall | Verify endpoint URL; check Premium/Fabric capacity is running |
| `401 Unauthorized` (XMLA) | Token expired or wrong tenant | Re-run `pbi connections add`; check `--tenant-id` |
| `403 Forbidden` (XMLA) | Service principal lacks workspace access | Add SP as Member in the workspace |
| `AMO: The session has been cancelled` | Timeout on large model push | Add `--timeout 3600` |
| `DurableId overflow` | PBIR file with invalid ID | Run `pack.py` auto-repair or regenerate the PBIR file |

---

## Platform Matrix

| Platform | Desktop backend | XMLA backend | Mock backend |
|---|---|---|---|
| Windows 10/11 | ✓ (requires Desktop open) | ✓ (requires Premium/Fabric) | ✓ |
| Windows Server | ✗ (no Desktop) | ✓ | ✓ |
| Linux / macOS | ✗ | ✗ (pythonnet limitation) | ✓ |
| GitHub Actions ubuntu-latest | ✗ | ✗ | ✓ |
| GitHub Actions windows-latest | ✓ | ✓ | ✓ |

---

## Edge Cases

**`pbi doctor` passes but `pbi model tables` still fails:** The CLI is installed correctly but Desktop isn't running or no `.pbip` is open. `doctor` checks Python dependencies, not Desktop state.

**pythonnet installs but `clr` import fails at runtime:** A second Python environment has a conflicting pythonnet version. Check `where python` and `pip show pythonnet` to confirm you're in the right venv.

**Mock backend returns empty results for custom commands:** The mock backend simulates a synthetic model. Commands that call backend-specific methods return canned data. For real validation, switch to `--backend desktop`.

---

## Cross-skill handoffs

- XMLA connection auth setup → **power-bi-deployment**
- Governance check failures → **power-bi-governance**
- DAX validation errors → **power-bi-dax**
- Performance tracing (slow queries) → **power-bi-performance**
