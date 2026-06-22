"""Build schema-valid PBIR filter definitions (``filterConfig`` entries).

Grounded in the official Microsoft schemas:

  filterConfiguration : .../report/definition/filterConfiguration/1.3.0/schema.json
  semanticQuery       : .../report/definition/semanticQuery/1.4.0/schema.json

A page/report/visual stores its filters in a ``filterConfig`` object::

    "filterConfig": {
        "$schema": ".../filterConfiguration/1.3.0/schema.json",
        "filters": [ FilterContainer, ... ]
    }

Each FilterContainer carries metadata (``name`` is the only required field) plus a
``filter`` whose value is a *FilterDefinition* — a partial semantic query of the
shape ``{ "Version": 2, "From": [...], "Where": [...] }``. The ``Where`` holds the
actual boolean condition as a QueryExpressionContainer (``In``, ``Comparison``,
``And``, ``Not`` ...).

This module deliberately replaces the previous flat ``{operator, timeUnitsCount}``
shape, which did not match any published PBIR schema and would be rejected by
Power BI Desktop as a blocking error.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

# QueryComparisonKind (semanticQuery schema)
COMPARISON_KIND = {"=": 0, "==": 0, ">": 1, ">=": 2, "<": 3, "<=": 4}

# TimeUnit (semanticQuery schema)
TIME_UNIT = {"Days": 0, "Weeks": 1, "Months": 2, "Years": 3, "Decades": 4,
             "Seconds": 5, "Minutes": 6, "Hours": 7}


def _alias(table: str) -> str:
    """Short query alias for a table, matching Desktop's style (e.g. 'f')."""
    first = next((c for c in table if c.isalpha()), "t")
    return first.lower()


def _filter_name() -> str:
    """A unique 20-char filter name, matching Desktop's id convention."""
    return uuid.uuid4().hex[:20]


def _source_ref(alias: str) -> dict[str, Any]:
    return {"SourceRef": {"Source": alias}}


def _column(alias: str, column: str) -> dict[str, Any]:
    return {"Column": {"Expression": _source_ref(alias), "Property": column}}


def _measure(alias: str, measure: str) -> dict[str, Any]:
    return {"Measure": {"Expression": _source_ref(alias), "Property": measure}}


def _string_literal(value: str) -> dict[str, Any]:
    # String literals are single-quoted inside the Value per the literal grammar.
    return {"Literal": {"Value": f"'{value}'"}}


def _num_literal(value: float | int) -> dict[str, Any]:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # Numbers use the 'D' (double) suffix in the literal grammar.
    return {"Literal": {"Value": f"{value}D"}}


def _container(
    *,
    name: str,
    field: dict[str, Any],
    filter_type: str,
    definition: dict[str, Any],
    locked: bool = False,
    hidden: bool = False,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Assemble a FilterContainer. ``howCreated='User'`` marks it as added by a
    user/tool against a field not necessarily on a visual (vs. 'Auto')."""
    container: dict[str, Any] = {
        "name": name,
        "field": field,
        "type": filter_type,
        "filter": definition,
        "howCreated": "User",
    }
    if display_name:
        container["displayName"] = display_name
    if locked:
        container["isLockedInViewMode"] = True
    if hidden:
        container["isHiddenInViewMode"] = True
    return container


# ── Public builders ─────────────────────────────────────────────────────────────


def build_value_filter(
    table: str,
    column: str,
    values: list[str],
    *,
    exclude: bool = False,
    locked: bool = False,
    hidden: bool = False,
) -> dict[str, Any]:
    """A categorical (value-in) filter: keep rows where ``column`` is in ``values``.

    With ``exclude=True`` the condition is negated (``Not In``) and the filter type
    becomes ``Exclude`` — the standard way Desktop records an exclusion filter.
    """
    if not values:
        raise ValueError("at least one value is required")
    alias = _alias(table)
    col = _column(alias, column)
    in_expr = {
        "In": {
            "Expressions": [col],
            "Values": [[_string_literal(v)] for v in values],
        }
    }
    condition = {"Not": {"Expression": in_expr}} if exclude else in_expr
    definition = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": table, "Type": 0}],
        "Where": [{"Condition": condition}],
    }
    return _container(
        name=_filter_name(),
        field=col,
        filter_type="Exclude" if exclude else "Categorical",
        definition=definition,
        locked=locked,
        hidden=hidden,
    )


def build_advanced_filter(
    table: str,
    column: str,
    conditions: list[tuple[str, float]],
    *,
    logic: str = "And",
    is_measure: bool = False,
    locked: bool = False,
    hidden: bool = False,
) -> dict[str, Any]:
    """An advanced numeric filter: one or two comparisons joined by And/Or.

    ``conditions`` is a list of ``(operator, threshold)`` where operator is one of
    ``= > >= < <=``. Power BI advanced filters allow up to two conditions; more
    than two raises ``ValueError``.
    """
    if not conditions:
        raise ValueError("at least one condition is required")
    if len(conditions) > 2:
        raise ValueError("advanced filters allow at most two conditions")
    if logic not in ("And", "Or"):
        raise ValueError("logic must be 'And' or 'Or'")

    alias = _alias(table)
    left = _measure(alias, column) if is_measure else _column(alias, column)

    def _cmp(op: str, threshold: float) -> dict[str, Any]:
        if op not in COMPARISON_KIND:
            raise ValueError(f"unknown operator '{op}'; use one of {sorted(COMPARISON_KIND)}")
        return {
            "Comparison": {
                "ComparisonKind": COMPARISON_KIND[op],
                "Left": left,
                "Right": _num_literal(threshold),
            }
        }

    comparisons = [_cmp(op, thr) for op, thr in conditions]
    condition = (
        comparisons[0]
        if len(comparisons) == 1
        else {logic: {"Left": comparisons[0], "Right": comparisons[1]}}
    )
    definition = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": table, "Type": 0}],
        "Where": [{"Condition": condition}],
    }
    return _container(
        name=_filter_name(),
        field=left,
        filter_type="Advanced",
        definition=definition,
        locked=locked,
        hidden=hidden,
    )


def build_relative_date_filter(
    table: str,
    column: str,
    last: int,
    unit: str = "Days",
    *,
    include_today: bool = True,
    locked: bool = False,
    hidden: bool = False,
) -> dict[str, Any]:
    """A relative-date filter keeping the last ``last`` ``unit`` up to now.

    PBIR expresses this as an advanced date range on the column::

        column >= DateAdd(Now(), -last, unit)   [ AND column <= Now() ]

    ``DateAdd``/``Now`` are first-class semantic-query expressions, so the result
    is a valid date-range condition. ``include_today=False`` adds the upper bound
    ``column < DateSpan(Now(), unit)`` to exclude the current period.
    """
    if last <= 0:
        raise ValueError("last must be a positive integer")
    if unit not in TIME_UNIT:
        raise ValueError(f"unit must be one of {sorted(TIME_UNIT)}")
    alias = _alias(table)
    col = _column(alias, column)
    unit_num = TIME_UNIT[unit]

    lower_bound = {
        "DateAdd": {
            "Amount": -last,
            "TimeUnit": unit_num,
            "Expression": {"Now": {}},
        }
    }
    ge = {
        "Comparison": {
            "ComparisonKind": COMPARISON_KIND[">="],
            "Left": col,
            "Right": lower_bound,
        }
    }
    if include_today:
        condition: dict[str, Any] = ge
    else:
        # Exclude the current period: column < start of this period.
        upper_bound = {"DateSpan": {"TimeUnit": unit_num, "Expression": {"Now": {}}}}
        lt = {
            "Comparison": {
                "ComparisonKind": COMPARISON_KIND["<"],
                "Left": col,
                "Right": upper_bound,
            }
        }
        condition = {"And": {"Left": ge, "Right": lt}}

    definition = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": table, "Type": 0}],
        "Where": [{"Condition": condition}],
    }
    return _container(
        name=_filter_name(),
        field=col,
        filter_type="RelativeDate",
        definition=definition,
        locked=locked,
        hidden=hidden,
    )


# ── filterConfig envelope helpers ───────────────────────────────────────────────
# NOTE: a `filterConfig` embedded in page.json / report.json / visual.json is the
# filterConfiguration schema *inlined by $ref*. Power BI Desktop's runtime
# validator rejects a `$schema` key inside this embedded object ("An additional
# property '$schema' was included in the /filterConfig property") — verified live
# 2026-06-22. Only standalone filter files would carry `$schema`. So the embedded
# object holds just `filters` (and optionally `filterSortOrder`).


def empty_filter_config() -> dict[str, Any]:
    """A fresh, empty embedded filterConfig object (no ``$schema`` — see note)."""
    return {"filters": []}


def add_filter(config: dict[str, Any] | None, filter_container: dict[str, Any]) -> dict[str, Any]:
    """Append ``filter_container`` to an embedded filterConfig, creating one if
    needed. Strips any stray ``$schema`` (Desktop rejects it here). Returns the
    (possibly new) config object."""
    cfg = config or empty_filter_config()
    cfg.pop("$schema", None)
    cfg.setdefault("filters", []).append(filter_container)
    return cfg


_NAME_RE = re.compile(r"^[\w-]+$")


def is_valid_name(name: str) -> bool:
    """PBIR object names must be word chars or hyphens (per the naming convention)."""
    return bool(name) and bool(_NAME_RE.match(name))
