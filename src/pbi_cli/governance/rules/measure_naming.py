"""Rule: measure naming conventions — Title Case, no ALL_CAPS, hidden prefix consistency."""

from __future__ import annotations

import re
from typing import Any

RULE_ID = "measure-naming"


def check(backend: Any) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for measure in backend.measure_list():
        name: str = measure["name"]
        table: str = measure.get("table", "")
        is_hidden: bool = measure.get("isHidden", False)

        # Strip leading bracket if present (shouldn't be there, but be defensive)
        bare = name.lstrip("[").rstrip("]")

        # ALL_CAPS names are hard to read — suggest Title Case
        if bare == bare.upper() and len(bare) > 2 and "_" in bare:
            violations.append({
                "rule": RULE_ID,
                "object": f"Measure '{name}'",
                "message": (
                    f"Measure '{name}' is ALL_CAPS. Use Title Case (e.g. 'Total Sales')."
                ),
                "severity": "warning",
                "autoFixable": True,
                "table": table,
                "suggestedName": _to_title(bare),
            })

        # Hidden measures should start with _ prefix
        if is_hidden and not bare.startswith("_"):
            violations.append({
                "rule": RULE_ID,
                "object": f"Measure '{name}'",
                "message": (
                    f"Measure '{name}' is hidden but does not start with '_'. "
                    "Use '_' prefix for hidden measures (e.g. '_Sales Base')."
                ),
                "severity": "info",
                "autoFixable": True,
                "table": table,
                "suggestedName": f"_{bare}",
            })

        # Non-hidden measures starting with _ are inconsistent
        if not is_hidden and bare.startswith("_"):
            violations.append({
                "rule": RULE_ID,
                "object": f"Measure '{name}'",
                "message": (
                    f"Measure '{name}' starts with '_' (hidden convention) but is not hidden. "
                    "Either hide it or remove the '_' prefix."
                ),
                "severity": "info",
                "autoFixable": False,
                "table": table,
            })

    return violations


def fix(backend: Any, violation: dict[str, Any]) -> bool:
    """Rename the measure to the suggested name."""
    suggested = violation.get("suggestedName")
    if not suggested:
        return False
    name = violation["object"].split("'")[1]
    table = violation.get("table", "")
    if not table:
        for m in backend.measure_list():
            if m["name"] == name:
                table = m.get("table", "")
                break
    try:
        backend.measure_update(table, name, new_name=suggested)
        return True
    except Exception:
        return False


def _to_title(name: str) -> str:
    """Convert ALL_CAPS_SNAKE to Title Case With Spaces."""
    return " ".join(word.capitalize() for word in name.split("_") if word)
