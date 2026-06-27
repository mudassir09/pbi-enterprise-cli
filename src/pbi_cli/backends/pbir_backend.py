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

    def theme_register(self, theme_json: dict[str, Any], name: str = "CustomTheme") -> str:
        """Register a custom theme and bind it in report.json. PBIR GA only.

        Writes the theme to ``StaticResources/RegisteredResources/<name>.json``,
        sets ``themeCollection.customTheme`` and adds the matching
        ``resourcePackages`` item so Power BI actually loads it (writing the file
        alone is not enough — it must be referenced from report.json). Returns the
        written theme path. Re-registering the same name updates in place.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Theme registration requires PBIR GA format (definition/ folder).")
        assert self._report_dir
        res_dir = self._report_dir / "StaticResources" / "RegisteredResources"
        res_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{name}.json"
        (res_dir / fname).write_text(json.dumps(theme_json, indent=2), encoding="utf-8")

        rj = self._ga_read_report_json()
        # Desktop requires customTheme to carry reportVersionAtImport, exactly like
        # baseTheme — omitting it raises "Required property 'reportVersionAtImport'
        # was not included in /themeCollection/customTheme" at load (verified live).
        rj.setdefault("themeCollection", {})["customTheme"] = {
            "name": name,
            "reportVersionAtImport": dict(_schemas.REPORT_VERSION_AT_IMPORT),
            "type": "RegisteredResources",
        }
        packages = rj.setdefault("resourcePackages", [])
        pkg = next((p for p in packages if p.get("type") == "RegisteredResources"), None)
        if pkg is None:
            pkg = {"name": "RegisteredResources", "type": "RegisteredResources", "items": []}
            packages.append(pkg)
        items = pkg.setdefault("items", [])
        if not any(it.get("path") == fname for it in items):
            items.append({"name": name, "path": fname, "type": "CustomTheme"})
        self._ga_write_report_json(rj)
        return str(res_dir / fname)

    def custom_visual_register(self, guid: str) -> bool:
        """Register a custom (.pbiviz) visual GUID in report.json. PBIR GA only.

        A visual whose ``visualType`` is a custom-visual GUID only renders if that
        GUID is listed in report.json's ``publicCustomVisuals``. After registering,
        add the visual with ``visual add`` using the GUID as the type. Returns True
        if the GUID was newly added, False if it was already registered.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Custom visual registration requires PBIR GA format.")
        rj = self._ga_read_report_json()
        pcv = rj.setdefault("publicCustomVisuals", [])
        if guid in pcv:
            return False
        pcv.append(guid)
        self._ga_write_report_json(rj)
        return True

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

    def visual_get(self, page: str, visual_name: str) -> dict[str, Any] | None:
        """Introspect a visual: bindings, formatting, conditional formatting, filters.

        Reads the visual.json back into a structured summary — the read-side
        counterpart to the add/rebind/format writers. PBIR GA only. Returns None
        if the visual is not found.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("visual_get requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return None
        vj, data = found
        visual = data.get("visual", {})

        # Role → field queryRefs.
        bindings: dict[str, list[str]] = {}
        for role, role_data in visual.get("query", {}).get("queryState", {}).items():
            refs = [p.get("queryRef", "") for p in role_data.get("projections", [])]
            if refs:
                bindings[role] = refs

        # Conditional formatting: which properties target which field.
        cond_fmt: list[dict[str, str]] = []
        for entry in visual.get("objects", {}).get("values", []):
            field = entry.get("selector", {}).get("metadata", "")
            for prop in entry.get("properties", {}):
                cond_fmt.append({"field": field, "property": prop})

        # Button action, if any.
        action = None
        for link in visual.get("visualContainerObjects", {}).get("visualLink", []):
            lit = link.get("properties", {}).get("type", {}).get("expr", {}).get("Literal", {})
            if lit.get("Value"):
                action = str(lit["Value"]).strip("'")

        vtype = visual.get("visualType", "")
        if not vtype and "visualGroup" in data:
            vtype = "group"

        return {
            "name": data.get("name", vj.parent.name),
            "visualType": vtype,
            "position": data.get("position", {}),
            "bindings": bindings,
            "formattingObjects": sorted(visual.get("objects", {}).keys()),
            "containerObjects": sorted(visual.get("visualContainerObjects", {}).keys()),
            "conditionalFormatting": cond_fmt,
            "filters": len(data.get("filterConfig", {}).get("filters", [])),
            "isHidden": bool(data.get("isHidden")),
            "parentGroupName": data.get("parentGroupName"),
            "syncGroup": visual.get("syncGroup"),
            "action": action,
            "hasMobileLayout": (vj.parent / "mobile.json").exists(),
        }

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

    def _ga_report_json_path(self) -> Path:
        assert self._report_dir
        return self._report_dir / "definition" / "report.json"

    def _ga_read_report_json(self) -> dict[str, Any]:
        """Read report.json, creating the default if it does not yet exist."""
        rj = self._ga_report_json_path()
        if not rj.exists():
            self._write_ga_report_json()
        return json.loads(rj.read_text(encoding="utf-8"))

    def _ga_write_report_json(self, data: dict[str, Any]) -> None:
        rj = self._ga_report_json_path()
        rj.parent.mkdir(parents=True, exist_ok=True)
        rj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_ga_report_json(self) -> None:
        self._ga_write_report_json({
            "$schema": _schemas.definition_schema("report"),
            "themeCollection": {
                "baseTheme": {
                    "name": "Fluent2-CY26SU04",
                    "reportVersionAtImport": dict(_schemas.REPORT_VERSION_AT_IMPORT),
                    "type": "SharedResources",
                }
            },
        })

    # ── Page / visual duplication & move (PBIR GA) ─────────────────────────────
    # Folder-per-object makes copy cheap, but ids must stay unique: a duplicated
    # page gets a fresh page id AND fresh visual ids (with parentGroupName and
    # page visualInteractions remapped), so the copy is fully independent.

    def page_duplicate(self, display_name: str, new_display_name: str | None = None) -> dict[str, Any]:  # noqa: E501
        """Duplicate a page (and all its visuals) under a new id. PBIR GA only.

        Visual ids are regenerated and every internal reference (parentGroupName,
        visualInteractions source/target) is remapped so the new page does not
        alias the original. Returns the new page's {name, displayName}.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Page duplication requires PBIR GA format (definition/ folder).")
        src_dir = self._ga_find_page_dir(display_name)
        if not src_dir:
            raise ValueError(f"Page '{display_name}' not found.")

        new_page_id = uuid.uuid4().hex
        dst_dir = self._ga_pages_dir() / new_page_id
        shutil.copytree(src_dir, dst_dir)

        # Rewrite page.json identity.
        pj = dst_dir / "page.json"
        page_data = json.loads(pj.read_text(encoding="utf-8"))
        page_data["name"] = new_page_id
        page_data["displayName"] = new_display_name or f"{display_name} (copy)"

        # Regenerate visual ids and build an old→new map.
        vd = dst_dir / "visuals"
        id_map: dict[str, str] = {}
        visual_dirs: list[Path] = []
        if vd.is_dir():
            for vdir in [d for d in vd.iterdir() if d.is_dir()]:
                vj = vdir / "visual.json"
                if not vj.exists():
                    continue
                old = json.loads(vj.read_text(encoding="utf-8")).get("name", vdir.name)
                id_map[old] = uuid.uuid4().hex[:20]
                visual_dirs.append(vdir)
            for vdir in visual_dirs:
                vj = vdir / "visual.json"
                data = json.loads(vj.read_text(encoding="utf-8"))
                old = data.get("name", vdir.name)
                new = id_map[old]
                data["name"] = new
                if data.get("parentGroupName") in id_map:
                    data["parentGroupName"] = id_map[data["parentGroupName"]]
                vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
                vdir.rename(vdir.parent / new)

        # Remap page-level visualInteractions to the new visual ids.
        for inter in page_data.get("visualInteractions", []):
            for slot in ("source", "target"):
                if inter.get(slot) in id_map:
                    inter[slot] = id_map[inter[slot]]
        pj.write_text(json.dumps(page_data, indent=2), encoding="utf-8")

        meta = self._ga_read_pages_json()
        meta.setdefault("pageOrder", []).append(new_page_id)
        self._ga_write_pages_json(meta)

        return {"name": new_page_id, "displayName": page_data["displayName"],
                "visuals": len(id_map)}

    def visual_clone(
        self,
        page: str,
        visual_name: str,
        target_page: str | None = None,
        *,
        dx: int = 24,
        dy: int = 24,
    ) -> dict[str, Any] | None:
        """Clone a visual under a fresh id, on the same page or another page.

        The clone is offset by (dx, dy) when staying on the same page, and never
        inherits group membership. PBIR GA only. Returns the new {name, page} or
        None if the source visual was not found.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Visual clone requires PBIR GA format (definition/ folder).")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return None
        src_vj, _ = found
        dest_page = target_page or page
        dest_vd = self._ga_visuals_dir(dest_page)
        if dest_vd is None:
            raise ValueError(f"Target page '{dest_page}' not found.")

        new_name = uuid.uuid4().hex[:20]
        dst_dir = dest_vd / new_name
        shutil.copytree(src_vj.parent, dst_dir)

        vj = dst_dir / "visual.json"
        data = json.loads(vj.read_text(encoding="utf-8"))
        data["name"] = new_name
        data.pop("parentGroupName", None)  # never auto-join a group
        if target_page is None:
            pos = data.setdefault("position", {})
            pos["x"] = pos.get("x", 0) + dx
            pos["y"] = pos.get("y", 0) + dy
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"name": new_name, "page": dest_page}

    def visual_move(self, page: str, visual_name: str, target_page: str) -> dict[str, Any] | None:
        """Move a visual to another page, keeping its id. PBIR GA only.

        Drops group membership and removes any visualInteractions on the source
        page that referenced it (they would otherwise dangle). Returns
        {name, page} or None if the source visual was not found.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Visual move requires PBIR GA format (definition/ folder).")
        if target_page == page:
            raise ValueError("Source and target page are the same.")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return None
        src_vj, data = found
        dest_vd = self._ga_visuals_dir(target_page)
        if dest_vd is None:
            raise ValueError(f"Target page '{target_page}' not found.")

        name = data.get("name", src_vj.parent.name)
        data.pop("parentGroupName", None)
        src_vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        shutil.move(str(src_vj.parent), str(dest_vd / src_vj.parent.name))

        # Scrub dangling interactions on the source page.
        src_page_dir = self._ga_find_page_dir(page)
        if src_page_dir:
            pj = src_page_dir / "page.json"
            pdata = json.loads(pj.read_text(encoding="utf-8"))
            inters = pdata.get("visualInteractions")
            if inters:
                pdata["visualInteractions"] = [
                    i for i in inters if name not in (i.get("source"), i.get("target"))
                ]
                pj.write_text(json.dumps(pdata, indent=2), encoding="utf-8")
        return {"name": name, "page": target_page}

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

        objects = data.setdefault("visual", {}).setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        # Merge into the field's existing entry so a previously-applied data bar,
        # icon set or font colour on the same field is preserved (Desktop keeps a
        # single values entry per field with multiple property keys).
        self._upsert_values_entry(
            values_obj, selector, query_ref,
            {"backColor": {"solid": {"color": {"expr": gradient_expr}}}},
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

        objects = data.setdefault("visual", {}).setdefault("objects", {})
        values_obj = objects.setdefault("values", [])
        self._upsert_values_entry(
            values_obj, selector, query_ref,
            {
                "dataBarEnabled": {"expr": {"Literal": {"Value": "true"}}},
                "positiveColor": {
                    "solid": {"color": {"expr": {"Literal": {"Value": f"'{positive_color}'"}}}}
                },
                "negativeColor": {
                    "solid": {"color": {"expr": {"Literal": {"Value": f"'{negative_color}'"}}}}
                },
            },
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

    # ── Analytics: constant reference line ─────────────────────────────────────
    # A constant line lives under visual.objects.referenceLine as a list entry with
    # its own selector id and properties (show/value/lineColor/style/displayName).
    # Each call adds one line; ids keep multiple lines distinct.

    def visual_add_reference_line(
        self,
        page: str,
        visual_name: str,
        value: float,
        *,
        name: str = "Target",
        color: str = "#E81123",
        style: str = "dashed",
        show_label: bool = True,
    ) -> bool:
        """Add a constant Y reference line to a cartesian chart. PBIR GA only.

        style: 'solid' | 'dashed' | 'dotted'. Returns True if found and updated.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Reference lines require PBIR GA format (definition/ folder).")
        if style not in ("solid", "dashed", "dotted"):
            raise ValueError("style must be 'solid', 'dashed' or 'dotted'")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        entry = {
            "selector": {"id": uuid.uuid4().hex[:20]},
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "displayName": {"expr": {"Literal": {"Value": f"'{name}'"}}},
                "value": {"expr": {"Literal": {"Value": self._num_literal(value)}}},
                "lineColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}},
                "style": {"expr": {"Literal": {"Value": f"'{style}'"}}},
                "dataLabelShow": {
                    "expr": {"Literal": {"Value": "true" if show_label else "false"}}
                },
            },
        }
        objects = data.setdefault("visual", {}).setdefault("objects", {})
        objects.setdefault("referenceLine", []).append(entry)
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # ── Analytics: trend line / forecast / sparkline ───────────────────────────
    # These follow the same objects.<name> analytics-container shape as
    # referenceLine. Trend and forecast are single-instance objects, so each call
    # replaces the object (re-applying updates it rather than stacking duplicates).

    def _bool_literal(self, flag: bool) -> dict[str, Any]:
        return {"expr": {"Literal": {"Value": "true" if flag else "false"}}}

    def _color_solid(self, hex_color: str) -> dict[str, Any]:
        return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hex_color}'"}}}}}

    def _num_expr(self, value: float | int) -> dict[str, Any]:
        return {"expr": {"Literal": {"Value": self._num_literal(value)}}}

    def _require_ga_visual(
        self, page: str, visual_name: str, feature: str
    ) -> tuple[Any, dict[str, Any]] | None:
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError(f"{feature} requires PBIR GA format (definition/ folder).")
        return self._ga_find_visual_json(page, visual_name)

    def visual_add_trend_line(
        self,
        page: str,
        visual_name: str,
        *,
        color: str = "#118DFF",
        style: str = "dashed",
        transparency: int = 0,
        combine_series: bool = False,
    ) -> bool:
        """Add (or update) a trend line on a cartesian chart. PBIR GA only.

        style: 'solid' | 'dashed' | 'dotted'. Returns True if found and updated.
        """
        if style not in ("solid", "dashed", "dotted"):
            raise ValueError("style must be 'solid', 'dashed' or 'dotted'")
        found = self._require_ga_visual(page, visual_name, "Trend lines")
        if not found:
            return False
        vj, data = found
        props = {
            "show": self._bool_literal(True),
            "lineColor": self._color_solid(color),
            "style": {"expr": {"Literal": {"Value": f"'{style}'"}}},
            "transparency": self._num_expr(transparency),
            "combineSeries": self._bool_literal(combine_series),
        }
        objects = data.setdefault("visual", {}).setdefault("objects", {})
        objects["trend"] = [{"properties": props}]
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    def visual_add_forecast(
        self,
        page: str,
        visual_name: str,
        *,
        length: int = 10,
        confidence_level: float = 0.95,
        seasonality: int | None = None,
        ignore_last: int = 0,
        color: str = "#118DFF",
        show_confidence_band: bool = True,
    ) -> bool:
        """Add (or update) a forecast on a line chart with a date/numeric axis.

        length: number of points to forecast forward. confidence_level: 0..1
        (e.g. 0.95). seasonality: points per cycle (None = auto-detect).
        Returns True if the visual was found and updated.
        """
        if not 0 < confidence_level < 1:
            raise ValueError("confidence_level must be between 0 and 1 (e.g. 0.95)")
        if length < 1:
            raise ValueError("length must be >= 1")
        found = self._require_ga_visual(page, visual_name, "Forecast")
        if not found:
            return False
        vj, data = found
        props: dict[str, Any] = {
            "show": self._bool_literal(True),
            "forecastLength": self._num_expr(length),
            "confidenceLevel": self._num_expr(confidence_level),
            "confidenceBand": self._bool_literal(show_confidence_band),
            "ignoreLast": self._num_expr(ignore_last),
            "lineColor": self._color_solid(color),
        }
        if seasonality is not None:
            props["seasonality"] = self._num_expr(seasonality)
        objects = data.setdefault("visual", {}).setdefault("objects", {})
        objects["forecast"] = [{"properties": props}]
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    # Note: table/matrix sparklines are intentionally NOT implemented as a format
    # object. Live testing in Power BI Desktop showed a standalone
    # ``objects.sparkline`` entry is stripped on load — real sparklines require a
    # query-level sparkline grouping (an extra projection), not just formatting.
    # Deferred until that binding is reverse-engineered and verified.

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

    # ── Button / shape actions ─────────────────────────────────────────────────
    # A button's action is a `visualLink` entry under visualContainerObjects
    # (the GA home for the legacy vcObjects.visualLink). `type` selects the action
    # and the target property depends on it: PageNavigation→navigationSection
    # (page GUID), Bookmark→bookmark (bookmark id), WebUrl→webUrl. Back / Drill /
    # QnA need no target.

    ACTION_TYPES = ("Back", "PageNavigation", "Bookmark", "Drill", "QnA", "WebUrl")

    def visual_set_action(
        self, page: str, visual_name: str, action_type: str, target: str | None = None
    ) -> bool:
        """Wire a navigation/action onto a button (or shape) visual. PBIR GA only.

        For PageNavigation, ``target`` is a page display name or GUID; for Bookmark
        it is a bookmark display name or id; for WebUrl it is the URL. Back/Drill/
        QnA ignore ``target``. Returns True if the visual was found and updated.
        """
        self._require_load()
        if self._format != "pbir_ga":
            raise RuntimeError("Button actions require PBIR GA format (definition/ folder).")
        if action_type not in self.ACTION_TYPES:
            raise ValueError(f"type must be one of {self.ACTION_TYPES}")
        found = self._ga_find_visual_json(page, visual_name)
        if not found:
            return False
        vj, data = found

        props: dict[str, Any] = {
            "type": {"expr": {"Literal": {"Value": f"'{action_type}'"}}}
        }
        if action_type == "PageNavigation":
            if not target:
                raise ValueError("PageNavigation needs a target page.")
            page_id = next(
                (p["name"] for p in self.page_list()
                 if target in (p["displayName"], p["name"])),
                target,
            )
            props["navigationSection"] = {"expr": {"Literal": {"Value": f"'{page_id}'"}}}
        elif action_type == "Bookmark":
            if not target:
                raise ValueError("Bookmark action needs a target bookmark.")
            bm_id = next(
                (b["name"] for b in self.bookmark_list()
                 if target in (b["displayName"], b["name"])),
                target,
            )
            props["bookmark"] = {"expr": {"Literal": {"Value": f"'{bm_id}'"}}}
        elif action_type == "WebUrl":
            if not target:
                raise ValueError("WebUrl action needs a target URL.")
            props["webUrl"] = {"expr": {"Literal": {"Value": f"'{target}'"}}}

        vco = data.setdefault("visual", {}).setdefault("visualContainerObjects", {})
        vco["visualLink"] = [{"properties": props}]
        vj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

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
