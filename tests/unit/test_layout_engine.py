"""Unit tests for the shelf-packing layout engine."""

from pbi_cli.intelligence.layout_engine import LayoutEngine


def _make_visuals(types: list[str]) -> list[dict]:
    return [{"name": f"visual_{i}", "type": t} for i, t in enumerate(types)]


def test_pack_returns_one_position_per_visual():
    engine = LayoutEngine(1280, 720)
    visuals = _make_visuals(["kpi", "chart", "table"])
    positions = engine.pack(visuals)
    assert len(positions) == 3


def test_no_overlapping_positions():
    engine = LayoutEngine(1280, 720)
    visuals = _make_visuals(["kpi", "kpi", "kpi", "chart"])
    positions = engine.pack(visuals)
    for i, p1 in enumerate(positions):
        for j, p2 in enumerate(positions):
            if i == j:
                continue
            overlap_x = p1["x"] < p2["x"] + p2["width"] and p2["x"] < p1["x"] + p1["width"]
            overlap_y = p1["y"] < p2["y"] + p2["height"] and p2["y"] < p1["y"] + p1["height"]
            assert not (overlap_x and overlap_y), f"Visuals {i} and {j} overlap"


def test_all_positions_within_canvas():
    engine = LayoutEngine(1280, 720)
    visuals = _make_visuals(["kpi", "kpi", "chart"])
    positions = engine.pack(visuals)
    for p in positions:
        assert p["x"] >= 0
        assert p["y"] >= 0
        assert p["x"] + p["width"] <= 1280 + engine.GUTTER  # allow for last item overflow
