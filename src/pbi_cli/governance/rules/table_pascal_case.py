"""Rule: table names must be PascalCase (or optionally FACT_/DIM_ prefixed)."""

from __future__ import annotations

RULE_ID = "table-pascal-case"

import re
from typing import Any


def check(backend: Any) -> list[dict[str, Any]]:
    violations = []
    for table in backend.table_list():
        name = table["name"]
        if not re.match(r"^[A-Z][a-zA-Z0-9]*$", name) and not name.startswith(("FACT_", "DIM_")):
            violations.append({
                "rule": "table-pascal-case",
                "object": f"Table '{name}'",
                "message": f"Table '{name}' should be PascalCase (e.g. 'SalesData')",
                "severity": "warning",
                "autoFixable": True,
            })
    return violations


def fix(backend: Any, violation: dict[str, Any]) -> bool:
    """Rename the table to PascalCase."""
    name = violation["object"].split("'")[1]
    pascal = _to_pascal(name)
    if pascal == name:
        return False
    try:
        backend.table_update(name, new_name=pascal)
        return True
    except Exception:
        return False


def _to_pascal(name: str) -> str:
    """Convert snake_case or space-separated name to PascalCase."""
    parts = re.split(r"[\s_\-]+", name)
    return "".join(p.capitalize() for p in parts if p)
