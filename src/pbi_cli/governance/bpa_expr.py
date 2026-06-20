"""Safe expression evaluator for BPA (Best Practice Analyzer) rules.

Tabular Editor's BPARules.json encodes each rule as a C#/Dynamic-LINQ boolean
expression evaluated against a model object. This module parses that dialect
into a small AST and evaluates it against a plain-dict context.

Why a real parser instead of ``eval()``:

* **Safety** — the old implementation regex-translated the C# string to Python
  and ran ``eval()`` on rule text fetched from a remote URL. This module never
  calls ``eval``/``exec`` and never executes arbitrary Python.
* **Coverage** — it understands the LINQ-style collection methods
  (``.Any(...)``, ``.All(...)``, ``.Where(...)``, ``.Count``) and ``RegEx.IsMatch``
  that the regex approach rejected outright, so many more community rules run.
* **Honesty** — anything the grammar or the model schema genuinely cannot
  express raises :class:`BpaUnsupported`, so the caller can count it as
  *skipped* rather than silently mis-evaluating it.

Supported grammar (covers the bulk of the Microsoft community rule set)::

    or_expr    := and_expr ( ("||" | "or") and_expr )*
    and_expr   := not_expr ( ("&&" | "and") not_expr )*
    not_expr   := ("!" | "not") not_expr | comparison
    comparison := add ( ("==" | "=" | "!=" | "<>" | "<" | ">" | "<=" | ">="
                         | "in") add )?
    add        := mul ( ("+" | "-") mul )*
    mul        := unary ( ("*" | "/") unary )*
    unary      := "-" unary | postfix
    postfix    := primary ( "." IDENT ( "(" args ")" )? )*
    primary    := NUMBER | STRING | "true" | "false" | "null"
                | IDENT | "[" IDENT "]" | "(" or_expr ")" | list
    list       := "{" or_expr ("," or_expr)* "}"
    args       := ( or_expr ("," or_expr)* )?

String methods:  StartsWith, EndsWith, Contains, ToUpper, ToLower, Trim,
                 Replace, IndexOf, Length (property or method).
Collection methods: Count (property or method), Any, All, Where.
Builtins:        RegEx.IsMatch(text, pattern).
"""

from __future__ import annotations

import re
from typing import Any


class BpaUnsupported(Exception):
    """Raised when an expression (or a property it references) cannot be evaluated.

    The caller treats this as *skip this rule* rather than a failure.
    """


# TOM enum types used as ``EnumType.Member`` constants in BPA expressions, e.g.
# ``DataType != DataType.Int64`` or ``CrossFilteringBehavior.BothDirections``.
# ``EnumType.Member`` evaluates to the member name string ("Int64"), which the
# rules compare against the matching scalar property.
_BPA_ENUMS = frozenset(
    {
        "DataType",
        "CrossFilteringBehavior",
        "ObjectType",
        "ModeType",
        "DataViewType",
        "Alignment",
        "DataCategory",
        "SummarizationType",
    }
)

# Inline global regex flags like "(?i)" are valid .NET but only legal at the
# very start of a Python pattern (and error mid-pattern on 3.11+). Lift them out
# and apply them as compile flags so .NET-authored BPA regexes work.
_INLINE_FLAG_RE = re.compile(r"\(\?([imsx]+)\)")
_FLAG_MAP = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}


def _dotnet_regex_search(pattern: str, text: str) -> bool:
    """Run a .NET-flavoured BPA regex against text, returning whether it matches.

    Relocates inline global flags ("(?i)") to Python compile flags. Raises
    :class:`BpaUnsupported` for patterns Python's ``re`` cannot compile.
    """
    flags = 0
    for match in _INLINE_FLAG_RE.findall(pattern):
        for ch in match:
            flags |= _FLAG_MAP[ch]
    cleaned = _INLINE_FLAG_RE.sub("", pattern)
    try:
        return re.search(cleaned, text, flags) is not None
    except re.error as exc:
        raise BpaUnsupported(f"bad regex {pattern!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Context — one model object plus its child collections
# ---------------------------------------------------------------------------


# Closure variables a BPA predicate can reference: the object the rule is
# evaluating (``current``), the element being iterated (``it``), and the element
# of the enclosing iteration (``outerit``). Bare element properties resolve
# without a prefix, so ``it`` is mostly used explicitly as ``it.X``.
_CLOSURE_NAMES = frozenset({"current", "it", "outerit"})


class BpaContext:
    """Evaluation scope for one object: known scalar properties + collections.

    Property/collection names are looked up case-insensitively. A value may be a
    scalar, a list of child ``BpaContext`` (a collection), or a nested
    ``BpaContext`` (a navigable sub-object such as a column's ``Table``).
    Referencing an identifier that is neither a known property/collection nor a
    bound closure raises :class:`BpaUnsupported` — we never silently default an
    unmodelled property, which would produce wrong results.
    """

    __slots__ = ("_props", "_collections", "_closures", "_annotations")

    def __init__(
        self,
        props: dict[str, Any],
        collections: dict[str, Any] | None = None,
        closures: dict[str, Any] | None = None,
        annotations: dict[str, str] | None = None,
    ) -> None:
        self._props = {k.lower(): v for k, v in props.items()}
        self._collections = {k.lower(): v for k, v in (collections or {}).items()}
        self._closures = {k.lower(): v for k, v in (closures or {}).items()}
        # None => VertiPaq stats were not collected, so GetAnnotation raises
        # (the rule is honestly skipped). A dict (even empty) => collected.
        self._annotations = annotations

    def lookup(self, name: str) -> Any:
        key = name.lower()
        if key in self._closures:
            return self._closures[key]
        if key in self._collections:
            return self._collections[key]
        if key in self._props:
            return self._props[key]
        raise BpaUnsupported(f"unknown property or collection {name!r}")

    def closure(self, name: str) -> Any:
        """Return a bound closure variable (current/it/outerit), or None."""
        return self._closures.get(name.lower())

    def get_prop(self, name: str, default: Any = None) -> Any:
        """Non-raising property lookup (used for internal filtering)."""
        return self._props.get(name.lower(), default)

    def get_annotation(self, name: str) -> str:
        """Return a VertiPaq annotation value, defaulting to '0' when collected.

        Raises :class:`BpaUnsupported` if stats were never collected, so rules
        that need runtime statistics skip honestly on a static run.
        """
        if self._annotations is None:
            raise BpaUnsupported(f"annotation {name!r} requires VertiPaq stats (--vertipaq)")
        return self._annotations.get(name, "0")

    def bind_closures(self, mapping: dict[str, Any]) -> BpaContext:
        """Return a shallow copy that also resolves the given closure names."""
        merged = dict(self._closures)
        for k, v in mapping.items():
            if v is not None:
                merged[k.lower()] = v
        clone = BpaContext.__new__(BpaContext)
        clone._props = self._props
        clone._collections = self._collections
        clone._closures = merged
        clone._annotations = self._annotations
        return clone

    # -- post-construction wiring (used to set up cross-references) ----------
    def set_prop(self, name: str, value: Any) -> None:
        self._props[name.lower()] = value

    def set_collection(self, name: str, items: list[Any]) -> None:
        self._collections[name.lower()] = items

    def set_annotations(self, annotations: dict[str, str]) -> None:
        self._annotations = annotations


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"\\]|\\.|"")*"|'(?:[^'\\]|\\.|'')*')
  | (?P<number>\d+\.?\d*(?:[eE][+-]?\d+)?)
  | (?P<op><=|>=|<>|!=|==|&&|\|\||[-+*/<>=.,()\[\]{}!])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
""",
    re.VERBOSE,
)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise BpaUnsupported(f"unexpected character at {pos}: {expr[pos:pos + 12]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        assert kind is not None
        tokens.append((kind, m.group()))
    tokens.append(("eof", ""))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class _Node:
    def eval(self, ctx: BpaContext) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


class _Lit(_Node):
    def __init__(self, value: Any) -> None:
        self.value = value

    def eval(self, ctx: BpaContext) -> Any:
        return self.value


class _Ref(_Node):
    """An identifier or ``[Bracketed]`` property reference."""

    def __init__(self, name: str) -> None:
        self.name = name

    def eval(self, ctx: BpaContext) -> Any:
        return ctx.lookup(self.name)


class _ListLit(_Node):
    def __init__(self, items: list[_Node]) -> None:
        self.items = items

    def eval(self, ctx: BpaContext) -> Any:
        return [i.eval(ctx) for i in self.items]


class _Unary(_Node):
    def __init__(self, op: str, operand: _Node) -> None:
        self.op = op
        self.operand = operand

    def eval(self, ctx: BpaContext) -> Any:
        val = self.operand.eval(ctx)
        if self.op in ("!", "not"):
            return not _truthy(val)
        if self.op == "-":
            return -_as_number(val)
        raise BpaUnsupported(f"unary {self.op!r}")  # pragma: no cover


class _Binary(_Node):
    def __init__(self, op: str, left: _Node, right: _Node) -> None:
        self.op = op
        self.left = left
        self.right = right

    def eval(self, ctx: BpaContext) -> Any:
        op = self.op
        if op in ("&&", "and"):
            return _truthy(self.left.eval(ctx)) and _truthy(self.right.eval(ctx))
        if op in ("||", "or"):
            return _truthy(self.left.eval(ctx)) or _truthy(self.right.eval(ctx))

        left = self.left.eval(ctx)
        if op == "in":
            right = self.right.eval(ctx)
            if not isinstance(right, (list, tuple)):
                raise BpaUnsupported("'in' requires a list on the right-hand side")
            return left in right

        right = self.right.eval(ctx)
        if op in ("==", "="):
            return _eq(left, right)
        if op in ("!=", "<>"):
            return not _eq(left, right)
        if op in ("<", ">", "<=", ">="):
            ln, rn = _as_number(left), _as_number(right)
            if op == "<":
                return ln < rn
            if op == ">":
                return ln > rn
            if op == "<=":
                return ln <= rn
            return ln >= rn
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return _as_str(left) + _as_str(right)
            return _as_number(left) + _as_number(right)
        if op == "-":
            return _as_number(left) - _as_number(right)
        if op == "*":
            return _as_number(left) * _as_number(right)
        if op == "/":
            return _as_number(left) / _as_number(right)
        raise BpaUnsupported(f"operator {op!r}")  # pragma: no cover


class _Member(_Node):
    """``obj.Name`` property access, or ``obj.Name(args)`` method call.

    For collection predicate methods (Any/All/Where) the single argument is
    evaluated lazily against each element, so the raw arg nodes are kept.
    """

    def __init__(self, obj: _Node, name: str, args: list[_Node] | None) -> None:
        self.obj = obj
        self.name = name
        self.args = args  # None => property access, list => method call

    def eval(self, ctx: BpaContext) -> Any:
        # RegEx.IsMatch(text, pattern) — the only supported static builtin.
        if isinstance(self.obj, _Ref) and self.obj.name == "RegEx":
            if self.name == "IsMatch" and self.args is not None and len(self.args) == 2:
                text = _as_str(self.args[0].eval(ctx))
                pattern = _as_str(self.args[1].eval(ctx))
                return _dotnet_regex_search(pattern, text)
            raise BpaUnsupported(f"RegEx.{self.name}")

        # Convert.ToInt64 / ToInt32 / ToDouble / ToString — .NET numeric casts.
        if isinstance(self.obj, _Ref) and self.obj.name == "Convert":
            if self.args is None or len(self.args) != 1:
                raise BpaUnsupported(f"Convert.{self.name}")
            value = self.args[0].eval(ctx)
            if self.name in ("ToInt64", "ToInt32", "ToInt16"):
                return int(_as_number(value))
            if self.name in ("ToDouble", "ToDecimal", "ToSingle"):
                return _as_number(value)
            if self.name == "ToString":
                return _as_str(value)
            if self.name == "ToBoolean":
                return _to_bool(value)
            raise BpaUnsupported(f"Convert.{self.name}")

        # string.IsNullOrEmpty / IsNullOrWhiteSpace — .NET static string helpers.
        if isinstance(self.obj, _Ref) and self.obj.name == "string":
            if self.args is not None and len(self.args) == 1:
                value = self.args[0].eval(ctx)
                s = "" if value is None else _as_str(value)
                nm = self.name.lower()
                if nm == "isnullorempty":
                    return s == ""
                if nm == "isnullorwhitespace":
                    return s.strip() == ""
            raise BpaUnsupported(f"string.{self.name}")

        # char.IsControl / IsWhiteSpace — static, operate on a single-char string.
        if isinstance(self.obj, _Ref) and self.obj.name == "char":
            if self.args is not None and len(self.args) == 1:
                ch = _as_str(self.args[0].eval(ctx))
                c = ch[0] if ch else ""
                nm = self.name.lower()
                if nm == "iscontrol":
                    return c != "" and (ord(c) < 32 or ord(c) == 127)
                if nm == "iswhitespace":
                    return c != "" and c.isspace()
                if nm == "isletterordigit":
                    return c.isalnum()
            raise BpaUnsupported(f"char.{self.name}")

        # Math.Max / Min / Abs / Round — static numeric helpers.
        if isinstance(self.obj, _Ref) and self.obj.name == "Math":
            vals = [_as_number(a.eval(ctx)) for a in (self.args or [])]
            nm = self.name.lower()
            if nm == "max" and len(vals) == 2:
                return max(vals)
            if nm == "min" and len(vals) == 2:
                return min(vals)
            if nm == "abs" and len(vals) == 1:
                return abs(vals[0])
            if nm == "round" and vals:
                return round(vals[0], int(vals[1]) if len(vals) > 1 else 0)
            raise BpaUnsupported(f"Math.{self.name}")

        # EnumType.Member -> "Member" (e.g. DataType.Int64 -> "Int64")
        if (
            isinstance(self.obj, _Ref)
            and self.args is None
            and self.obj.name in _BPA_ENUMS
        ):
            return self.name

        target = self.obj.eval(ctx)

        if isinstance(target, BpaContext):
            # Sub-object navigation, e.g. current.Table.Name or FromColumn.Name
            if self.args is not None:
                raise BpaUnsupported(f"method .{self.name} on object")
            return target.lookup(self.name)
        if isinstance(target, list):
            return self._collection_member(target, ctx)
        if isinstance(target, str):
            return self._string_member(target, ctx)
        raise BpaUnsupported(
            f".{self.name} on {type(target).__name__}"
        )

    # -- collections --------------------------------------------------------
    def _collection_member(self, items: list[Any], ctx: BpaContext) -> Any:
        name = self.name
        if name == "Count":
            return len(items)
        # .AllMeasures / .AllColumns / .AllRelationships — filter a mixed
        # collection (e.g. ReferencedBy) to one object type.
        if name in ("AllMeasures", "AllColumns", "AllRelationships", "AllPartitions"):
            want = name[3:-1]  # "Measure" / "Column" / ...
            return [
                el
                for el in items
                if isinstance(el, BpaContext) and el.get_prop("ObjectType") == want
            ]
        if name in ("Any", "All", "Where"):
            if not self.args or len(self.args) != 1:
                # .Any() with no predicate == "is non-empty"
                if name == "Any" and not self.args:
                    return len(items) > 0
                raise BpaUnsupported(f".{name} expects one predicate")
            pred = self.args[0]
            # Inside the predicate, bind closure variables: `current` = the rule
            # object (inherited from the enclosing scope, else the scope itself),
            # `it` = the element, `outerit` = the enclosing element.
            root = ctx.closure("current") or ctx
            # outerit = the enclosing iteration's element, or the rule object at
            # the first nesting level (matches Tabular Editor semantics).
            parent_it = ctx.closure("it")
            if parent_it is None:
                parent_it = root
            results = [
                el
                for el in items
                if _truthy(pred.eval(_pred_ctx(el, root, parent_it)))
            ]
            if name == "Any":
                return len(results) > 0
            if name == "All":
                return len(results) == len(items)
            return results  # Where
        raise BpaUnsupported(f"collection method .{name}")

    # -- strings ------------------------------------------------------------
    def _string_member(self, s: str, ctx: BpaContext) -> Any:
        name = self.name
        if name == "Length":
            return len(s)
        if name == "ToCharArray" and not self.args:
            return list(s)
        if name == "ToString" and not self.args:
            return s
        if self.args is None:
            raise BpaUnsupported(f"string property .{name}")
        evaled = [a.eval(ctx) for a in self.args]
        if name == "Substring":
            start = int(_as_number(evaled[0]))
            if len(evaled) > 1:
                length = int(_as_number(evaled[1]))
                return s[start:start + length]
            return s[start:]
        args = [_as_str(v) for v in evaled]
        if name == "StartsWith":
            return s.startswith(args[0])
        if name == "EndsWith":
            return s.endswith(args[0])
        if name == "Contains":
            return args[0] in s
        if name == "ToUpper":
            return s.upper()
        if name == "ToLower":
            return s.lower()
        if name == "Trim":
            return s.strip()
        if name == "IndexOf":
            return s.find(args[0])
        if name == "Replace" and len(args) == 2:
            return s.replace(args[0], args[1])
        raise BpaUnsupported(f"string method .{name}")


class _Index(_Node):
    """A collection indexer: ``Partitions[0]`` -> the nth element."""

    def __init__(self, obj: _Node, index: _Node) -> None:
        self.obj = obj
        self.index = index

    def eval(self, ctx: BpaContext) -> Any:
        target = self.obj.eval(ctx)
        if not isinstance(target, list):
            raise BpaUnsupported(f"indexing a {type(target).__name__}")
        idx = int(_as_number(self.index.eval(ctx)))
        if not -len(target) <= idx < len(target):
            raise BpaUnsupported(f"index {idx} out of range")
        return target[idx]


class _Func(_Node):
    """A bare function call: ``GetAnnotation("X")`` or ``char(9)``."""

    def __init__(self, name: str, args: list[_Node]) -> None:
        self.name = name
        self.args = args

    def eval(self, ctx: BpaContext) -> Any:
        if self.name == "GetAnnotation" and len(self.args) == 1:
            return ctx.get_annotation(_as_str(self.args[0].eval(ctx)))
        if self.name == "char" and len(self.args) == 1:
            return chr(int(_as_number(self.args[0].eval(ctx))))
        raise BpaUnsupported(f"function {self.name}()")


def _pred_ctx(el: Any, root: Any, parent_it: Any) -> BpaContext:
    """Build the context for evaluating a collection predicate against an element.

    Object elements expose their own properties plus the closure variables; scalar
    elements (e.g. RLS filter strings) expose only the closures, with ``it`` bound
    to the value so ``it.Replace(...)`` and ``char.IsControl(it)`` work.
    """
    closures = {"current": root, "it": el, "outerit": parent_it}
    if isinstance(el, BpaContext):
        return el.bind_closures(closures)
    return BpaContext({}, closures=closures)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _truthy(val: Any) -> bool:
    if isinstance(val, str):
        # C# bool props arrive as real bools; a bare string is truthy if non-empty
        return val != ""
    if isinstance(val, list):
        return len(val) > 0
    return bool(val)


def _eq(left: Any, right: Any) -> bool:
    # Object identity for context comparisons (e.g. it <> outerit).
    if isinstance(left, BpaContext) or isinstance(right, BpaContext):
        return left is right
    # bool vs string literal ("True"/"False") — common in BPA rules
    if isinstance(left, bool) and not isinstance(right, bool):
        return left == _to_bool(right)
    if isinstance(right, bool) and not isinstance(left, bool):
        return right == _to_bool(left)
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return _as_str(left) == _as_str(right)


def _to_bool(other: Any) -> bool:
    """Coerce the non-bool side of a comparison to a bool."""
    if isinstance(other, str) and other.lower() in ("true", "false"):
        return other.lower() == "true"
    return _truthy(other)


def _as_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "True" if val else "False"
    return str(val)


def _as_number(val: Any) -> float:
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError as exc:
            raise BpaUnsupported(f"not a number: {val!r}") from exc
    raise BpaUnsupported(f"not a number: {val!r}")


# ---------------------------------------------------------------------------
# Parser (recursive descent)
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, str]:
        return self.tokens[self.pos]

    def _next(self) -> tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _accept(self, *values: str) -> str | None:
        kind, val = self._peek()
        if val in values or kind in values:
            self.pos += 1
            return val
        return None

    def _expect(self, value: str) -> None:
        if self._accept(value) is None:
            raise BpaUnsupported(f"expected {value!r}, got {self._peek()[1]!r}")

    def parse(self) -> _Node:
        node = self._or()
        if self._peek()[0] != "eof":
            raise BpaUnsupported(f"trailing tokens at {self._peek()[1]!r}")
        return node

    def _or(self) -> _Node:
        node = self._and()
        while True:
            op = self._accept("||", "or")
            if op is None:
                return node
            node = _Binary(op, node, self._and())

    def _and(self) -> _Node:
        node = self._not()
        while True:
            op = self._accept("&&", "and")
            if op is None:
                return node
            node = _Binary(op, node, self._not())

    def _not(self) -> _Node:
        op = self._accept("!", "not")
        if op is not None:
            return _Unary("not", self._not())
        return self._comparison()

    def _comparison(self) -> _Node:
        node = self._add()
        op = self._accept("==", "=", "!=", "<>", "<", ">", "<=", ">=", "in")
        if op is not None:
            node = _Binary(op, node, self._add())
        return node

    def _add(self) -> _Node:
        node = self._mul()
        while True:
            op = self._accept("+", "-")
            if op is None:
                return node
            node = _Binary(op, node, self._mul())

    def _mul(self) -> _Node:
        node = self._unary()
        while True:
            op = self._accept("*", "/")
            if op is None:
                return node
            node = _Binary(op, node, self._unary())

    def _unary(self) -> _Node:
        if self._accept("-"):
            return _Unary("-", self._unary())
        return self._postfix()

    def _postfix(self) -> _Node:
        node = self._primary()
        while True:
            if self._accept("."):
                kind, name = self._next()
                if kind != "ident":
                    raise BpaUnsupported(f"expected member name, got {name!r}")
                args: list[_Node] | None = None
                if self._accept("("):
                    args = self._args()
                    self._expect(")")
                node = _Member(node, name, args)
            elif self._peek()[1] == "[":
                # Collection indexer, e.g. Partitions[0]
                self.pos += 1
                index = self._or()
                self._expect("]")
                node = _Index(node, index)
            else:
                return node

    def _args(self) -> list[_Node]:
        args: list[_Node] = []
        if self._peek()[1] == ")":
            return args
        args.append(self._or())
        while self._accept(","):
            args.append(self._or())
        return args

    def _primary(self) -> _Node:
        kind, val = self._peek()
        if kind == "number":
            self.pos += 1
            return _Lit(float(val) if ("." in val or "e" in val.lower()) else int(val))
        if kind == "string":
            self.pos += 1
            return _Lit(_unquote(val))
        if kind == "ident":
            self.pos += 1
            low = val.lower()
            if low == "true":
                return _Lit(True)
            if low == "false":
                return _Lit(False)
            if low == "null":
                return _Lit(None)
            # Bare function call: GetAnnotation("X"), char(9), ...
            if self._peek()[1] == "(":
                self.pos += 1
                args = self._args()
                self._expect(")")
                return _Func(val, args)
            return _Ref(val)
        if val == "[":
            self.pos += 1
            ikind, iname = self._next()
            if ikind != "ident":
                raise BpaUnsupported(f"expected identifier in [], got {iname!r}")
            self._expect("]")
            return _Ref(iname)
        if val == "(":
            self.pos += 1
            node = self._or()
            self._expect(")")
            return node
        if val == "{":
            self.pos += 1
            items = [self._or()]
            while self._accept(","):
                items.append(self._or())
            self._expect("}")
            return _ListLit(items)
        raise BpaUnsupported(f"unexpected token {val!r}")


def _unquote(token: str) -> str:
    """Strip the surrounding quotes and resolve only quote/backslash escapes.

    BPA string literals are predominantly regex patterns (``"(?i)RELATED\\s*\\("``),
    so we must NOT apply general escape decoding — that would turn ``\\t`` into a
    real tab and corrupt the pattern. Only ``\\"``, ``\\'`` and ``\\\\`` are
    resolved; every other backslash sequence is preserved verbatim.
    """
    quote = token[0]
    body = token[1:-1]
    if "\\" not in body and quote * 2 not in body:
        return body
    out: list[str] = []
    i = 0
    while i < len(body):
        # Doubled-quote escape (C# verbatim style): "" -> "  and  '' -> '
        if body[i] == quote and i + 1 < len(body) and body[i + 1] == quote:
            out.append(quote)
            i += 2
        elif body[i] == "\\" and i + 1 < len(body) and body[i + 1] in ('"', "'", "\\"):
            out.append(body[i + 1])
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_expression(expr: str) -> _Node:
    """Parse a BPA expression once into a reusable AST.

    Raises :class:`BpaUnsupported` if the expression cannot be parsed.
    """
    if not expr or not expr.strip():
        raise BpaUnsupported("empty expression")
    return _Parser(_tokenize(expr)).parse()


def evaluate(node: _Node, ctx: BpaContext) -> bool:
    """Evaluate a compiled expression against a context. Returns a bool.

    Raises :class:`BpaUnsupported` if evaluation hits an unmodelled property or
    an operation the evaluator does not implement.
    """
    return _truthy(node.eval(ctx))


def evaluate_expression(expr: str, ctx: BpaContext) -> bool:
    """Convenience: parse and evaluate in one call."""
    return evaluate(compile_expression(expr), ctx)
