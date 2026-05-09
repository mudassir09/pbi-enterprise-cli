"""Build Power BI PBIR GA visual JSON blobs.

Schema reference:
  visualContainer: https://developer.microsoft.com/json-schemas/fabric/item/
                   report/definition/visualContainer/2.7.0/schema.json
  visualConfiguration (embedded inside "visual" key):
    - visualType, query, objects, visualContainerObjects
  query.queryState:
    - keys are visual-role names (e.g. Category, Y, Values)
    - each role has a "projections" array
    - each projection: { "field": <QueryExpressionContainer>, "queryRef": str }
  Field expressions:
    - Measure:     {"Measure":     {"Expression": {"SourceRef": {"Entity": tbl}}, "Property": prop}}
    - Column:      {"Column":      {"Expression": {"SourceRef": {"Entity": tbl}}, "Property": prop}}
    - Aggregation: {"Aggregation": {"Expression": {"Column": {...}}, "Function": 0}}
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

AGG_SUM = 0
AGG_AVG = 1
AGG_MIN = 2
AGG_MAX = 3
AGG_COUNT = 4
AGG_NAMES = {AGG_SUM: "Sum", AGG_AVG: "Avg", AGG_MIN: "Min", AGG_MAX: "Max", AGG_COUNT: "Count"}

VISUAL_CONTAINER_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "visualContainer/2.7.0/schema.json"
)


@dataclass
class FieldDef:
    """One field to bind to a visual role slot."""

    entity: str  # table name, e.g. "financials"
    property: str  # column or measure name, e.g. "Sales"
    is_measure: bool = False  # True = explicit DAX measure
    agg: int | None = AGG_SUM  # None = no aggregation (plain column)

    @property  # type: ignore[operator]
    def query_ref(self) -> str:
        """Unique queryRef string for this field within a visual."""
        if self.is_measure or self.agg is None:
            return f"{self.entity}.{self.property}"
        agg_name = AGG_NAMES.get(self.agg, "Sum")
        return f"{agg_name}({self.entity}[{self.property}])"

    def to_field_expr(self) -> dict[str, Any]:
        """Build the QueryExpressionContainer for this field."""
        src = {"SourceRef": {"Entity": self.entity}}
        if self.is_measure:
            return {"Measure": {"Expression": src, "Property": self.property}}
        if self.agg is None:
            return {"Column": {"Expression": src, "Property": self.property}}
        return {
            "Aggregation": {
                "Expression": {"Column": {"Expression": src, "Property": self.property}},
                "Function": self.agg,
            }
        }

    def to_projection(self) -> dict[str, Any]:
        """Build a projection entry for query.queryState.{role}.projections."""
        return {"field": self.to_field_expr(), "queryRef": self.query_ref}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _query_state(roles: dict[str, list[FieldDef]]) -> dict[str, Any]:
    """Build query.queryState from a role-name → FieldDef list mapping."""
    return {
        role: {"projections": [f.to_projection() for f in fields]}
        for role, fields in roles.items()
        if fields
    }


# ── Visual body builders ───────────────────────────────────────────────────────


def build_card(value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "card",
        "query": {"queryState": _query_state({"Values": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_bar_chart(category: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "barChart",
        "query": {"queryState": _query_state({"Category": [category], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_column_chart(category: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "columnChart",
        "query": {"queryState": _query_state({"Category": [category], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_line_chart(axis: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "lineChart",
        "query": {"queryState": _query_state({"Category": [axis], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_slicer(value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "slicer",
        "query": {"queryState": _query_state({"Values": [value]})},
        "objects": {
            "data": [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Basic'"}}}}}]
        },
        "visualContainerObjects": {},
    }


def build_table(columns: list[FieldDef]) -> dict[str, Any]:
    return {
        "visualType": "tableEx",
        "query": {"queryState": _query_state({"Values": columns})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_multi_row_card(fields: list[FieldDef]) -> dict[str, Any]:
    return {
        "visualType": "multiRowCard",
        "query": {"queryState": _query_state({"Values": fields})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_scatter_chart(
    x_axis: FieldDef,
    y_axis: FieldDef,
    details: FieldDef | None = None,
    size: FieldDef | None = None,
) -> dict[str, Any]:
    roles: dict[str, list[FieldDef]] = {"X": [x_axis], "Y": [y_axis]}
    if details:
        roles["Details"] = [details]
    if size:
        roles["Size"] = [size]
    return {
        "visualType": "scatterChart",
        "query": {"queryState": _query_state(roles)},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_gauge(
    value: FieldDef,
    target: FieldDef | None = None,
    min_val: FieldDef | None = None,
    max_val: FieldDef | None = None,
) -> dict[str, Any]:
    roles: dict[str, list[FieldDef]] = {"Y": [value]}
    if target:
        roles["TargetValue"] = [target]
    if min_val:
        roles["MinValue"] = [min_val]
    if max_val:
        roles["MaxValue"] = [max_val]
    return {
        "visualType": "gauge",
        "query": {"queryState": _query_state(roles)},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_donut_chart(category: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "donutChart",
        "query": {"queryState": _query_state({"Category": [category], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_pie_chart(category: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "pieChart",
        "query": {"queryState": _query_state({"Category": [category], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_treemap(group: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "treemap",
        "query": {"queryState": _query_state({"Group": [group], "Values": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_funnel(category: FieldDef, value: FieldDef) -> dict[str, Any]:
    return {
        "visualType": "funnel",
        "query": {"queryState": _query_state({"Category": [category], "Y": [value]})},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_waterfall(
    category: FieldDef, value: FieldDef, breakdown: FieldDef | None = None
) -> dict[str, Any]:
    roles: dict[str, list[FieldDef]] = {"Category": [category], "Y": [value]}
    if breakdown:
        roles["Breakdown"] = [breakdown]
    return {
        "visualType": "waterfallChart",
        "query": {"queryState": _query_state(roles)},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_matrix(
    rows: list[FieldDef], values: list[FieldDef], columns: list[FieldDef] | None = None
) -> dict[str, Any]:
    roles: dict[str, list[FieldDef]] = {"Rows": rows, "Values": values}
    if columns:
        roles["Columns"] = columns
    return {
        "visualType": "pivotTable",
        "query": {"queryState": _query_state(roles)},
        "objects": {},
        "visualContainerObjects": {},
    }


def build_ribbon_chart(
    category: FieldDef, value: FieldDef, series: FieldDef | None = None
) -> dict[str, Any]:
    roles: dict[str, list[FieldDef]] = {"Category": [category], "Y": [value]}
    if series:
        roles["Series"] = [series]
    return {
        "visualType": "ribbonChart",
        "query": {"queryState": _query_state(roles)},
        "objects": {},
        "visualContainerObjects": {},
    }


# ── VisualSpec and serialisation ───────────────────────────────────────────────


@dataclass
class VisualSpec:
    visual_type: str
    visual_body: dict[str, Any]
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 200
    tab_order: int = 0
    name: str = field(default_factory=_new_id)
    title: str = ""


def spec_to_pbir_visual(spec: VisualSpec) -> dict[str, Any]:
    """Produce the visual.json dict for PBIR GA format."""
    body = dict(spec.visual_body)  # shallow copy

    if spec.title:
        body.setdefault("visualContainerObjects", {})
        body["visualContainerObjects"]["title"] = [
            {
                "properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{spec.title}'"}}},
                }
            }
        ]

    return {
        "$schema": VISUAL_CONTAINER_SCHEMA,
        "name": spec.name,
        "position": {
            "x": spec.x,
            "y": spec.y,
            "z": 0,
            "width": spec.width,
            "height": spec.height,
            "tabOrder": spec.tab_order,
        },
        "visual": body,
    }


def spec_to_old_pbip_container(spec: VisualSpec) -> dict[str, Any]:
    """Produce a visualContainer for old single-file PBIP report.json."""
    import json as _json

    # Old format still uses projections/prototypeQuery inside singleVisual config
    body = spec.visual_body
    qs = body.get("query", {}).get("queryState", {})

    projections: dict[str, Any] = {}
    select_items = []
    from_aliases: dict[str, str] = {}

    for role, role_data in qs.items():
        role_projs = []
        for proj in role_data.get("projections", []):
            qr = proj["queryRef"]
            role_projs.append({"queryRef": qr})
            fe = proj["field"]
            select_item, alias = _field_expr_to_select(fe, from_aliases)
            select_item["Name"] = qr
            select_items.append(select_item)
        projections[role] = role_projs

    from_items = [
        {"Name": alias, "Entity": entity, "Type": 0} for entity, alias in from_aliases.items()
    ]

    config = {
        "name": spec.name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": spec.x,
                    "y": spec.y,
                    "z": 0,
                    "width": spec.width,
                    "height": spec.height,
                    "tabOrder": spec.tab_order,
                },
            }
        ],
        "singleVisual": {
            "visualType": body.get("visualType", spec.visual_type),
            "projections": projections,
            "prototypeQuery": {"Version": 2, "From": from_items, "Select": select_items},
            "columnProperties": {},
            "objects": body.get("objects", {}),
            "vcObjects": {},
        },
    }
    if spec.title:
        config["singleVisual"]["objects"].setdefault(  # type: ignore[index]
            "title",
            [
                {
                    "properties": {
                        "show": {"expr": {"Literal": {"Value": "true"}}},
                        "text": {"expr": {"Literal": {"Value": f"'{spec.title}'"}}},
                    }
                }
            ],
        )

    return {
        "x": spec.x,
        "y": spec.y,
        "z": 0,
        "width": spec.width,
        "height": spec.height,
        "config": _json.dumps(config, separators=(",", ":")),
        "filters": "[]",
        "tabOrder": spec.tab_order,
    }


def _field_expr_to_select(
    fe: dict[str, Any],
    from_aliases: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """Convert a PBIR GA field expression to an old-format SELECT item."""

    def _alias(entity: str) -> str:
        if entity not in from_aliases:
            from_aliases[entity] = entity[0].lower() + str(len(from_aliases))
        return from_aliases[entity]

    if "Measure" in fe:
        m = fe["Measure"]
        entity = m["Expression"]["SourceRef"]["Entity"]
        alias = _alias(entity)
        src = {"SourceRef": {"Name": alias}}
        return {"Measure": {"Expression": src, "Property": m["Property"]}}, alias

    if "Column" in fe:
        c = fe["Column"]
        entity = c["Expression"]["SourceRef"]["Entity"]
        alias = _alias(entity)
        src = {"SourceRef": {"Name": alias}}
        return {"Column": {"Expression": src, "Property": c["Property"]}}, alias

    if "Aggregation" in fe:
        a = fe["Aggregation"]
        inner, alias = _field_expr_to_select(a["Expression"], from_aliases)
        return {
            "Aggregation": {
                "Expression": inner["Column"] if "Column" in inner else inner,
                "Function": a["Function"],
            }
        }, alias

    return fe, ""
