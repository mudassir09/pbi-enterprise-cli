"""Generate a self-contained PBIR demo project that opens in Power BI Desktop.

Produces a .pbip with:
  - an offline import semantic model (entered data via M #table, no data source)
  - a PBIR report exercising the new report-layer features:
      visual update, rule-based + font conditional formatting, color scale,
      visual interactions, slicer sync, and a state-capturing bookmark.

Run:  python scripts/make_demo_pbip.py "<output folder>"
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_bar_chart,
    build_card,
    build_line_chart,
    build_slicer,
    build_table,
)

NAME = "Sales Demo"
TABLE = "Financials"


def _platform(item_type: str, display: str) -> str:
    return json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
            "gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": item_type, "displayName": display},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
        },
        indent=2,
    )


def _data_rows() -> list[list]:
    countries = ["USA", "Canada", "France", "Germany"]
    segments = {"USA": "Enterprise", "Canada": "Midmarket", "France": "Government", "Germany": "Channel"}
    months = ["01-Jan", "02-Feb", "03-Mar", "04-Apr", "05-May", "06-Jun",
              "07-Jul", "08-Aug", "09-Sep", "10-Oct", "11-Nov", "12-Dec"]
    rows: list[list] = []
    for y, year in enumerate(["2023", "2024"]):
        for c, country in enumerate(countries):
            for m, month in enumerate(months):
                base = 4000 + c * 1500 + m * 350 + y * 2000
                sales = base + ((m * 7 + c * 13) % 9) * 220
                cogs = round(sales * (0.55 + 0.03 * c), 0)
                profit = round(sales - cogs, 0)
                units = 80 + c * 20 + m * 5 + y * 30
                rows.append([country, segments[country], year, month,
                             float(sales), float(profit), int(units), float(cogs)])
    return rows


def _m_table(rows: list[list]) -> str:
    def lit(v) -> str:
        return f'"{v}"' if isinstance(v, str) else (str(int(v)) if isinstance(v, int) else str(v))

    row_lines = ",\n\t\t\t\t\t".join(
        "{" + ", ".join(lit(v) for v in r) + "}" for r in rows
    )
    return (
        "let\n"
        "\t\t\t\tSource = #table(\n"
        "\t\t\t\t\ttype table [Country = text, Segment = text, Year = text, Month = text, "
        'Sales = number, Profit = number, #"Units Sold" = Int64.Type, COGS = number],\n'
        "\t\t\t\t\t{\n\t\t\t\t\t" + row_lines + "\n\t\t\t\t\t}\n"
        "\t\t\t\t)\n"
        "\t\t\tin\n"
        "\t\t\t\tSource"
    )


def write_model(root: Path) -> None:
    sm = root / f"{NAME}.SemanticModel"
    (sm / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    (sm / ".platform").write_text(_platform("SemanticModel", NAME), encoding="utf-8")
    (sm / "definition.pbism").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                "item/semanticModel/definitionProperties/1.0.0/schema.json",
                "version": "4.2",
                "settings": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (sm / "definition" / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1550\n", encoding="utf-8"
    )
    # NOTE: TMDL does NOT auto-discover tables — model.tmdl must explicitly
    # `ref table <name>` every table file, and `ref cultureInfo` every culture.
    (sm / "definition" / "model.tmdl").write_text(
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        '\tannotation PBI_QueryOrder = ["Financials"]\n\n'
        '\tannotation PBI_ProTooling = ["DevMode"]\n\n'
        "ref table Financials\n\n"
        "ref cultureInfo en-US\n",
        encoding="utf-8",
    )
    (sm / "definition" / "cultures").mkdir(parents=True, exist_ok=True)
    (sm / "definition" / "cultures" / "en-US.tmdl").write_text(
        "cultureInfo en-US\n", encoding="utf-8"
    )

    rows = _data_rows()
    cols = [
        ("Country", "string", "none"),
        ("Segment", "string", "none"),
        ("Year", "string", "none"),
        ("Month", "string", "none"),
        ("Sales", "double", "sum"),
        ("Profit", "double", "sum"),
        ("Units Sold", "int64", "sum"),
        ("COGS", "double", "sum"),
    ]
    parts = ["table Financials\n"]
    for cname, dtype, summ in cols:
        obj = f"'{cname}'" if " " in cname else cname
        parts.append(
            f"\n\tcolumn {obj}\n"
            f"\t\tdataType: {dtype}\n"
            f"\t\tsummarizeBy: {summ}\n"
            f"\t\tsourceColumn: {cname}\n"
        )
    parts.append(
        "\n\tmeasure 'Profit Margin %' = DIVIDE(SUM(Financials[Profit]), SUM(Financials[Sales]))\n"
        "\t\tformatString: 0.0%\n"
    )
    parts.append(
        "\n\tpartition Financials = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        "\t\t\t" + _m_table(rows) + "\n"
    )
    (sm / "definition" / "tables" / "Financials.tmdl").write_text(
        "".join(parts), encoding="utf-8"
    )


def write_report(root: Path) -> PbirBackend:
    rep = root / f"{NAME}.Report"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / ".platform").write_text(_platform("Report", NAME), encoding="utf-8")
    (rep / "definition.pbir").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                "item/report/definitionProperties/2.0.0/schema.json",
                "version": "4.0",
                "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Backend creates definition/ + report.json (PBIR GA) on load.
    b = PbirBackend(str(root))
    (rep / "definition" / "version.json").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                "item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return b


def col(prop: str) -> FieldDef:
    return FieldDef(entity=TABLE, property=prop, is_measure=False, agg=None)


def agg(prop: str) -> FieldDef:
    return FieldDef(entity=TABLE, property=prop, agg=AGG_SUM)


def build(b: PbirBackend) -> None:
    PAGE = "Overview"
    b.page_add(PAGE)
    G = 16
    names: dict[str, str] = {}

    # Row 1 — KPI cards
    for i, (prop, title) in enumerate(
        [("Sales", "Total Sales"), ("Profit", "Total Profit"), ("Units Sold", "Units Sold")]
    ):
        info = b.visual_add(
            PAGE,
            VisualSpec("card", build_card(agg(prop)), x=G + i * 296, y=G,
                       width=280, height=120, title=title),
        )
        names[prop] = info["name"]

    # Row 2 — bar (Sales by Country), slicer (Year), line (Sales by Month)
    y2 = 152
    bar = b.visual_add(
        PAGE, VisualSpec("barChart", build_bar_chart(col("Country"), agg("Sales")),
                         x=G, y=y2, width=560, height=320, title="Sales by Country"))
    slicer = b.visual_add(
        PAGE, VisualSpec("slicer", build_slicer(col("Year")),
                         x=592, y=y2, width=180, height=320, title="Year"))
    line = b.visual_add(
        PAGE, VisualSpec("lineChart", build_line_chart(col("Month"), agg("Sales")),
                         x=788, y=y2, width=476, height=320, title="Sales by Month"))

    # Row 3 — detail table
    table = b.visual_add(
        PAGE, VisualSpec("tableEx",
                         build_table([col("Country"), agg("Sales"), agg("Profit")]),
                         x=G, y=488, width=1248, height=216, title="Detail"))

    # ── Exercise the new features ──────────────────────────────────────────────
    # 1) visual update — reposition + retitle the Units card
    b.visual_update(PAGE, names["Units Sold"], width=280, title="Units Sold (YTD)")

    # 2) color scale on Sales + rule-based font colour on Profit (red if negative)
    b.visual_format_color_scale(PAGE, table["name"], TABLE, "Sales",
                                low_color="#FFF3B0", high_color="#2A9D8F", mid_color=None)
    b.visual_format_rules(PAGE, table["name"], TABLE, "Profit",
                          [(">=", 0, "#107C10"), ("<", 0, "#A4262C")], target="fontColor")

    # 3) interaction — Year slicer should NOT filter the Total Sales card
    b.set_visual_interaction(PAGE, slicer["name"], names["Sales"], "NoFilter")

    # 4) slicer sync group
    b.set_slicer_sync(PAGE, slicer["name"], "YearSync")

    # 5) bookmarks — full view, and a "focus" view with the bar chart hidden
    b.bookmark_add("Full View", page=PAGE)
    b.bookmark_add("Focus: hide bar", page=PAGE, hidden_visuals=[bar["name"]])


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Documents" / "pbi-cli-demo"
    root = out / NAME
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{NAME}.pbip").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                "pbip/pbipProperties/1.0.0/schema.json",
                "version": "1.0",
                "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                "settings": {"enableAutoRecovery": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_model(root)
    b = write_report(root)
    build(b)
    print(f"Created PBIP at: {root / (NAME + '.pbip')}")


if __name__ == "__main__":
    main()
