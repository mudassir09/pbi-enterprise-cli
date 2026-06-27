"""FileBackend — read a TMDL / PBIP semantic model folder directly.

Pure Python, no Power BI Desktop, no Windows, no .NET. Lights up governance,
BPA, lint, docs, diff, and impact analysis against the artifacts in a git repo
— exactly what CI wants. Measure writes are persisted back to the TMDL files;
all other writes are in-memory only (use the desktop/xmla backends for those).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from pbi_cli.backends.mock_backend import MockTomBackend
from pbi_cli.tmdl_util import (
    atomic_write_text,
    ensure_ref_table,
    quote_tmdl_name,
    remove_ref_table,
)
from pbi_cli.tmdl_writer import (
    find_block_span,
    render_column,
    render_hierarchy,
    render_measure,
    render_partition,
    render_relationship,
    render_role,
    render_table,
)

# Object declaration keywords that open a TMDL block
_DECL_KEYWORDS = {
    "database", "model", "table", "measure", "column", "partition", "hierarchy",
    "level", "relationship", "role", "tablePermission", "expression", "annotation",
    "calculationGroup", "calculationItem", "variation", "extendedProperty",
    "member", "perspective", "perspectiveTable", "culture", "kpi", "refreshPolicy",
}

_DECL_RE = re.compile(
    r"^(?P<kw>[A-Za-z]+)(?:\s+(?P<name>'(?:[^']|'')*'|\"[^\"]*\"|[^=\s][^=]*?))?\s*(?:=\s*(?P<expr>.*))?$"
)


class TmdlNode:
    """One parsed TMDL object: declaration, properties, expression, children."""

    __slots__ = ("keyword", "name", "indent", "expr_lines", "props", "children", "description")

    def __init__(self, keyword: str, name: str, indent: int) -> None:
        self.keyword = keyword
        self.name = name
        self.indent = indent
        self.expr_lines: list[str] = []
        self.props: dict[str, str] = {}
        self.children: list[TmdlNode] = []
        self.description = ""

    @property
    def expression(self) -> str:
        return "\n".join(self.expr_lines).strip()

    def find_all(self, keyword: str) -> list[TmdlNode]:
        out = [c for c in self.children if c.keyword == keyword]
        for c in self.children:
            out.extend(c.find_all(keyword))
        return out


def _strip_name(raw: str | None) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        inner = raw[1:-1]
        return inner.replace("''", "'") if raw[0] == "'" else inner
    return raw


def _indent_of(line: str) -> int:
    n = 0
    i = 0
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


def parse_tmdl(text: str) -> list[TmdlNode]:
    """Parse a TMDL document into a tree of nodes. Tolerant by design."""
    roots: list[TmdlNode] = []
    stack: list[TmdlNode] = []
    pending_desc: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            i += 1
            continue
        if stripped.startswith("//"):
            i += 1
            continue

        indent = _indent_of(line)
        while stack and stack[-1].indent >= indent:
            stack.pop()
        parent = stack[-1] if stack else None

        m = _DECL_RE.match(stripped)
        kw = m.group("kw") if m else ""
        is_decl = bool(m) and kw in _DECL_KEYWORDS

        # Property line: `key: value` (and not a declaration)
        if not is_decl and ":" in stripped and parent is not None:
            key, _, value = stripped.partition(":")
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key.strip()):
                parent.props[key.strip()] = value.strip()
                i += 1
                continue

        # Bare boolean flag: `isHidden`
        if not is_decl and re.fullmatch(r"[a-z][A-Za-z0-9]*", stripped) and parent is not None:
            parent.props[stripped] = "true"
            i += 1
            continue

        if not is_decl or m is None:
            # Unrecognised content inside a block — attach to parent expression
            if parent is not None:
                parent.expr_lines.append(stripped)
            i += 1
            continue

        node = TmdlNode(kw, _strip_name(m.group("name")), indent)
        if pending_desc:
            node.description = " ".join(pending_desc)
            pending_desc = []
        if parent is not None:
            parent.children.append(node)
        else:
            roots.append(node)

        expr = (m.group("expr") or "").strip()
        if expr and expr != "```":
            node.expr_lines.append(expr)

        i += 1

        # Collect a multi-line expression block: fenced ``` or deeper-indented lines
        if expr == "```" or (m.group("expr") is not None and not expr):
            fenced = expr == "```"
            while i < len(lines):
                nxt = lines[i]
                nstripped = nxt.strip()
                if fenced:
                    if nstripped == "```":
                        i += 1
                        break
                    node.expr_lines.append(nstripped)
                    i += 1
                    continue
                if not nstripped:
                    i += 1
                    continue
                nindent = _indent_of(nxt)
                # Expression continuation is indented deeper than properties
                if nindent >= indent + 2:
                    node.expr_lines.append(nstripped)
                    i += 1
                    continue
                break
        stack.append(node)
    return roots


def _dedent_block(lines: list[str]) -> list[str]:
    """Strip the common leading indent from a block so it parses at top level."""
    indents = [_indent_of(ln) for ln in lines if ln.strip()]
    if not indents:
        return list(lines)
    base = min(indents)
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            out.append("")
            continue
        # Remove `base` indent units (tab or 4 spaces), whichever the line uses.
        rest = ln
        for _ in range(base):
            if rest.startswith("\t"):
                rest = rest[1:]
            elif rest.startswith("    "):
                rest = rest[4:]
            else:
                break
        out.append(rest)
    return out


def _calc_item_block(name: str, expression: str, level: int) -> list[str]:
    """Render a `calculationItem` block at the given indent level."""
    pad = "\t" * level
    body_pad = "\t" * (level + 2)
    expr = (expression or "").strip()
    lines = expr.splitlines()
    if len(lines) <= 1:
        return [f"{pad}calculationItem {quote_tmdl_name(name)} = {expr}"]
    out = [f"{pad}calculationItem {quote_tmdl_name(name)} ="]
    out += [f"{body_pad}{ln.rstrip()}" for ln in lines]
    return out


def resolve_definition_dir(path: str | Path | None) -> Path:
    """Locate the TMDL `definition` folder from a project path."""
    base = Path(path) if path else Path.cwd()
    if base.is_file() and base.suffix == ".pbip":
        base = base.parent
    candidates = [base, base / "definition"]
    candidates += sorted(base.glob("*.SemanticModel"))
    candidates += sorted(base.glob("*.SemanticModel/definition"))
    candidates += sorted(base.glob("*.Dataset/definition"))
    for c in candidates:
        d = c / "definition" if (c / "definition").is_dir() else c
        if (d / "model.tmdl").exists() or (d / "tables").is_dir():
            return d
    raise FileNotFoundError(
        f"No TMDL definition folder found under '{base}'. "
        "Expected model.tmdl or a tables/ directory (PBIP / pbi-tools layout)."
    )


def _is_calculated_table(node: TmdlNode) -> bool:
    """A table is calculated if any partition is a calculated/DAX partition."""
    for child in node.children:
        if child.keyword != "partition":
            continue
        for ln in child.expr_lines:
            if ln.strip() in ("calculated", "calculationGroup"):
                return True
    return False


def _rel_endpoint(value: str) -> tuple[str, str]:
    """Split `Table.Column` / `'Tab le'.Column` into (table, column)."""
    value = value.strip()
    m = re.match(r"^(?:'((?:[^']|'')*)'|([^.]+))\.(.+)$", value)
    if not m:
        return value, ""
    table = (m.group(1) or m.group(2) or "").replace("''", "'")
    return table.strip(), m.group(3).strip()


class FileBackend(MockTomBackend):
    """TMDL-folder backend. Read everything; persist measure writes to disk."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.definition_dir = resolve_definition_dir(path)
        super().__init__(fixture=self._load_state())

    # --- Connection ---

    def connect(self, **kwargs: Any) -> None:
        self._connected = True

    # --- TMDL loading ---

    def _table_files(self) -> list[Path]:
        tables_dir = self.definition_dir / "tables"
        return sorted(tables_dir.glob("*.tmdl")) if tables_dir.is_dir() else []

    def _load_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "model": {"name": "Model", "compatibility_level": 1600},
            "tables": [], "columns": [], "measures": [], "relationships": [],
            "roles": [], "partitions": [], "hierarchies": [], "calc_groups": [],
            "expressions": [],
        }

        db_file = self.definition_dir / "database.tmdl"
        if db_file.exists():
            for node in parse_tmdl(db_file.read_text(encoding="utf-8")):
                if node.keyword == "database":
                    lvl = node.props.get("compatibilityLevel")
                    if lvl and lvl.isdigit():
                        state["model"]["compatibility_level"] = int(lvl)
                    if node.name:
                        state["model"]["name"] = node.name

        model_file = self.definition_dir / "model.tmdl"
        if model_file.exists():
            for node in parse_tmdl(model_file.read_text(encoding="utf-8")):
                if node.keyword == "model":
                    state["model"]["culture"] = node.props.get("culture", "")
                    if node.name and state["model"]["name"] == "Model":
                        state["model"]["name"] = node.name

        if state["model"]["name"] == "Model":
            # Fall back to the PBIP folder name: Sales.SemanticModel → Sales
            for parent in [self.definition_dir, *self.definition_dir.parents]:
                if parent.name.endswith(".SemanticModel"):
                    state["model"]["name"] = parent.name.rsplit(".", 1)[0]
                    break

        for tf in self._table_files():
            self._load_table_file(tf, state)

        for rel_name in ("relationships.tmdl", "relationship.tmdl"):
            rf = self.definition_dir / rel_name
            if rf.exists():
                for node in parse_tmdl(rf.read_text(encoding="utf-8")):
                    if node.keyword != "relationship":
                        continue
                    ft, fc = _rel_endpoint(node.props.get("fromColumn", ""))
                    tt, tc = _rel_endpoint(node.props.get("toColumn", ""))
                    # TMDL omits the default cardinalities (many on the from side,
                    # one on the to side); make the derived marker explicit.
                    from_card = node.props.get("fromCardinality", "many")
                    to_card = node.props.get("toCardinality", "one")
                    cardinality = (
                        f"{from_card.capitalize()}To{to_card.capitalize()}"
                    )
                    state["relationships"].append({
                        "from": f"{ft}[{fc}]",
                        "to": f"{tt}[{tc}]",
                        "cardinality": cardinality,
                        "crossFilteringBehavior": node.props.get(
                            "crossFilteringBehavior", "OneDirection"
                        ),
                        "isActive": node.props.get("isActive", "true") != "false",
                    })

        expr_file = self.definition_dir / "expressions.tmdl"
        if expr_file.exists():
            for node in parse_tmdl(expr_file.read_text(encoding="utf-8")):
                if node.keyword == "expression":
                    state["expressions"].append(
                        {"name": node.name, "expression": node.expression, "kind": "m"}
                    )

        roles_dir = self.definition_dir / "roles"
        role_files = sorted(roles_dir.glob("*.tmdl")) if roles_dir.is_dir() else []
        for rf in role_files:
            for node in parse_tmdl(rf.read_text(encoding="utf-8")):
                if node.keyword != "role":
                    continue
                perms = [
                    {"table": tp.name, "filterExpression": tp.expression}
                    for tp in node.children if tp.keyword == "tablePermission"
                ]
                state["roles"].append({
                    "name": node.name,
                    "modelPermission": node.props.get("modelPermission", "read"),
                    "tablePermissions": perms,
                })
        return state

    def _load_table_file(self, tf: Path, state: dict[str, Any]) -> None:
        for node in parse_tmdl(tf.read_text(encoding="utf-8")):
            if node.keyword != "table":
                continue
            tname = node.name
            calc_group = next(
                (c for c in node.children if c.keyword == "calculationGroup"), None
            )
            state["tables"].append({
                "name": tname,
                "isHidden": node.props.get("isHidden", "false") == "true",
                "description": node.description,
                "dataCategory": node.props.get("dataCategory", ""),
                "sourceFile": str(tf),
                "isCalculationGroup": calc_group is not None,
                "objectTypeName": "Calculated Table" if _is_calculated_table(node)
                else "Table",
            })
            for child in node.children:
                if child.keyword == "measure":
                    state["measures"].append({
                        "table": tname,
                        "name": child.name,
                        "expression": child.expression,
                        "formatString": child.props.get("formatString", ""),
                        "description": child.description,
                        "displayFolder": child.props.get("displayFolder", ""),
                        "isHidden": child.props.get("isHidden", "false") == "true",
                    })
                elif child.keyword == "column":
                    is_calc = bool(child.expression.strip())
                    state["columns"].append({
                        "table": tname,
                        "name": child.name,
                        "dataType": child.props.get("dataType", ""),
                        "isHidden": child.props.get("isHidden", "false") == "true",
                        "sourceColumn": child.props.get("sourceColumn", ""),
                        "expression": child.expression,
                        "formatString": child.props.get("formatString", ""),
                        "summarizeBy": child.props.get("summarizeBy", ""),
                        "description": child.description,
                        "dataCategory": child.props.get("dataCategory", ""),
                        "isKey": child.props.get("isKey", "false") == "true",
                        "sortByColumn": child.props.get("sortByColumn", ""),
                        "isAvailableInMDX": child.props.get("isAvailableInMDX", "true")
                        != "false",
                        "columnType": "Calculated" if is_calc else "Data",
                    })
                elif child.keyword == "partition":
                    lines = [ln for ln in child.expr_lines if ln.strip()]
                    kind = ""
                    if lines and lines[0].strip() in (
                        "m", "calculated", "entity", "query", "calculationGroup", "policyRange",
                    ):
                        kind = lines.pop(0).strip()
                    source = "\n".join(lines).strip()
                    if source.lower().startswith("source ="):
                        source = source[len("source ="):].strip()
                    elif source.lower().startswith("source"):
                        source = source[len("source"):].strip()
                    if not source:
                        source = next(
                            (c.expression for c in child.children if c.keyword == "expression"),
                            "",
                        )
                    # TMDL partition kind -> TOM SourceType casing
                    _src_type = {"m": "M", "query": "Query", "calculated": "Calculated",
                                 "entity": "Entity", "calculationGroup": "CalculationGroup",
                                 "policyRange": "PolicyRange"}.get(kind, kind)
                    state["partitions"].append({
                        "table": tname,
                        "name": child.name,
                        "kind": kind,
                        "mode": child.props.get("mode", "import"),
                        "state": "Ready",
                        "source": source,
                        "sourceType": _src_type,
                        "query": source,
                    })
                elif child.keyword == "hierarchy":
                    state["hierarchies"].append({
                        "table": tname,
                        "name": child.name,
                        "levels": [
                            {"name": lv.name, "column": lv.props.get("column", "")}
                            for lv in child.children if lv.keyword == "level"
                        ],
                    })
                elif child.keyword == "calculationGroup":
                    state["calc_groups"].append({
                        "table": tname,
                        "precedence": int(child.props.get("precedence", "0") or 0),
                        "items": [
                            {"group": tname, "name": ci.name, "expression": ci.expression}
                            for ci in child.children if ci.keyword == "calculationItem"
                        ],
                    })

    # --- Extra read surface ---

    def expression_list(self) -> list[dict[str, Any]]:
        """Shared M expressions from expressions.tmdl."""
        return list(self._state.get("expressions", []))

    def reload(self) -> None:
        """Re-read state from disk (used by watch mode)."""
        self._state = self._load_state()

    # --- Persisted writes (pure-Python TMDL, no engine) ---
    #
    # Every structural edit is serialised back to the TMDL files via
    # pbi_cli.tmdl_writer. Edits splice a single object in place (find_block_span)
    # so untouched objects, comments, lineageTags and annotations are preserved;
    # additions append a rendered block; the model.tmdl ref-table block is kept in
    # sync because TMDL does not auto-discover table files.

    def _table_file_for(self, table: str) -> Path:
        for t in self._state.get("tables", []):
            if t["name"] == table and t.get("sourceFile"):
                return Path(t["sourceFile"])
        raise KeyError(f"Table '{table}' not found in TMDL definition.")

    def _model_tmdl(self) -> Path:
        return self.definition_dir / "model.tmdl"

    @staticmethod
    def _quote(name: str) -> str:
        return quote_tmdl_name(name)

    @staticmethod
    def _append_block(tf: Path, block: str) -> None:
        """Append a rendered block to a TMDL file, blank-line separated."""
        text = tf.read_text(encoding="utf-8") if tf.exists() else ""
        text = text.rstrip("\n")
        sep = "\n\n" if text else ""
        atomic_write_text(tf, text + sep + block.rstrip("\n") + "\n")

    @staticmethod
    def _delete_block(tf: Path, keyword: str, name: str) -> bool:
        """Delete a `<keyword> <name>` block from a TMDL file. Returns True if removed."""
        lines = tf.read_text(encoding="utf-8").splitlines()
        span = find_block_span(lines, keyword, name)
        if span is None:
            return False
        start, end = span
        # Absorb one adjacent blank line so the file stays single-blank separated.
        if end < len(lines) and lines[end].strip() == "":
            end += 1
        elif start > 0 and lines[start - 1].strip() == "":
            start -= 1
        del lines[start:end]
        atomic_write_text(tf, "\n".join(lines).rstrip("\n") + "\n")
        return True

    def _set_source_file(self, table: str, path: Path) -> None:
        for t in self._state.get("tables", []):
            if t["name"] == table:
                t["sourceFile"] = str(path)

    # --- Measures ---

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_add(table, name, expression, **kwargs)
        tf = self._table_file_for(table)
        self._append_block(tf, render_measure({"name": name, "expression": expression, **kwargs}))
        return record

    def _read_block_node(self, tf: Path, keyword: str, name: str) -> TmdlNode | None:
        """Parse the on-disk block for `<keyword> <name>` into a TmdlNode."""
        lines = tf.read_text(encoding="utf-8").splitlines()
        span = find_block_span(lines, keyword, name)
        if span is None:
            return None
        start, end = span
        roots = parse_tmdl("\n".join(_dedent_block(lines[start:end])))
        return roots[0] if roots else None

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_update(table, name, **dict(kwargs))
        tf = self._table_file_for(table)
        # Read the existing block so lineageTag / annotations / unchanged props
        # survive the rewrite (the in-memory state does not carry them).
        node = self._read_block_node(tf, "measure", name)
        spec: dict[str, Any] = {
            "name": kwargs.get("new_name") or record.get("name", name),
            "expression": record.get("expression", ""),
            "formatString": record.get("formatString", ""),
            "displayFolder": record.get("displayFolder", ""),
            "description": record.get("description", ""),
            "isHidden": record.get("isHidden", False),
        }
        if node is not None:
            spec["expression"] = spec["expression"] or node.expression
            spec["formatString"] = spec["formatString"] or node.props.get("formatString", "")
            spec["displayFolder"] = spec["displayFolder"] or node.props.get("displayFolder", "")
            spec["description"] = spec["description"] or node.description
            spec["lineageTag"] = node.props.get("lineageTag", "")
            spec["annotations"] = [
                {"name": a.name, "value": a.expression}
                for a in node.children if a.keyword == "annotation"
            ]
            if not kwargs.get("isHidden") and node.props.get("isHidden") == "true":
                spec["isHidden"] = True
        lines = tf.read_text(encoding="utf-8").splitlines()
        span = find_block_span(lines, "measure", name)
        if span:
            start, end = span
            lines[start:end] = render_measure(spec).splitlines()
            atomic_write_text(tf, "\n".join(lines).rstrip("\n") + "\n")
        return record

    def measure_delete(self, table: str, name: str) -> None:
        super().measure_delete(table, name)
        self._delete_block(self._table_file_for(table), "measure", name)

    # --- Tables ---

    def table_add(self, name: str, **kwargs: Any) -> dict[str, Any]:
        record = super().table_add(name, **kwargs)
        tf = self.definition_dir / "tables" / f"{name}.tmdl"
        tf.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(tf, render_table({"name": name, **kwargs}))
        self._set_source_file(name, tf)
        model = self._model_tmdl()
        if model.exists():
            ensure_ref_table(model, name)
        return record

    def table_delete(self, name: str) -> None:
        try:
            tf = self._table_file_for(name)
        except KeyError:
            tf = self.definition_dir / "tables" / f"{name}.tmdl"
        super().table_delete(name)
        if tf.exists():
            tf.unlink()
        model = self._model_tmdl()
        if model.exists():
            remove_ref_table(model, name)

    # --- Columns ---

    def column_add(self, table: str, name: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        record = super().column_add(table, name, data_type, **kwargs)
        spec = {"name": name, "dataType": data_type, **kwargs}
        spec.setdefault("summarizeBy", "none")
        spec.setdefault("sourceColumn", name)
        self._append_block(self._table_file_for(table), render_column(spec))
        return record

    def column_delete(self, table: str, name: str) -> None:
        super().column_delete(table, name)
        self._delete_block(self._table_file_for(table), "column", name)

    # --- Relationships ---

    def relationship_add(
        self, from_table: str, from_column: str, to_table: str, to_column: str, **kwargs: Any
    ) -> dict[str, Any]:
        record = super().relationship_add(from_table, from_column, to_table, to_column, **kwargs)
        rel = {
            "name": kwargs.get("name") or uuid.uuid4().hex,
            "fromTable": from_table, "fromColumn": from_column,
            "toTable": to_table, "toColumn": to_column,
            "crossFilteringBehavior": kwargs.get("crossFilteringBehavior"),
            "isActive": kwargs.get("isActive", True),
        }
        rf = self.definition_dir / "relationships.tmdl"
        if not rf.exists() and (self.definition_dir / "relationship.tmdl").exists():
            rf = self.definition_dir / "relationship.tmdl"
        self._append_block(rf, render_relationship(rel))
        return record

    # --- Hierarchies ---

    def hierarchy_add(self, table: str, name: str, levels: list[dict[str, Any]]) -> dict[str, Any]:
        record = super().hierarchy_add(table, name, levels)
        self._append_block(
            self._table_file_for(table), render_hierarchy({"name": name, "levels": levels})
        )
        return record

    def hierarchy_delete(self, table: str, name: str) -> None:
        super().hierarchy_delete(table, name)
        self._delete_block(self._table_file_for(table), "hierarchy", name)

    # --- Calculation groups ---

    def calc_group_add(self, name: str, precedence: int = 0) -> dict[str, Any]:
        record = super().calc_group_add(name, precedence)
        tf = self.definition_dir / "tables" / f"{name}.tmdl"
        tf.parent.mkdir(parents=True, exist_ok=True)
        # A calculation group is a table carrying a calculationGroup block, a
        # string column (the calc-group "name" axis) and a calculationGroup
        # partition. All three are required for Power BI Desktop to load it.
        body = (
            f"table {self._quote(name)}\n\n"
            f"\tcalculationGroup\n\t\tprecedence: {precedence}\n\n"
            f"\tcolumn Name\n\t\tdataType: string\n\t\tsourceColumn: Name\n\n"
            f"\tpartition {self._quote(name)} = calculationGroup\n\t\tmode: import\n"
        )
        # The calculationGroup block is empty on creation; calc items are spliced
        # in by calc_item_add. Keep a blank line after precedence for that.
        atomic_write_text(tf, body)
        self._state["tables"].append({"name": name, "sourceFile": str(tf),
                                       "isCalculationGroup": True})
        model = self._model_tmdl()
        if model.exists():
            ensure_ref_table(model, name)
        return record

    def calc_item_add(
        self, group_table: str, name: str, expression: str, ordinal: int = 0
    ) -> dict[str, Any]:
        record = super().calc_item_add(group_table, name, expression, ordinal)
        tf = self._table_file_for(group_table)
        lines = tf.read_text(encoding="utf-8").splitlines()
        # Insert the calculationItem inside the calculationGroup block.
        for idx, line in enumerate(lines):
            if re.match(r"^\s*calculationGroup\b", line):
                base = _indent_of(line)
                # Find the end of the calculationGroup block (next sibling/dedent).
                end = idx + 1
                while end < len(lines) and not (
                    lines[end].strip() and _indent_of(lines[end]) <= base
                ):
                    end += 1
                # Insert after the block's last content line, before trailing blanks,
                # so items stay grouped without doubling blank lines.
                insert_at = end
                while insert_at - 1 > idx and not lines[insert_at - 1].strip():
                    insert_at -= 1
                block = _calc_item_block(name, expression, base + 1)
                lines[insert_at:insert_at] = ["", *block]
                atomic_write_text(tf, "\n".join(lines).rstrip("\n") + "\n")
                break
        return record

    def calc_item_delete(self, group_table: str, name: str) -> None:
        super().calc_item_delete(group_table, name)
        self._delete_block(self._table_file_for(group_table), "calculationItem", name)

    # --- RLS roles ---

    def role_add(self, name: str, table: str, filter_expression: str) -> dict[str, Any]:
        record = super().role_add(name, table, filter_expression)
        roles_dir = self.definition_dir / "roles"
        roles_dir.mkdir(parents=True, exist_ok=True)
        tf = roles_dir / f"{name}.tmdl"
        atomic_write_text(
            tf,
            render_role({
                "name": name,
                "modelPermission": record.get("modelPermission", "read"),
                "tablePermissions": record.get("tablePermissions", []),
            }) + "\n",
        )
        return record

    def role_delete(self, name: str) -> None:
        super().role_delete(name)
        tf = self.definition_dir / "roles" / f"{name}.tmdl"
        if tf.exists():
            tf.unlink()

    # --- Partitions ---

    def partition_add(self, table: str, name: str, query: str) -> dict[str, Any]:
        record = super().partition_add(table, name, query)
        self._append_block(
            self._table_file_for(table),
            render_partition({"name": name, "source": query, "kind": "m"}),
        )
        return record

    def partition_delete(self, table: str, name: str) -> None:
        super().partition_delete(table, name)
        self._delete_block(self._table_file_for(table), "partition", name)

    def partition_refresh(self, table: str, name: str) -> dict[str, Any]:
        raise NotImplementedError(
            "The file backend cannot refresh a partition — there is no engine to "
            "process data. Use --backend desktop or xmla against a live model."
        )

    # --- Not supported without a live engine ---

    def dax_query(self, expression: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "The file backend cannot execute DAX (no engine). "
            "Use --backend rest, xmla, or desktop for live queries."
        )

    def dax_validate(self, expression: str) -> dict[str, Any]:
        # Static parenthesis/quote balance check — no engine available
        problems: list[str] = []
        for open_ch, close_ch in (("(", ")"), ("[", "]")):
            if expression.count(open_ch) != expression.count(close_ch):
                problems.append(f"Unbalanced {open_ch}{close_ch}")
        if expression.count('"') % 2:
            problems.append("Unbalanced string quotes")
        return {"valid": not problems, "expression": expression, "problems": problems,
                "engine": "static"}

    def tmdl_export(self, path: str) -> None:
        import shutil

        shutil.copytree(self.definition_dir, path, dirs_exist_ok=True)

    def tmdl_import(self, path: str) -> None:
        raise NotImplementedError("The file backend reads TMDL in place — edit the files directly.")
