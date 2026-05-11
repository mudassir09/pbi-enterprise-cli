"""BPA (Best Practice Analyzer) — loader and Python expression evaluator.

Supports the BPARules.json schema used by Tabular Editor and the Microsoft
community rule set. Runs the same rules without any .NET tooling.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMUNITY_BPA_URL = (
    "https://raw.githubusercontent.com/microsoft/Analysis-Services"
    "/master/BestPracticeRules/BPARules.json"
)

_SEVERITY_MAP = {1: "warning", 2: "error", 3: "info"}

# Scopes we can evaluate — anything else is skipped
_SUPPORTED_SCOPES = {"Column", "Table", "Measure", "Relationship"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BpaRule:
    id: str
    name: str
    category: str
    description: str
    severity: int  # 1=warning, 2=error, 3=info
    scope: str
    expression: str
    fix_expression: str | None = None
    compatibility_level: int = 1200

    @property
    def severity_label(self) -> str:
        return _SEVERITY_MAP.get(self.severity, "warning")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _parse_rules(data: list[dict[str, Any]]) -> list[BpaRule]:
    rules: list[BpaRule] = []
    for item in data:
        rules.append(
            BpaRule(
                id=item.get("ID", ""),
                name=item.get("Name", ""),
                category=item.get("Category", ""),
                description=item.get("Description", ""),
                severity=item.get("Severity", 1),
                scope=item.get("Scope", ""),
                expression=item.get("Expression", ""),
                fix_expression=item.get("FixExpression"),
                compatibility_level=item.get("CompatibilityLevel", 1200),
            )
        )
    return rules


def load_rules_from_file(path: str) -> list[BpaRule]:
    """Load BPA rules from a local BPARules.json file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "Rules" in data:
        data = data["Rules"]
    return _parse_rules(data)


def load_rules_from_url(url: str) -> list[BpaRule]:
    """Fetch BPA rules from a URL. Uses httpx if available, falls back to urllib."""
    try:
        import httpx  # type: ignore

        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

    if isinstance(data, dict) and "Rules" in data:
        data = data["Rules"]
    return _parse_rules(data)


# ---------------------------------------------------------------------------
# Expression evaluator
# ---------------------------------------------------------------------------


def _build_context(scope: str, obj: dict[str, Any]) -> dict[str, Any]:
    """Build the local variable dict for eval() based on scope and object."""
    if scope == "Column":
        return {
            "Name": obj.get("name", ""),
            "DataType": obj.get("dataType", ""),
            "IsHidden": obj.get("isHidden", False),
            "Description": obj.get("description", ""),
            "Table": obj.get("table", ""),
            # lower-case aliases for convenience
            "name": obj.get("name", ""),
            "data_type": obj.get("dataType", ""),
            "hidden": obj.get("isHidden", False),
            "description": obj.get("description", ""),
        }
    if scope == "Table":
        return {
            "Name": obj.get("name", ""),
            "IsHidden": obj.get("isHidden", False),
            "Description": obj.get("description", ""),
            "name": obj.get("name", ""),
            "hidden": obj.get("isHidden", False),
            "description": obj.get("description", ""),
        }
    if scope == "Measure":
        return {
            "Name": obj.get("name", ""),
            "Expression": obj.get("expression", ""),
            "Description": obj.get("description", ""),
            "FormatString": obj.get("formatString", ""),
            "IsHidden": obj.get("isHidden", False),
            "Table": obj.get("table", ""),
            "name": obj.get("name", ""),
            "expression": obj.get("expression", ""),
            "description": obj.get("description", ""),
            "format_string": obj.get("formatString", ""),
            "hidden": obj.get("isHidden", False),
        }
    if scope == "Relationship":
        return {
            "From": obj.get("from", ""),
            "To": obj.get("to", ""),
            "Cardinality": obj.get("cardinality", ""),
            "name": obj.get("from", ""),
            "cardinality": obj.get("cardinality", ""),
        }
    return {}


def _translate_expression(expr: str) -> str:
    """Translate a C# BPA expression string into a Python expression string.

    Handles the most common patterns from the community rule set.
    Raises NotImplementedError for patterns we cannot safely translate.
    """
    # Reject expressions that contain method calls we don't support yet
    # (LINQ-style .Count(), .Any(), etc.)
    _unsupported_methods = re.compile(
        r"\.(Count|Sum|Average|Any|All|Select|Where|OrderBy|First|Last|Min|Max)\s*\(",
        re.IGNORECASE,
    )
    if _unsupported_methods.search(expr):
        raise NotImplementedError(f"Unsupported LINQ expression: {expr!r}")

    result = expr

    # Logical operators
    result = re.sub(r"\s*&&\s*", " and ", result)
    result = re.sub(r"\s*\|\|\s*", " or ", result)

    # not keyword (case-insensitive)
    result = re.sub(r"\bnot\b\s*", "not ", result, flags=re.IGNORECASE)

    # [PropName].StartsWith("x")  →  PropName.startswith("x")
    result = re.sub(
        r'\[(\w+)\]\.StartsWith\("([^"]*)"\)',
        lambda m: f'{m.group(1)}.startswith("{m.group(2)}")',
        result,
        flags=re.IGNORECASE,
    )

    # [PropName].EndsWith("x")  →  PropName.endswith("x")
    result = re.sub(
        r'\[(\w+)\]\.EndsWith\("([^"]*)"\)',
        lambda m: f'{m.group(1)}.endswith("{m.group(2)}")',
        result,
        flags=re.IGNORECASE,
    )

    # [PropName].Contains("x")  →  "x" in PropName
    result = re.sub(
        r'\[(\w+)\]\.Contains\("([^"]*)"\)',
        lambda m: f'"{m.group(2)}" in {m.group(1)}',
        result,
        flags=re.IGNORECASE,
    )

    # PropName.Contains("x")  →  "x" in PropName   (no brackets variant)
    result = re.sub(
        r'(\w+)\.Contains\("([^"]*)"\)',
        lambda m: f'"{m.group(2)}" in {m.group(1)}',
        result,
        flags=re.IGNORECASE,
    )

    # PropName = "value"  →  PropName == "value"
    # Must not already be == and must not be preceded by < or >
    result = re.sub(r'(?<![=<>!])=(?![=])', "==", result)

    # PropName <> "value"  →  PropName != "value"
    result = result.replace("<>", "!=")

    # [PropName] == "value"  →  PropName == "value"  (comparison context — strip brackets)
    result = re.sub(
        r'\[(\w+)\](\s*(?:==|!=|<=|>=|<(?!>)|>))',
        lambda m: f"{m.group(1)}{m.group(2)}",
        result,
    )

    # [BoolProp]  →  bool(BoolProp)   — standalone bracketed reference (not method, not comparison)
    result = re.sub(
        r'\[(\w+)\](?![\.\[])',
        lambda m: f"bool({m.group(1)})",
        result,
    )

    return result


def _evaluate_expression(expr: str, ctx: dict[str, Any]) -> bool:
    """Evaluate a translated Python expression against ctx. Returns True if violated."""
    try:
        py_expr = _translate_expression(expr)
        safe_builtins = {"bool": bool, "str": str, "int": int, "float": float, "len": len}
        return bool(eval(py_expr, {"__builtins__": safe_builtins}, ctx))  # noqa: S307
    except NotImplementedError:
        raise
    except Exception as exc:
        raise NotImplementedError(f"Cannot evaluate expression {expr!r}: {exc}") from exc


def _object_path(scope: str, obj: dict[str, Any]) -> str:
    """Build a human-readable object path string."""
    if scope == "Column":
        return f"{obj.get('table', '?')}[{obj.get('name', '?')}]"
    if scope == "Measure":
        return f"{obj.get('table', '?')}[{obj.get('name', '?')}]"
    if scope == "Table":
        return obj.get("name", "?")
    if scope == "Relationship":
        return f"{obj.get('from', '?')} → {obj.get('to', '?')}"
    return str(obj)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class BpaEvaluator:
    """Evaluate a list of BpaRules against a backend and return violations."""

    def evaluate(
        self,
        rules: list[BpaRule],
        backend: Any,
        severity_filter: str | None = None,
        category_filter: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run all rules against the backend.

        Returns:
            (violations, skipped_count)
        """
        # Pre-fetch backend objects once
        objects_by_scope: dict[str, list[dict[str, Any]]] = {
            "Column": backend.column_list(),
            "Table": backend.table_list(),
            "Measure": backend.measure_list(),
            "Relationship": backend.relationship_list(),
        }

        violations: list[dict[str, Any]] = []
        skipped = 0

        for rule in rules:
            # Apply filters early
            if severity_filter and rule.severity_label != severity_filter:
                continue
            if category_filter and rule.category.lower() != category_filter.lower():
                continue

            if rule.scope not in _SUPPORTED_SCOPES:
                skipped += 1
                continue

            objects = objects_by_scope.get(rule.scope, [])
            for obj in objects:
                ctx = _build_context(rule.scope, obj)
                try:
                    violated = _evaluate_expression(rule.expression, ctx)
                except NotImplementedError:
                    skipped += 1
                    break  # skip entire rule (not per-object)
                else:
                    if violated:
                        violations.append(self._make_violation(rule, obj))

        return violations, skipped

    @staticmethod
    def _make_violation(rule: BpaRule, obj: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule": f"bpa.{rule.id.lower()}",
            "bpa_id": rule.id,
            "object": _object_path(rule.scope, obj),
            "message": rule.name,
            "description": rule.description,
            "severity": rule.severity_label,
            "category": rule.category,
            "autoFixable": False,
        }
