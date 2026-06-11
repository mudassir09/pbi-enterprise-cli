"""Semantic model diff: compare two model states object-by-object.

Used by `pbi diff` (two TMDL folders / git refs) and `pbi env drift`
(git TMDL vs a live workspace). Output is human-readable change records,
not raw text diffs.
"""

from __future__ import annotations

from typing import Any


def snapshot_state(backend: Any) -> dict[str, Any]:
    """Capture the comparable state of a model from any backend."""
    return {
        "tables": {t["name"]: t for t in backend.table_list()},
        "columns": {f"{c['table']}[{c['name']}]": c for c in backend.column_list()},
        "measures": {f"{m['table']}[{m['name']}]": m for m in backend.measure_list()},
        "relationships": {
            f"{r.get('from', '')} -> {r.get('to', '')}": r
            for r in backend.relationship_list()
        },
        "roles": {r["name"]: r for r in backend.role_list()}
        if hasattr(backend, "role_list") else {},
    }


_COMPARED_PROPS = {
    "measures": ("expression", "formatString", "description", "displayFolder", "isHidden"),
    "columns": ("dataType", "isHidden", "formatString", "summarizeBy"),
    "tables": ("isHidden",),
    "relationships": ("cardinality", "isActive"),
    "roles": ("modelPermission", "tablePermissions"),
}


def semantic_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshot_state() results. Returns structured change records."""
    changes: list[dict[str, str]] = []
    for kind in ("tables", "columns", "measures", "relationships", "roles"):
        old_objs = old.get(kind, {})
        new_objs = new.get(kind, {})
        singular = kind.rstrip("s") if kind != "roles" else "role"

        for key in sorted(set(old_objs) - set(new_objs)):
            changes.append({"change": f"{singular}-removed", "object": key, "detail": ""})
        for key in sorted(set(new_objs) - set(old_objs)):
            changes.append({"change": f"{singular}-added", "object": key, "detail": ""})
        for key in sorted(set(old_objs) & set(new_objs)):
            for prop in _COMPARED_PROPS.get(kind, ()):
                ov = old_objs[key].get(prop)
                nv = new_objs[key].get(prop)
                if _normalize(ov) != _normalize(nv):
                    detail = f"{prop}: {_short(ov)} → {_short(nv)}"
                    changes.append({"change": f"{singular}-changed", "object": key,
                                    "detail": detail})
    return {
        "changes": changes,
        "has_changes": bool(changes),
        "summary": _summarize(changes),
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _short(value: Any, limit: int = 60) -> str:
    text = " ".join(str(value).split()) if value is not None else "(none)"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _summarize(changes: list[dict[str, str]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for c in changes:
        summary[c["change"]] = summary.get(c["change"], 0) + 1
    return summary


def to_release_notes(diff: dict[str, Any], title: str = "Model changes") -> str:
    """Render a semantic diff as markdown release notes."""
    if not diff["has_changes"]:
        return f"## {title}\n\nNo model changes."
    lines = [f"## {title}", ""]
    by_change: dict[str, list[dict[str, str]]] = {}
    for c in diff["changes"]:
        by_change.setdefault(c["change"], []).append(c)
    for change, items in sorted(by_change.items()):
        lines.append(f"### {change.replace('-', ' ').title()} ({len(items)})")
        for item in items:
            detail = f" — {item['detail']}" if item["detail"] else ""
            lines.append(f"- `{item['object']}`{detail}")
        lines.append("")
    return "\n".join(lines).rstrip()
