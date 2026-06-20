"""FileBackend — read a TMDL / PBIP semantic model folder directly.

Pure Python, no Power BI Desktop, no Windows, no .NET. Lights up governance,
BPA, lint, docs, diff, and impact analysis against the artifacts in a git repo
— exactly what CI wants. Measure writes are persisted back to the TMDL files;
all other writes are in-memory only (use the desktop/xmla backends for those).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pbi_cli.backends.mock_backend import MockTomBackend

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

    # --- Persisted measure writes ---

    def _table_file_for(self, table: str) -> Path:
        for t in self._state.get("tables", []):
            if t["name"] == table and t.get("sourceFile"):
                return Path(t["sourceFile"])
        raise KeyError(f"Table '{table}' not found in TMDL definition.")

    @staticmethod
    def _quote(name: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_]+", name):
            return name
        return "'" + name.replace("'", "''") + "'"

    def _measure_block(self, name: str, expression: str, **props: Any) -> str:
        lines = expression.splitlines()
        if len(lines) <= 1:
            block = f"\tmeasure {self._quote(name)} = {expression}\n"
        else:
            block = f"\tmeasure {self._quote(name)} =\n"
            block += "".join(f"\t\t\t{ln}\n" for ln in lines)
        for key in ("formatString", "displayFolder", "description"):
            if props.get(key):
                block += f"\t\t{key}: {props[key]}\n"
        return block

    def _measure_block_span(self, lines: list[str], name: str) -> tuple[int, int] | None:
        """Find [start, end) line span of a measure block in a table file."""
        pat = re.compile(
            r"^\s*measure\s+(?:'" + re.escape(name.replace("'", "''")) + r"'|"
            + re.escape(name) + r")\s*=",
        )
        for idx, line in enumerate(lines):
            if pat.match(line):
                base_indent = _indent_of(line)
                end = idx + 1
                while end < len(lines):
                    nxt = lines[end]
                    if nxt.strip() and _indent_of(nxt) <= base_indent:
                        break
                    end += 1
                return idx, end
        return None

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_add(table, name, expression, **kwargs)
        tf = self._table_file_for(table)
        text = tf.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + self._measure_block(name, expression, **kwargs)
        tf.write_text(text, encoding="utf-8")
        return record

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_update(table, name, **dict(kwargs))
        tf = self._table_file_for(table)
        lines = tf.read_text(encoding="utf-8").splitlines(keepends=True)
        span = self._measure_block_span(lines, name)
        if span:
            start, end = span
            new_block = self._measure_block(
                kwargs.get("new_name") or record.get("name", name),
                record.get("expression", ""),
                formatString=record.get("formatString", ""),
                displayFolder=record.get("displayFolder", ""),
                description=record.get("description", ""),
            )
            lines[start:end] = [new_block]
            tf.write_text("".join(lines), encoding="utf-8")
        return record

    def measure_delete(self, table: str, name: str) -> None:
        super().measure_delete(table, name)
        tf = self._table_file_for(table)
        lines = tf.read_text(encoding="utf-8").splitlines(keepends=True)
        span = self._measure_block_span(lines, name)
        if span:
            start, end = span
            del lines[start:end]
            tf.write_text("".join(lines), encoding="utf-8")

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
