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
        self._format: str = "unknown"   # "pbir_ga" | "old_pbip"
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
        (theme_dir / "CY24SU10.json").write_text(
            json.dumps(theme_json, indent=2), encoding="utf-8"
        )

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
            data["$schema"] = (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.0.0/schema.json"
            )
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
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/page/2.1.0/schema.json"
            ),
            "name": page_id,
            "displayName": display_name,
            "displayOption": "FitToPage",
            "width": self.PAGE_W,
            "height": self.PAGE_H,
        }
        (page_dir / "page.json").write_text(
            json.dumps(page_json, indent=2), encoding="utf-8"
        )

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
            results.append({
                "name": data.get("name", vdir.name),
                "visualType": data.get("visual", {}).get("visualType", ""),
                "x": pos.get("x", 0), "y": pos.get("y", 0),
                "width": pos.get("width", 0), "height": pos.get("height", 0),
            })
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
        (vdir / "visual.json").write_text(
            json.dumps(visual_json, indent=2), encoding="utf-8"
        )
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
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/report/3.2.0/schema.json"
            ),
            "themeCollection": {
                "baseTheme": {
                    "name": "Fluent2-CY26SU04",
                    "reportVersionAtImport": {
                        "visual": "2.8.0", "report": "3.2.0", "page": "2.3.1"
                    },
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
            "config": json.dumps({"defaultVisualInteraction": "includeFilters"}, separators=(",", ":")),
            "width": self.PAGE_W,
            "height": self.PAGE_H,
        }
        sections.append(section)
        self._save_old()
        return {"name": page_id, "displayName": display_name}

    def _old_page_delete(self, display_name: str) -> None:
        sections = self._report_data.get("sections", [])
        self._report_data["sections"] = [
            s for s in sections
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
                results.append({
                    "name": cfg.get("name", ""),
                    "visualType": cfg.get("singleVisual", {}).get("visualType", ""),
                    "x": vc.get("x", 0), "y": vc.get("y", 0),
                    "width": vc.get("width", 0), "height": vc.get("height", 0),
                })
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
        data["$schema"] = (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/bookmarksMetadata/1.0.0/schema.json"
        )
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

    def bookmark_add(self, display_name: str, page: str | None = None) -> dict[str, Any]:
        """Add a named bookmark as a flat {id}.bookmark.json file.

        Desktop format: schema 2.1.0, explorationState version "1.3",
        options.targetVisualNames: [].
        """
        self._require_load()
        bm_id = uuid.uuid4().hex[:20]  # Desktop uses 20-char hex ids

        # Resolve active page GUID
        active_section = ""
        if page:
            page_info = next(
                (p for p in self.page_list() if p["displayName"] == page), None
            )
            if page_info:
                active_section = page_info["name"]
        else:
            pages = self.page_list()
            if pages:
                active_section = pages[0]["name"]

        bm: dict[str, Any] = {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/bookmark/2.1.0/schema.json"
            ),
            "displayName": display_name,
            "name": bm_id,
            "options": {"targetVisualNames": []},
            "explorationState": {
                "version": "1.3",
                "activeSection": active_section,
                "sections": {},
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

        return {"name": bm_id, "displayName": display_name, "page": active_section}

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
                    item for item in meta.get("items", [])
                    if item.get("name") != bm_id
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
        query_state = (
            visual_data.get("visual", {})
            .get("query", {})
            .get("queryState", {})
        )
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
        field_expr = proj[1] if proj else {
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
                    "nullColoringStrategy": {
                        "strategy": {"Literal": {"Value": "'asZero'"}}
                    },
                }
            }
        else:
            gradient_rule = {
                "linearGradient2": {
                    "min": {"color": _color_literal(low_color)},
                    "max": {"color": _color_literal(high_color)},
                    "nullColoringStrategy": {
                        "strategy": {"Literal": {"Value": "'asZero'"}}
                    },
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
            v for v in values_obj
            if v.get("selector", {}).get("metadata") != query_ref
        ]
        values_obj.append(
            {
                "selector": selector,
                "properties": {
                    "backColor": {
                        "solid": {"color": {"expr": gradient_expr}}
                    }
                },
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
            v for v in values_obj
            if v.get("selector", {}).get("metadata") != query_ref
        ]
        values_obj.append(
            {
                "selector": selector,
                "properties": {
                    "dataBarEnabled": {"expr": {"Literal": {"Value": "true"}}},
                    "positiveColor": {
                        "solid": {
                            "color": {
                                "expr": {"Literal": {"Value": f"'{positive_color}'"}}
                            }
                        }
                    },
                    "negativeColor": {
                        "solid": {
                            "color": {
                                "expr": {"Literal": {"Value": f"'{negative_color}'"}}
                            }
                        }
                    },
                },
            }
        )
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
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
