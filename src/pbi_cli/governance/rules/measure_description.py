"""Rule: all measures must have a non-empty description."""

from __future__ import annotations

from typing import Any

RULE_ID = "measure-description-required"


def check(backend: Any) -> list[dict[str, Any]]:
    violations = []
    for measure in backend.measure_list():
        if not measure.get("description"):
            violations.append(
                {
                    "rule": "measure-description-required",
                    "object": f"Measure '{measure['name']}'",
                    "message": f"Measure '{measure['name']}' is missing a description",
                    "severity": "warning",
                    "autoFixable": True,
                    "table": measure.get("table", ""),
                }
            )
    return violations


def fix(backend: Any, violation: dict[str, Any]) -> bool:
    """Set a generated placeholder description so the measure is documented."""
    name = violation["object"].split("'")[1]
    table = violation.get("table", "")
    placeholder = f"Calculates {name}. (Auto-generated — replace with a meaningful description.)"
    if not table:
        for m in backend.measure_list():
            if m["name"] == name:
                table = m.get("table", "")
                break
    try:
        backend.measure_update(table, name, description=placeholder)
        return True
    except Exception:
        return False
