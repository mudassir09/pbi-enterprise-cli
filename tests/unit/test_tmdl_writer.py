"""Tests for the pure-Python TMDL serializer (tmdl_writer) and the lossless
structural write-back it powers in the file backend.

The serializer's contract is round-trip fidelity: text it emits must parse back
into the same logical object, and an *edit* must preserve every untouched
detail (lineageTag, annotations, description) of the object it rewrites.
"""

from __future__ import annotations

from pbi_cli.backends.file_backend import FileBackend, parse_tmdl
from pbi_cli.tmdl_writer import (
    find_block_span,
    render_column,
    render_measure,
    render_partition,
    render_relationship,
    render_role,
    render_table,
)


class TestRenderRoundTrip:
    def test_measure_inline(self):
        text = render_measure(
            {"name": "Total Revenue", "expression": "SUM(Sales[Revenue])",
             "formatString": "#,0.00", "displayFolder": "KPIs"}
        )
        node = parse_tmdl(text)[0]
        assert node.keyword == "measure" and node.name == "Total Revenue"
        assert node.expression == "SUM(Sales[Revenue])"
        assert node.props["formatString"] == "#,0.00"
        assert node.props["displayFolder"] == "KPIs"

    def test_measure_multiline_and_description(self):
        text = render_measure(
            {"name": "Revenue YTD",
             "expression": "TOTALYTD(\n[Total Revenue],\n'Calendar'[Date]\n)",
             "description": "Year-to-date revenue"}
        )
        # Description renders as /// comment lines, never a `description:` property.
        assert "/// Year-to-date revenue" in text
        assert "description:" not in text
        node = parse_tmdl(text)[0]
        assert node.description == "Year-to-date revenue"
        assert "TOTALYTD(" in node.expression and "'Calendar'[Date]" in node.expression

    def test_calculated_column_has_no_source_column(self):
        text = render_column(
            {"name": "Margin", "expression": "[Revenue] - [Cost]", "dataType": "decimal",
             "sourceColumn": "ignored"}
        )
        assert "sourceColumn" not in text
        node = parse_tmdl(text)[0]
        assert node.expression == "[Revenue] - [Cost]"

    def test_data_column_round_trip(self):
        text = render_column(
            {"name": "Units Sold", "dataType": "int64", "isHidden": True,
             "summarizeBy": "sum", "sourceColumn": "Units Sold"}
        )
        node = parse_tmdl(text)[0]
        assert node.name == "Units Sold"
        assert node.props["isHidden"] == "true"
        assert node.props["summarizeBy"] == "sum"

    def test_partition_multiline_m(self):
        text = render_partition(
            {"name": "Sales", "kind": "m",
             "source": 'let\nSource = Sql.Database("srv", "db")\nin\nSource'}
        )
        node = parse_tmdl(text)[0]
        assert node.keyword == "partition"
        assert "Sql.Database" in node.expression

    def test_relationship_quotes_table_with_spaces(self):
        text = render_relationship(
            {"name": "rel1", "fromTable": "Sales", "fromColumn": "ProductKey",
             "toTable": "Product Catalog", "toColumn": "ProductKey", "isActive": False}
        )
        assert "fromColumn: Sales.ProductKey" in text
        assert "toColumn: 'Product Catalog'.ProductKey" in text
        assert "isActive: false" in text

    def test_role_round_trip(self):
        text = render_role(
            {"name": "Regional", "modelPermission": "read",
             "tablePermissions": [{"table": "Sales", "filterExpression": 'Sales[Region] = "West"'}]}
        )
        node = parse_tmdl(text)[0]
        assert node.keyword == "role"
        tp = next(c for c in node.children if c.keyword == "tablePermission")
        assert tp.expression == 'Sales[Region] = "West"'

    def test_table_with_children_round_trips(self):
        text = render_table({
            "name": "Sales", "description": "Fact table",
            "columns": [{"name": "Revenue", "dataType": "decimal", "sourceColumn": "Revenue"}],
            "measures": [{"name": "Total", "expression": "SUM(Sales[Revenue])"}],
        })
        table = parse_tmdl(text)[0]
        assert table.description == "Fact table"
        assert {c.name for c in table.children if c.keyword == "column"} == {"Revenue"}
        assert {m.name for m in table.children if m.keyword == "measure"} == {"Total"}


class TestFindBlockSpan:
    SRC = (
        "table Sales\n"
        "\tcolumn A\n\t\tdataType: int64\n"
        "\t/// keep me\n"
        "\tmeasure 'My M' = SUM(Sales[A])\n\t\tformatString: 0\n"
        "\tcolumn B\n\t\tdataType: int64\n"
    ).splitlines()

    def test_finds_quoted_measure_with_description(self):
        span = find_block_span(self.SRC, "measure", "My M")
        assert span is not None
        start, end = span
        # The /// description line above is absorbed into the span.
        assert self.SRC[start].strip() == "/// keep me"
        assert "formatString: 0" in self.SRC[end - 1]

    def test_finds_bare_column(self):
        span = find_block_span(self.SRC, "column", "A")
        assert span is not None
        start, end = span
        assert self.SRC[start].strip() == "column A"

    def test_missing_returns_none(self):
        assert find_block_span(self.SRC, "measure", "Nope") is None


# --- Lossless update preservation (the headline guarantee) ---

TABLE_WITH_METADATA = """\
table Sales

\tmeasure 'Total Revenue' = SUM(Sales[Revenue])
\t\tformatString: #,0.00
\t\tlineageTag: abc-123-def

\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}

\tcolumn Revenue
\t\tdataType: decimal
\t\tsourceColumn: Revenue
"""


def _project(tmp_path, table_text=TABLE_WITH_METADATA):
    d = tmp_path / "Demo.SemanticModel" / "definition"
    (d / "tables").mkdir(parents=True)
    (d / "model.tmdl").write_text("model Model\n\tculture: en-US\n\nref table Sales\n",
                                  encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n", encoding="utf-8")
    (d / "tables" / "Sales.tmdl").write_text(table_text, encoding="utf-8")
    return tmp_path


class TestLosslessUpdate:
    def test_measure_update_preserves_lineage_and_annotation(self, tmp_path):
        proj = _project(tmp_path)
        b = FileBackend(path=proj)
        b.measure_update("Sales", "Total Revenue", expression="SUMX(Sales, Sales[Revenue])")
        text = (proj / "Demo.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(
            encoding="utf-8"
        )
        assert "SUMX(Sales, Sales[Revenue])" in text
        # lineageTag and annotation must survive the rewrite.
        assert "lineageTag: abc-123-def" in text
        assert 'annotation PBI_FormatHint = {"isGeneralNumber":true}' in text
        # formatString (not changed) is retained.
        assert "formatString: #,0.00" in text

    def test_measure_update_format_only_keeps_expression(self, tmp_path):
        proj = _project(tmp_path)
        b = FileBackend(path=proj)
        b.measure_update("Sales", "Total Revenue", formatString="0.0%")
        m = next(x for x in FileBackend(path=proj).measure_list("Sales")
                 if x["name"] == "Total Revenue")
        assert m["expression"] == "SUM(Sales[Revenue])"
        assert m["formatString"] == "0.0%"

    def test_measure_delete_leaves_sibling_column(self, tmp_path):
        proj = _project(tmp_path)
        b = FileBackend(path=proj)
        b.measure_delete("Sales", "Total Revenue")
        b2 = FileBackend(path=proj)
        assert not b2.measure_list("Sales")
        assert any(c["name"] == "Revenue" for c in b2.column_list("Sales"))
