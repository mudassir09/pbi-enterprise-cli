"""AI-readiness rule pack — is this semantic model ready for Copilot and Fabric IQ?

Checks the metadata that AI consumers depend on: Copilot and Q&A generate DAX
from the measures/columns they can "see", and Fabric IQ ontology generation
maps tables → entity types, columns → properties, and model relationships →
relationship types. Poor metadata here means poor AI answers and a poor
generated ontology.

Run via ``pbi govern ai-readiness`` — this pack is intentionally not part of
the default ``govern check`` rule set.
"""

from __future__ import annotations

import re
from typing import Any

RULE_ID = "ai-readiness"

# Auto date/time artifacts created by Power BI Desktop
_AUTO_DATE_RE = re.compile(r"^(LocalDateTable_|DateTableTemplate_)")

# Column names that are technical keys: SalesKey, CustomerID, RowGUID, Product_SK
_KEY_NAME_RE = re.compile(r"(?:[Kk]ey|Id|ID|GUID|_[Ss][Kk])$")


def _violation(rule: str, obj: str, message: str, severity: str = "warning") -> dict[str, Any]:
    return {
        "rule": rule,
        "object": obj,
        "message": message,
        "severity": severity,
        "autoFixable": False,
    }


def _business_tables(backend: Any) -> list[dict[str, Any]]:
    """Visible, non-auto-date, non-calculation-group tables."""
    return [
        t for t in backend.table_list()
        if not t.get("isHidden")
        and not _AUTO_DATE_RE.match(t.get("name", ""))
        and not t.get("isCalculationGroup")
    ]


def check_measure_descriptions(backend: Any) -> list[dict[str, Any]]:
    return [
        _violation(
            "ai-measure-description",
            f"Measure '{m['name']}'",
            f"Measure '{m['name']}' has no description — Copilot and ontology "
            "generation rely on descriptions to understand business meaning.",
        )
        for m in backend.measure_list()
        if not m.get("description") and not m.get("isHidden")
    ]


def check_column_descriptions(backend: Any) -> list[dict[str, Any]]:
    business = {t["name"] for t in _business_tables(backend)}
    return [
        _violation(
            "ai-column-description",
            f"Column '{c['table']}'[{c['name']}]",
            f"Visible column '{c['table']}'[{c['name']}] has no description — "
            "it becomes an undescribed ontology property and an opaque field for Copilot.",
            severity="info",
        )
        for c in backend.column_list()
        if c.get("table") in business
        and not c.get("isHidden")
        and not c.get("description")
    ]


def check_technical_columns_visible(backend: Any) -> list[dict[str, Any]]:
    business = {t["name"] for t in _business_tables(backend)}
    return [
        _violation(
            "ai-technical-column-visible",
            f"Column '{c['table']}'[{c['name']}]",
            f"Key column '{c['table']}'[{c['name']}] is visible — hide technical "
            "join/key columns so AI consumers only see business-facing fields.",
        )
        for c in backend.column_list()
        if c.get("table") in business
        and not c.get("isHidden")
        and _KEY_NAME_RE.search(c.get("name", ""))
    ]


def check_date_table_marked(backend: Any) -> list[dict[str, Any]]:
    tables = backend.table_list()
    has_datetime = any(
        str(c.get("dataType", "")).lower() == "datetime" for c in backend.column_list()
    )
    if not has_datetime:
        return []
    marked = any(str(t.get("dataCategory", "")).lower() == "time" for t in tables)
    if marked:
        return []
    return [
        _violation(
            "ai-date-table-marked",
            "Model",
            "No table is marked as the date table (dataCategory: Time) — time "
            "intelligence and AI date reasoning need an explicit date table.",
        )
    ]


def check_auto_datetime_tables(backend: Any) -> list[dict[str, Any]]:
    return [
        _violation(
            "ai-auto-datetime",
            f"Table '{t['name']}'",
            f"Auto date/time table '{t['name']}' present — disable auto date/time "
            "and use a dedicated date table; auto tables pollute Copilot context "
            "and ontology generation.",
        )
        for t in backend.table_list()
        if _AUTO_DATE_RE.match(t.get("name", ""))
    ]


def check_decimal_columns(backend: Any) -> list[dict[str, Any]]:
    return [
        _violation(
            "ai-decimal-column",
            f"Column '{c['table']}'[{c['name']}]",
            f"Column '{c['table']}'[{c['name']}] is Decimal — the Fabric IQ graph "
            "does not support Decimal and returns nulls for these properties; "
            "use Double (floating point) instead.",
        )
        for c in backend.column_list()
        if str(c.get("dataType", "")).lower() == "decimal"
    ]


def check_isolated_tables(backend: Any) -> list[dict[str, Any]]:
    business = _business_tables(backend)
    if len(business) < 2:
        return []
    related: set[str] = set()
    for r in backend.relationship_list():
        for endpoint in (r.get("from", ""), r.get("to", "")):
            related.add(endpoint.split("[", 1)[0].strip("'"))
    return [
        _violation(
            "ai-isolated-table",
            f"Table '{t['name']}'",
            f"Table '{t['name']}' has no relationships — ontology relationship "
            "types are generated from model relationships, so this entity type "
            "will be disconnected.",
            severity="info",
        )
        for t in business
        if t["name"] not in related
    ]


_CHECKS = [
    check_measure_descriptions,
    check_column_descriptions,
    check_technical_columns_visible,
    check_date_table_marked,
    check_auto_datetime_tables,
    check_decimal_columns,
    check_isolated_tables,
]


def check(backend: Any) -> list[dict[str, Any]]:
    """Run every AI-readiness check and return the combined violation list."""
    violations: list[dict[str, Any]] = []
    for fn in _CHECKS:
        violations.extend(fn(backend))
    return violations
