"""Single source of truth for PBIR (Power BI enhanced report format) JSON schema
versions.

PBIR is a young, evolving format: Microsoft bumps the schema version of each file
type independently (visualContainer is already at 2.9.0, report at 3.3.0, ...).
Hard-coding those URLs across the codebase means a Microsoft version bump turns
into a multi-file hunt. Centralising them here makes a bump a one-line change.

The version numbers below are the latest *published* versions in the official
schema repository:

    https://github.com/microsoft/json-schemas/tree/main/fabric/item/report

To refresh them, run ``scripts/check_pbir_schemas.py`` (compares this table with
the live repo) or re-list the repo with::

    gh api repos/microsoft/json-schemas/contents/fabric/item/report/definition \\
        --jq '.[] | select(.type=="dir") | .name'

Schema URLs are publicly resolvable and double as IntelliSense/validation hints
in editors like VS Code, so writing the correct, current URL matters.
"""

from __future__ import annotations

_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report"

# ── Schemas under report/definition/ ────────────────────────────────────────────
# name -> latest published version. Keep alphabetical; verified against the repo.
DEFINITION_SCHEMA_VERSIONS: dict[str, str] = {
    "bookmark": "2.1.0",
    "bookmarksMetadata": "1.0.0",
    "filterConfiguration": "1.3.0",
    "formattingObjectDefinitions": "1.5.0",
    "page": "2.1.0",
    "pagesMetadata": "1.1.0",
    "report": "3.3.0",
    "reportExtension": "1.0.0",
    "semanticQuery": "1.4.0",
    "versionMetadata": "1.0.0",
    "visualConfiguration": "2.3.0",
    "visualContainer": "2.9.0",
    "visualContainerMobileState": "2.4.0",
}

# ── Schemas directly under report/ (not the definition/ folder) ─────────────────
_ITEM_SCHEMA_VERSIONS: dict[str, str] = {
    "definitionProperties": "2.0.0",  # the definition.pbir file
}

# ``reportVersionAtImport`` records the Power BI *application* feature versions a
# report was authored against — distinct from the JSON-schema versions above.
# Desktop writes this into report.json's themeCollection.baseTheme.
REPORT_VERSION_AT_IMPORT: dict[str, str] = {
    "visual": "2.8.0",
    "report": "3.2.0",
    "page": "2.3.1",
}


def definition_schema(name: str) -> str:
    """Return the full ``$schema`` URL for a report/definition/ file type.

    >>> definition_schema("visualContainer")
    'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json'
    """
    try:
        version = DEFINITION_SCHEMA_VERSIONS[name]
    except KeyError as exc:  # pragma: no cover - guards typos at call sites
        raise KeyError(
            f"Unknown PBIR definition schema '{name}'. "
            f"Known: {sorted(DEFINITION_SCHEMA_VERSIONS)}"
        ) from exc
    return f"{_BASE}/definition/{name}/{version}/schema.json"


def item_schema(name: str) -> str:
    """Return the full ``$schema`` URL for a report/ item file type (e.g. the
    definition.pbir ``definitionProperties`` file)."""
    try:
        version = _ITEM_SCHEMA_VERSIONS[name]
    except KeyError as exc:  # pragma: no cover
        raise KeyError(
            f"Unknown PBIR item schema '{name}'. Known: {sorted(_ITEM_SCHEMA_VERSIONS)}"
        ) from exc
    return f"{_BASE}/{name}/{version}/schema.json"
