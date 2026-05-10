"""FastAPI REST server — wraps all pbi-cli commands as HTTP endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

try:
    from pathlib import Path

    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="pbi-server", version="0.1.0.dev0", docs_url="/api/docs")

    # ── Singleton backend ──────────────────────────────────────────────────
    _backend: Any = None

    def get_backend() -> Any:
        global _backend
        if _backend is None:
            from pbi_cli.backends.tom_backend import TomBackend

            _backend = TomBackend()
        if not _backend.is_connected():
            try:
                _backend.connect()
            except Exception as exc:
                raise HTTPException(
                    status_code=503, detail=f"Not connected to Power BI Desktop: {exc}"
                )
        return _backend

    # ── Status ─────────────────────────────────────────────────────────────

    @app.get("/api/status")
    def status() -> dict:
        from pbi_cli.backends.tom_backend import find_pbi_port

        port = find_pbi_port()
        if port is None:
            return {"connected": False, "message": "No running Power BI Desktop found"}
        try:
            b = get_backend()
            info = b.model_info()
            return {
                "connected": True,
                "port": port,
                "model": info["name"],
                "compatibilityLevel": info.get("compatibilityLevel"),
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    # ── Model ──────────────────────────────────────────────────────────────

    @app.get("/api/tables")
    def list_tables() -> list[dict]:
        return get_backend().table_list()

    @app.get("/api/columns")
    def list_columns(table: str | None = None) -> list[dict]:
        return get_backend().column_list(table=table)

    @app.get("/api/relationships")
    def list_relationships() -> list[dict]:
        return get_backend().relationship_list()

    # ── Measures ───────────────────────────────────────────────────────────

    @app.get("/api/measures")
    def list_measures(table: str | None = None) -> list[dict]:
        return get_backend().measure_list(table=table)

    class MeasureCreate(BaseModel):
        table: str
        name: str
        expression: str
        formatString: str = ""
        description: str = ""

    @app.post("/api/measures", status_code=201)
    def create_measure(body: MeasureCreate) -> dict:
        kwargs: dict[str, Any] = {}
        if body.formatString:
            kwargs["formatString"] = body.formatString
        if body.description:
            kwargs["description"] = body.description
        try:
            return get_backend().measure_add(body.table, body.name, body.expression, **kwargs)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    class MeasureUpdate(BaseModel):
        expression: str | None = None
        formatString: str | None = None
        description: str | None = None

    @app.patch("/api/measures/{table}/{name}")
    def update_measure(table: str, name: str, body: MeasureUpdate) -> dict:
        kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            return get_backend().measure_update(table, name, **kwargs)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Measure '{name}' not found in '{table}'")

    @app.delete("/api/measures/{table}/{name}", status_code=204)
    def delete_measure(table: str, name: str) -> None:
        try:
            get_backend().measure_delete(table, name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Measure '{name}' not found")

    # ── DAX ────────────────────────────────────────────────────────────────

    class DaxQuery(BaseModel):
        expression: str

    @app.post("/api/dax/query")
    def dax_query(body: DaxQuery) -> list[dict]:
        try:
            return get_backend().dax_query(body.expression)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/dax/validate")
    def dax_validate(body: DaxQuery) -> dict:
        return get_backend().dax_validate(body.expression)

    # ── Governance ─────────────────────────────────────────────────────────

    @app.get("/api/govern/check")
    def govern_check() -> list[dict]:
        from pbi_cli.governance.engine import GovernanceEngine

        return GovernanceEngine(get_backend()).run_all()

    @app.post("/api/govern/fix")
    def govern_fix() -> dict:
        from pbi_cli.governance.engine import GovernanceEngine

        engine = GovernanceEngine(get_backend())
        violations = engine.run_all()
        fixable = [v for v in violations if v.get("autoFixable")]
        fixed = engine.auto_fix(fixable)
        return {"fixed": fixed}

    # ── Docs ───────────────────────────────────────────────────────────────

    @app.get("/api/docs/markdown", response_class=__import__("fastapi").responses.PlainTextResponse)
    def docs_markdown() -> str:
        from pbi_cli.docs_gen.markdown import MarkdownDocsGenerator

        return MarkdownDocsGenerator(get_backend()).generate()

    # ── Suggest ────────────────────────────────────────────────────────────

    @app.get("/api/suggest/measures")
    def suggest_measures() -> list[dict]:
        b = get_backend()
        from pbi_cli.commands.model import _build_measure_suggestions

        return _build_measure_suggestions(b.table_list(), b.column_list())

    @app.post("/api/suggest/visuals")
    def suggest_visuals(body: dict) -> list[dict]:
        from pbi_cli.intelligence.visual_recommender import VisualRecommender

        measures = body.get("measures", [])
        return VisualRecommender().recommend(measures)

    # ── Static frontend ────────────────────────────────────────────────────

    _static_dir = Path(__file__).parent / "static"
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(_static_dir / "index.html"))

except ImportError:
    app = None  # type: ignore[assignment]
