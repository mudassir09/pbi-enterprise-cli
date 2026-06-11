"""DAX developer tooling: offline formatter and expression-level linter.

The formatter follows DAX Formatter conventions (uppercase functions/keywords,
long-line style: one argument per line once an expression exceeds the width).
The linter runs static expression rules that complement model-level BPA.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|--[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:[^"]|"")*")
  | (?P<table>'(?:[^']|'')*')
  | (?P<bracket>\[[^\]]*\])
  | (?P<number>\d+\.?\d*(?:[eE][+-]?\d+)?)
  | (?P<op><=|>=|<>|&&|\|\||==|[-+*/^&=<>!])
  | (?P<punct>[(),{}])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
""",
    re.VERBOSE | re.DOTALL,
)

_KEYWORDS = {
    "var", "return", "evaluate", "define", "measure", "order", "by", "asc", "desc",
    "true", "false", "in", "not", "and", "or", "start", "at", "column", "table",
}

_BINARY_OPS = {"=", "<", ">", "<=", ">=", "<>", "==", "+", "-", "*", "/", "^", "&", "&&", "||",
               "IN", "NOT"}


def tokenize(expression: str) -> list[tuple[str, str]]:
    """Tokenize DAX into (kind, text) pairs; whitespace dropped, comments kept."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expression):
        m = _TOKEN_RE.match(expression, pos)
        if not m:
            tokens.append(("other", expression[pos]))
            pos += 1
            continue
        kind = m.lastgroup or "other"
        if kind != "ws":
            tokens.append((kind, m.group()))
        pos = m.end()
    return tokens


def _normalize_case(tokens: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for idx, (kind, text) in enumerate(tokens):
        if kind == "ident":
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            if text.lower() in _KEYWORDS or (nxt and nxt[1] == "("):
                text = text.upper()
        out.append((kind, text))
    return out


class _Node:
    """Either an atom, or a call/group with comma-separated argument nodes."""

    def __init__(self, kind: str, text: str = "", args: list[list[_Node]] | None = None) -> None:
        self.kind = kind  # atom | call | group
        self.text = text
        self.args = args or []


def _parse(tokens: list[tuple[str, str]], pos: int = 0) -> tuple[list[_Node], int]:
    nodes: list[_Node] = []
    while pos < len(tokens):
        kind, text = tokens[pos]
        if text == ")":
            return nodes, pos
        if text == "(":
            inner_args, pos = _parse_args(tokens, pos + 1)
            if nodes and nodes[-1].kind == "atom" and tokens[pos - 1] and (
                nodes[-1].text and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", nodes[-1].text)
            ):
                fn = nodes.pop()
                nodes.append(_Node("call", fn.text, inner_args))
            else:
                nodes.append(_Node("group", "", inner_args))
            pos += 1  # past ")"
            continue
        nodes.append(_Node("atom", text))
        pos += 1
    return nodes, pos


def _parse_args(tokens: list[tuple[str, str]], pos: int) -> tuple[list[list[_Node]], int]:
    args: list[list[_Node]] = []
    current: list[_Node] = []
    while pos < len(tokens):
        kind, text = tokens[pos]
        if text == ")":
            if current or args:
                args.append(current)
            return args, pos
        if text == ",":
            args.append(current)
            current = []
            pos += 1
            continue
        if text == "(":
            inner_args, pos = _parse_args(tokens, pos + 1)
            if current and current[-1].kind == "atom" and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_.]*", current[-1].text or ""
            ):
                fn = current.pop()
                current.append(_Node("call", fn.text, inner_args))
            else:
                current.append(_Node("group", "", inner_args))
            pos += 1
            continue
        current.append(_Node("atom", text))
        pos += 1
    if current or args:
        args.append(current)
    return args, pos


def _flat(nodes: list[_Node]) -> str:
    parts: list[str] = []
    prev: str | None = None
    for n in nodes:
        if n.kind == "atom":
            text = n.text
        elif n.kind == "call":
            text = f"{n.text} ( {', '.join(_flat(a) for a in n.args)} )" if n.args else f"{n.text} ()"  # noqa: E501
        else:
            text = f"( {', '.join(_flat(a) for a in n.args)} )"
        if prev is None:
            parts.append(text)
        elif text in (",",):
            parts[-1] += text
        elif prev in ("-", "+") and parts and len(parts) >= 2 and parts[-2] in _BINARY_OPS:
            parts[-1] += text  # unary sign
        else:
            parts.append(text)
        prev = text
    return " ".join(parts)


def _render(nodes: list[_Node], indent: int, width: int) -> str:
    pad = "    " * indent
    flat = _flat(nodes)
    if len(flat) + len(pad) <= width and "\n" not in flat:
        return flat

    # Find the last call/group worth expanding; everything else stays inline
    out_parts: list[str] = []
    for n in nodes:
        if n.kind in ("call", "group") and n.args and len(_flat([n])) + len(pad) > width:
            head = f"{n.text} (" if n.kind == "call" else "("
            arg_pad = "    " * (indent + 1)
            rendered_args = [
                f"{arg_pad}{_render(a, indent + 1, width)}" for a in n.args if a is not None
            ]
            out_parts.append(head + "\n" + ",\n".join(rendered_args) + f"\n{pad})")
        else:
            out_parts.append(_flat([n]))
    return " ".join(out_parts)


def format_dax(expression: str, width: int = 100) -> str:
    """Format a DAX expression: normalized case, spacing, long-line arg breaks."""
    tokens = _normalize_case(tokenize(expression))

    # Split top-level VAR/RETURN sections so each lands on its own line
    sections: list[list[tuple[str, str]]] = [[]]
    depth = 0
    for kind, text in tokens:
        if text == "(":
            depth += 1
        elif text == ")":
            depth -= 1
        if depth == 0 and kind == "ident" and text in ("VAR", "RETURN"):
            sections.append([(kind, text)])
        else:
            sections[-1].append((kind, text))

    lines: list[str] = []
    for sec in sections:
        if not sec:
            continue
        nodes, _ = _parse(sec)
        rendered = _render(nodes, 0, width)
        if sec[0][1] == "RETURN":
            ret_nodes, _ = _parse(sec[1:])
            body = _render(ret_nodes, 1, width)
            joiner = "\n    " if "\n" not in body else "\n    "
            lines.append("RETURN" + joiner + body.lstrip())
        else:
            lines.append(rendered)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------


def _strip_noise(expression: str) -> str:
    """Remove comments and string literals so rules don't false-positive."""
    out: list[str] = []
    for kind, text in tokenize(expression):
        if kind in ("comment",):
            continue
        if kind == "string":
            out.append('""')
        else:
            out.append(text)
    return " ".join(out)


_AGGREGATORS = r"(?:SUM|AVERAGE|MIN|MAX|COUNT|COUNTA|DISTINCTCOUNT|MEDIAN|PRODUCT|STDEV\.[PS]|VAR\.[PS])"  # noqa: E501


def lint_expression(
    name: str,
    expression: str,
    table: str = "",
    measure_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Run all static DAX rules against one expression."""
    violations: list[dict[str, Any]] = []
    clean = _strip_noise(expression)

    def add(rule: str, severity: str, message: str) -> None:
        violations.append({
            "rule": rule, "severity": severity, "object": f"{table}[{name}]" if table else name,
            "message": message,
        })

    if re.search(r"[^/]/[^/*]", f" {clean} "):
        add("dax.division-operator", "warning",
            "Use DIVIDE() instead of '/' to handle divide-by-zero safely.")

    if re.search(r"\bIFERROR\s*\(", clean, re.IGNORECASE):
        add("dax.iferror", "warning",
            "IFERROR forces row-by-row error handling — restructure to avoid errors instead.")

    if re.search(r"\bEARLIER\s*\(", clean, re.IGNORECASE):
        add("dax.earlier", "warning", "Replace EARLIER with VAR for readability and speed.")

    if len(re.findall(r"\bIF\s*\(", clean, re.IGNORECASE)) >= 3:
        add("dax.nested-if", "info", "3+ IF calls — consider SWITCH or SWITCH(TRUE()).")

    if re.search(r"\b(TODAY|NOW|UTCNOW|UTCTODAY)\s*\(", clean, re.IGNORECASE):
        add("dax.volatile-function", "info",
            "TODAY/NOW are volatile — results change between refreshes and defeat caching.")

    for year in re.findall(r"(?<![\w\[\.])((?:19|20)\d{2})(?![\w\]\.])", clean):
        add("dax.hardcoded-year", "info",
            f"Hardcoded year {year} — derive from a date table or parameter instead.")
        break  # one violation per measure is enough

    if re.search(_AGGREGATORS + r"\s*\(\s*\[", clean):
        add("dax.unqualified-aggregator", "warning",
            "Aggregator over a bare [reference]: qualify columns as Table[Column]; "
            "if it references a measure, the outer aggregation is redundant.")

    if re.search(r"\bCALCULATE(?:TABLE)?\s*\(", clean, re.IGNORECASE) and re.search(
        r"\bFILTER\s*\(\s*(?:'[^']+'|[A-Za-z_][\w ]*)\s*,", clean
    ):
        add("dax.calculate-filter-table", "info",
            "FILTER over a whole table inside CALCULATE — prefer a boolean filter "
            "or KEEPFILTERS when the predicate touches a single column.")

    if re.search(r"\b(?:SUMX|AVERAGEX|COUNTX|MINX|MAXX)\s*\(\s*FILTER\s*\(", clean, re.IGNORECASE):
        add("dax.iterator-over-filter", "info",
            "Iterator over FILTER(...) — CALCULATE with a filter argument usually "
            "folds better into the storage engine.")

    if measure_names:
        qualified = re.findall(r"(?:'[^']+'|\b[A-Za-z_]\w*)\s*\[([^\]]+)\]", clean)
        for ref in qualified:
            if ref in measure_names:
                add("dax.qualified-measure-ref", "warning",
                    f"Measure reference '[{ref}]' should not be table-qualified.")
                break

    return violations


def lint_measures(measures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lint every measure in a model."""
    names = {m["name"] for m in measures}
    violations: list[dict[str, Any]] = []
    for m in measures:
        violations.extend(
            lint_expression(m["name"], m.get("expression", ""), m.get("table", ""), names)
        )
    return violations
