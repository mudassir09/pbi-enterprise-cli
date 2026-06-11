"""RestBackend — live DAX via the Power BI executeQueries REST endpoint.

Works from any OS (no Windows, no .NET): runs DAX against a published dataset
in any workspace. Metadata is discovered through DAX INFO functions, so
model/measure/column listings and read-only governance work against live
Fabric/Premium models on ubuntu-latest.

Connection resolution: connect(workspace_id=..., dataset_id=...) or the
PBI_WORKSPACE_ID / PBI_DATASET_ID environment variables.
"""

from __future__ import annotations

import os
from typing import Any

from pbi_cli import fabric_api

_READ_ONLY_MSG = (
    "The rest backend is read-only (executeQueries API). "
    "Use --backend xmla or desktop for model writes."
)


def _strip_brackets(row: dict[str, Any]) -> dict[str, Any]:
    """executeQueries returns column keys like 'Table[Column]' or '[Name]'."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        clean = key
        if clean.endswith("]"):
            clean = clean[:-1]
            clean = clean.rsplit("[", 1)[-1]
        out[clean] = value
    return out


class RestBackend:
    """Read-only TOM-protocol backend over the Power BI REST API."""

    def __init__(
        self,
        workspace_id: str | None = None,
        dataset_id: str | None = None,
        token: str | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.dataset_id = dataset_id
        self._token = token
        self._connected = False
        self._table_id_map: dict[Any, str] | None = None

    # --- Connection ---

    def connect(self, **kwargs: Any) -> None:
        self.workspace_id = (
            kwargs.get("workspace_id") or self.workspace_id or os.environ.get("PBI_WORKSPACE_ID")
        )
        self.dataset_id = (
            kwargs.get("dataset_id") or self.dataset_id or os.environ.get("PBI_DATASET_ID")
        )
        if not self.workspace_id or not self.dataset_id:
            raise ConnectionError(
                "rest backend needs a workspace and dataset: set PBI_WORKSPACE_ID and "
                "PBI_DATASET_ID, or pass --connection with workspace/dataset ids."
            )
        if self._token is None:
            self._token = fabric_api.get_token()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # --- DAX ---

    def _auth(self) -> str:
        if not self._connected or self._token is None:
            self.connect()
        assert self._token is not None
        return self._token

    def dax_query(self, expression: str) -> list[dict[str, Any]]:
        url = (
            f"{fabric_api.POWERBI_API_BASE}/groups/{self.workspace_id}"
            f"/datasets/{self.dataset_id}/executeQueries"
        )
        body = {
            "queries": [{"query": expression}],
            "serializerSettings": {"includeNulls": True},
        }
        result = fabric_api.post(url, self._auth(), payload=body)
        rows: list[dict[str, Any]] = []
        for res in result.get("results", []):
            for tbl in res.get("tables", []):
                rows.extend(_strip_brackets(r) for r in tbl.get("rows", []))
        return rows

    def dax_validate(self, expression: str) -> dict[str, Any]:
        probe = expression if expression.lstrip().upper().startswith(("EVALUATE", "DEFINE")) else (
            f"EVALUATE ROW(\"result\", {expression})"
        )
        try:
            self.dax_query(probe)
            return {"valid": True, "expression": expression}
        except fabric_api.FabricApiError as exc:
            return {"valid": False, "expression": expression, "error": exc.message}

    # --- Model info via INFO functions ---

    def _info(self, fn: str) -> list[dict[str, Any]]:
        return self.dax_query(f"EVALUATE INFO.{fn}()")

    def _tables_by_id(self) -> dict[Any, str]:
        if self._table_id_map is None:
            self._table_id_map = {
                t.get("ID"): str(t.get("Name", "")) for t in self._info("TABLES")
            }
        return self._table_id_map

    def model_info(self) -> dict[str, Any]:
        url = (
            f"{fabric_api.POWERBI_API_BASE}/groups/{self.workspace_id}"
            f"/datasets/{self.dataset_id}"
        )
        ds = fabric_api.get(url, self._auth())
        return {
            "name": ds.get("name", self.dataset_id),
            "compatibilityLevel": ds.get("targetStorageMode", ""),
            "workspaceId": self.workspace_id,
            "datasetId": self.dataset_id,
            "webUrl": ds.get("webUrl", ""),
        }

    def table_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.get("Name", ""),
                "isHidden": bool(t.get("IsHidden")),
            }
            for t in self._info("TABLES")
            if not str(t.get("Name", "")).startswith("DateTableTemplate")
        ]

    def column_list(self, table: str | None = None) -> list[dict[str, Any]]:
        id_map = self._tables_by_id()
        cols = []
        for c in self._info("COLUMNS"):
            tname = id_map.get(c.get("TableID"), "")
            name = c.get("ExplicitName") or c.get("InferredName") or ""
            if not name or name == "RowNumber-2662979B-1795-4F74-8F37-6A1BA8059B61":
                continue
            cols.append({
                "table": tname,
                "name": name,
                "dataType": str(c.get("ExplicitDataType", "")),
                "isHidden": bool(c.get("IsHidden")),
            })
        if table:
            return [c for c in cols if c["table"] == table]
        return cols

    def relationship_list(self) -> list[dict[str, Any]]:
        id_map = self._tables_by_id()
        col_name: dict[Any, tuple[str, str]] = {}
        for c in self._info("COLUMNS"):
            col_name[c.get("ID")] = (
                id_map.get(c.get("TableID"), ""),
                str(c.get("ExplicitName") or c.get("InferredName") or ""),
            )
        rels = []
        for r in self._info("RELATIONSHIPS"):
            ft, fc = col_name.get(r.get("FromColumnID"), ("", ""))
            tt, tc = col_name.get(r.get("ToColumnID"), ("", ""))
            rels.append({
                "from": f"{ft}[{fc}]",
                "to": f"{tt}[{tc}]",
                "cardinality": "ManyToOne",
                "isActive": bool(r.get("IsActive", True)),
            })
        return rels

    def measure_list(self, table: str | None = None) -> list[dict[str, Any]]:
        id_map = self._tables_by_id()
        measures = [
            {
                "table": id_map.get(m.get("TableID"), ""),
                "name": m.get("Name", ""),
                "expression": m.get("Expression", ""),
                "formatString": m.get("FormatString") or "",
                "description": m.get("Description") or "",
                "isHidden": bool(m.get("IsHidden")),
            }
            for m in self._info("MEASURES")
        ]
        if table:
            return [m for m in measures if m["table"] == table]
        return measures

    def role_list(self) -> list[dict[str, Any]]:
        try:
            return [
                {"name": r.get("Name", ""), "modelPermission": str(r.get("ModelPermission", ""))}
                for r in self._info("ROLES")
            ]
        except fabric_api.FabricApiError:
            return []

    def partition_list(self, table: str | None = None) -> list[dict[str, Any]]:
        id_map = self._tables_by_id()
        parts = [
            {
                "table": id_map.get(p.get("TableID"), ""),
                "name": p.get("Name", ""),
                "mode": str(p.get("Mode", "")),
                "state": str(p.get("State", "")),
                "source": "",
            }
            for p in self._info("PARTITIONS")
        ]
        if table:
            return [p for p in parts if p["table"] == table]
        return parts

    # --- Writes: not supported over executeQueries ---

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def measure_delete(self, table: str, name: str) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    def table_add(self, name: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def table_delete(self, name: str) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    def column_add(self, table: str, name: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def column_delete(self, table: str, name: str) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    def relationship_add(
        self, from_table: str, from_column: str, to_table: str, to_column: str, **kwargs: Any
    ) -> dict[str, Any]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def tmdl_export(self, path: str) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    def tmdl_import(self, path: str) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)
