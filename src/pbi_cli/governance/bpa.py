"""BPA (Best Practice Analyzer) — loader and safe expression evaluator.

Loads the BPARules.json schema used by Tabular Editor and the Microsoft
community rule set, and evaluates the rules with no .NET tooling.

Expressions are parsed into an AST and evaluated against the model
(:mod:`pbi_cli.governance.bpa_expr`) — there is no ``eval()``. A rule whose
expression, or a property it references, is outside what we can model is
reported as *skipped* rather than silently mis-evaluated, so the count of rules
actually run is honest. See ``govern bpa check`` output for the evaluated/skipped
tally.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from pbi_cli.governance.bpa_expr import (
    BpaContext,
    BpaUnsupported,
    compile_expression,
    evaluate,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMUNITY_BPA_URL = (
    "https://raw.githubusercontent.com/microsoft/Analysis-Services"
    "/master/BestPracticeRules/BPARules.json"
)

_SEVERITY_MAP = {1: "warning", 2: "error", 3: "info"}

# Scopes we can evaluate — anything else is skipped
_SUPPORTED_SCOPES = {"Column", "Table", "Measure", "Relationship", "Model", "Partition"}

# A BPA rule's "Scope" is a comma-separated list of TOM object types (e.g.
# "DataColumn, CalculatedColumn, CalculatedTableColumn"). Map each TOM type to
# the object family we evaluate against. Tokens with no mapping (Hierarchy, KPI,
# Perspective, CalculationItem, ModelRole, …) are types we do not model, so a
# rule scoped *only* to those is skipped.
_SCOPE_TOKEN_MAP = {
    # Column sub-types map to distinct buckets so a rule scoped only to
    # CalculatedColumn does not also flag data columns (and vice-versa).
    "column": "Column",
    "datacolumn": "DataColumn",
    "calculatedcolumn": "CalculatedColumn",
    "calculatedtablecolumn": "CalculatedTableColumn",
    "table": "Table",
    "calculatedtable": "CalculatedTable",
    "measure": "Measure",
    "relationship": "Relationship",
    "model": "Model",
    "partition": "Partition",
    "calculationitem": "CalculationItem",
    "calculationgroup": "CalculationGroup",
    "modelrole": "Role",
    "perspective": "Perspective",
    "tablepermission": "TablePermission",
    "providerdatasource": "DataSource",
    "structureddatasource": "DataSource",
    "hierarchy": "Hierarchy",
}


def _map_scopes(scope: str) -> list[str]:
    """Map a rule's (possibly compound) Scope string to the scopes we evaluate.

    Returns the de-duplicated, order-stable list of evaluable scopes. Empty if
    the rule targets only object types we do not model.
    """
    seen: dict[str, None] = {}
    for token in scope.split(","):
        mapped = _SCOPE_TOKEN_MAP.get(token.strip().lower())
        if mapped is not None:
            seen.setdefault(mapped, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BpaRule:
    id: str
    name: str
    category: str
    description: str
    severity: int  # 1=warning, 2=error, 3=info
    scope: str
    expression: str
    fix_expression: str | None = None
    compatibility_level: int = 1200

    @property
    def severity_label(self) -> str:
        return _SEVERITY_MAP.get(self.severity, "warning")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _parse_rules(data: list[dict[str, Any]]) -> list[BpaRule]:
    rules: list[BpaRule] = []
    for item in data:
        rules.append(
            BpaRule(
                id=item.get("ID", ""),
                name=item.get("Name", ""),
                category=item.get("Category", ""),
                description=item.get("Description", ""),
                severity=item.get("Severity", 1),
                scope=item.get("Scope", ""),
                expression=item.get("Expression", ""),
                fix_expression=item.get("FixExpression"),
                compatibility_level=item.get("CompatibilityLevel", 1200),
            )
        )
    return rules


def load_rules_from_file(path: str) -> list[BpaRule]:
    """Load BPA rules from a local BPARules.json file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "Rules" in data:
        data = data["Rules"]
    return _parse_rules(data)


def load_rules_from_url(url: str) -> list[BpaRule]:
    """Fetch BPA rules from a URL. Uses httpx if available, falls back to urllib."""
    try:
        import httpx  # type: ignore

        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

    if isinstance(data, dict) and "Rules" in data:
        data = data["Rules"]
    return _parse_rules(data)


# ---------------------------------------------------------------------------
# Object → evaluation context
#
# Each builder maps a backend object dict (camelCase keys) to the PascalCase
# property names BPA rules use. Property lookup is case-insensitive, so a single
# spelling suffices. Only properties we actually model are exposed; a rule that
# references anything else raises BpaUnsupported and is counted as skipped.
# ---------------------------------------------------------------------------


def _column_props(obj: dict[str, Any]) -> dict[str, Any]:
    # "Table" is wired as a navigable sub-object in _build_entries, not here.
    sort_by = obj.get("sortByColumn", "")
    return {
        "Name": obj.get("name", ""),
        "DataType": obj.get("dataType", ""),
        "IsHidden": bool(obj.get("isHidden", False)),
        "Description": obj.get("description", ""),
        "FormatString": obj.get("formatString", ""),
        "SummarizeBy": obj.get("summarizeBy", ""),
        "SourceColumn": obj.get("sourceColumn", ""),
        "Expression": obj.get("expression", ""),
        "DisplayFolder": obj.get("displayFolder", ""),
        "ObjectType": "Column",
        "DataCategory": obj.get("dataCategory", ""),
        "IsKey": bool(obj.get("isKey", False)),
        "IsAvailableInMDX": bool(obj.get("isAvailableInMDX", True)),
        # SortByColumn / AlternateOf are null when absent (rules compare to null).
        "SortByColumn": (sort_by or None),
        "Type": obj.get("columnType", "Data"),
        "AlternateOf": ("Aggregation" if obj.get("hasAlternateOf") else None),
    }


def _measure_props(obj: dict[str, Any]) -> dict[str, Any]:
    # "Table" is wired as a navigable sub-object in _build_entries, not here.
    table = obj.get("table", "")
    name = obj.get("name", "")
    return {
        "Name": name,
        "Expression": obj.get("expression", ""),
        "FormatString": obj.get("formatString", ""),
        "Description": obj.get("description", ""),
        "DisplayFolder": obj.get("displayFolder", ""),
        "IsHidden": bool(obj.get("isHidden", False)),
        "ObjectType": "Measure",
        "DaxObjectName": f"'{table}'[{name}]",
    }


def _table_props(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "Name": obj.get("name", ""),
        "IsHidden": bool(obj.get("isHidden", False)),
        "Description": obj.get("description", ""),
        "DataCategory": obj.get("dataCategory", ""),
        "IsCalculationGroup": bool(obj.get("isCalculationGroup", False)),
        "ObjectTypeName": obj.get("objectTypeName", "Table"),
        "ObjectType": "Table",
    }


def _partition_props(obj: dict[str, Any]) -> dict[str, Any]:
    ds_type = obj.get("dataSourceType", "")
    return {
        "Name": obj.get("name", ""),
        "Table": obj.get("table", ""),
        "Mode": obj.get("mode", ""),
        "Kind": obj.get("kind", ""),
        "Source": obj.get("source", ""),
        "State": obj.get("state", ""),
        "SourceType": obj.get("sourceType", "") or obj.get("kind", ""),
        "Query": obj.get("query", "") or obj.get("source", ""),
        # DataSource is a navigable sub-object: DataSource.Type
        "DataSource": BpaContext({"Type": ds_type, "Name": obj.get("dataSourceName", "")}),
    }


def _parse_endpoint(endpoint: str) -> tuple[str, str]:
    """Split a 'Table[Column]' (or ''Quoted Table''[Column]) endpoint.

    Returns (table, column); column is "" if there is no bracketed part.
    """
    endpoint = endpoint.strip()
    if endpoint.endswith("]") and "[" in endpoint:
        table, col = endpoint.rsplit("[", 1)
        col = col[:-1]
    else:
        table, col = endpoint, ""
    table = table.strip()
    if len(table) >= 2 and table[0] == "'" and table[-1] == "'":
        table = table[1:-1].replace("''", "'")
    return table, col


def _split_cardinality(cardinality: str) -> tuple[str, str]:
    """Derive (FromCardinality, ToCardinality) as 'Many'/'One' from a marker.

    Accepts TOM-style ('ManyToOne', 'OneToMany', 'ManyToMany', 'OneToOne') and
    short markers ('many', 'one'). Defaults to the standard many-to-one.
    """
    c = cardinality.strip().lower().replace("-", "").replace("_", "")
    if c in ("manytomany", "many:many", "m:m"):
        return "Many", "Many"
    if c in ("onetomany",):
        return "One", "Many"
    if c in ("onetoone", "one:one"):
        return "One", "One"
    if c in ("manytoone", "many", "", "many:one"):
        return "Many", "One"
    if c == "one":
        return "One", "Many"
    return "Many", "One"


def _relationship_context(obj: dict[str, Any]) -> BpaContext:
    """Build a navigable relationship context.

    Exposes From/To as sub-objects with ``Name`` (``FromColumn.Name``,
    ``FromTable.Name``, …), plus From/To cardinality, cross-filtering and active
    state — the shape BPA relationship rules navigate.
    """
    ft, fc = _parse_endpoint(obj.get("from", ""))
    tt, tc = _parse_endpoint(obj.get("to", ""))
    from_card, to_card = _split_cardinality(str(obj.get("cardinality", "")))
    cfb = obj.get("crossFilteringBehavior") or obj.get("crossFilteringBehaviour") or "OneDirection"
    return BpaContext(
        {
            "Name": f"{ft}[{fc}] -> {tt}[{tc}]",
            "FromTable": BpaContext({"Name": ft}),
            "FromColumn": BpaContext({"Name": fc, "Table": BpaContext({"Name": ft})}),
            "ToTable": BpaContext({"Name": tt}),
            "ToColumn": BpaContext({"Name": tc, "Table": BpaContext({"Name": tt})}),
            "FromCardinality": from_card,
            "ToCardinality": to_card,
            "CrossFilteringBehavior": cfb,
            "IsActive": bool(obj.get("isActive", True)),
        }
    )


_QUALIFIED_REF = re.compile(r"(?:'(?P<qt>[^']+)'|(?P<bt>[A-Za-z_]\w*))\s*\[(?P<qn>[^\]]+)\]")
_UNQUALIFIED_REF = re.compile(r"(?<![\w'\])])\[(?P<un>[^\]]+)\]")


def _call(backend: Any, method: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Call a backend enumeration method, tolerating missing methods/kwargs."""
    fn = getattr(backend, method, None)
    if fn is None:
        return []
    try:
        return list(fn(**kwargs))
    except TypeError:
        try:
            return list(fn())
        except Exception:
            return []
    except Exception:
        return []


def _depends_on(
    expression: str, measure_names: set[str], column_names: set[str]
) -> list[BpaContext]:
    """Approximate Tabular Editor's DependsOn from a DAX expression.

    Returns one entry per referenced object, each exposing ``Key.ObjectType`` and a
    ``Value`` collection of reference instances carrying ``FullyQualified``. Static
    parse: a ``Table[X]`` reference is fully qualified, a bare ``[X]`` is not; the
    name is classified as Measure or Column against the model's name sets.
    """
    grouped: dict[tuple[str, str], list[bool]] = {}
    for m in _QUALIFIED_REF.finditer(expression):
        name = m.group("qn")
        if name in measure_names:
            grouped.setdefault(("Measure", name), []).append(True)
        elif name in column_names:
            grouped.setdefault(("Column", name), []).append(True)
    for m in _UNQUALIFIED_REF.finditer(expression):
        name = m.group("un")
        if name in measure_names:
            grouped.setdefault(("Measure", name), []).append(False)
        elif name in column_names:
            grouped.setdefault(("Column", name), []).append(False)

    entries: list[BpaContext] = []
    for (obj_type, name), fqs in grouped.items():
        value = [BpaContext({"FullyQualified": fq, "ObjectType": obj_type}) for fq in fqs]
        entries.append(
            BpaContext(
                {"ObjectType": obj_type, "Name": name,
                 "Key": BpaContext({"ObjectType": obj_type, "Name": name})},
                {"Value": value},
            )
        )
    return entries


def _object_path(scope: str, obj: dict[str, Any]) -> str:
    """Build a human-readable object path string."""
    if scope in ("Column", "DataColumn", "CalculatedColumn", "CalculatedTableColumn",
                 "Measure"):
        return f"{obj.get('table', '?')}[{obj.get('name', '?')}]"
    if scope in ("Table", "CalculatedTable"):
        return obj.get("name", "?")
    if scope == "Relationship":
        return f"{obj.get('from', '?')} → {obj.get('to', '?')}"
    if scope == "Partition":
        return f"{obj.get('table', '?')}.{obj.get('name', '?')}"
    if scope == "CalculationGroup":
        return obj.get("table", obj.get("name", "?"))
    if scope in ("CalculationItem", "Role", "Perspective", "DataSource"):
        return obj.get("name", "?")
    if scope == "TablePermission":
        return f"{obj.get('table', '?')} (RLS)"
    if scope == "Model":
        return "Model"
    return str(obj)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class BpaEvaluator:
    """Evaluate a list of BpaRules against a backend and return violations."""

    def evaluate(
        self,
        rules: list[BpaRule],
        backend: Any,
        severity_filter: str | None = None,
        category_filter: str | None = None,
        vertipaq: Any = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run all rules against the backend.

        Args:
            vertipaq: optional :class:`~pbi_cli.governance.vertipaq.VertiPaqStats`.
                When provided, runtime-statistics rules (``GetAnnotation(...)``)
                are evaluated; otherwise they are honestly skipped.

        Returns:
            (violations, skipped_count)

        A rule is counted as *skipped* (not failed) when its expression cannot be
        parsed, references an unmodelled property, or uses a construct the
        evaluator does not implement — for any object in scope. Skipped rules
        produce no violations, so the result never contains partial findings.
        """
        entries_by_scope = self._build_entries(backend, vertipaq)

        violations: list[dict[str, Any]] = []
        skipped = 0

        for rule in rules:
            if severity_filter and rule.severity_label != severity_filter:
                continue
            if category_filter and rule.category.lower() != category_filter.lower():
                continue

            scopes = _map_scopes(rule.scope)
            if not scopes:
                skipped += 1
                continue

            try:
                compiled = compile_expression(rule.expression)
            except BpaUnsupported:
                skipped += 1
                continue

            rule_violations: list[dict[str, Any]] = []
            rule_skipped = False
            for scope in scopes:
                for obj, ctx in entries_by_scope.get(scope, []):
                    try:
                        # `current` resolves to the object under evaluation, even
                        # at the top level (not only inside .Any predicates).
                        violated = evaluate(compiled, ctx.bind_closures({"current": ctx}))
                    except BpaUnsupported:
                        rule_skipped = True
                        break
                    if violated:
                        rule_violations.append(self._make_violation(rule, obj, scope))
                if rule_skipped:
                    break

            if rule_skipped:
                skipped += 1
            else:
                violations.extend(rule_violations)

        return violations, skipped

    @staticmethod
    def _build_entries(
        backend: Any,
        vertipaq: Any = None,
    ) -> dict[str, list[tuple[dict[str, Any], BpaContext]]]:
        """Pre-fetch backend objects once and build (object, context) pairs per scope.

        Table and Model contexts carry child collections (Columns, Measures,
        Partitions, …) so LINQ-style rules like ``Columns.Any(IsKey)`` work. When
        ``vertipaq`` stats are supplied, VertiPaq annotations are attached so
        ``GetAnnotation(...)`` rules evaluate instead of skipping.
        """
        # BPA must see hidden objects too (many rules reason about IsHidden).
        columns = _call(backend, "column_list", include_hidden=True)
        tables = _call(backend, "table_list", include_hidden=True)
        measures = _call(backend, "measure_list")
        relationships = _call(backend, "relationship_list")
        partitions = _call(backend, "partition_list")

        # 1. Table contexts first, so columns/measures can navigate to them.
        tab_entries: list[tuple[dict[str, Any], BpaContext]] = [
            (t, BpaContext(_table_props(t))) for t in tables
        ]
        table_ctx_by_name: dict[str, BpaContext] = {
            t.get("name", ""): ctx for t, ctx in tab_entries
        }

        def _table_ref(name: str) -> BpaContext:
            return table_ctx_by_name.get(name) or BpaContext({"Name": name})

        # 2. Column / measure / partition contexts, with a navigable Table object.
        col_entries: list[tuple[dict[str, Any], BpaContext]] = []
        for c in columns:
            ctx = BpaContext(_column_props(c))
            ctx.set_prop("Table", _table_ref(c.get("table", "")))
            col_entries.append((c, ctx))
        meas_entries: list[tuple[dict[str, Any], BpaContext]] = []
        for m in measures:
            ctx = BpaContext(_measure_props(m))
            ctx.set_prop("Table", _table_ref(m.get("table", "")))
            meas_entries.append((m, ctx))
        part_entries = [(p, BpaContext(_partition_props(p))) for p in partitions]

        # 3. Relationship contexts + parsed endpoints (for the usage graph).
        rel_entries: list[tuple[dict[str, Any], BpaContext]] = []
        rel_endpoints: list[tuple[BpaContext, tuple[str, str], tuple[str, str]]] = []
        for r in relationships:
            ctx = _relationship_context(r)
            rel_entries.append((r, ctx))
            rel_endpoints.append(
                (ctx, _parse_endpoint(r.get("from", "")), _parse_endpoint(r.get("to", "")))
            )

        # 4. Group children by table; wire table collections.
        cols_by_table: dict[str, list[BpaContext]] = defaultdict(list)
        for c, cx in col_entries:
            cols_by_table[c.get("table", "")].append(cx)
        meas_by_table: dict[str, list[BpaContext]] = defaultdict(list)
        for m, cx in meas_entries:
            meas_by_table[m.get("table", "")].append(cx)
        parts_by_table: dict[str, list[BpaContext]] = defaultdict(list)
        for p, cx in part_entries:
            parts_by_table[p.get("table", "")].append(cx)
        for t, ctx in tab_entries:
            name = t.get("name", "")
            ctx.set_collection("Columns", cols_by_table.get(name, []))
            ctx.set_collection("Measures", meas_by_table.get(name, []))
            ctx.set_collection("Partitions", parts_by_table.get(name, []))

        # 5. UsedInRelationships graph — derived from the relationship endpoints.
        col_uir: dict[tuple[str, str], list[BpaContext]] = defaultdict(list)
        tab_uir: dict[str, list[BpaContext]] = defaultdict(list)
        for rel_ctx, (ft, fc), (tt, tc) in rel_endpoints:
            col_uir[(ft, fc)].append(rel_ctx)
            col_uir[(tt, tc)].append(rel_ctx)
            tab_uir[ft].append(rel_ctx)
            if tt != ft:
                tab_uir[tt].append(rel_ctx)
        for c, cx in col_entries:
            cx.set_collection(
                "UsedInRelationships", col_uir.get((c.get("table", ""), c.get("name", "")), [])
            )
        for t, cx in tab_entries:
            cx.set_collection("UsedInRelationships", tab_uir.get(t.get("name", ""), []))

        # 5b. Relationship endpoints -> real column contexts (FromColumn.DataType…)
        col_ctx_by_key = {(c.get("table", ""), c.get("name", "")): cx for c, cx in col_entries}
        for r, rctx in rel_entries:
            ft, fc = _parse_endpoint(r.get("from", ""))
            tt, tc = _parse_endpoint(r.get("to", ""))
            if (ft, fc) in col_ctx_by_key:
                rctx.set_prop("FromColumn", col_ctx_by_key[(ft, fc)])
            if (tt, tc) in col_ctx_by_key:
                rctx.set_prop("ToColumn", col_ctx_by_key[(tt, tc)])

        # 5c. Column usage collections: UsedInSortBy / UsedInHierarchies / UsedInVariations
        sortby_users: dict[tuple[str, str], list[BpaContext]] = defaultdict(list)
        for c, cx in col_entries:
            sb = c.get("sortByColumn", "")
            if sb:
                sortby_users[(c.get("table", ""), sb)].append(cx)
        hier_cols: dict[tuple[str, str], list[BpaContext]] = defaultdict(list)
        for h in _call(backend, "hierarchy_list"):
            for lv in h.get("levels", []):
                col = lv.get("column", "")
                if col:
                    hier_cols[(h.get("table", ""), col)].append(
                        BpaContext({"Name": h.get("name", "")})
                    )
        for c, cx in col_entries:
            key = (c.get("table", ""), c.get("name", ""))
            cx.set_collection("UsedInSortBy", sortby_users.get(key, []))
            cx.set_collection("UsedInHierarchies", hier_cols.get(key, []))
            cx.set_collection("UsedInVariations", [])

        # 5d. DAX dependency graph: DependsOn (measures + calc columns) + ReferencedBy
        measure_names = {m.get("name", "") for m in measures}
        column_names = {c.get("name", "") for c in columns}
        ref_by_column: dict[str, list[BpaContext]] = defaultdict(list)
        ref_by_measure: dict[str, list[BpaContext]] = defaultdict(list)
        for m, mx in meas_entries:
            deps = _depends_on(m.get("expression", ""), measure_names, column_names)
            mx.set_collection("DependsOn", deps)
            for entry in deps:
                if entry.get_prop("ObjectType") == "Column":
                    ref_by_column[entry.get_prop("Name")].append(mx)
                else:
                    ref_by_measure[entry.get_prop("Name")].append(mx)
        for c, cx in col_entries:
            expr = c.get("expression", "")
            cx.set_collection(
                "DependsOn",
                _depends_on(expr, measure_names, column_names) if expr else [],
            )
        for c, cx in col_entries:
            refs = ref_by_column.get(c.get("name", ""), [])
            cx.set_prop("ReferencedBy", BpaContext({"Count": len(refs)},
                                                  {"AllMeasures": refs, "Value": refs}))
        for m, mx in meas_entries:
            refs = ref_by_measure.get(m.get("name", ""), [])
            mx.set_prop("ReferencedBy", BpaContext({"Count": len(refs)},
                                                  {"AllMeasures": refs, "Value": refs}))

        # 5e. Object-type scopes: calc groups/items, roles, table permissions, RLS,
        # perspectives, data sources.
        cg_entries: list[tuple[dict[str, Any], BpaContext]] = []
        ci_entries: list[tuple[dict[str, Any], BpaContext]] = []
        all_calc_items: list[BpaContext] = []
        for cg in _call(backend, "calc_group_list"):
            items = cg.get("items", [])
            item_ctxs = [
                BpaContext({"Name": it.get("name", ""), "Expression": it.get("expression", ""),
                            "ObjectType": "CalculationItem"})
                for it in items
            ]
            all_calc_items.extend(item_ctxs)
            ci_entries.extend(zip(items, item_ctxs))
            cg_entries.append(
                (cg, BpaContext({"Name": cg.get("table", "")}, {"CalculationItems": item_ctxs}))
            )

        role_entries: list[tuple[dict[str, Any], BpaContext]] = []
        tp_entries: list[tuple[dict[str, Any], BpaContext]] = []
        rls_by_table: dict[str, list[str]] = defaultdict(list)
        for role in _call(backend, "role_list"):
            members = [BpaContext({}) for _ in range(int(role.get("memberCount", 0)))]
            role_entries.append((role, BpaContext({"Name": role.get("name", "")},
                                                  {"Members": members})))
            for tp in role.get("tablePermissions", []):
                expr = tp.get("filterExpression", "")
                if expr:
                    rls_by_table[tp.get("table", "")].append(expr)
                    tp_entries.append((tp, BpaContext({"Name": tp.get("table", ""),
                                                       "Expression": expr})))
        for t, cx in tab_entries:
            cx.set_collection("RowLevelSecurity", rls_by_table.get(t.get("name", ""), []))

        persp_entries = [
            (p, BpaContext(
                {"Name": p.get("name", "")},
                {"Objects": [BpaContext({}) for _ in range(int(p.get("objectCount", 0)))]},
            ))
            for p in _call(backend, "perspective_list")
        ]
        ds_entries = [
            (d, BpaContext({"Name": d.get("name", ""), "Type": d.get("type", "")},
                           {"UsedByPartitions": []}))
            for d in _call(backend, "datasource_list")
        ]

        # 5f. Normalize properties that multi-type-scope rules expect on every
        # object (e.g. AVOID_INVALID_DESCRIPTION_CHARACTERS spans many types;
        # DAX_MEASURES_UNQUALIFIED scopes include CalculatedTable -> Table).
        for _, cx in (*part_entries, *cg_entries, *ci_entries, *role_entries,
                      *tp_entries, *persp_entries, *ds_entries):
            cx.set_prop("Description", "")
        for _, cx in (*tab_entries, *ci_entries):
            cx.set_collection("DependsOn", [])

        # 6. Model context + Model back-reference on every object.
        all_columns = [cx for _, cx in col_entries]
        all_measures = [cx for _, cx in meas_entries]
        all_tables = [cx for _, cx in tab_entries]
        all_relationships = [cx for _, cx in rel_entries]
        all_partitions = [cx for _, cx in part_entries]
        model_info: dict[str, Any] = {}
        try:
            model_info = backend.model_info() or {}
        except Exception:
            model_info = {}
        model_ctx = BpaContext(
            {
                "Name": "Model",
                "ObjectType": "Model",
                "DefaultPowerBIDataSourceVersion": model_info.get(
                    "defaultPowerBIDataSourceVersion", "PowerBI_V3"
                ),
            },
            {
                "Tables": all_tables,
                "Columns": all_columns,
                "AllColumns": all_columns,
                "Measures": all_measures,
                "AllMeasures": all_measures,
                "Relationships": all_relationships,
                "AllPartitions": all_partitions,
                "AllCalculationItems": all_calc_items,
                "Roles": [cx for _, cx in role_entries],
                "Perspectives": [cx for _, cx in persp_entries],
            },
        )
        model_ctx.set_prop("Model", model_ctx)
        for _, cx in (*col_entries, *meas_entries, *tab_entries, *rel_entries,
                      *cg_entries, *ci_entries, *role_entries, *tp_entries,
                      *persp_entries, *ds_entries):
            cx.set_prop("Model", model_ctx)

        # 7. VertiPaq annotations (GetAnnotation). A dict (even empty) marks stats
        # as collected; without it GetAnnotation rules skip honestly.
        if vertipaq is not None:
            for t, cx in tab_entries:
                cx.set_annotations(vertipaq.tables.get(t.get("name", ""), {}))
            for c, cx in col_entries:
                cx.set_annotations(
                    vertipaq.columns.get((c.get("table", ""), c.get("name", "")), {})
                )
            for r, cx in rel_entries:
                cx.set_annotations(
                    vertipaq.relationships.get((r.get("from", ""), r.get("to", "")), {})
                )
            for _, cx in (*meas_entries, *part_entries):
                cx.set_annotations({})

        # Column / table sub-type buckets for type-aware scoping.
        def _col_type(c: dict[str, Any]) -> str:
            return c.get("columnType") or ("Calculated" if c.get("expression") else "Data")

        data_cols = [(c, cx) for c, cx in col_entries if _col_type(c) == "Data"]
        calc_cols = [(c, cx) for c, cx in col_entries if _col_type(c) == "Calculated"]
        calc_table_cols = [
            (c, cx) for c, cx in col_entries if _col_type(c) == "CalculatedTableColumn"
        ]
        calc_tables = [
            (t, cx) for t, cx in tab_entries
            if t.get("objectTypeName") == "Calculated Table"
        ]

        return {
            "Column": col_entries,
            "DataColumn": data_cols,
            "CalculatedColumn": calc_cols,
            "CalculatedTableColumn": calc_table_cols,
            "Table": tab_entries,
            "CalculatedTable": calc_tables,
            "Measure": meas_entries,
            "Relationship": rel_entries,
            "Partition": part_entries,
            "CalculationGroup": cg_entries,
            "CalculationItem": ci_entries,
            "Role": role_entries,
            "TablePermission": tp_entries,
            "Perspective": persp_entries,
            "DataSource": ds_entries,
            "Model": [({"name": "Model"}, model_ctx)],
        }

    @staticmethod
    def _make_violation(rule: BpaRule, obj: dict[str, Any], scope: str) -> dict[str, Any]:
        return {
            "rule": f"bpa.{rule.id.lower()}",
            "bpa_id": rule.id,
            "object": _object_path(scope, obj),
            "message": rule.name,
            "description": rule.description,
            "severity": rule.severity_label,
            "category": rule.category,
            "autoFixable": False,
        }
