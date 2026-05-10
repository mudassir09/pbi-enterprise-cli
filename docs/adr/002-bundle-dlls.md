# ADR-002: Bundle Microsoft Analysis Services DLLs inside the Python package

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

Power BI's TOM API is exposed by the Microsoft Analysis Services Client Libraries (AMO): `Microsoft.AnalysisServices.Tabular.dll` and related DLLs. Users need these DLLs to use pbi-cli's TOM backend.

## Decision

Ship the Microsoft Analysis Services DLLs inside `src/pbi_cli/dlls/` as part of the Python package distribution.

## Rationale

- **Zero-dependency install:** `pip install pbi-enterprise-cli` is sufficient. Users do not need to know what AMO is, install Visual Studio, or hunt for NuGet packages.
- **Version pinning:** Bundling a specific DLL version prevents "works on my machine" failures caused by different AMO versions installed on different systems.
- **Contributor experience:** New contributors can clone and run without any additional setup steps.

## Trade-offs

- **Licensing:** The Microsoft Analysis Services Client Libraries are not MIT-licensed. They are distributed under Microsoft's separate license terms. This requires:
  - A dual SPDX expression in `pyproject.toml`: `MIT AND LicenseRef-Microsoft-AS-Client-Libraries`
  - A `THIRD_PARTY_LICENSES.md` file in the repository root documenting the Microsoft license terms
  - The `LICENSE` file must clearly note the dual licensing
- **Package size:** DLLs add ~15 MB to the wheel. Acceptable for a developer tool; documented in the README.
- **Update cadence:** When Microsoft releases new AMO versions, the DLLs must be manually updated in the repository.

## Consequences

- `src/pbi_cli/dlls/` directory contains the bundled DLLs.
- `THIRD_PARTY_LICENSES.md` is maintained at the repository root.
- `pyproject.toml` uses the dual SPDX license expression.
- `MANIFEST.in` includes the `dlls/` directory.
- CI validates that the DLL directory is present on every release build.
