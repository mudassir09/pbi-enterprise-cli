"""Pure-Python TMDL serializer.

The :mod:`pbi_cli.backends.file_backend` parser turns a TMDL document into a tree
of :class:`~pbi_cli.backends.file_backend.TmdlNode` objects, but historically the
only write path back to disk was a string-templated measure block. Everything
structural (tables, columns, relationships, partitions, …) required a live
engine (``--backend desktop``/``xmla``).

This module closes that gap with two complementary tools:

* **Block renderers** (``render_table``, ``render_column``, ``render_measure``,
  ``render_partition``, ``render_hierarchy``, ``render_relationship``,
  ``render_role``) that emit canonical TMDL text from plain dicts — used when
  *adding* an object. They preserve ``description`` (as ``///`` comment lines,
  the way TMDL actually represents it — not a bogus ``description:`` property),
  ``lineageTag`` and ``annotation`` blocks so a model survives a round-trip
  through Power BI Desktop.
* **``find_block_span``**, a generalised version of the old measure-span finder,
  so an *edit* or *delete* can splice a single object in place without disturbing
  any other object, comment, ``lineageTag`` or annotation in the file.

Indentation is tabs (matching ``TmdlSerializer`` and ``project_scaffold``). All
renderers take a ``level`` (number of leading tabs for the declaration); table
children default to level 1, top-level objects to level 0.
"""

from __future__ import annotations

import re
from typing import Any

from pbi_cli.tmdl_util import quote_tmdl_name

TAB = "\t"

# Properties that TMDL writes as a bare flag line (``isHidden``) rather than
# ``key: value`` when true. Anything else is rendered as ``key: value``.
_BARE_FLAGS = {"isHidden", "isKey"}


def _q(name: str) -> str:
    """Quote a TMDL object name (delegates to the shared helper)."""
    return quote_tmdl_name(name)


def _desc_lines(description: str, level: int) -> list[str]:
    """Render a description as ``///`` comment lines above a declaration."""
    if not description:
        return []
    pad = TAB * level
    return [f"{pad}/// {ln}" for ln in description.splitlines() or [description]]


def _annotation_lines(annotations: Any, level: int) -> list[str]:
    """Render ``annotation Name = Value`` lines (preceded by a blank line).

    Accepts a dict ``{name: value}`` or a list of ``(name, value)`` / ``{"name",
    "value"}`` items so callers can pass whatever they captured from the parser.
    """
    items: list[tuple[str, str]] = []
    if isinstance(annotations, dict):
        items = [(k, v) for k, v in annotations.items()]
    elif isinstance(annotations, list):
        for a in annotations:
            if isinstance(a, dict):
                items.append((str(a.get("name", "")), str(a.get("value", a.get("expression", "")))))
            elif isinstance(a, (list, tuple)) and len(a) == 2:
                items.append((str(a[0]), str(a[1])))
    pad = TAB * level
    out: list[str] = []
    for name, value in items:
        if not name:
            continue
        out.append("")
        out.append(f"{pad}annotation {name} = {value}")
    return out


def _expr_block(keyword: str, name: str, expression: str, level: int) -> list[str]:
    """Render a ``<keyword> <name> = <expression>`` declaration.

    Single-line expressions stay inline; multi-line expressions are written as a
    ``= `` header followed by the body indented two levels deeper (the shape the
    parser recognises as an expression continuation).
    """
    pad = TAB * level
    expr = (expression or "").strip()
    decl = f"{pad}{keyword} {_q(name)}"
    if not expr:
        return [decl]
    lines = expr.splitlines()
    if len(lines) == 1:
        return [f"{decl} = {expr}"]
    body_pad = TAB * (level + 2)
    out = [f"{decl} ="]
    out += [f"{body_pad}{ln.rstrip()}" for ln in lines]
    return out


def render_measure(m: dict[str, Any], level: int = 1) -> str:
    """Render a ``measure`` block from a dict.

    Recognised keys: ``name`` (required), ``expression``, ``formatString``,
    ``displayFolder``, ``description``, ``isHidden``, ``lineageTag``,
    ``annotations``.
    """
    p = level + 1
    pad = TAB * p
    out = _desc_lines(m.get("description", ""), level)
    out += _expr_block("measure", m["name"], m.get("expression", ""), level)
    if m.get("formatString"):
        out.append(f"{pad}formatString: {m['formatString']}")
    if m.get("displayFolder"):
        out.append(f"{pad}displayFolder: {m['displayFolder']}")
    if m.get("isHidden"):
        out.append(f"{pad}isHidden")
    if m.get("lineageTag"):
        out.append(f"{pad}lineageTag: {m['lineageTag']}")
    out += _annotation_lines(m.get("annotations"), p)
    return "\n".join(out)


def render_column(c: dict[str, Any], level: int = 1) -> str:
    """Render a ``column`` block (data or calculated) from a dict."""
    p = level + 1
    pad = TAB * p
    expr = (c.get("expression") or "").strip()
    out = _desc_lines(c.get("description", ""), level)
    out += _expr_block("column", c["name"], expr, level)
    if c.get("dataType"):
        out.append(f"{pad}dataType: {c['dataType']}")
    if c.get("formatString"):
        out.append(f"{pad}formatString: {c['formatString']}")
    if c.get("isHidden"):
        out.append(f"{pad}isHidden")
    if c.get("isKey"):
        out.append(f"{pad}isKey")
    if c.get("summarizeBy"):
        out.append(f"{pad}summarizeBy: {c['summarizeBy']}")
    # A calculated column has no sourceColumn.
    if c.get("sourceColumn") and not expr:
        out.append(f"{pad}sourceColumn: {c['sourceColumn']}")
    if c.get("sortByColumn"):
        out.append(f"{pad}sortByColumn: {c['sortByColumn']}")
    if c.get("dataCategory"):
        out.append(f"{pad}dataCategory: {c['dataCategory']}")
    if c.get("displayFolder"):
        out.append(f"{pad}displayFolder: {c['displayFolder']}")
    if c.get("isAvailableInMDX") is False:
        out.append(f"{pad}isAvailableInMDX: false")
    if c.get("lineageTag"):
        out.append(f"{pad}lineageTag: {c['lineageTag']}")
    out += _annotation_lines(c.get("annotations"), p)
    return "\n".join(out)


def render_partition(part: dict[str, Any], level: int = 1) -> str:
    """Render a ``partition`` block from a dict.

    ``kind`` is the TMDL source kind (``m``/``query``/``calculated``/``entity``);
    it defaults to ``m``. ``source`` is the partition source expression (M for an
    ``m`` partition, DAX for a ``calculated`` one).
    """
    p = level + 1
    pad = TAB * p
    kind = (part.get("kind") or "m").strip()
    out = [f"{TAB * level}partition {_q(part['name'])} = {kind}"]
    out.append(f"{pad}mode: {part.get('mode', 'import')}")
    source = (part.get("source") or part.get("query") or "").strip()
    if source:
        body_pad = TAB * (level + 2)
        src_lines = source.splitlines()
        if len(src_lines) == 1:
            out.append(f"{pad}source = {source}")
        else:
            out.append(f"{pad}source =")
            out += [f"{body_pad}{ln.rstrip()}" for ln in src_lines]
    return "\n".join(out)


def render_hierarchy(h: dict[str, Any], level: int = 1) -> str:
    """Render a ``hierarchy`` block with its ``level`` children from a dict."""
    p = level + 1
    pad = TAB * p
    inner = TAB * (p + 1)
    out = _desc_lines(h.get("description", ""), level)
    out.append(f"{TAB * level}hierarchy {_q(h['name'])}")
    if h.get("lineageTag"):
        out.append(f"{pad}lineageTag: {h['lineageTag']}")
    for lv in h.get("levels", []):
        out.append(f"{pad}level {_q(lv['name'])}")
        if lv.get("column"):
            out.append(f"{inner}column: {lv['column']}")
    return "\n".join(out)


def render_table(t: dict[str, Any], level: int = 0) -> str:
    """Render a complete ``table`` block (the body of a table ``.tmdl`` file).

    Recognised keys: ``name`` (required), ``description``, ``isHidden``,
    ``lineageTag``, ``dataCategory``, ``annotations``, and the child collections
    ``columns``, ``measures``, ``partitions``, ``hierarchies``.
    """
    p = level + 1
    pad = TAB * p
    out = _desc_lines(t.get("description", ""), level)
    out.append(f"{TAB * level}table {_q(t['name'])}")
    if t.get("isHidden"):
        out.append(f"{pad}isHidden")
    if t.get("dataCategory"):
        out.append(f"{pad}dataCategory: {t['dataCategory']}")
    if t.get("lineageTag"):
        out.append(f"{pad}lineageTag: {t['lineageTag']}")
    out += _annotation_lines(t.get("annotations"), p)

    blocks: list[str] = []
    for col in t.get("columns", []):
        blocks.append(render_column(col, p))
    for meas in t.get("measures", []):
        blocks.append(render_measure(meas, p))
    for hier in t.get("hierarchies", []):
        blocks.append(render_hierarchy(hier, p))
    for part in t.get("partitions", []):
        blocks.append(render_partition(part, p))

    body = "\n".join(out)
    if blocks:
        body += "\n\n" + "\n\n".join(blocks)
    return body + "\n"


def _endpoint(table: str, column: str) -> str:
    """Render a relationship endpoint ``Table.Column`` with table quoting."""
    return f"{_q(table)}.{column}"


def render_relationship(r: dict[str, Any], level: int = 0) -> str:
    """Render a ``relationship`` block from a dict.

    Recognised keys: ``name`` (required), ``fromTable``/``fromColumn`` and
    ``toTable``/``toColumn`` (or pre-joined ``from``/``to`` ``Table[Column]``
    strings), ``crossFilteringBehavior``, ``isActive`` (default true),
    ``fromCardinality``/``toCardinality``.
    """
    p = level + 1
    pad = TAB * p

    def split(joined: str) -> tuple[str, str]:
        m = re.match(r"^(.*)\[(.*)\]$", joined.strip())
        return (m.group(1), m.group(2)) if m else (joined, "")

    if r.get("fromTable"):
        ft, fc = r["fromTable"], r.get("fromColumn", "")
    else:
        ft, fc = split(r.get("from", ""))
    if r.get("toTable"):
        tt, tc = r["toTable"], r.get("toColumn", "")
    else:
        tt, tc = split(r.get("to", ""))

    out = [f"{TAB * level}relationship {r['name']}"]
    if r.get("isActive") is False:
        out.append(f"{pad}isActive: false")
    if r.get("crossFilteringBehavior"):
        out.append(f"{pad}crossFilteringBehavior: {r['crossFilteringBehavior']}")
    if r.get("fromCardinality"):
        out.append(f"{pad}fromCardinality: {r['fromCardinality']}")
    if r.get("toCardinality"):
        out.append(f"{pad}toCardinality: {r['toCardinality']}")
    out.append(f"{pad}fromColumn: {_endpoint(ft, fc)}")
    out.append(f"{pad}toColumn: {_endpoint(tt, tc)}")
    return "\n".join(out)


def _camel_enum(value: str) -> str:
    """Normalise a TMDL enum value to its camelCase form (``Read`` -> ``read``).

    TMDL writes enum values like ``modelPermission`` in camelCase (``read``,
    ``readRefresh``); callers may pass the TOM PascalCase form (``Read``,
    ``ReadRefresh``). Lower-casing only the first character preserves the rest.
    """
    return value[:1].lower() + value[1:] if value else value


def render_role(r: dict[str, Any], level: int = 0) -> str:
    """Render a ``role`` block (the body of a role ``.tmdl`` file) from a dict."""
    p = level + 1
    pad = TAB * p
    out = [f"{TAB * level}role {_q(r['name'])}"]
    out.append(f"{pad}modelPermission: {_camel_enum(str(r.get('modelPermission', 'read')))}")
    for tp in r.get("tablePermissions", []):
        expr = (tp.get("filterExpression") or "").strip()
        out.append("")
        if expr:
            out.append(f"{pad}tablePermission {_q(tp['table'])} = {expr}")
        else:
            out.append(f"{pad}tablePermission {_q(tp['table'])}")
    return "\n".join(out)


def _indent_width(line: str) -> int:
    """Indent depth in tab-equivalents (matches the parser: tab or 4 spaces)."""
    n, i = 0, 0
    while i < len(line):
        if line[i] == "\t":
            n += 1
            i += 1
        elif line[i : i + 4] == "    ":
            n += 1
            i += 4
        else:
            break
    return n


def find_block_span(
    lines: list[str], keyword: str, name: str
) -> tuple[int, int] | None:
    """Find the ``[start, end)`` line span of a ``<keyword> <name>`` block.

    Generalises the old measure-only span finder to any TMDL object. The block
    starts at the declaration line and runs until the next line at the same or
    shallower indent. Leading ``///`` description lines immediately above the
    declaration are included so a delete also removes the object's description.
    Matches both the quoted (``'My Name'``) and bare declaration forms.
    """
    quoted = re.escape("'" + name.replace("'", "''") + "'")
    bare = re.escape(name)
    pat = re.compile(rf"^\s*{re.escape(keyword)}\s+(?:{quoted}|{bare})\s*(?:=|$)")
    for idx, line in enumerate(lines):
        if not pat.match(line):
            continue
        base = _indent_width(line)
        start = idx
        # Absorb contiguous description / comment lines directly above.
        while start > 0:
            prev = lines[start - 1].strip()
            if prev.startswith("///") and _indent_width(lines[start - 1]) == base:
                start -= 1
            else:
                break
        end = idx + 1
        while end < len(lines):
            nxt = lines[end]
            if nxt.strip() and _indent_width(nxt) <= base:
                break
            end += 1
        return start, end
    return None
