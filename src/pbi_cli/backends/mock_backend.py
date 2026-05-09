"""MockTomBackend — fixture-based mock for testing without Power BI Desktop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE: dict[str, Any] = {
    "model": {"name": "MockModel", "compatibility_level": 1600},
    "tables": [
        {"name": "Sales", "isHidden": False},
        {"name": "Products", "isHidden": False},
        {"name": "Customers", "isHidden": False},
        {"name": "Calendar", "isHidden": False},
    ],
    "columns": [
        {"table": "Sales", "name": "SalesKey", "dataType": "Int64", "isHidden": False},
        {"table": "Sales", "name": "ProductKey", "dataType": "Int64", "isHidden": False},
        {"table": "Sales", "name": "CustomerKey", "dataType": "Int64", "isHidden": False},
        {"table": "Sales", "name": "DateKey", "dataType": "Int64", "isHidden": False},
        {"table": "Sales", "name": "Revenue", "dataType": "Decimal", "isHidden": False},
        {"table": "Sales", "name": "Units", "dataType": "Int64", "isHidden": False},
        {"table": "Products", "name": "ProductKey", "dataType": "Int64", "isHidden": False},
        {"table": "Products", "name": "ProductName", "dataType": "String", "isHidden": False},
        {"table": "Products", "name": "Category", "dataType": "String", "isHidden": False},
        {"table": "Customers", "name": "CustomerKey", "dataType": "Int64", "isHidden": False},
        {"table": "Customers", "name": "CustomerName", "dataType": "String", "isHidden": False},
        {"table": "Customers", "name": "Region", "dataType": "String", "isHidden": False},
        {"table": "Calendar", "name": "DateKey", "dataType": "Int64", "isHidden": False},
        {"table": "Calendar", "name": "Date", "dataType": "DateTime", "isHidden": False},
        {"table": "Calendar", "name": "Year", "dataType": "Int64", "isHidden": False},
        {"table": "Calendar", "name": "Month", "dataType": "Int64", "isHidden": False},
        {"table": "Calendar", "name": "Quarter", "dataType": "String", "isHidden": False},
    ],
    "relationships": [
        {"from": "Sales[ProductKey]", "to": "Products[ProductKey]", "cardinality": "ManyToOne"},
        {"from": "Sales[CustomerKey]", "to": "Customers[CustomerKey]", "cardinality": "ManyToOne"},
        {"from": "Sales[DateKey]", "to": "Calendar[DateKey]", "cardinality": "ManyToOne"},
    ],
    "measures": [
        {"table": "Sales", "name": "Total Revenue", "expression": "SUM(Sales[Revenue])", "formatString": "#,0.00"},
        {"table": "Sales", "name": "Total Units", "expression": "SUM(Sales[Units])", "formatString": "#,0"},
    ],
}


class MockTomBackend:
    """Fixture-based TOM backend for unit and integration testing.

    Requires no Power BI Desktop, no Windows, no DLLs.
    All writes go to in-memory state and are inspectable via get_state().
    """

    def __init__(self, fixture: dict[str, Any] | None = None, fixture_path: Path | None = None) -> None:
        if fixture_path is not None:
            self._state: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
        elif fixture is not None:
            self._state = json.loads(json.dumps(fixture))  # deep copy
        else:
            self._state = json.loads(json.dumps(DEFAULT_FIXTURE))
        self._connected = False
        self._write_log: list[dict[str, Any]] = []

    # --- Connection ---

    def connect(self, **kwargs: Any) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_state(self) -> dict[str, Any]:
        """Return current in-memory state (for test assertions)."""
        return self._state

    def get_write_log(self) -> list[dict[str, Any]]:
        """Return all write operations performed (for test assertions)."""
        return self._write_log

    # --- Model info ---

    def model_info(self) -> dict[str, Any]:
        return dict(self._state.get("model", {}))

    def table_list(self) -> list[dict[str, Any]]:
        return list(self._state.get("tables", []))

    def column_list(self, table: str | None = None) -> list[dict[str, Any]]:
        cols = self._state.get("columns", [])
        if table:
            return [c for c in cols if c["table"] == table]
        return list(cols)

    def relationship_list(self) -> list[dict[str, Any]]:
        return list(self._state.get("relationships", []))

    # --- Measures ---

    def measure_list(self, table: str | None = None) -> list[dict[str, Any]]:
        measures = self._state.get("measures", [])
        if table:
            return [m for m in measures if m["table"] == table]
        return list(measures)

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        record = {"table": table, "name": name, "expression": expression, **kwargs}
        self._state.setdefault("measures", []).append(record)
        self._write_log.append({"op": "measure_add", "data": record})
        return dict(record)

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        for m in self._state.get("measures", []):
            if m["table"] == table and m["name"] == name:
                # Handle rename specially so the key stays consistent
                new_name = kwargs.pop("new_name", None)
                if new_name:
                    m["name"] = new_name
                m.update(kwargs)
                self._write_log.append({"op": "measure_update", "data": {"table": table, "name": name, **kwargs}})
                return dict(m)
        raise KeyError(f"Measure '{table}'['{name}'] not found.")

    def measure_delete(self, table: str, name: str) -> None:
        measures = self._state.get("measures", [])
        before = len(measures)
        self._state["measures"] = [m for m in measures if not (m["table"] == table and m["name"] == name)]
        if len(self._state["measures"]) == before:
            raise KeyError(f"Measure '{table}'['{name}'] not found.")
        self._write_log.append({"op": "measure_delete", "data": {"table": table, "name": name}})

    # --- Tables ---

    def table_add(self, name: str, **kwargs: Any) -> dict[str, Any]:
        record = {"name": name, **kwargs}
        self._state.setdefault("tables", []).append(record)
        self._write_log.append({"op": "table_add", "data": record})
        return dict(record)

    def table_delete(self, name: str) -> None:
        tables = self._state.get("tables", [])
        self._state["tables"] = [t for t in tables if t["name"] != name]
        self._write_log.append({"op": "table_delete", "data": {"name": name}})

    # --- Columns ---

    def column_add(self, table: str, name: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        record = {"table": table, "name": name, "dataType": data_type, **kwargs}
        self._state.setdefault("columns", []).append(record)
        self._write_log.append({"op": "column_add", "data": record})
        return dict(record)

    def column_delete(self, table: str, name: str) -> None:
        cols = self._state.get("columns", [])
        self._state["columns"] = [c for c in cols if not (c["table"] == table and c["name"] == name)]
        self._write_log.append({"op": "column_delete", "data": {"table": table, "name": name}})

    # --- Relationships ---

    def relationship_add(self, from_table: str, from_column: str, to_table: str, to_column: str, **kwargs: Any) -> dict[str, Any]:
        record = {
            "from": f"{from_table}[{from_column}]",
            "to": f"{to_table}[{to_column}]",
            "cardinality": kwargs.get("cardinality", "ManyToOne"),
            **kwargs,
        }
        self._state.setdefault("relationships", []).append(record)
        self._write_log.append({"op": "relationship_add", "data": record})
        return dict(record)

    # --- Hierarchies ---

    def hierarchy_list(self, table: str | None = None) -> list[dict[str, Any]]:
        hierarchies = self._state.get("hierarchies", [])
        if table:
            return [h for h in hierarchies if h["table"] == table]
        return list(hierarchies)

    def hierarchy_add(self, table: str, name: str, levels: list[dict[str, Any]]) -> dict[str, Any]:
        record = {"table": table, "name": name, "levels": levels}
        self._state.setdefault("hierarchies", []).append(record)
        self._write_log.append({"op": "hierarchy_add", "data": record})
        return dict(record)

    def hierarchy_delete(self, table: str, name: str) -> None:
        self._state["hierarchies"] = [
            h for h in self._state.get("hierarchies", [])
            if not (h["table"] == table and h["name"] == name)
        ]
        self._write_log.append({"op": "hierarchy_delete", "data": {"table": table, "name": name}})

    # --- Calculation Groups ---

    def calc_group_list(self) -> list[dict[str, Any]]:
        return list(self._state.get("calc_groups", []))

    def calc_group_add(self, name: str, precedence: int = 0) -> dict[str, Any]:
        record = {"table": name, "precedence": precedence, "items": []}
        self._state.setdefault("calc_groups", []).append(record)
        self._write_log.append({"op": "calc_group_add", "data": record})
        return dict(record)

    def calc_item_add(self, group_table: str, name: str, expression: str, ordinal: int = 0) -> dict[str, Any]:
        record = {"group": group_table, "name": name, "expression": expression, "ordinal": ordinal}
        for cg in self._state.get("calc_groups", []):
            if cg["table"] == group_table:
                cg.setdefault("items", []).append(record)
        self._write_log.append({"op": "calc_item_add", "data": record})
        return dict(record)

    def calc_item_delete(self, group_table: str, name: str) -> None:
        for cg in self._state.get("calc_groups", []):
            if cg["table"] == group_table:
                cg["items"] = [i for i in cg.get("items", []) if i["name"] != name]
        self._write_log.append({"op": "calc_item_delete", "data": {"group": group_table, "name": name}})

    # --- RLS Roles ---

    def role_list(self) -> list[dict[str, Any]]:
        return list(self._state.get("roles", []))

    def role_add(self, name: str, table: str, filter_expression: str) -> dict[str, Any]:
        record = {"name": name, "modelPermission": "Read", "tablePermissions": [{"table": table, "filterExpression": filter_expression}]}
        self._state.setdefault("roles", []).append(record)
        self._write_log.append({"op": "role_add", "data": record})
        return dict(record)

    def role_delete(self, name: str) -> None:
        self._state["roles"] = [r for r in self._state.get("roles", []) if r["name"] != name]
        self._write_log.append({"op": "role_delete", "data": {"name": name}})

    def role_test(self, role_name: str, dax_expression: str) -> dict[str, Any]:
        return {"role": role_name, "rowCount": 1, "rows": [{"__mock": True, "expression": dax_expression}]}

    # --- Partitions ---

    def partition_list(self, table: str | None = None) -> list[dict[str, Any]]:
        partitions = self._state.get("partitions", [])
        if table:
            return [p for p in partitions if p["table"] == table]
        return list(partitions)

    def partition_add(self, table: str, name: str, query: str) -> dict[str, Any]:
        record = {"table": table, "name": name, "mode": "Import", "state": "Ready", "source": query}
        self._state.setdefault("partitions", []).append(record)
        self._write_log.append({"op": "partition_add", "data": record})
        return dict(record)

    def partition_delete(self, table: str, name: str) -> None:
        self._state["partitions"] = [
            p for p in self._state.get("partitions", [])
            if not (p["table"] == table and p["name"] == name)
        ]
        self._write_log.append({"op": "partition_delete", "data": {"table": table, "name": name}})

    def partition_refresh(self, table: str, name: str) -> dict[str, Any]:
        self._write_log.append({"op": "partition_refresh", "data": {"table": table, "name": name}})
        return {"table": table, "partition": name, "status": "refresh_requested"}

    # --- Model Diff ---

    def model_diff(self, snapshot_path: str) -> dict[str, Any]:
        return {"snapshot": snapshot_path, "added": [], "removed": [], "changed": [], "unchanged_count": 0, "has_changes": False}

    # --- DAX ---

    def dax_query(self, expression: str) -> list[dict[str, Any]]:
        return [{"__result": "mock", "expression": expression}]

    def dax_validate(self, expression: str) -> dict[str, Any]:
        return {"valid": True, "expression": expression}

    # --- TMDL ---

    def tmdl_export(self, path: str) -> None:
        self._write_log.append({"op": "tmdl_export", "data": {"path": path}})

    def tmdl_import(self, path: str) -> None:
        self._write_log.append({"op": "tmdl_import", "data": {"path": path}})
