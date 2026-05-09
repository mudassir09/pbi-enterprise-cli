"""Rule: all measures must have a formatString."""

from __future__ import annotations

RULE_ID = "measure-format-required"

from typing import Any

_DEFAULT_FORMAT = "#,0.00"


def check(backend: Any) -> list[dict[str, Any]]:
    violations = []
    for measure in backend.measure_list():
        if not measure.get("formatString"):
            violations.append({
                "rule": "measure-format-required",
                "object": f"Measure '{measure['name']}'",
                "message": f"Measure '{measure['name']}' is missing a formatString",
                "severity": "warning",
                "autoFixable": True,
            })
    return violations


def fix(backend: Any, violation: dict[str, Any]) -> bool:
    """Apply the default format string to the measure."""
    name = violation["object"].split("'")[1]
    for measure in backend.measure_list():
        if measure["name"] == name:
            try:
                backend.measure_update(measure["table"], name, formatString=_DEFAULT_FORMAT)
                return True
            except Exception:
                return False
    return False
