"""Tests for the PBIR visual JSON builders, including old-PBIP serialisation."""

from __future__ import annotations

import json

from pbi_cli.intelligence import visual_builder as vb
from pbi_cli.intelligence.visual_builder import (
    AGG_AVG,
    AGG_SUM,
    FieldDef,
    VisualSpec,
    spec_to_old_pbip_container,
    spec_to_pbir_visual,
)

# ── FieldDef ────────────────────────────────────────────────────────────────


def test_fielddef_measure_expr_and_ref():
    f = FieldDef("Sales", "Revenue", is_measure=True)
    assert f.query_ref == "Sales.Revenue"
    expr = f.to_field_expr()
    assert expr["Measure"]["Property"] == "Revenue"
    assert expr["Measure"]["Expression"]["SourceRef"]["Entity"] == "Sales"


def test_fielddef_plain_column_expr():
    f = FieldDef("Sales", "Month", agg=None)
    assert f.query_ref == "Sales.Month"
    assert "Column" in f.to_field_expr()


def test_fielddef_aggregation_expr_and_ref():
    f = FieldDef("Sales", "Amount", agg=AGG_AVG)
    assert f.query_ref == "Avg(Sales[Amount])"
    agg = f.to_field_expr()["Aggregation"]
    assert agg["Function"] == AGG_AVG
    assert agg["Expression"]["Column"]["Property"] == "Amount"


def test_projection_shape():
    proj = FieldDef("Sales", "Amount", agg=AGG_SUM).to_projection()
    assert proj["queryRef"] == "Sum(Sales[Amount])"
    assert "field" in proj


# ── Builders with optional roles (exercise the branching) ───────────────────


def test_scatter_with_details_and_size():
    body = vb.build_scatter_chart(
        FieldDef("S", "x", agg=AGG_SUM),
        FieldDef("S", "y", agg=AGG_SUM),
        details=FieldDef("S", "d", agg=None),
        size=FieldDef("S", "z", agg=AGG_SUM),
    )
    roles = body["query"]["queryState"]
    assert set(roles) == {"X", "Y", "Details", "Size"}


def test_gauge_with_all_targets():
    body = vb.build_gauge(
        FieldDef("S", "v", agg=AGG_SUM),
        target=FieldDef("S", "t", is_measure=True),
        min_val=FieldDef("S", "mn", agg=AGG_SUM),
        max_val=FieldDef("S", "mx", agg=AGG_SUM),
    )
    assert set(body["query"]["queryState"]) == {"Y", "TargetValue", "MinValue", "MaxValue"}


def test_waterfall_with_breakdown():
    body = vb.build_waterfall(
        FieldDef("S", "c", agg=None),
        FieldDef("S", "v", agg=AGG_SUM),
        breakdown=FieldDef("S", "b", agg=None),
    )
    assert "Breakdown" in body["query"]["queryState"]


def test_matrix_with_columns():
    body = vb.build_matrix(
        rows=[FieldDef("S", "r", agg=None)],
        values=[FieldDef("S", "v", agg=AGG_SUM)],
        columns=[FieldDef("S", "c", agg=None)],
    )
    assert body["visualType"] == "pivotTable"
    assert set(body["query"]["queryState"]) == {"Rows", "Values", "Columns"}


def test_ribbon_with_series():
    body = vb.build_ribbon_chart(
        FieldDef("S", "c", agg=None),
        FieldDef("S", "v", agg=AGG_SUM),
        series=FieldDef("S", "s", agg=None),
    )
    assert "Series" in body["query"]["queryState"]


def test_simple_builders_smoke():
    f = FieldDef("S", "v", agg=AGG_SUM)
    c = FieldDef("S", "c", agg=None)
    assert vb.build_card(f)["visualType"] == "card"
    assert vb.build_donut_chart(c, f)["visualType"] == "donutChart"
    assert vb.build_pie_chart(c, f)["visualType"] == "pieChart"
    assert vb.build_treemap(c, f)["visualType"] == "treemap"
    assert vb.build_funnel(c, f)["visualType"] == "funnel"
    assert vb.build_line_chart(c, f)["visualType"] == "lineChart"
    assert vb.build_column_chart(c, f)["visualType"] == "columnChart"
    assert vb.build_table([c, f])["visualType"] == "tableEx"
    assert vb.build_multi_row_card([c, f])["visualType"] == "multiRowCard"
    assert vb.build_slicer(c)["visualType"] == "slicer"


def test_ai_and_nondata_visuals():
    a = FieldDef("S", "v", is_measure=True)
    d = [FieldDef("S", "d", agg=None)]
    assert vb.build_decomposition_tree(a, d)["visualType"] == "decompositionTreeVisual"
    assert vb.build_key_influencers(a, d)["visualType"] == "keyDrivers"
    assert vb.build_smart_narrative()["visualType"] == "narrativeVisual"
    assert vb.build_qna()["visualType"] == "qnaVisual"
    assert vb.build_page_navigator()["visualType"] == "pageNavigator"
    assert vb.build_bookmark_navigator()["visualType"] == "bookmarkNavigator"


def test_textbox_and_action_button_with_text():
    tb = vb.build_textbox("Hello")
    assert tb["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"] == (
        "Hello"
    )
    btn = vb.build_action_button(shape="back", text="Go back")
    assert btn["objects"]["icon"][0]["properties"]["shapeType"]["expr"]["Literal"]["Value"] == (
        "'back'"
    )
    assert btn["objects"]["text"][0]["properties"]["text"]["expr"]["Literal"]["Value"] == (
        "'Go back'"
    )


# ── Serialisation ────────────────────────────────────────────────────────────


def test_spec_to_pbir_visual_with_title():
    body = vb.build_card(FieldDef("S", "v", agg=AGG_SUM))
    spec = VisualSpec("card", body, x=10, y=20, width=100, height=80, title="KPI")
    out = spec_to_pbir_visual(spec)
    assert out["position"] == {"x": 10, "y": 20, "z": 0, "width": 100, "height": 80, "tabOrder": 0}
    title = out["visual"]["visualContainerObjects"]["title"][0]["properties"]
    assert title["text"]["expr"]["Literal"]["Value"] == "'KPI'"
    assert out["$schema"]  # schema URL set


def test_spec_to_old_pbip_container_covers_all_field_exprs():
    # Category = plain column, Y = aggregation, Tooltips = measure → all 3 branches.
    body = vb.build_bar_chart(
        FieldDef("Sales", "Month", agg=None),
        FieldDef("Sales", "Amount", agg=AGG_SUM),
    )
    body["query"]["queryState"]["Tooltips"] = {
        "projections": [FieldDef("Sales", "Revenue", is_measure=True).to_projection()]
    }
    spec = VisualSpec("barChart", body, title="Sales by Month")
    container = spec_to_old_pbip_container(spec)

    assert container["filters"] == "[]"
    config = json.loads(container["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "barChart"

    # From clause has a single alias for the one entity referenced.
    from_items = sv["prototypeQuery"]["From"]
    assert len(from_items) == 1
    assert from_items[0]["Entity"] == "Sales"

    # Select carries the column, aggregation and measure items.
    selects = sv["prototypeQuery"]["Select"]
    kinds = {next(iter(s)) for s in selects if isinstance(s, dict) and "Name" in s}
    assert {"Column", "Aggregation", "Measure"} <= kinds

    # Title injected into singleVisual.objects.
    assert "title" in sv["objects"]
