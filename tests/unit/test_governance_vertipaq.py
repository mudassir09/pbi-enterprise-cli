"""Unit tests for the VertiPaq statistics collector.

A fake backend stands in for a live (desktop/xmla) connection: it answers the
collector's batched ``EVALUATE ROW(...)`` and RI queries by reflecting back the
result-column names the collector asked for, with deterministic values.
"""

from __future__ import annotations

import re

import pytest

from pbi_cli.governance.bpa import BpaEvaluator, BpaRule
from pbi_cli.governance.vertipaq import VertiPaqStats, collect

_KEY_RE = re.compile(r'"([^"]+)"\s*,')


class FakeLiveBackend:
    """Minimal live-backend stand-in with a deterministic dax_query."""

    def __init__(self, tables, columns, relationships, *, row_count=1000, ri=0):
        self._tables = tables
        self._columns = columns
        self._relationships = relationships
        self._row_count = row_count
        self._ri = ri
        self.queries: list[str] = []

    def table_list(self):
        return self._tables

    def column_list(self):
        return self._columns

    def relationship_list(self):
        return self._relationships

    def measure_list(self):
        return []

    def partition_list(self, table=None):
        return []

    def dax_query(self, expr):
        self.queries.append(expr)
        keys = _KEY_RE.findall(expr)
        row = {}
        for k in keys:
            if k == "__rows":
                row[k] = self._row_count
            elif k == "__ri":
                row[k] = self._ri
            elif k.startswith("card_"):
                row[k] = 42
            elif k.startswith("dt_"):
                row[k] = 7
            elif k.startswith("ll_"):
                row[k] = 3
        return [row]


def _model(**kw):
    return FakeLiveBackend(
        tables=[{"name": "Sales"}, {"name": "Dates"}],
        columns=[
            {"table": "Sales", "name": "Amount", "dataType": "Double"},
            {"table": "Sales", "name": "Note", "dataType": "String"},
            {"table": "Dates", "name": "Date", "dataType": "DateTime"},
        ],
        relationships=[{"from": "Sales[Date]", "to": "Dates[Date]", "cardinality": "ManyToOne"}],
        **kw,
    )


class TestCollect:
    def test_row_counts_for_all_tables(self) -> None:
        stats = collect(_model(row_count=342086))
        assert stats.tables["Sales"]["Vertipaq_RowCount"] == "342086"
        assert stats.tables["Dates"]["Vertipaq_RowCount"] == "342086"

    def test_column_cardinality(self) -> None:
        stats = collect(_model())
        assert stats.columns[("Sales", "Amount")]["Vertipaq_Cardinality"] == "42"

    def test_datetime_stat_only_for_datetime_columns(self) -> None:
        stats = collect(_model())
        assert stats.columns[("Dates", "Date")]["DateTimeWithHourMinSec"] == "7"
        assert "DateTimeWithHourMinSec" not in stats.columns[("Sales", "Amount")]

    def test_longlength_stat_only_for_string_columns(self) -> None:
        stats = collect(_model())
        assert stats.columns[("Sales", "Note")]["LongLengthRowCount"] == "3"
        assert "LongLengthRowCount" not in stats.columns[("Sales", "Amount")]

    def test_ri_violation_count(self) -> None:
        stats = collect(_model(ri=5))
        assert stats.relationships[("Sales[Date]", "Dates[Date]")][
            "Vertipaq_RIViolationInvalidRows"
        ] == "5"

    def test_clean_ri_is_zero_not_missing(self) -> None:
        stats = collect(_model(ri=0))
        assert stats.relationships[("Sales[Date]", "Dates[Date]")][
            "Vertipaq_RIViolationInvalidRows"
        ] == "0"

    def test_non_live_backend_rejected(self) -> None:
        class Static:
            pass

        with pytest.raises(TypeError):
            collect(Static())

    def test_query_failure_is_tolerated(self) -> None:
        class Flaky(FakeLiveBackend):
            def dax_query(self, expr):
                raise RuntimeError("boom")

        stats = collect(
            Flaky(tables=[{"name": "T"}], columns=[], relationships=[])
        )
        assert stats.is_empty()


class TestEndToEndWithEvaluator:
    """Stats flow through BpaEvaluator so GetAnnotation rules evaluate."""

    def _rule(self) -> BpaRule:
        return BpaRule(
            id="LARGE_TABLES", name="Large tables should be partitioned",
            category="Performance", description="", severity=2, scope="Table",
            expression='Convert.ToInt64(GetAnnotation("Vertipaq_RowCount")) > 25000000',
        )

    def test_rule_skipped_without_vertipaq(self) -> None:
        v, skipped = BpaEvaluator().evaluate([self._rule()], _model())
        assert v == []
        assert skipped == 1

    def test_rule_evaluated_with_vertipaq(self) -> None:
        stats = collect(_model(row_count=30000000))
        v, skipped = BpaEvaluator().evaluate([self._rule()], _model(), vertipaq=stats)
        assert skipped == 0
        assert {x["object"] for x in v} == {"Sales", "Dates"}

    def test_rule_clean_with_small_tables(self) -> None:
        stats = collect(_model(row_count=100))
        v, skipped = BpaEvaluator().evaluate([self._rule()], _model(), vertipaq=stats)
        assert skipped == 0
        assert v == []


def test_vertipaq_stats_helpers() -> None:
    s = VertiPaqStats()
    assert s.is_empty()
    s.tables["T"] = {"Vertipaq_RowCount": "1"}
    assert not s.is_empty()
    assert s.annotation_count() == 1
