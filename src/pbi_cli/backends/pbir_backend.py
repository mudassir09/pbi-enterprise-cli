"""PBIR backend — reads and writes Power BI Project (.pbip) report files.

Supports two formats:
  - PBIR GA  (new): {Name}.Report/definition/pages/{Page}/visuals/{id}.visual/visual.json
  - Old PBIP (legacy): {Name}.Report/report.json with embedded visualContainers
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from pbi_cli.backends import pbir_schemas as _schemas


def _slug(name: str) -> str:
    """Sanitise a display name for use as a directory name."""
    return re.sub(r"[^\w\- ]", "", name).strip().replace(" ", "_")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class PbirBackend:
    """Read/write Power BI report JSON files in a .pbip project folder."""

    PAGE_W = 1280
    PAGE_H = 720

    def __init__(self, pbip_path: str | Path | None = None) -> None:
        self._root: Path | None = None
        self._report_dir: Path | None = None
        self._format: str = "unknown"  # "pbir_ga" | "old_pbip"
        self._report_data: dict[str, Any] = {}  # only used for old_pbip
        if pbip_path:
            self.load(pbip_path)

    # ── Loading ────────────────────────────────────────────────────────────────

    def load(self, pbip_path: str | Path) -> None:
        """Load a .pbip project folder or the .pbip file itself."""
        p = Path(pbip_path)
        if p.is_file() and p.suffix == ".pbip":
            p = p.parent

        self._root = p
        # Find the .Report subfolder
        report_dirs = list(p.glob("*.Report"))
        if not report_dirs:
            raise FileNotFoundError(
                f"No *.Report folder found in {p}. "
                "Save your file as a Power BI Project (.pbip) in Power BI Desktop first."
            )
        self._report_dir = report_dirs[0]

        # Detect format
        if (self._report_dir / "definition").exists():
            self._format = "pbir_ga"
        elif (self._report_dir / "report.json").exists():
            self._format = "old_pbip"
            self._report_data = json.loads(
                (self._report_dir / "report.json").read_text(encoding="utf-8")
            )
        else:
            # Create definition structure for a brand-new report folder
            self._format = "pbir_ga"
            (self._report_dir / "definition" / "pages").mkdir(parents=True, exist_ok=True)
            self._write_ga_report_json()

    # ── Pages ──────────────────────────────────────────────────────────────────

    def page_list(self) -> list[dict[str, Any]]:
        self._require_load()
        if self._format == "pbir_ga":
            return self._ga_page_list()
        return self._old_page_list()

    def page_add(self, display_name: str) -> dict[str, Any]:
        self._require_load()
        if self._format == "pbir_ga":
            return self._ga_page_add(display_name)
        return self._old_page_add(display_name)

    def page_delete(self, display_name: str) -> None:
        self._require_load()
        if self._format == "pbir_ga":
            self._ga_page_delete(display_name)
        else:
            self._old_page_delete(display_name)

    # ── Visuals ────────────────────────────────────────────────────────────────

    def visual_list(self, page: str) -> list[dict[str, Any]]:
        self._require_load()
        if self._format == "pbir_ga":
            return self._ga_visual_list(page)
        return self._old_visual_list(page)

    def visual_add(self, page: str, spec: Any) -> dict[str, Any]:
        """Add a visual to a page. spec is a VisualSpec from visual_builder."""
        self._require_load()
        if self._format == "pbir_ga":
            return self._ga_visual_add(page, spec)
        return self._old_visual_add(page, spec)

    def visual_delete(self, page: str, visual_name: str) -> None:
        self._require_load()
        if self._format == "pbir_ga":
            self._ga_visual_delete(page, visual_name)
        else:
            self._old_visual_delete(page, visual_name)

    def page_clear(self, page: str) -> None:
        """Remove all visuals from a page."""
        self._require_load()
        for v in self.visual_list(page):
            try:
                self.visual_delete(page, v["name"])
            except Exception:
                pass

    # ── Themes ─────────────────────────────────────────────────────────────────

    def theme_apply(self, theme_json: dict[str, Any]) -> None:
        """Write a theme JSON to the report's theme file."""
        self._require_load()
        assert self._report_dir
        theme_dir = self._report_dir / "StaticResources" / "SharedResources" / "BaseThemes"
        theme_dir.mkdir(parents=True, exist_ok=True)
        (theme_dir / "CY24SU10.json").write_text(json.dumps(theme_json, indent=2), encoding="utf-8")

    # ── PBIR GA implementation ─────────────────────────────────────────────────
    # Pages are stored in folders named by their GUID (= page `name` field).
    # A pages.json file at the pages/ level tracks page order.

    def _ga_pages_dir(self) -> Path:
        assert self._report_dir
        d = self._report_dir / "definition" / "pages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ga_read_pages_json(self) -> dict[str, Any]:
        pj = self._ga_pages_dir() / "pages.json"
        if pj.exists():
            return json.loads(pj.read_text(encoding="utf-8"))
        return {"pageOrder": [], "activePageName": ""}

    def _ga_write_pages_json(self, data: dict[str, Any]) -> None:
        pj = self._ga_pages_dir() / "pages.json"
        if "$schema" not in data:
            data["$schema"] = _schemas.definition_schema("pagesMetadata")
        pj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _ga_page_list(self) -> list[dict[str, Any]]:
        pages_meta = self._ga_read_pages_json()
        order = pages_meta.get("pageOrder", [])
        pages_dir = self._ga_pages_dir()

        # Collect all valid pages, preserving order from pages.json
        by_id: dict[str, dict[str, Any]] = {}
        for page_dir in pages_dir.iterdir():
            if not page_dir.is_dir():
                continue
            pj = page_dir / "page.json"
            if not pj.exists():
                continue
            data = json.loads(pj.read_text(encoding="utf-8"))
            pid = data.get("name", page_dir.name)
            by_id[pid] = {
                "name": pid,
                "displayName": data.get("displayName", page_dir.name),
                "width": data.get("width", self.PAGE_W),
                "height": data.get("height", self.PAGE_H),
            }

        # Return in declared order, then any extras
        result = [by_id[pid] for pid in order if pid in by_id]
        result += [v for k, v in by_id.items() if k not in order]
        return result

    def _ga_page_add(self, display_name: str) -> dict[str, Any]:
        # Folder name = page GUID (same value as `name` field)
        page_id = uuid.uuid4().hex
        page_dir = self._ga_pages_dir() / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "visuals").mkdir(exist_ok=True)

        page_json: dict[str, Any] = {
            "$schema": _schemas.definition_schema("page"),
            "name": page_id,
            "displayName": display_name,
            "displayOption": "FitToPage",
            "width": self.PAGE_W,
            "height": self.PAGE_H,
        }
        (page_dir / "page.json").write_text(json.dumps(page_json, indent=2), encoding="utf-8")

        # Update pages.json
        meta = self._ga_read_pages_json()
        meta.setdefault("pageOrder", []).append(page_id)
        if not meta.get("activePageName"):
            meta["activePageName"] = page_id
        self._ga_write_pages_json(meta)

        return {"name": page_id, "displayName": display_name}

    def _ga_page_delete(self, display_name: str) -> None:
        for page_dir in self._ga_pages_dir().iterdir():
            if not page_dir.is_dir():
                continue
            pj = page_dir / "page.json"
            if not pj.exists():
                continue
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("displayName") == display_name:
                page_id = data.get("name", page_dir.name)
                shutil.rmtree(page_dir)
                # Remove from pages.json
                meta = self._ga_read_pages_json()
                meta["pageOrder"] = [p for p in meta.get("pageOrder", []) if p != page_id]
                if meta.get("activePageName") == page_id:
                    meta["activePageName"] = meta["pageOrder"][0] if meta["pageOrder"] else ""
                self._ga_write_pages_json(meta)
                return

    def _ga_find_page_dir(self, page: str) -> Path | None:
        """Find a page directory by displayName or page GUID."""
        for page_dir in self._ga_pages_dir().iterdir():
            if not page_dir.is_dir():
                continue
            pj = page_dir / "page.json"
            if not pj.exists():
                continue
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("displayName") == page or data.get("name") == page:
                return page_dir
        return None

    def _ga_visuals_dir(self, page: str) -> Path | None:
        page_dir = self._ga_find_page_dir(page)
        if not page_dir:
            return None
        vd = page_dir / "visuals"
        vd.mkdir(exist_ok=True)
        return vd

    def _ga_visual_list(self, page: str) -> list[dict[str, Any]]:
        vd = self._ga_visuals_dir(page)
        if not vd:
            return []
        results = []
        for vdir in sorted(vd.iterdir()):
            if not vdir.is_dir():
                continue
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            data = json.loads(vj.read_text(encoding="utf-8"))
            pos = data.get("position", {})
            # Group containers have a `visualGroup` block instead of `visual`.
            vtype = data.get("visual", {}).get("visualType", "")
            if not vtype and "visualGroup" in data:
                vtype = "group"
            results.append(
                {
                    "name": data.get("name", vdir.name),
                    "visualType": vtype,
                    "x": pos.get("x", 0),
                    "y": pos.get("y", 0),
                    "width": pos.get("width", 0),
                    "height": pos.get("height", 0),
                }
            )
        return results

    def _ga_visual_add(self, page: str, spec: Any) -> dict[str, Any]:
        from pbi_cli.intelligence.visual_builder import spec_to_pbir_visual

        vd = self._ga_visuals_dir(page)
        if vd is None:
            self._ga_page_add(page)
            vd = self._ga_visuals_dir(page)
        assert vd is not None

        visual_json = spec_to_pbir_visual(spec)
        # Visual folder name = visual name (GUID)
        vdir = vd / spec.name
        vdir.mkdir(exist_ok=True)
        (vdir / "visual.json").write_text(json.dumps(visual_json, indent=2), encoding="utf-8")
        return {"name": spec.name, "visualType": spec.visual_type, "page": page}

    def _ga_visual_delete(self, page: str, visual_name: str) -> None:
        vd = self._ga_visuals_dir(page)
        if not vd:
            return
        for vdir in vd.iterdir():
            if not vdir.is_dir():
                continue
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            data = json.loads(vj.read_text(encoding="utf-8"))
            if data.get("name") == visual_name or vdir.name == visual_name:
                shutil.rmtree(vdir)
                return

    def _write_ga_report_json(self) -> None:
        assert self._report_dir
        report_json = {
            "$schema": _schemas.definition_schema("report"),
            "themeCollection": {
                "baseTheme": {
                    "name": "Fluent2-CY26SU04",
                    "reportVersionAtImport": dict(_schemas.REPORT_VERSION_AT_IMPORT),
                    "type": "SharedResources",
                }
            },
        }
        rj = self._report_dir / "definition" / "report.json"
        rj.parent.mkdir(parents=True, exist_ok=True)
        rj.write_text(json.dumps(report_json, indent=2), encoding="utf-8")

    # ── Old PBIP implementation ────────────────────────────────────────────────

    def _old_page_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.get("name", s.get("id", "")),
                "displayName": s.get("displayName", s.get("name", "")),
                "width": s.get("width", self.PAGE_W),
                "height": s.get("height", self.PAGE_H),
            }
            for s in self._report_data.get("sections", [])
        ]

    def _old_page_add(self, display_name: str) -> dict[str, Any]:
        sections = self._report_data.setdefault("sections", [])
        ordinal = len(sections)
        page_id = f"ReportSection{ordinal + 1}"
        section: dict[str, Any] = {
            "id": page_id,
            "name": page_id,
            "displayName": display_name,
            "filters": "[]",
            "ordinal": ordinal,
            "visualContainers": [],
            "config": json.dumps(
                {"defaultVisualInteraction": "includeFilters"}, separators=(",", ":")
            ),
            "width": self.PAGE_W,
            "height": self.PAGE_H,
        }
        sections.append(section)
        self._save_old()
        return {"name": page_id, "displayName": display_name}

    def _old_page_delete(self, display_name: str) -> None:
        sections = self._report_data.get("sections", [])
        self._report_data["sections"] = [
            s
            for s in sections
            if s.get("displayName") != display_name and s.get("name") != display_name
        ]
        self._save_old()

    def _old_find_section(self, page: str) -> dict[str, Any] | None:
        for s in self._report_data.get("sections", []):
            if s.get("displayName") == page or s.get("name") == page:
                return s
        return None

    def _old_visual_list(self, page: str) -> list[dict[str, Any]]:
        section = self._old_find_section(page)
        if not section:
            return []
        results = []
        for vc in section.get("visualContainers", []):
            try:
                cfg = json.loads(vc.get("config", "{}"))
                results.append(
                    {
                        "name": cfg.get("name", ""),
                        "visualType": cfg.get("singleVisual", {}).get("visualType", ""),
                        "x": vc.get("x", 0),
                        "y": vc.get("y", 0),
                        "width": vc.get("width", 0),
                        "height": vc.get("height", 0),
                    }
                )
            except Exception:
                pass
        return results

    def _old_visual_add(self, page: str, spec: Any) -> dict[str, Any]:
        from pbi_cli.intelligence.visual_builder import spec_to_old_pbip_container

        section = self._old_find_section(page)
        if section is None:
            self._old_page_add(page)
            section = self._old_find_section(page)
        assert section is not None
        container = spec_to_old_pbip_container(spec)
        section.setdefault("visualContainers", []).append(container)
        self._save_old()
        return {"name": spec.name, "visualType": spec.visual_type, "page": page}

    def _old_visual_delete(self, page: str, visual_name: str) -> None:
        section = self._old_find_section(page)
        if not section:
            return
        kept = []
        for vc in section.get("visualContainers", []):
            try:
                cfg = json.loads(vc.get("config", "{}"))
                if cfg.get("name") != visual_name:
                    kept.append(vc)
            except Exception:
                kept.append(vc)
        section["visualContainers"] = kept
        self._save_old()

    def _save_old(self) -> None:
        assert self._report_dir
        (self._report_dir / "report.json").write_text(
            json.dumps(self._report_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Bookmarks ──────────────────────────────────────────────────────────────
    # PBIR GA stores bookmarks as flat files: definition/bookmarks/{id}.bookmark.json
    # with an index at definition/bookmarks/bookmarks.json
    # Desktop uses schema 2.1.0, explorationState version "1.3".

    def _ga_bookmarks_dir(self) -> Path:
        assert self._report_dir
        d = self._report_dir / "definition" / "bookmarks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ga_read_bookmarks_json(self) -> dict[str, Any]:
        bj = self._ga_bookmarks_dir() / "bookmarks.json"
        if bj.exists():
            return json.loads(bj.read_text(encoding="utf-8"))
        return {"items": []}

    def _ga_write_bookmarks_json(self, data: dict[str, Any]) -> None:
        bj = self._ga_bookmarks_dir() / "bookmarks.json"
        data["$schema"] = _schemas.definition_schema("bookmarksMetadata")
        bj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def bookmark_list(self) -> list[dict[str, Any]]:
        """List all bookmarks in the report (PBIR GA only)."""
        self._require_load()
        bdir = self._ga_bookmarks_dir()
        meta = self._ga_read_bookmarks_json()
        ordered_ids = [item["name"] for item in meta.get("items", []) if "name" in item]

        by_id: dict[str, dict[str, Any]] = {}
        for entry in bdir.iterdir():
            # Flat file format: {id}.bookmark.json
            if not entry.is_file() or not entry.name.endswith(".bookmark.json"):
                continue
            data = json.loads(entry.read_text(encoding="utf-8"))
            bid = data.get("name", entry.stem.replace(".bookmark", ""))
            active = data.get("explorationState", {}).get("activeSection", "")
            by_id[bid] = {
                "name": bid,
                "displayName": data.get("displayName", bid),
                "page": active,
            }

        result = [by_id[bid] for bid in ordered_ids if bid in by_id]
        result += [v for k, v in by_id.items() if k not in ordered_ids]
        return result

    def bookmark_add(
        self,
        display_name: str,
        page: str | None = None,
        hidden_visuals: list[str] | None = None,
        capture: bool = True,
    ) -> dict[str, Any]:
        """Add a named bookmark as a flat {id}.bookmark.json file.

        Desktop format: schema 2.1.0, explorationState version "1.3".

        When ``capture`` is True (default), the bookmark records the actual
        visuals on the target page into ``explorationState.sections`` so the
        bookmark is not stripped when reopened in Desktop. Any visual name in
        ``hidden_visuals`` is recorded with ``display.mode = "hidden"`` —
        the standard way to build show/hide (storytelling) bookmarks.
        """
        self._require_load()
        bm_id = uuid.uuid4().hex[:20]  # Desktop uses 20-char hex ids
        hidden = set(hidden_visuals or [])

        # Resolve active page GUID + its display name for capture
        active_section = ""
        active_display = page
        pages = self.page_list()
        if page:
            page_info = next((p for p in pages if p["displayName"] == page), None)
            if page_info:
                active_section = page_info["name"]
        elif pages:
            active_section = pages[0]["name"]
            active_display = pages[0]["displayName"]

        sections: dict[str, Any] = {}
        target_visuals: list[str] = []
        if capture and active_section and active_display:
            visual_containers: dict[str, Any] = {}
            for v in self.visual_list(active_display):
                vname = v["name"]
                single_visual: dict[str, Any] = {"visualType": v["visualType"]}
                if vname in hidden:
                    single_visual["display"] = {"mode": "hidden"}
                visual_containers[vname] = {"singleVisual": single_visual}
                target_visuals.append(vname)
            if visual_containers:
                sections[active_section] = {"visualContainers": visual_containers}

        bm: dict[str, Any] = {
            "$schema": _schemas.definition_schema("bookmark"),
            "displayName": display_name,
            "name": bm_id,
            "options": {"targetVisualNames": target_visuals},
            "explorationState": {
                "version": "1.3",
                "activeSection": active_section,
                "sections": sections,
            },
        }

        # Flat file: {id}.bookmark.json in bookmarks dir
        bm_file = self._ga_bookmarks_dir() / f"{bm_id}.bookmark.json"
        bm_file.write_text(json.dumps(bm, indent=2), encoding="utf-8")

        meta = self._ga_read_bookmarks_json()
        items: list[dict[str, Any]] = meta.get("items", [])
        items.append({"name": bm_id})
        meta["items"] = items
        self._ga_write_bookmarks_json(meta)

        return {
            "name": bm_id,
            "displayName": display_name,
            "page": active_section,
            "options": {"targetVisualNames": target_visuals},
            "hiddenCount": len(hidden & set(target_visuals)),
        }

    def bookmark_delete(self, display_name: str) -> bool:
        """Delete a bookmark by display name. Returns True if found and deleted."""
        self._require_load()
        bdir = self._ga_bookmarks_dir()
        for entry in bdir.iterdir():
            if not entry.is_file() or not entry.name.endswith(".bookmark.json"):
                continue
            data = json.loads(entry.read_text(encoding="utf-8"))
            if data.get("displayName") == display_name:
                bm_id = data.get("name", entry.stem.replace(".bookmark", ""))
                entry.unlink()
                meta = self._ga_read_bookmarks_json()
                meta["items"] = [
                    item for item in meta.get("items", []) if item.get("name") != bm_id
                ]
                self._ga_write_bookmarks_json(meta)
                return True
        return False

    # ── Drillthrough / Tooltip page setup ─────────────────────────────────────

    def page_set_type(
        self, page: str, page_type: str, drillthrough_table: str | None = None
    ) -> None:
        """Set a page to Drillthrough or ReportTooltip type.

        page_type: "Drillthrough" | "ReportTooltip" | "Normal"
        drillthrough_table: for Drillthrough pages, the source entity to filter.
        """
        self._require_load()
        page_dir = self._ga_find_page_dir(page)
        if not page_dir:
            raise ValueError(f"Page '{page}' not found.")
        pj = page_dir / "page.json"
        data = json.loads(pj.read_text(encoding="utf-8"))
        if page_type == "Normal":
            data.pop("pageType", None)
            data.pop("drillthroughFields", None)
        else:
            data["pageType"] = page_type
            if page_type == "Drillthrough" and drillthrough_table:
                data["drillthroughFields"] = [
                    {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": drillthrough_table}},
                            "Property": drillthrough_table,
                        }
                    }
                ]
        pj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Conditional Formatting ─────────────────────────────────────────────────

    @staticmethod
    def _find_projection(
        visual_data: dict[str, Any], table: str, field: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Scan a visual's queryState projections to find the queryRef and field expression.

        Returns (queryRef, field_dict) or None. The field_dict can be used
        directly as the FillRule Input expression (Measure, Aggregation, or Column).
        """
        query_state = visual_data.get("visual", {}).get("query", {}).get("queryState", {})
        field_lower = field.lower()
        table_lower = table.lower()
        for _role, role_data in query_state.items():
            for proj in role_data.get("projections", []):
                query_ref: str = proj.get("queryRef", "")
                f = proj.get("field", {})
                # Plain Column
                col = f.get("Column")
                if col:
                    entity = col.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                    prop = col.get("Property", "")
                    if entity.lower() == table_lower and prop.lower() == field_lower:
                        return query_ref, f
                # Aggregated Column (e.g. SUM)
                agg_col = f.get("Aggregation", {}).get("Expression", {}).get("Column")
                if agg_col:
                    entity = agg_col.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                    prop = agg_col.get("Property", "")
                    if entity.lower() == table_lower and prop.lower() == field_lower:
                        return query_ref, f
                # Explicit Measure
                meas = f.get("Measure")
                if meas:
                    entity = meas.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                    prop = meas.get("Property", "")
                    if entity.lower() == table_lower and prop.lower() == field_lower:
                        return query_ref, f
        return None

    @staticmethod
    def _find_projection_query_ref(
        visual_data: dict[str, Any], table: str, field: str
    ) -> str | None:
        """Backwards-compatible wrapper — returns only the queryRef."""
        result = PbirBackend._find_projection(visual_data, table, field)
        return result[0] if result else None

    def _ga_find_visual_json(
        self, page: str, visual_name: str
    ) -> tuple[Path, dict[str, Any]] | None:
        """Return (path, data) for a named visual on a page, or None if not found."""
        vd = self._ga_visuals_dir(page)
        if not vd:
            return None
        for vdir in vd.iterdir():
            if not vdir.is_dir():
                continue
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            data = json.loads(vj.read_text(encoding="utf-8"))
            if data.get("name") == visual_name or vdir.name == visual_name:
                return vj, data
        return None

    def visual_format_color_scale(
        self,
        page: str,
        visual_name: str,
        table: str,
        measure: str,
        low_color: str = "#FF0000",
        mid_color: str | None = "#FFFF00",
        high_color: str = "#00FF00",
    ) -> bool:
        """Apply color-scale conditional formatting to a field in a table/matrix visual.

        Uses the exact PBIR format that Power BI Desktop writes:
        - Property name: ``backColor`` (not ``background``)
        - FillRule: nested ``FillRule`` key with ``linearGradient3`` (lowercase)
        - Color values: single-quoted hex strings inside Literal nodes
        - Selector: both ``data`` (dataViewWildcard) and ``metadata`` (queryRef)
        - Input: derived from the projection's actual field type (Aggregation or Measure)

        Returns True if the visual was found and updated.
        """
        self._require_load()
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        proj = self._find_projection(data, table, measure)
        query_ref = proj[0] if proj else f"Sum({table}[{measure}])"
        field_expr = (
            proj[1]
            if proj
            else {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": table}},
                            "Property": measure,
                        }
                    },
                    "Function": 0,
                }
            }
        )

        # Selector: Desktop always writes both data (wildcard) + metadata
        selector: dict[str, Any] = {
            "data": [{"dataViewWildcard": {"matchingOption": 1}}],
            "metadata": query_ref,
        }

        def _color_literal(hex_color: str) -> dict[str, Any]:
            return {"Literal": {"Value": f"'{hex_color}'"}}

        # linearGradient3 (3-stop) or linearGradient2 (2-stop) — lowercase keys
        if mid_color:
            gradient_rule: dict[str, Any] = {
                "linearGradient3": {
                    "min": {"color": _color_literal(low_color)},
                    "mid": {"color": _color_literal(mid_color)},
                    "max": {"color": _color_literal(high_color)},
                    "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}},
                }
            }
        else:
            gradient_rule = {
                "linearGradient2": {
                    "min": {"color": _color_literal(low_color)},
                    "max": {"color": _color_literal(high_color)},
                    "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}},
                }
            }

        # FillRule expression — nested FillRule key (not FillRuleDef)
        gradient_expr: dict[str, Any] = {
            "FillRule": {
                "Input": field_expr,
                "FillRule": gradient_rule,
            }
        }

        visual = data.setdefault("visual", {})
        objects = visual.setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        # Remove ALL existing entries for this field (deduplication)
        values_obj[:] = [
            v for v in values_obj if v.get("selector", {}).get("metadata") != query_ref
        ]
        values_obj.append(
            {
                "selector": selector,
                "properties": {"backColor": {"solid": {"color": {"expr": gradient_expr}}}},
            }
        )
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    def visual_format_data_bar(
        self,
        page: str,
        visual_name: str,
        table: str,
        measure: str,
        positive_color: str = "#118DFF",
        negative_color: str = "#FC4E2A",
    ) -> bool:
        """Enable data bar conditional formatting for a measure in a table/matrix visual."""
        self._require_load()
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        query_ref = self._find_projection_query_ref(data, table, measure)
        if not query_ref:
            query_ref = f"Sum({table}[{measure}])"
        # Selector: both data (wildcard) + metadata — matching Desktop format
        selector: dict[str, Any] = {
            "data": [{"dataViewWildcard": {"matchingOption": 1}}],
            "metadata": query_ref,
        }

        visual = data.setdefault("visual", {})
        objects = visual.setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        values_obj[:] = [
            v for v in values_obj if v.get("selector", {}).get("metadata") != query_ref
        ]
        values_obj.append(
            {
                "selector": selector,
                "properties": {
                    "dataBarEnabled": {"expr": {"Literal": {"Value": "true"}}},
                    "positiveColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{positive_color}'"}}}}
                    },
                    "negativeColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{negative_color}'"}}}}
                    },
                },
            }
        )
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Visual update / patch ──────────────────────────────────────────────────

    def visual_update(
        self,
        page: str,
        visual_name: str,
        *,
        x: int | None = None,
        y: int | None = None,
        z: int | None = None,
        width: int | None = None,
        height: int | None = None,
        tab_order: int | None = None,
        title: str | None = None,
    ) -> bool:
        """Patch an existing visual's position and/or title in place.

        Only the supplied arguments are changed; everything else (query
        bindings, formatting) is preserved. Returns True if the visual was
        found and updated. To rebind fields, delete + re-add the visual.
        """
        self._require_load()
        if self._format == "pbir_ga":
            return self._ga_visual_update(
                page, visual_name, x, y, z, width, height, tab_order, title
            )
        return self._old_visual_update(
            page, visual_name, x, y, z, width, height, tab_order, title
        )

    @staticmethod
    def _title_object(title: str) -> list[dict[str, Any]]:
        return [
            {
                "properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                }
            }
        ]

    def _ga_visual_update(
        self,
        page: str,
        visual_name: str,
        x: int | None,
        y: int | None,
        z: int | None,
        width: int | None,
        height: int | None,
        tab_order: int | None,
        title: str | None,
    ) -> bool:
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found
        pos = data.setdefault("position", {})
        for key, value in (
            ("x", x),
            ("y", y),
            ("z", z),
            ("width", width),
            ("height", height),
            ("tabOrder", tab_order),
        ):
            if value is not None:
                pos[key] = value
        if title is not None:
            vco = data.setdefault("visual", {}).setdefault("visualContainerObjects", {})
            vco["title"] = self._title_object(title)
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    def _old_visual_update(
        self,
        page: str,
        visual_name: str,
        x: int | None,
        y: int | None,
        z: int | None,
        width: int | None,
        height: int | None,
        tab_order: int | None,
        title: str | None,
    ) -> bool:
        section = self._old_find_section(page)
        if not section:
            return False
        for vc in section.get("visualContainers", []):
            try:
                cfg = json.loads(vc.get("config", "{}"))
            except Exception:
                continue
            if cfg.get("name") != visual_name:
                continue
            updates = {
                "x": x,
                "y": y,
                "z": z,
                "width": width,
                "height": height,
                "tabOrder": tab_order,
            }
            for key, value in updates.items():
                if value is None:
                    continue
                vc[key] = value
                for layout in cfg.get("layouts", []):
                    layout.setdefault("position", {})[key] = value
            if title is not None:
                sv = cfg.setdefault("singleVisual", {})
                sv.setdefault("objects", {})["title"] = self._title_object(title)
            vc["config"] = json.dumps(cfg, separators=(",", ":"))
            self._save_old()
            return True
        return False

    # ── Conditional formatting: rule-based (range) + font color ─────────────────
    # Rule-based colouring uses a Conditional/Cases expression. Cases evaluate
    # top-to-bottom and the first matching case wins, so order your rules from
    # most specific (highest threshold) to least.

    COMPARISON_KIND = {">": 1, ">=": 2, "<": 3, "<=": 4, "=": 0, "==": 0}

    @staticmethod
    def _num_literal(value: float | int) -> str:
        """Power BI numeric literal — double suffix 'D' (e.g. 50000 -> '50000D')."""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value}D"

    @classmethod
    def _comparison(cls, left: dict[str, Any], op: str, threshold: float) -> dict[str, Any]:
        if op not in cls.COMPARISON_KIND:
            raise ValueError(f"unknown operator '{op}'; use one of {sorted(cls.COMPARISON_KIND)}")
        return {
            "Comparison": {
                "ComparisonKind": cls.COMPARISON_KIND[op],
                "Left": left,
                "Right": {"Literal": {"Value": cls._num_literal(threshold)}},
            }
        }

    @classmethod
    def _rule_conditions(
        cls, rules: list[tuple], left: dict[str, Any]
    ) -> list[tuple[dict[str, Any], str]]:
        """Turn (op, threshold, color) / ('between', low, high, color) rules into
        (Condition, color) pairs. 'between' becomes an And of >= low and < high."""
        out: list[tuple[dict[str, Any], str]] = []
        for rule in rules:
            if rule and rule[0] == "between":
                _, low, high, color = rule
                cond = {
                    "And": {
                        "Left": cls._comparison(left, ">=", low),
                        "Right": cls._comparison(left, "<", high),
                    }
                }
            else:
                op, threshold, color = rule
                cond = cls._comparison(left, op, threshold)
            out.append((cond, color))
        return out

    @staticmethod
    def _upsert_values_entry(
        values_obj: list[dict[str, Any]],
        selector: dict[str, Any],
        query_ref: str,
        properties: dict[str, Any],
    ) -> None:
        """Merge `properties` into the values entry for `query_ref`, or append one.

        Desktop keeps a single entry per selector with multiple property keys,
        so applying backColor then fontColor to the same field yields one entry.
        """
        for entry in values_obj:
            if entry.get("selector", {}).get("metadata") == query_ref:
                entry.setdefault("properties", {}).update(properties)
                entry["selector"] = selector
                return
        values_obj.append({"selector": selector, "properties": properties})

    def visual_format_rules(
        self,
        page: str,
        visual_name: str,
        table: str,
        measure: str,
        rules: list[tuple[str, float, str]],
        target: str = "backColor",
    ) -> bool:
        """Apply rule-based (conditional) colour formatting to a table/matrix field.

        rules: list of (operator, threshold, hex_color). operator is one of
        ``> >= < <= =``. Cases are evaluated in the given order; first match wins.
        target: ``backColor`` (cell fill) or ``fontColor`` (text colour).

        Returns True if the visual was found and updated.
        """
        if target not in ("backColor", "fontColor"):
            raise ValueError("target must be 'backColor' or 'fontColor'")
        if not rules:
            raise ValueError("at least one rule is required")

        self._require_load()
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        proj = self._find_projection(data, table, measure)
        query_ref = proj[0] if proj else f"Sum({table}[{measure}])"
        field_expr = (
            proj[1]
            if proj
            else {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": table}},
                            "Property": measure,
                        }
                    },
                    "Function": 0,
                }
            }
        )

        cases: list[dict[str, Any]] = [
            {"Condition": cond, "Value": {"Literal": {"Value": f"'{color}'"}}}
            for cond, color in self._rule_conditions(rules, field_expr)
        ]

        conditional_expr = {"Conditional": {"Cases": cases}}
        selector: dict[str, Any] = {
            "data": [{"dataViewWildcard": {"matchingOption": 1}}],
            "metadata": query_ref,
        }
        properties = {target: {"solid": {"color": {"expr": conditional_expr}}}}

        objects = data.setdefault("visual", {}).setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        self._upsert_values_entry(values_obj, selector, query_ref, properties)
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Icon-set conditional formatting ────────────────────────────────────────
    # Format reverse-engineered from Power BI Desktop output. Icons live under
    # objects.values[].properties.icon as a Conditional/Cases over the field.
    # Default (rules=None) reproduces Desktop's 3-band percent-of-range icon set;
    # custom rules use absolute thresholds (first match wins).

    @staticmethod
    def _icon_select_ref(query_ref: str) -> dict[str, Any]:
        return {"SelectRef": {"ExpressionName": query_ref}}

    @staticmethod
    def _icon_range_percent(query_ref: str, percent: float) -> dict[str, Any]:
        """RangePercent node: percent of the field's min..max across all rows."""
        def _scoped_minmax(func: int) -> dict[str, Any]:
            # func 3 = Min, 4 = Max
            return {
                "ScopedEval": {
                    "Expression": {
                        "Aggregation": {
                            "Expression": {
                                "ScopedEval": {
                                    "Expression": {
                                        "SelectRef": {"ExpressionName": query_ref}
                                    },
                                    "Scope": [{"AllRolesRef": {}}],
                                }
                            },
                            "Function": func,
                        }
                    },
                    "Scope": [],
                }
            }

        return {
            "RangePercent": {
                "Min": _scoped_minmax(3),
                "Max": _scoped_minmax(4),
                "Percent": percent,
            }
        }

    def visual_format_icons(
        self,
        page: str,
        visual_name: str,
        table: str,
        measure: str,
        rules: list[tuple[str, float, str]] | None = None,
        layout: str = "Before",
    ) -> bool:
        """Apply icon-set conditional formatting to a table/matrix field.

        rules=None  → Desktop's default 3-band percent icon set
                      (>=67% CircleHigh, 33-67% SignMedium, <33% SignLow).
        rules       → list of (operator, threshold, icon_name); absolute
                      thresholds, first match wins. icon_name is a Power BI icon
                      id, e.g. 'CircleHigh', 'CircleMedium', 'CircleLow',
                      'SignMedium', 'SignLow', 'ArrowUp', 'ArrowDown'.
        layout: 'Before' | 'After' | 'IconOnly' — icon position vs the value.

        Returns True if the visual was found and updated.
        """
        self._require_load()
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        proj = self._find_projection(data, table, measure)
        query_ref = proj[0] if proj else f"Sum({table}[{measure}])"
        ref = self._icon_select_ref(query_ref)

        if rules:
            cases = [
                {"Condition": cond, "Value": {"Literal": {"Value": f"'{icon}'"}}}
                for cond, icon in self._rule_conditions(rules, ref)
            ]
        else:
            cases = [
                {
                    "Condition": {"Comparison": {
                        "ComparisonKind": 2, "Left": ref,
                        "Right": self._icon_range_percent(query_ref, 0.67),
                    }},
                    "Value": {"Literal": {"Value": "'CircleHigh'"}},
                },
                {
                    "Condition": {"And": {
                        "Left": {"Comparison": {
                            "ComparisonKind": 2, "Left": ref,
                            "Right": self._icon_range_percent(query_ref, 0.33),
                        }},
                        "Right": {"Comparison": {
                            "ComparisonKind": 3, "Left": ref,
                            "Right": self._icon_range_percent(query_ref, 0.67),
                        }},
                    }},
                    "Value": {"Literal": {"Value": "'SignMedium'"}},
                },
                {
                    "Condition": {"Comparison": {
                        "ComparisonKind": 3, "Left": ref,
                        "Right": self._icon_range_percent(query_ref, 0.33),
                    }},
                    "Value": {"Literal": {"Value": "'SignLow'"}},
                },
            ]

        icon_obj = {
            "kind": "Icon",
            "layout": {"expr": {"Literal": {"Value": f"'{layout}'"}}},
            "verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}},
            "value": {"expr": {"Conditional": {"Cases": cases}}},
        }
        selector: dict[str, Any] = {
            "data": [{"dataViewWildcard": {"matchingOption": 1}}],
            "metadata": query_ref,
        }
        objects = data.setdefault("visual", {}).setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        self._upsert_values_entry(values_obj, selector, query_ref, {"icon": icon_obj})
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Visual field rebinding ─────────────────────────────────────────────────

    def visual_set_field(
        self,
        page: str,
        visual_name: str,
        role: str,
        table: str,
        field: str,
        *,
        is_measure: bool = False,
        agg: int | None = 0,
        replace: bool = True,
    ) -> bool:
        """Bind a field to a visual role slot, rewriting its query projection.

        role: visual role name (Category, Y, Values, Rows, Columns, ...).
        replace=True swaps the role's existing projections for this one field;
        replace=False appends it. PBIR GA only. Returns True if found+updated.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Field rebinding requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        from pbi_cli.intelligence.visual_builder import FieldDef

        fd = FieldDef(entity=table, property=field, is_measure=is_measure, agg=agg)
        projection = fd.to_projection()

        query = data.setdefault("visual", {}).setdefault("query", {})
        query_state = query.setdefault("queryState", {})
        role_data = query_state.setdefault(role, {})
        projections = role_data.setdefault("projections", [])
        if replace:
            projections.clear()
            projections.append(projection)
        else:
            projections.append(projection)
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    def visual_rebind(
        self,
        page: str,
        visual_name: str,
        bindings: dict[str, list[Any]],
        *,
        clear_unlisted: bool = False,
    ) -> bool:
        """Atomically rebind several role slots of a visual in one write.

        ``bindings`` maps a role name (Category, Y, Values, Rows, Columns, ...) to
        a list of ``FieldDef``. Each listed role is fully replaced with its given
        fields. With ``clear_unlisted=True`` every role *not* in ``bindings`` is
        removed too, so the visual ends up bound to exactly ``bindings`` — the
        in-place equivalent of delete + re-add, but preserving position, title and
        formatting. PBIR GA only. Returns True if the visual was found+updated.

        The visual file is only written if every field is valid, so a bad binding
        never leaves the visual half-rewritten.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Field rebinding requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        # Build all projections first; any failure aborts before writing.
        new_state: dict[str, list[dict[str, Any]]] = {}
        for role, fields in bindings.items():
            if not role:
                raise ValueError("role names must be non-empty")
            new_state[role] = [f.to_projection() for f in fields]

        query = data.setdefault("visual", {}).setdefault("query", {})
        query_state = query.setdefault("queryState", {})
        if clear_unlisted:
            query_state.clear()
        for role, projections in new_state.items():
            query_state[role] = {"projections": projections}

        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Generic visual formatting (formatting object definitions) ──────────────
    # Beyond the bespoke conditional-formatting writers above, this writes any
    # formatting-object property Desktop supports. Structure (per the
    # formattingObjectDefinitions schema): visual.objects[<object>] is a list of
    # { selector?, properties } entries; each property value is an expression such
    # as a Literal, or a solid colour wrapper for colour properties.

    @staticmethod
    def _format_value_expr(value: Any, value_type: str) -> dict[str, Any]:
        """Build the expression for a formatting property value.

        value_type: 'text' | 'number' | 'bool' | 'color' | 'auto'. 'auto' infers
        from the Python type (bool/int/float/str; '#RRGGBB' strings → color).
        """
        vt = value_type
        if vt == "auto":
            if isinstance(value, bool):
                vt = "bool"
            elif isinstance(value, (int, float)):
                vt = "number"
            elif isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6,8}", value):
                vt = "color"
            else:
                vt = "text"

        if vt == "bool":
            literal = {"expr": {"Literal": {"Value": "true" if value else "false"}}}
        elif vt == "number":
            num = int(value) if isinstance(value, float) and value.is_integer() else value
            literal = {"expr": {"Literal": {"Value": f"{num}D"}}}
        elif vt == "color":
            return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{value}'"}}}}}
        else:  # text
            literal = {"expr": {"Literal": {"Value": f"'{value}'"}}}
        return literal

    def visual_set_format(
        self,
        page: str,
        visual_name: str,
        object_name: str,
        property_name: str,
        value: Any,
        *,
        value_type: str = "auto",
        selector: dict[str, Any] | None = None,
        container_level: bool = False,
    ) -> bool:
        """Set an arbitrary formatting-object property on a visual.

        Examples of (object_name, property_name): ('title','text'),
        ('title','show'), ('background','color'), ('legend','position'),
        ('dataLabels','show'), ('categoryAxis','titleText').

        ``container_level=True`` targets ``visualContainerObjects`` (chrome shared
        by all visual types: title, background, border, visualHeader) instead of
        the type-specific ``objects``. Entries are merged by ``selector`` so
        repeated calls accumulate into one entry. PBIR GA only. Returns True if
        the visual was found and updated.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Generic formatting requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        visual = data.setdefault("visual", {})
        bucket_key = "visualContainerObjects" if container_level else "objects"
        bucket = visual.setdefault(bucket_key, {})
        entries: list[dict[str, Any]] = bucket.setdefault(object_name, [])

        prop_expr = self._format_value_expr(value, value_type)

        # Merge into an entry with a matching selector (None == whole-visual).
        target = next(
            (e for e in entries if e.get("selector") == selector),
            None,
        )
        if target is None:
            target = {"properties": {}}
            if selector is not None:
                target["selector"] = selector
            entries.append(target)
        target.setdefault("properties", {})[property_name] = prop_expr

        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Report-level measures (reportExtensions.json) ──────────────────────────

    def _report_extension_path(self) -> Path:
        assert self._report_dir
        return self._report_dir / "definition" / "reportExtensions.json"

    def report_measure_add(
        self,
        table: str,
        name: str,
        expression: str,
        format_string: str | None = None,
        data_type: str = "Double",
    ) -> dict[str, Any]:
        """Add (or replace) a report-level measure in reportExtensions.json.

        Report-level measures live only in the report and target a table (entity)
        in the connected semantic model. Per the reportExtension schema, each
        measure requires name, expression and dataType (Text|Integer|Double|...).
        Intended for live-connection reports; with a byPath (full-edit) model,
        add measures to the model instead. PBIR GA only.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Report-level measures require PBIR GA format.")
        path = self._report_extension_path()
        if path.exists():
            ext = json.loads(path.read_text(encoding="utf-8"))
        else:
            ext = {
                "$schema": _schemas.definition_schema("reportExtension"),
                "name": "extension",
                "entities": [],
            }

        # dataType is required by the reportExtension schema.
        measure: dict[str, Any] = {
            "name": name,
            "dataType": data_type,
            "expression": expression,
        }
        if format_string:
            measure["formatString"] = format_string

        entities: list[dict[str, Any]] = ext.setdefault("entities", [])
        entity = next((e for e in entities if e.get("name") == table), None)
        if entity is None:
            entity = {"name": table, "measures": []}
            entities.append(entity)
        measures: list[dict[str, Any]] = entity.setdefault("measures", [])
        measures[:] = [m for m in measures if m.get("name") != name]
        measures.append(measure)

        path.write_text(json.dumps(ext, indent=2), encoding="utf-8")
        return {"table": table, "name": name}

    def report_measure_list(self) -> list[dict[str, Any]]:
        """List report-level measures defined in reportExtensions.json."""
        self._require_load()
        path = self._report_extension_path()
        if not path.exists():
            return []
        ext = json.loads(path.read_text(encoding="utf-8"))
        out: list[dict[str, Any]] = []
        for entity in ext.get("entities", []):
            for m in entity.get("measures", []):
                out.append(
                    {
                        "table": entity.get("name", ""),
                        "name": m.get("name", ""),
                        "expression": m.get("expression", ""),
                    }
                )
        return out

    # ── Bookmark groups ────────────────────────────────────────────────────────

    def bookmark_group_add(
        self, display_name: str, member_display_names: list[str]
    ) -> dict[str, Any]:
        """Create a bookmark group containing the named bookmarks (PBIR GA).

        Groups are recorded in bookmarks.json: a group item carries a nested
        `children` list referencing member bookmark ids.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Bookmark groups require PBIR GA format.")

        existing = {b["displayName"]: b["name"] for b in self.bookmark_list()}
        member_ids = [existing[n] for n in member_display_names if n in existing]

        meta = self._ga_read_bookmarks_json()
        items: list[dict[str, Any]] = meta.get("items", [])
        # Remove members from the top level — they move under the group.
        member_set = set(member_ids)
        items = [it for it in items if it.get("name") not in member_set]

        group_id = uuid.uuid4().hex[:20]
        items.append(
            {
                "name": group_id,
                "displayName": display_name,
                "children": [{"name": mid} for mid in member_ids],
            }
        )
        meta["items"] = items
        self._ga_write_bookmarks_json(meta)
        return {"name": group_id, "displayName": display_name, "members": member_ids}

    # ── Visual interactions (page level) ───────────────────────────────────────

    INTERACTION_TYPES = ("Default", "DataFilter", "HighlightFilter", "NoFilter")

    def set_visual_interaction(
        self, page: str, source: str, target: str, interaction_type: str
    ) -> None:
        """Set how a source visual filters a target visual on a page.

        interaction_type: Default | DataFilter | HighlightFilter | NoFilter.
        Replaces any existing rule for the same source/target pair.
        PBIR GA only.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Visual interactions require PBIR GA format (definition/ folder).")
        if interaction_type not in self.INTERACTION_TYPES:
            raise ValueError(f"type must be one of {self.INTERACTION_TYPES}")

        page_dir = self._ga_find_page_dir(page)
        if not page_dir:
            raise ValueError(f"Page '{page}' not found.")
        pj = page_dir / "page.json"
        data = json.loads(pj.read_text(encoding="utf-8"))
        interactions: list[dict[str, Any]] = data.setdefault("visualInteractions", [])
        interactions[:] = [
            i for i in interactions if not (i.get("source") == source and i.get("target") == target)
        ]
        interactions.append({"source": source, "target": target, "type": interaction_type})
        pj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Slicer sync ────────────────────────────────────────────────────────────

    def set_slicer_sync(
        self,
        page: str,
        visual_name: str,
        group_name: str,
        field_changes: bool = True,
        filter_changes: bool = True,
    ) -> bool:
        """Place a slicer visual into a named sync group.

        Slicers sharing the same group_name stay synchronised. PBIR GA only.
        Returns True if the visual was found and updated.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Slicer sync requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found
        data.setdefault("visual", {})["syncGroup"] = {
            "groupName": group_name,
            "fieldChanges": field_changes,
            "filterChanges": filter_changes,
        }
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Visual container groups ────────────────────────────────────────────────
    # Verified against Desktop: a group is its own visual.json (no `visual` key)
    # carrying `visualGroup: {displayName, groupMode}` and a bounding-box position;
    # each member visual.json gets a top-level `parentGroupName` = the group id.

    def visual_group_add(
        self,
        page: str,
        member_names: list[str],
        display_name: str | None = None,
        group_mode: str = "ScaleMode",
    ) -> dict[str, Any]:
        """Group existing visuals on a page. Returns the group info.

        Computes the group's bounding box from its members. PBIR GA only.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Visual groups require PBIR GA format (definition/ folder).")
        from pbi_cli.intelligence.visual_builder import VISUAL_CONTAINER_SCHEMA

        vd = self._ga_visuals_dir(page)
        if vd is None:
            raise ValueError(f"Page '{page}' not found.")

        members: list[tuple[Path, dict[str, Any]]] = []
        for name in member_names:
            found = self._ga_find_visual_json(page, name)
            if found:
                members.append(found)
        if len(members) < 2:
            raise ValueError("A group needs at least two existing member visuals.")

        # Bounding box across members
        xs = [m[1].get("position", {}).get("x", 0) for m in members]
        ys = [m[1].get("position", {}).get("y", 0) for m in members]
        x2 = [m[1].get("position", {}).get("x", 0) + m[1].get("position", {}).get("width", 0)
              for m in members]
        y2 = [m[1].get("position", {}).get("y", 0) + m[1].get("position", {}).get("height", 0)
              for m in members]
        gx, gy = min(xs), min(ys)
        gw, gh = max(x2) - gx, max(y2) - gy

        group_id = uuid.uuid4().hex[:20]
        group_display = display_name or "Group"
        group_dir = vd / group_id
        group_dir.mkdir(exist_ok=True)
        group_json: dict[str, Any] = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": group_id,
            "position": {"x": gx, "y": gy, "z": 1, "height": gh, "width": gw, "tabOrder": 1},
            "visualGroup": {"displayName": group_display, "groupMode": group_mode},
        }
        (group_dir / "visual.json").write_text(
            json.dumps(group_json, indent=2), encoding="utf-8"
        )

        # Tag each member with parentGroupName (top-level key)
        for vj, data in members:
            data["parentGroupName"] = group_id
            vj.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return {"name": group_id, "displayName": group_display,
                "members": [m[1].get("name") for m in members]}

    # ── Mobile layout ──────────────────────────────────────────────────────────
    # Each visual's mobile position is a sibling mobile.json (visualContainerMobileState).

    MOBILE_STATE_SCHEMA = _schemas.definition_schema("visualContainerMobileState")

    def visual_set_mobile(
        self,
        page: str,
        visual_name: str,
        x: int,
        y: int,
        width: int,
        height: int,
        z: int = 1,
        tab_order: int = 0,
    ) -> bool:
        """Set a visual's position on the mobile (phone) layout canvas.

        Writes a mobile.json beside the visual's visual.json. The mobile canvas
        is 320 units wide. PBIR GA only. Returns True if the visual was found.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Mobile layout requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, _ = found
        mobile = {
            "$schema": self.MOBILE_STATE_SCHEMA,
            "position": {
                "x": x, "y": y, "z": z, "height": height, "width": width, "tabOrder": tab_order
            },
        }
        (vj.parent / "mobile.json").write_text(json.dumps(mobile, indent=2), encoding="utf-8")
        return True

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _require_load(self) -> None:
        if self._report_dir is None:
            raise RuntimeError("No PBIP folder loaded. Call load() or pass pbip_path= first.")

    @property
    def format(self) -> str:
        return self._format

    @property
    def report_dir(self) -> Path | None:
        return self._report_dir
