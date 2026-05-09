"""Shelf-packing layout engine for Power BI visuals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VISUAL_SIZES = {
    "kpi":       (200, 120),
    "card":      (300, 130),
    "chart":     (624, 240),
    "bar":       (624, 240),
    "column":    (624, 240),
    "line":      (624, 240),
    "scatter":   (624, 300),
    "gauge":     (300, 200),
    "donut":     (400, 280),
    "pie":       (400, 280),
    "treemap":   (624, 300),
    "funnel":    (400, 300),
    "waterfall": (624, 300),
    "matrix":    (900, 400),
    "ribbon":    (624, 240),
    "table":     (900, 400),
    "multirow":  (624, 200),
    "slicer":    (200,  56),
    "map":       (624, 400),
    "stackedbar":   (624, 240),
    "stackedcolumn":(624, 240),
    "100percentbar":(624, 240),
    "100percentcolumn": (624, 240),
    "area":         (624, 240),
    "stackedarea":  (624, 240),
    "combo":        (624, 280),
    "bubble":       (624, 300),
    "filledmap":    (624, 400),
    "azuremap":     (624, 400),
    "decomptree":   (900, 500),
    "keyinfluencers":(900, 500),
    "smartnarrative":(624, 240),
    "qanda":        (624, 300),
}

PRIORITY_ORDER = [
    "kpi", "card",
    "gauge", "donut", "pie",
    "bar", "column", "line", "scatter", "waterfall", "funnel", "treemap", "ribbon", "chart",
    "slicer",
    "map", "multirow", "table", "matrix",
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
            vtype = v.get("type", "chart").lower()
            w, h = VISUAL_SIZES.get(vtype, VISUAL_SIZES["chart"])
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

            if x + w + self.GUTTER > self.canvas_width:
                x = self.GUTTER
                y += row_height + self.GUTTER
                row_height = 0

            positions.append(VisualPosition(
                name=v.get("name", "visual"),
                visual_type=v.get("type", "chart"),
                x=x, y=y, width=w, height=h,
            ))
            x += w + self.GUTTER
            row_height = max(row_height, h)

        return positions

    def _snap(self, value: int) -> int:
        return ((value + self.GRID - 1) // self.GRID) * self.GRID
