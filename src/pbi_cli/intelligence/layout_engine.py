"""Shelf-packing layout engine for Power BI visuals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VISUAL_SIZES = {
    "kpi": (200, 120),
    "card": (300, 130),
    "chart": (624, 240),
    "bar": (624, 240),
    "column": (624, 240),
    "line": (624, 240),
    "scatter": (624, 300),
    "gauge": (300, 200),
    "donut": (400, 280),
    "pie": (400, 280),
    "treemap": (624, 300),
    "funnel": (400, 300),
    "waterfall": (624, 300),
    "matrix": (900, 400),
    "ribbon": (624, 240),
    "table": (900, 400),
    "multirow": (624, 200),
    "slicer": (200, 56),
    "map": (624, 400),
    "stackedbar": (624, 240),
    "stackedcolumn": (624, 240),
    "100percentbar": (624, 240),
    "100percentcolumn": (624, 240),
    "area": (624, 240),
    "stackedarea": (624, 240),
    "combo": (624, 280),
    "bubble": (624, 300),
    "filledmap": (624, 400),
    "azuremap": (624, 400),
    "decomptree": (900, 500),
    "keyinfluencers": (900, 500),
    "smartnarrative": (624, 240),
    "qanda": (624, 300),
}

# Map Power BI internal visualType names → layout engine short names
_PBI_TYPE_TO_SHORT: dict[str, str] = {
    "card": "card",
    "kpiVisual": "kpi",
    "multiRowCard": "multirow",
    "barChart": "bar",
    "clusteredBarChart": "bar",
    "columnChart": "column",
    "clusteredColumnChart": "column",
    "stackedBarChart": "stackedbar",
    "stackedColumnChart": "stackedcolumn",
    "hundredPercentStackedBarChart": "100percentbar",
    "hundredPercentStackedColumnChart": "100percentcolumn",
    "lineChart": "line",
    "areaChart": "area",
    "stackedAreaChart": "stackedarea",
    "lineClusteredColumnComboChart": "combo",
    "lineStackedColumnComboChart": "combo",
    "scatterChart": "scatter",
    "pieChart": "pie",
    "donutChart": "donut",
    "gauge": "gauge",
    "waterfallChart": "waterfall",
    "funnel": "funnel",
    "ribbonChart": "ribbon",
    "treemap": "treemap",
    "tableEx": "table",
    "pivotTable": "matrix",
    "slicer": "slicer",
    "map": "map",
    "filledMap": "filledmap",
    "azureMap": "azuremap",
    "decompositionTreeVisual": "decomptree",
    "keyDrivers": "keyinfluencers",
    "narrativeVisual": "smartnarrative",
    "qnaVisual": "qanda",
}

PRIORITY_ORDER = [
    "kpi",
    "card",
    "gauge",
    "donut",
    "pie",
    "bar",
    "column",
    "line",
    "scatter",
    "waterfall",
    "funnel",
    "treemap",
    "ribbon",
    "chart",
    "slicer",
    "map",
    "multirow",
    "table",
    "matrix",
]


@dataclass
class VisualPosition:
    name: str
    visual_type: str
    x: int
    y: int
    width: int
    height: int


class LayoutEngine:
    """Classify visuals, sort by importance, pack onto canvas using shelf algorithm."""

    GUTTER = 8
    GRID = 8

    def __init__(self, canvas_width: int = 1280, canvas_height: int = 720) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

    def pack(self, visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        classified = self._classify(visuals)
        sorted_visuals = self._sort_by_priority(classified)
        positions = self._shelf_pack(sorted_visuals)
        return [
            {
                "name": p.name,
                "visualType": p.visual_type,
                "x": p.x,
                "y": p.y,
                "width": p.width,
                "height": p.height,
            }
            for p in positions
        ]

    def _classify(self, visuals: list[dict]) -> list[dict]:
        for v in visuals:
            # Accept both "type" (CLI shortname) and "visualType" (PBI internal name)
            raw = v.get("visualType") or v.get("type") or "chart"
            # Map PBI internal name → short name; already-short names pass through
            vtype = _PBI_TYPE_TO_SHORT.get(raw, raw.lower())
            w, h = VISUAL_SIZES.get(vtype, VISUAL_SIZES["chart"])
            v["_short_type"] = vtype
            v["_width"] = w
            v["_height"] = h
            v["_priority"] = PRIORITY_ORDER.index(vtype) if vtype in PRIORITY_ORDER else 99
        return visuals

    def _sort_by_priority(self, visuals: list[dict]) -> list[dict]:
        return sorted(visuals, key=lambda v: v.get("_priority", 99))

    def _shelf_pack(self, visuals: list[dict]) -> list[VisualPosition]:
        positions: list[VisualPosition] = []
        x, y = self.GUTTER, self.GUTTER
        row_height = 0

        for v in visuals:
            w = self._snap(v.get("_width", 200))
            h = self._snap(v.get("_height", 120))

            # Wrap to next row if we'd exceed canvas width
            if x + w + self.GUTTER > self.canvas_width:
                x = self.GUTTER
                y += row_height + self.GUTTER
                row_height = 0

            # Skip visuals that would overflow the canvas height
            if y + h > self.canvas_height:
                break

            positions.append(
                VisualPosition(
                    name=v.get("name", "visual"),
                    visual_type=v.get("_short_type", v.get("visualType", v.get("type", "chart"))),
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                )
            )
            x += w + self.GUTTER
            row_height = max(row_height, h)

        return positions

    def _snap(self, value: int) -> int:
        return ((value + self.GRID - 1) // self.GRID) * self.GRID
