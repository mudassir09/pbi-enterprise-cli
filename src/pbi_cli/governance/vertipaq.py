"""VertiPaq statistics collector for live (desktop / xmla) backends.

The Best Practice Analyzer community ruleset has rules that depend on *runtime*
statistics — row counts, column cardinality, RI violations — which only exist
once a model is processed and loaded into the VertiPaq engine. A static TMDL
read cannot produce them. This module queries a connected model (via the
backend's ``dax_query`` primitive, which runs both DAX and DMV statements) and
returns the per-object annotations those rules read through ``GetAnnotation``:

* ``Vertipaq_RowCount``              — table     (DAX ``COUNTROWS``)
* ``Vertipaq_Cardinality``          — column    (DAX ``DISTINCTCOUNT``)
* ``DateTimeWithHourMinSec``         — column    (DateTime values carrying a time part)
* ``LongLengthRowCount``            — column    (string values longer than 100 chars)
* ``Vertipaq_RIViolationInvalidRows`` — relationship (best-effort; orphan fact rows)

One batched DAX query per table keeps round-trips to O(#tables). Values are
returned as strings, matching how Tabular Editor stores annotations and how the
rules consume them (``Convert.ToInt64(GetAnnotation(...))``).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# Rows whose string length exceeds this are counted for LongLengthRowCount.
# Matches Tabular Editor's VertiPaq Analyzer convention.
_LONG_LENGTH_THRESHOLD = 100


class VertiPaqStats:
    """Collected annotations, keyed for lookup when building the BPA context."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, str]] = {}
        self.columns: dict[tuple[str, str], dict[str, str]] = {}
        self.relationships: dict[tuple[str, str], dict[str, str]] = {}

    def is_empty(self) -> bool:
        return not (self.tables or self.columns or self.relationships)

    def annotation_count(self) -> int:
        return (
            sum(len(v) for v in self.tables.values())
            + sum(len(v) for v in self.columns.values())
            + sum(len(v) for v in self.relationships.values())
        )


def _q_table(name: str) -> str:
    """Quote a table name for DAX: 'My Table' with '' escaping."""
    return "'" + name.replace("'", "''") + "'"


def _q_column(table: str, column: str) -> str:
    """Fully-qualified DAX column reference 'Table'[Column] with ] escaping."""
    return f"{_q_table(table)}[{column.replace(']', ']]')}]"


def collect(backend: Any, *, include_ri: bool = True) -> VertiPaqStats:
    """Collect VertiPaq statistics from a connected backend.

    Raises ``TypeError`` if the backend cannot run queries (file/mock backends).
    Individual query failures are tolerated: the affected stats are simply absent
    so the dependent rules stay honestly skipped.
    """
    if not hasattr(backend, "dax_query"):
        raise TypeError(
            "VertiPaq stats require a live backend (desktop/xmla) with query support."
        )

    stats = VertiPaqStats()
    cols_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for col in backend.column_list():
        cols_by_table[col.get("table", "")].append(col)

    # Drive off the table list so fact tables (whose columns may not surface in
    # column_list) still get a row count.
    for table_obj in backend.table_list():
        table = table_obj.get("name", "")
        if not table:
            continue
        _collect_table(backend, stats, table, cols_by_table.get(table, []))

    if include_ri:
        for rel in backend.relationship_list():
            _collect_ri(backend, stats, rel)

    return stats


def _collect_table(
    backend: Any, stats: VertiPaqStats, table: str, cols: list[dict[str, Any]]
) -> None:
    """One batched DAX query: row count + per-column cardinality / scan stats."""
    tq = _q_table(table)
    # COALESCE(..., 0) so an empty table / empty filter yields a real 0 rather
    # than BLANK (which we cannot distinguish from a failed query).
    parts = [f'"__rows", COALESCE(COUNTROWS({tq}), 0)']
    keymap: dict[str, tuple[str, str]] = {}  # result key -> (column, annotation)

    for i, col in enumerate(cols):
        name = col.get("name", "")
        if not name:
            continue
        cq = _q_column(table, name)
        dtype = str(col.get("dataType", "")).lower()

        parts.append(f'"card_{i}", COALESCE(DISTINCTCOUNT({cq}), 0)')
        keymap[f"card_{i}"] = (name, "Vertipaq_Cardinality")

        if "datetime" in dtype or dtype == "date":
            parts.append(
                f'"dt_{i}", COALESCE(COUNTROWS(FILTER({tq}, '
                f"HOUR({cq}) + MINUTE({cq}) + SECOND({cq}) > 0)), 0)"
            )
            keymap[f"dt_{i}"] = (name, "DateTimeWithHourMinSec")
        elif "string" in dtype:
            parts.append(
                f'"ll_{i}", COALESCE(COUNTROWS(FILTER({tq}, '
                f"LEN({cq}) > {_LONG_LENGTH_THRESHOLD})), 0)"
            )
            keymap[f"ll_{i}"] = (name, "LongLengthRowCount")

    expr = f"EVALUATE ROW({', '.join(parts)})"
    try:
        rows = backend.dax_query(expr)
    except Exception:
        # Fall back to a plain row count so LARGE_TABLES rules still work.
        try:
            rows = backend.dax_query(f'EVALUATE ROW("__rows", COALESCE(COUNTROWS({tq}), 0))')
            keymap = {}
        except Exception:
            return
    if not rows:
        return
    row = rows[0]

    rc = _as_int_str(row.get("__rows"))
    if rc is not None:
        stats.tables[table] = {"Vertipaq_RowCount": rc}

    for key, (col_name, annotation) in keymap.items():
        val = _as_int_str(row.get(key))
        if val is not None:
            stats.columns.setdefault((table, col_name), {})[annotation] = val


def _collect_ri(backend: Any, stats: VertiPaqStats, rel: dict[str, Any]) -> None:
    """Best-effort referential-integrity violation count for one relationship.

    Counts rows on the 'from' (many) side whose key is blank or has no matching
    value on the 'to' (one) side. Any failure leaves the annotation absent.
    """
    ft, fc = _split(rel.get("from", ""))
    tt, tc = _split(rel.get("to", ""))
    if not (ft and fc and tt and tc):
        return
    fcol = _q_column(ft, fc)
    tcol = _q_column(tt, tc)
    expr = (
        f"EVALUATE ROW(\"__ri\", COALESCE(COUNTROWS(FILTER({_q_table(ft)}, "
        f"ISBLANK({fcol}) || ISBLANK(LOOKUPVALUE({tcol}, {tcol}, {fcol})))), 0))"
    )
    try:
        rows = backend.dax_query(expr)
    except Exception:
        return
    if rows:
        val = _as_int_str(rows[0].get("__ri"))
        if val is not None:
            stats.relationships[(rel.get("from", ""), rel.get("to", ""))] = {
                "Vertipaq_RIViolationInvalidRows": val
            }


def _split(endpoint: str) -> tuple[str, str]:
    endpoint = endpoint.strip()
    if endpoint.endswith("]") and "[" in endpoint:
        table, col = endpoint.rsplit("[", 1)
        return table.strip().strip("'").replace("''", "'"), col[:-1]
    return endpoint, ""


def _as_int_str(value: Any) -> str | None:
    """Coerce a DAX numeric result to an integer string, or None if blank/invalid."""
    if value is None:
        return None
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return None
