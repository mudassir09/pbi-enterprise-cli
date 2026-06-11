"""PBIR report analysis: lint, field usage, semantic diff, accessibility audit.

Operates on PBIR GA folders ({Name}.Report/definition/pages/...) read raw,
so it works on any OS with no Desktop. Field extraction walks the visual
query JSON for Column/Measure/HierarchyLevel references.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIELD_KINDS = ("Column", "Measure", "HierarchyLevel", "Aggregation")


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a PBIR GA report folder into a plain structure for analysis."""
    p = Path(path)
    if p.is_file() and p.suffix == ".pbip":
        p = p.parent
    report_dirs = [p] if p.name.endswith(".Report") else sorted(p.glob("*.Report"))
    if not report_dirs:
        raise FileNotFoundError(f"No *.Report folder found in {p}.")
    report_dir = report_dirs[0]
    pages_dir = report_dir / "definition" / "pages"
    pages: list[dict[str, Any]] = []
    if pages_dir.is_dir():
        for page_dir in sorted(d for d in pages_dir.iterdir() if d.is_dir()):
            page_json = {}
            pj = page_dir / "page.json"
            if pj.exists():
                page_json = json.loads(pj.read_text(encoding="utf-8"))
            visuals = []
            vd = page_dir / "visuals"
            if vd.is_dir():
                for vdir in sorted(d for d in vd.iterdir() if d.is_dir()):
                    vj = vdir / "visual.json"
                    if vj.exists():
                        visuals.append(json.loads(vj.read_text(encoding="utf-8")))
            pages.append({
                "name": page_dir.name,
                "displayName": page_json.get("displayName", page_dir.name),
                "pageJson": page_json,
                "visuals": visuals,
            })
    return {"reportDir": str(report_dir), "pages": pages}


def extract_fields(obj: Any) -> set[tuple[str, str, str]]:
    """Collect (entity, property, kind) field references from PBIR JSON."""
    found: set[tuple[str, str, str]] = set()

    def _entity_of(expr: Any) -> str:
        if isinstance(expr, dict):
            source = expr.get("SourceRef") or {}
            return source.get("Entity") or source.get("Source") or ""
        return ""

    def walk(node: Any, parent_key: str = "") -> None:
        if isinstance(node, dict):
            if "Property" in node and "Expression" in node:
                kind = parent_key if parent_key in _FIELD_KINDS else "Column"
                found.add((_entity_of(node["Expression"]), str(node["Property"]), kind))
            for key, value in node.items():
                walk(value, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, parent_key)

    walk(obj)
    return found


def _visual_alt_text(visual: dict[str, Any]) -> str:
    vco = visual.get("visual", {}).get("visualContainerObjects", {})
    for entry in vco.get("general", []):
        alt = entry.get("properties", {}).get("altText", {})
        literal = alt.get("expr", {}).get("Literal", {}).get("Value", "")
        if literal:
            return str(literal).strip("'")
    return ""


def _visual_title(visual: dict[str, Any]) -> bool:
    vco = visual.get("visual", {}).get("visualContainerObjects", {})
    return bool(vco.get("title"))


_DECORATIVE_TYPES = {"shape", "image", "textbox", "actionButton", "basicShape"}


def lint_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Report-layer lint rules, mirroring govern check's violation shape."""
    violations: list[dict[str, Any]] = []

    def add(rule: str, severity: str, obj: str, message: str) -> None:
        violations.append({"rule": rule, "severity": severity, "object": obj,
                           "message": message})

    pages = report["pages"]
    if len(pages) > 10:
        add("report.too-many-pages", "info", "Report",
            f"{len(pages)} pages — consider splitting or using drillthrough.")

    for page in pages:
        pname = page["displayName"]
        visuals = page["visuals"]
        if not visuals:
            add("report.empty-page", "info", f"Page '{pname}'", "Page has no visuals.")
        if len(visuals) > 16:
            add("report.too-many-visuals", "warning", f"Page '{pname}'",
                f"{len(visuals)} visuals — more than ~16 hurts render time and readability.")
        if pname.lower().startswith(("page 1", "page 2", "page ")):
            add("report.default-page-name", "info", f"Page '{pname}'",
                "Page still has a default name.")

        boxes = []
        for v in visuals:
            vname = v.get("name", "?")
            vtype = v.get("visual", {}).get("visualType", "")
            obj = f"Visual '{vname}' ({vtype}) on '{pname}'"
            if v.get("isHidden"):
                add("report.hidden-visual", "info", obj,
                    "Hidden visual still renders queries — delete it if unused.")
            if vtype not in _DECORATIVE_TYPES and not _visual_alt_text(v):
                add("report.missing-alt-text", "warning", obj,
                    "No alt text — screen readers cannot describe this visual.")
            pos = v.get("position", {})
            if pos:
                boxes.append((obj, pos.get("x", 0), pos.get("y", 0),
                              pos.get("width", 0), pos.get("height", 0)))

        for i, (obj_a, ax, ay, aw, ah) in enumerate(boxes):
            for obj_b, bx, by, bw, bh in boxes[i + 1:]:
                overlap_w = min(ax + aw, bx + bw) - max(ax, bx)
                overlap_h = min(ay + ah, by + bh) - max(ay, by)
                if overlap_w > 0 and overlap_h > 0:
                    area = overlap_w * overlap_h
                    if area > 0.5 * min(aw * ah or 1, bw * bh or 1):
                        add("report.overlapping-visuals", "warning", obj_a,
                            f"Overlaps more than 50% with {obj_b}.")
    return violations


def field_usage(
    report: dict[str, Any],
    columns: list[dict[str, Any]],
    measures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cross-reference model fields against report usage. Returns used/unused."""
    used: set[tuple[str, str]] = set()
    for page in report["pages"]:
        for source in [page["pageJson"], *page["visuals"]]:
            used |= {(e, p) for e, p, _ in extract_fields(source)}

    # Measures referenced from other measures' DAX still count as used
    dax_refs: set[str] = set()
    for m in measures:
        import re

        for ref in re.findall(r"\[([^\]]+)\]", m.get("expression", "")):
            dax_refs.add(ref)

    used_props = {p for _, p in used}
    unused_columns = [
        f"{c['table']}[{c['name']}]"
        for c in columns
        if (c["table"], c["name"]) not in used
        and c["name"] not in used_props
        and not c.get("isHidden")
    ]
    unused_measures = [
        f"{m['table']}[{m['name']}]"
        for m in measures
        if (m["table"], m["name"]) not in used
        and m["name"] not in used_props
        and m["name"] not in dax_refs
    ]
    return {
        "fields_used_in_report": sorted(f"{e}[{p}]" for e, p in used if e or p),
        "unused_columns": unused_columns,
        "unused_measures": unused_measures,
    }


def diff_reports(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Semantic visual-level diff between two report versions."""
    changes: list[dict[str, str]] = []
    old_pages = {p["displayName"]: p for p in old["pages"]}
    new_pages = {p["displayName"]: p for p in new["pages"]}

    for name in sorted(set(old_pages) - set(new_pages)):
        changes.append({"change": "page-removed", "object": f"Page '{name}'", "detail": ""})
    for name in sorted(set(new_pages) - set(old_pages)):
        changes.append({"change": "page-added", "object": f"Page '{name}'", "detail": ""})

    for name in sorted(set(old_pages) & set(new_pages)):
        old_vis = {v.get("name"): v for v in old_pages[name]["visuals"]}
        new_vis = {v.get("name"): v for v in new_pages[name]["visuals"]}
        for vid in sorted(set(old_vis) - set(new_vis)):
            vtype = old_vis[vid].get("visual", {}).get("visualType", "")
            changes.append({"change": "visual-removed",
                            "object": f"{vtype} '{vid}' on '{name}'", "detail": ""})
        for vid in sorted(set(new_vis) - set(old_vis)):
            vtype = new_vis[vid].get("visual", {}).get("visualType", "")
            changes.append({"change": "visual-added",
                            "object": f"{vtype} '{vid}' on '{name}'", "detail": ""})
        for vid in sorted(set(old_vis) & set(new_vis)):
            ov, nv = old_vis[vid], new_vis[vid]
            obj = f"'{vid}' on '{name}'"
            ot = ov.get("visual", {}).get("visualType", "")
            nt = nv.get("visual", {}).get("visualType", "")
            if ot != nt:
                changes.append({"change": "visual-type-changed", "object": obj,
                                "detail": f"{ot} → {nt}"})
            if ov.get("position") != nv.get("position"):
                changes.append({"change": "visual-moved-or-resized", "object": obj,
                                "detail": ""})
            old_fields = extract_fields(ov)
            new_fields = extract_fields(nv)
            for e, p, _ in sorted(old_fields - new_fields):
                changes.append({"change": "field-removed", "object": obj,
                                "detail": f"{e}[{p}]"})
            for e, p, _ in sorted(new_fields - old_fields):
                changes.append({"change": "field-added", "object": obj,
                                "detail": f"{e}[{p}]"})
    return {"changes": changes, "has_changes": bool(changes)}


def a11y_check(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Accessibility audit: alt text, tab order, titles."""
    findings: list[dict[str, Any]] = []
    for page in report["pages"]:
        pname = page["displayName"]
        tab_orders = []
        for v in page["visuals"]:
            vname = v.get("name", "?")
            vtype = v.get("visual", {}).get("visualType", "")
            obj = f"Visual '{vname}' ({vtype}) on '{pname}'"
            if vtype not in _DECORATIVE_TYPES:
                if not _visual_alt_text(v):
                    findings.append({"rule": "a11y.alt-text", "severity": "warning",
                                     "object": obj, "message": "Missing alt text."})
                if not _visual_title(v):
                    findings.append({"rule": "a11y.title", "severity": "info",
                                     "object": obj,
                                     "message": "No visible title configured."})
            tab_orders.append(v.get("position", {}).get("tabOrder"))
        if len(page["visuals"]) > 1 and all(t is None for t in tab_orders):
            findings.append({"rule": "a11y.tab-order", "severity": "warning",
                             "object": f"Page '{pname}'",
                             "message": "No explicit tab order — keyboard navigation will "
                                        "follow z-order, which rarely matches reading order."})
    return findings
