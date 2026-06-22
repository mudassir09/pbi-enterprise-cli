"""PBIR structural + referential validation.

The schema registry in :mod:`pbi_cli.backends.pbir_schemas` records the *current*
published schema versions, but nothing checked that the files we (and Desktop)
write actually conform. Pulling the live JSON Schemas would add a network
dependency and the ``jsonschema`` package; more importantly, the rules that
actually break a report at *reload* time are runtime-validator rules that the
published JSON Schemas don't even express (e.g. "no ``$schema`` inside an embedded
``filterConfig``" — verified live, see :mod:`pbi_cli.intelligence.filter_builder`).

So this module validates the invariants we've reverse-engineered and verified
against Power BI Desktop, plus referential integrity across the file set. It runs
fully offline on any OS with no Desktop, mirroring :mod:`pbi_cli.pbir_analysis`.

Each finding is ``{rule, severity, object, message}`` (same shape as
``pbir_analysis.lint_report``). Severity is ``error`` | ``warning`` | ``info``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pbi_cli.backends import pbir_schemas as _schemas

_NAME_RE = re.compile(r"^[\w-]+$")

# Map a published $schema URL back to (name, version) so we can flag drift.
_SCHEMA_URL_RE = re.compile(
    r"/fabric/item/report/definition/(?P<name>[A-Za-z0-9]+)/(?P<version>[\d.]+)/schema\.json$"
)


def _finding(rule: str, severity: str, obj: str, message: str) -> dict[str, str]:
    return {"rule": rule, "severity": severity, "object": obj, "message": message}


def _report_dir(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file() and p.suffix == ".pbip":
        p = p.parent
    if p.name.endswith(".Report"):
        return p
    dirs = sorted(p.glob("*.Report"))
    if not dirs:
        raise FileNotFoundError(f"No *.Report folder found in {p}.")
    return dirs[0]


def _load_json(path: Path, findings: list[dict[str, str]], obj: str) -> dict[str, Any] | None:
    """Parse a JSON file, recording a blocking finding on malformed JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(_finding("pbir.invalid-json", "error", obj, f"Cannot parse: {exc}"))
        return None


def _check_schema_url(
    data: dict[str, Any], expected: str, findings: list[dict[str, str]], obj: str
) -> None:
    """Flag a missing/unknown/drifted ``$schema`` against the registry value."""
    url = data.get("$schema")
    if not url:
        findings.append(
            _finding("pbir.missing-schema", "warning", obj, "No $schema URL — editors lose validation hints.")  # noqa: E501
        )
        return
    m = _SCHEMA_URL_RE.search(url)
    em = _SCHEMA_URL_RE.search(expected)
    if not m:
        findings.append(
            _finding("pbir.unknown-schema", "warning", obj, f"Unrecognised $schema: {url}")
        )
        return
    if em and m.group("name") == em.group("name") and m.group("version") != em.group("version"):
        findings.append(
            _finding(
                "pbir.schema-version-drift", "info", obj,
                f"{m.group('name')} schema is v{m.group('version')}; "
                f"registry expects v{em.group('version')}.",
            )
        )


def _check_filter_config(
    container: dict[str, Any], findings: list[dict[str, str]], obj: str
) -> None:
    """Validate an embedded filterConfig against the rules Desktop enforces at reload.

    1. It must not carry a ``$schema`` key (Desktop rejects it).
    2. Each filter's ``field`` Column/Measure must reference a table — its
       ``Expression.SourceRef`` needs an ``Entity`` or ``Source``. An empty
       SourceRef ("invalid value", verified live) blocks the report from opening.
    """
    fc = container.get("filterConfig")
    if not isinstance(fc, dict):
        return
    if "$schema" in fc:
        findings.append(
            _finding(
                "pbir.filterconfig-schema", "error", obj,
                "Embedded filterConfig carries a $schema key — Power BI Desktop "
                "rejects this at reload ('additional property $schema').",
            )
        )
    for i, flt in enumerate(fc.get("filters", [])):
        field = flt.get("field", {})
        node = field.get("Column") or field.get("Measure")
        if not isinstance(node, dict):
            continue
        srcref = node.get("Expression", {}).get("SourceRef", {})
        if not (srcref.get("Entity") or srcref.get("Source")):
            findings.append(
                _finding(
                    "pbir.filter-field-sourceref", "error", obj,
                    f"filterConfig.filters[{i}].field SourceRef has neither Entity nor "
                    "Source — Power BI Desktop reports an invalid value and will not open "
                    "the report.",
                )
            )
        elif srcref.get("Source") and not srcref.get("Entity"):
            findings.append(
                _finding(
                    "pbir.filter-field-alias", "warning", obj,
                    f"filterConfig.filters[{i}].field SourceRef uses a query alias "
                    f"('Source': {srcref['Source']!r}) instead of a table ('Entity'). "
                    "Desktop cannot resolve an alias here and rewrites it to an empty, "
                    "report-blocking SourceRef on its next save — use Entity.",
                )
            )


def validate_report(path: str | Path) -> list[dict[str, str]]:
    """Validate a PBIR GA report folder. Returns a list of findings (possibly empty)."""
    report_dir = _report_dir(path)
    findings: list[dict[str, str]] = []

    definition = report_dir / "definition"
    if not definition.is_dir():
        findings.append(
            _finding(
                "pbir.not-ga", "error", str(report_dir),
                "No definition/ folder — only PBIR GA reports can be validated. "
                "Re-save as a Power BI project (.pbip) in a current Desktop.",
            )
        )
        return findings

    # ── report.json ────────────────────────────────────────────────────────────
    report_json = definition / "report.json"
    if not report_json.exists():
        findings.append(_finding("pbir.missing-report-json", "error", "report.json",
                                 "definition/report.json is missing."))
    else:
        data = _load_json(report_json, findings, "report.json")
        if data is not None:
            _check_schema_url(data, _schemas.definition_schema("report"), findings, "report.json")
            _check_filter_config(data, findings, "report.json (report-level filters)")

    # ── pages ───────────────────────────────────────────────────────────────────
    pages_dir = definition / "pages"
    page_ids: dict[str, str] = {}  # id -> displayName
    display_counts: dict[str, int] = {}
    page_visuals: dict[str, set[str]] = {}

    if pages_dir.is_dir():
        order_meta = _load_json(pages_dir / "pages.json", findings, "pages.json") \
            if (pages_dir / "pages.json").exists() else {}
        order_meta = order_meta or {}

        for page_dir in sorted(d for d in pages_dir.iterdir() if d.is_dir()):
            pj = page_dir / "page.json"
            obj = f"Page folder '{page_dir.name}'"
            if not pj.exists():
                findings.append(_finding("pbir.page-missing-json", "error", obj,
                                         "Folder has no page.json."))
                continue
            data = _load_json(pj, findings, obj)
            if data is None:
                continue
            pid = data.get("name", "")
            disp = data.get("displayName", page_dir.name)
            obj = f"Page '{disp}'"
            _check_schema_url(data, _schemas.definition_schema("page"), findings, obj)
            _check_filter_config(data, findings, f"{obj} (page filters)")
            if not pid:
                findings.append(
                    _finding("pbir.page-no-name", "error", obj, "page.json has no name.")
                )
            elif not _NAME_RE.match(pid):
                findings.append(_finding(
                    "pbir.bad-name", "error", obj,
                    f"Page name '{pid}' is not a valid PBIR id (word chars/hyphens).",
                ))
            if pid and pid != page_dir.name:
                findings.append(_finding("pbir.page-name-mismatch", "warning", obj,
                                         f"page.json name '{pid}' != folder '{page_dir.name}'."))
            page_ids[pid] = disp
            display_counts[disp] = display_counts.get(disp, 0) + 1

            # Drillthrough pages need a drillthrough field.
            if data.get("pageType") == "Drillthrough" and not data.get("drillthroughFields"):
                findings.append(_finding("pbir.drillthrough-no-field", "warning", obj,
                                         "Drillthrough page has no drillthroughFields — drill target is undefined."))  # noqa: E501

            # Visuals on this page.
            vids: set[str] = set()
            group_ids: set[str] = set()
            vd = page_dir / "visuals"
            if vd.is_dir():
                for vdir in sorted(d for d in vd.iterdir() if d.is_dir()):
                    vj = vdir / "visual.json"
                    vobj = f"Visual '{vdir.name}' on '{disp}'"
                    if not vj.exists():
                        findings.append(_finding("pbir.visual-missing-json", "error", vobj,
                                                 "Folder has no visual.json."))
                        continue
                    vdata = _load_json(vj, findings, vobj)
                    if vdata is None:
                        continue
                    _check_schema_url(vdata, _schemas.definition_schema("visualContainer"),
                                      findings, vobj)
                    _check_filter_config(vdata, findings, f"{vobj} (visual filters)")
                    vname = vdata.get("name", "")
                    if not vname:
                        findings.append(_finding("pbir.visual-no-name", "error", vobj,
                                                 "visual.json has no name."))
                    elif vname in vids:
                        findings.append(_finding("pbir.duplicate-visual", "error", vobj,
                                                 f"Duplicate visual name '{vname}' on the page."))
                    vids.add(vname or vdir.name)
                    if "position" not in vdata:
                        findings.append(_finding("pbir.visual-no-position", "warning", vobj,
                                                 "visual.json has no position block."))
                    is_group = "visualGroup" in vdata
                    if is_group:
                        group_ids.add(vname or vdir.name)
                    elif "visual" not in vdata:
                        findings.append(_finding("pbir.visual-no-body", "error", vobj,
                                                 "visual.json has neither a 'visual' nor 'visualGroup' block."))  # noqa: E501
                # Second pass: parentGroupName must resolve to a group on the page.
                for vdir in sorted(d for d in vd.iterdir() if d.is_dir()):
                    vj = vdir / "visual.json"
                    if not vj.exists():
                        continue
                    vdata = _load_json(vj, [], "")  # already reported above
                    if not vdata:
                        continue
                    parent = vdata.get("parentGroupName")
                    if parent and parent not in group_ids:
                        findings.append(_finding(
                            "pbir.dangling-group-ref", "error",
                            f"Visual '{vdir.name}' on '{disp}'",
                            f"parentGroupName '{parent}' has no matching group on the page.",
                        ))
            page_visuals[disp] = vids

            # visualInteractions must reference visuals that exist on the page.
            for inter in data.get("visualInteractions", []):
                for slot in ("source", "target"):
                    ref = inter.get(slot)
                    if ref and ref not in vids:
                        findings.append(_finding(
                            "pbir.dangling-interaction", "warning", obj,
                            f"visualInteraction {slot} '{ref}' is not a visual on this page.",
                        ))

        # pages.json order references.
        for pid in order_meta.get("pageOrder", []):
            if pid not in page_ids:
                findings.append(_finding("pbir.dangling-page-order", "warning", "pages.json",
                                         f"pageOrder references unknown page id '{pid}'."))
        active = order_meta.get("activePageName")
        if active and active not in page_ids:
            findings.append(_finding("pbir.dangling-active-page", "warning", "pages.json",
                                     f"activePageName '{active}' is not a known page."))
        for disp, n in display_counts.items():
            if n > 1:
                findings.append(_finding("pbir.duplicate-page-name", "warning", f"Page '{disp}'",
                                         f"{n} pages share the display name '{disp}'."))

    # ── bookmarks ────────────────────────────────────────────────────────────────
    bdir = definition / "bookmarks"
    if bdir.is_dir():
        file_ids: set[str] = set()
        for entry in sorted(bdir.iterdir()):
            if not entry.is_file() or not entry.name.endswith(".bookmark.json"):
                continue
            obj = f"Bookmark file '{entry.name}'"
            data = _load_json(entry, findings, obj)
            if data is None:
                continue
            _check_schema_url(data, _schemas.definition_schema("bookmark"), findings, obj)
            bid = data.get("name", "")
            disp = data.get("displayName", bid)
            obj = f"Bookmark '{disp}'"
            file_ids.add(bid)
            if not data.get("explorationState"):
                findings.append(_finding("pbir.bookmark-no-state", "warning", obj,
                                         "No explorationState — Desktop may strip this bookmark."))
            active_section = data.get("explorationState", {}).get("activeSection")
            if active_section and active_section not in page_ids:
                findings.append(_finding("pbir.bookmark-dangling-page", "warning", obj,
                                         f"explorationState.activeSection '{active_section}' is not a known page."))  # noqa: E501

        meta = _load_json(bdir / "bookmarks.json", findings, "bookmarks.json") \
            if (bdir / "bookmarks.json").exists() else {}
        for item in (meta or {}).get("items", []):
            iid = item.get("name")
            if iid and iid not in file_ids and "children" not in item:
                findings.append(_finding("pbir.dangling-bookmark", "warning", "bookmarks.json",
                                         f"items references unknown bookmark id '{iid}'."))
            for child in item.get("children", []):
                cid = child.get("name")
                if cid and cid not in file_ids:
                    findings.append(_finding("pbir.dangling-bookmark-child", "warning", "bookmarks.json",  # noqa: E501
                                             f"group '{item.get('displayName', iid)}' references unknown bookmark '{cid}'."))  # noqa: E501

    return findings
