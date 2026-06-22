"""Scaffold a complete, openable PBIP project from scratch.

Produces a .pbip with an offline import semantic model (entered data via an M
#table — no external data source) and a starter PBIR report. The model is
written with the `ref table` / `ref cultureInfo` lines that Power BI Desktop
requires (TMDL does not auto-discover table files), so the project opens cleanly.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pbi_cli.backends import pbir_schemas as _schemas
from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import (
    AGG_SUM,
    FieldDef,
    VisualSpec,
    build_bar_chart,
    build_card,
    build_line_chart,
    build_table,
)
from pbi_cli.tmdl_util import ensure_ref_culture, ensure_ref_table

# Default sample schema: (column, tmdl dtype, summarizeBy)
_COLUMNS = [
    ("Country", "string", "none"),
    ("Segment", "string", "none"),
    ("Year", "string", "none"),
    ("Month", "string", "none"),
    ("Sales", "double", "sum"),
    ("Profit", "double", "sum"),
    ("Units Sold", "int64", "sum"),
    ("COGS", "double", "sum"),
]


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


def _sample_rows() -> list[list[Any]]:
    countries = ["USA", "Canada", "France", "Germany"]
    segments = {"USA": "Enterprise", "Canada": "Midmarket",
                "France": "Government", "Germany": "Channel"}
    months = ["01-Jan", "02-Feb", "03-Mar", "04-Apr", "05-May", "06-Jun",
              "07-Jul", "08-Aug", "09-Sep", "10-Oct", "11-Nov", "12-Dec"]
    rows: list[list[Any]] = []
    for y, year in enumerate(["2023", "2024"]):
        for c, country in enumerate(countries):
            for m, month in enumerate(months):
                base = 4000 + c * 1500 + m * 350 + y * 2000
                sales = base + ((m * 7 + c * 13) % 9) * 220
                cogs = round(sales * (0.55 + 0.03 * c), 0)
                rows.append([country, segments[country], year, month,
                             float(sales), float(sales - cogs),
                             80 + c * 20 + m * 5 + y * 30, float(cogs)])
    return rows


def _m_table(rows: list[list[Any]]) -> str:
    def lit(v: Any) -> str:
        if isinstance(v, str):
            return f'"{v}"'
        return str(int(v)) if isinstance(v, int) else str(v)

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


def _write_model(root: Path, name: str, table: str) -> None:
    sm = root / f"{name}.SemanticModel"
    (sm / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    (sm / "definition" / "cultures").mkdir(parents=True, exist_ok=True)
    (sm / ".platform").write_text(_platform("SemanticModel", name), encoding="utf-8")
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
    # TMDL requires explicit ref table / ref cultureInfo lines — Desktop will not
    # auto-discover table files. Omitting them yields a model with no tables, so
    # the references are added via the shared, idempotent tmdl_util helpers.
    model_tmdl = sm / "definition" / "model.tmdl"
    model_tmdl.write_text(
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        f'\tannotation PBI_QueryOrder = ["{table}"]\n\n'
        '\tannotation PBI_ProTooling = ["DevMode"]\n',
        encoding="utf-8",
    )
    ensure_ref_table(model_tmdl, table)
    ensure_ref_culture(model_tmdl, "en-US")
    (sm / "definition" / "cultures" / "en-US.tmdl").write_text(
        "cultureInfo en-US\n", encoding="utf-8"
    )

    parts = [f"table {table}\n"]
    for cname, dtype, summ in _COLUMNS:
        obj = f"'{cname}'" if " " in cname else cname
        parts.append(
            f"\n\tcolumn {obj}\n\t\tdataType: {dtype}\n"
            f"\t\tsummarizeBy: {summ}\n\t\tsourceColumn: {cname}\n"
        )
    parts.append(
        f"\n\tmeasure 'Profit Margin %' = "
        f"DIVIDE(SUM({table}[Profit]), SUM({table}[Sales]))\n\t\tformatString: 0.0%\n"
    )
    parts.append(
        f"\n\tpartition {table} = m\n\t\tmode: import\n\t\tsource =\n"
        "\t\t\t" + _m_table(_sample_rows()) + "\n"
    )
    (sm / "definition" / "tables" / f"{table}.tmdl").write_text("".join(parts), encoding="utf-8")


def _write_report(root: Path, name: str, table: str) -> PbirBackend:
    rep = root / f"{name}.Report"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / ".platform").write_text(_platform("Report", name), encoding="utf-8")
    (rep / "definition.pbir").write_text(
        json.dumps(
            {
                "$schema": _schemas.item_schema("definitionProperties"),
                "version": "4.0",
                "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    b = PbirBackend(str(root))  # creates definition/ + report.json (PBIR GA)
    (rep / "definition" / "version.json").write_text(
        json.dumps(
            {
                "$schema": _schemas.definition_schema("versionMetadata"),
                "version": "2.0.0",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return b


def _build_report(b: PbirBackend, table: str) -> None:
    def col(p: str) -> FieldDef:
        return FieldDef(entity=table, property=p, is_measure=False, agg=None)

    def agg(p: str) -> FieldDef:
        return FieldDef(entity=table, property=p, agg=AGG_SUM)

    page = "Overview"
    b.page_add(page)
    for i, (prop, title) in enumerate([("Sales", "Total Sales"), ("Profit", "Total Profit")]):
        b.visual_add(page, VisualSpec("card", build_card(agg(prop)),
                                      x=16 + i * 296, y=16, width=280, height=120, title=title))
    b.visual_add(page, VisualSpec("barChart", build_bar_chart(col("Country"), agg("Sales")),
                                  x=16, y=152, width=600, height=320, title="Sales by Country"))
    b.visual_add(page, VisualSpec("lineChart", build_line_chart(col("Month"), agg("Sales")),
                                  x=632, y=152, width=632, height=320, title="Sales by Month"))
    b.visual_add(page, VisualSpec(
        "tableEx", build_table([col("Country"), agg("Sales"), agg("Profit")]),
        x=16, y=488, width=1248, height=216, title="Detail"))


def create_project(
    out_dir: str | Path, name: str = "New Report", table: str = "Financials"
) -> Path:
    """Create an openable PBIP under out_dir/<name>/ and return the .pbip path."""
    root = Path(out_dir) / name
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.pbip").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                "pbip/pbipProperties/1.0.0/schema.json",
                "version": "1.0",
                "artifacts": [{"report": {"path": f"{name}.Report"}}],
                "settings": {"enableAutoRecovery": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_model(root, name, table)
    b = _write_report(root, name, table)
    _build_report(b, table)
    return root / f"{name}.pbip"
