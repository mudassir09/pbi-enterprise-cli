"""Rule: measure names must not literally include [Brackets] in the name property."""

from __future__ import annotations

from typing import Any

RULE_ID = "measure-brackets"


def check(backend: Any) -> list[dict[str, Any]]:
    violations = []
    for measure in backend.measure_list():
        name = measure["name"]
        if name.startswith("[") and name.endswith("]"):
            violations.append(
                {
                    "rule": "measure-brackets",
                    "object": f"Measure '{name}'",
                    "message": (
                        f"Measure '{name}' name contains literal [Brackets] — "
                        "remove them; brackets are only used when referencing measures in DAX"
                    ),
                    "severity": "warning",
                    "autoFixable": False,
                }
            )
    return violations
