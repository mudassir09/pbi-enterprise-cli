"""TOM backend connecting to Power BI Desktop via pythonnet + AMO."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console(stderr=True)

_DLL_DIR = Path(__file__).parent.parent / "dlls"


def _load_amo() -> None:
    """Add AMO DLL directory to path and load assemblies."""
    import clr  # type: ignore[import]
    dll_dir = str(_DLL_DIR)
    if dll_dir not in sys.path:
        sys.path.append(dll_dir)
    clr.AddReference("Microsoft.AnalysisServices.Tabular")
    clr.AddReference("Microsoft.AnalysisServices.Core")
    clr.AddReference("Microsoft.AnalysisServices.AdomdClient")


def find_pbi_port() -> int | None:
    """Auto-discover the local Analysis Services port used by Power BI Desktop."""
    try:
        tasklist = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msmdsrv.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
        )
        pid_match = re.search(r'"msmdsrv\.exe","(\d+)"', tasklist.stdout)
        if not pid_match:
            return None
        pid = pid_match.group(1)

        netstat = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in netstat.stdout.splitlines():
            if pid in line and "LISTENING" in line:
                m = re.search(r"(?:127\.0\.0\.1|0\.0\.0\.0):(\d+)", line)
                if m and m.group(1) != "0":
                    return int(m.group(1))
    except Exception:
        pass
    return None


class TomBackend:
    """Connects to a running Power BI Desktop process via pythonnet + AMO.

    Auto-discovers the local Analysis Services port from the MSMDSRV.exe process.
    Pass port= to connect() to override.
    """

    def __init__(self) -> None:
        self._connected = False
        self._server: Any = None
        self._db: Any = None
        self._model: Any = None
        self._port: int | None = None

    def connect(self, port: int | None = None, **kwargs: Any) -> None:
        if sys.platform != "win32":
            raise RuntimeError("TOM backend requires Windows and Power BI Desktop.")

        _load_amo()
        from Microsoft.AnalysisServices.Tabular import Server  # type: ignore[import]

        target_port = port or find_pbi_port()
        if not target_port:
            raise RuntimeError(
                "Could not find a running Power BI Desktop instance. "
                "Open a PBIX file in Power BI Desktop and try again."
            )

        self._server = Server()
        self._server.Connect(f"Data Source=localhost:{target_port}")
        self._port = target_port

        # Get the first non-hidden database (the user's model)
        dbs = [db for db in self._server.Databases if not db.Name.startswith("$")]
        if not dbs:
            dbs = list(self._server.Databases)
        self._db = dbs[0]
        self._model = self._db.Model
        self._connected = True

    def disconnect(self) -> None:
        if self._server:
            try:
                self._server.Disconnect()
            except Exception:
                pass
        self._connected = False
        self._server = None
        self._db = None
        self._model = None

    def is_connected(self) -> bool:
        return self._connected

    # --- Model info ---

    def model_info(self) -> dict[str, Any]:
        self._require_connection()
        return {
            "name": self._db.Name,
            "compatibilityLevel": self._db.CompatibilityLevel,
            "port": self._port,
            "server": str(self._server.Name),
        }

    def table_list(self) -> list[dict[str, Any]]:
        self._require_connection()
        return [
            {"name": t.Name, "isHidden": t.IsHidden, "description": t.Description or ""}
            for t in self._model.Tables
            if not t.IsHidden
        ]

    def column_list(self, table: str | None = None) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for t in self._model.Tables:
            if t.IsHidden:
                continue
            if table and t.Name != table:
                continue
            for col in t.Columns:
                if col.IsHidden or col.Type.ToString() == "RowNumber":
                    continue
                results.append({
                    "table": t.Name,
                    "name": col.Name,
                    "dataType": col.DataType.ToString(),
                    "isHidden": col.IsHidden,
                    "description": col.Description or "",
                })
        return results

    def relationship_list(self) -> list[dict[str, Any]]:
        self._require_connection()
        return [
            {
                "from": f"{r.FromTable.Name}[{r.FromColumn.Name}]",
                "to": f"{r.ToTable.Name}[{r.ToColumn.Name}]",
                "isActive": r.IsActive,
                "crossFilteringBehavior": r.CrossFilteringBehavior.ToString(),
            }
            for r in self._model.Relationships
        ]

    # --- Measures ---

    def measure_list(self, table: str | None = None) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for t in self._model.Tables:
            if table and t.Name != table:
                continue
            for m in t.Measures:
                results.append({
                    "table": t.Name,
                    "name": m.Name,
                    "expression": m.Expression,
                    "formatString": m.FormatString or "",
                    "description": m.Description or "",
                    "isHidden": m.IsHidden,
                })
        return results

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import Measure  # type: ignore[import]
        target = self._model.Tables.Find(table)
        if not target:
            raise ValueError(f"Table '{table}' not found.")
        m = Measure()
        m.Name = name
        m.Expression = expression
        if "formatString" in kwargs:
            m.FormatString = kwargs["formatString"]
        if "description" in kwargs:
            m.Description = kwargs["description"]
        target.Measures.Add(m)
        self._model.SaveChanges()
        return {"table": table, "name": name, "expression": expression}

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        self._require_connection()
        target = self._model.Tables.Find(table)
        if not target:
            raise ValueError(f"Table '{table}' not found.")
        m = target.Measures.Find(name)
        if not m:
            raise KeyError(f"Measure '{name}' not found in '{table}'.")
        if "expression" in kwargs:
            m.Expression = kwargs["expression"]
        if "formatString" in kwargs:
            m.FormatString = kwargs["formatString"]
        if "description" in kwargs:
            m.Description = kwargs["description"]
        self._model.SaveChanges()
        return {"table": table, "name": name, **kwargs}

    def measure_delete(self, table: str, name: str) -> None:
        self._require_connection()
        target = self._model.Tables.Find(table)
        if not target:
            raise ValueError(f"Table '{table}' not found.")
        m = target.Measures.Find(name)
        if not m:
            raise KeyError(f"Measure '{name}' not found in '{table}'.")
        target.Measures.Remove(m)
        self._model.SaveChanges()

    # --- Tables ---

    def table_add(self, name: str, **kwargs: Any) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import Table  # type: ignore[import]
        t = Table()
        t.Name = name
        self._model.Tables.Add(t)
        self._model.SaveChanges()
        return {"name": name}

    def table_delete(self, name: str) -> None:
        self._require_connection()
        t = self._model.Tables.Find(name)
        if t:
            self._model.Tables.Remove(t)
            self._model.SaveChanges()

    # --- Columns ---

    def column_add(self, table: str, name: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import DataColumn, DataType  # type: ignore[import]
        target = self._model.Tables.Find(table)
        if not target:
            raise ValueError(f"Table '{table}' not found.")
        col = DataColumn()
        col.Name = name
        col.DataType = getattr(DataType, data_type, DataType.String)
        target.Columns.Add(col)
        self._model.SaveChanges()
        return {"table": table, "name": name, "dataType": data_type}

    def column_delete(self, table: str, name: str) -> None:
        self._require_connection()
        target = self._model.Tables.Find(table)
        if target:
            col = target.Columns.Find(name)
            if col:
                target.Columns.Remove(col)
                self._model.SaveChanges()

    # --- Relationships ---

    def relationship_add(self, from_table: str, from_column: str, to_table: str, to_column: str, **kwargs: Any) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import SingleColumnRelationship  # type: ignore[import]
        ft = self._model.Tables.Find(from_table)
        tt = self._model.Tables.Find(to_table)
        if not ft or not tt:
            raise ValueError(f"Tables '{from_table}' or '{to_table}' not found.")
        rel = SingleColumnRelationship()
        rel.FromColumn = ft.Columns.Find(from_column)
        rel.ToColumn = tt.Columns.Find(to_column)
        self._model.Relationships.Add(rel)
        self._model.SaveChanges()
        return {"from": f"{from_table}[{from_column}]", "to": f"{to_table}[{to_column}]"}

    # --- DAX ---

    def dax_query(self, expression: str) -> list[dict[str, Any]]:
        self._require_connection()
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection, AdomdCommand  # type: ignore[import]
        conn_str = f"Data Source=localhost:{self._port}"
        conn = AdomdConnection(conn_str)
        try:
            conn.Open()
            cmd = AdomdCommand(expression, conn)
            reader = cmd.ExecuteReader()
            # Strip surrounding [brackets] that ADOMD adds to column names
            cols = [reader.GetName(i).strip("[]") for i in range(reader.FieldCount)]
            rows = []
            while reader.Read():
                row: dict[str, Any] = {}
                for i, c in enumerate(cols):
                    try:
                        val = reader.GetValue(i)
                        # Convert .NET types to Python primitives
                        row[c] = float(val) if hasattr(val, "ToString") and not isinstance(val, str) else val
                    except Exception:
                        row[c] = None
                rows.append(row)
            reader.Close()
            return rows
        finally:
            conn.Close()

    def dax_validate(self, expression: str) -> dict[str, Any]:
        self._require_connection()
        # Wrap in EVALUATE to test parse — use a DAX query that returns nothing if invalid
        try:
            test_expr = f"EVALUATE ROW(\"__test\", {expression})"
            self.dax_query(test_expr)
            return {"valid": True, "expression": expression}
        except Exception as e:
            return {"valid": False, "expression": expression, "error": str(e)}

    # --- Hierarchies ---

    def hierarchy_list(self, table: str | None = None) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for t in self._model.Tables:
            if table and t.Name != table:
                continue
            for h in t.Hierarchies:
                levels = [
                    {"name": lv.Name, "column": lv.Column.Name, "ordinal": lv.Ordinal}
                    for lv in h.Levels
                ]
                results.append({"table": t.Name, "name": h.Name, "levels": levels})
        return results

    def hierarchy_add(self, table: str, name: str, levels: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import Hierarchy, Level  # type: ignore[import]
        t = self._model.Tables.Find(table)
        if not t:
            raise ValueError(f"Table '{table}' not found.")
        h = Hierarchy()
        h.Name = name
        for i, lv_def in enumerate(levels):
            lv = Level()
            lv.Name = lv_def["name"]
            lv.Column = t.Columns.Find(lv_def["column"])
            lv.Ordinal = i
            h.Levels.Add(lv)
        t.Hierarchies.Add(h)
        self._model.SaveChanges()
        return {"table": table, "name": name, "levels": levels}

    def hierarchy_delete(self, table: str, name: str) -> None:
        self._require_connection()
        t = self._model.Tables.Find(table)
        if t:
            h = t.Hierarchies.Find(name)
            if h:
                t.Hierarchies.Remove(h)
                self._model.SaveChanges()

    # --- Calculation Groups ---

    def calc_group_list(self) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for t in self._model.Tables:
            if not t.CalculationGroup:
                continue
            items = [
                {"name": ci.Name, "expression": ci.Expression, "ordinal": ci.Ordinal}
                for ci in t.CalculationGroup.CalculationItems
            ]
            results.append({"table": t.Name, "precedence": t.CalculationGroup.Precedence, "items": items})
        return results

    def calc_group_add(self, name: str, precedence: int = 0) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import (  # type: ignore[import]
            Table, CalculationGroup, CalculationGroupColumn, DataType,
        )
        t = Table()
        t.Name = name
        cg = CalculationGroup()
        cg.Precedence = precedence
        t.CalculationGroup = cg
        col = CalculationGroupColumn()
        col.Name = "Name"
        col.DataType = DataType.String
        t.Columns.Add(col)
        self._model.Tables.Add(t)
        self._model.SaveChanges()
        return {"table": name, "precedence": precedence, "items": []}

    def calc_item_add(self, group_table: str, name: str, expression: str, ordinal: int = 0) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import CalculationItem  # type: ignore[import]
        t = self._model.Tables.Find(group_table)
        if not t or not t.CalculationGroup:
            raise ValueError(f"Calculation group '{group_table}' not found.")
        ci = CalculationItem()
        ci.Name = name
        ci.Expression = expression
        ci.Ordinal = ordinal
        t.CalculationGroup.CalculationItems.Add(ci)
        self._model.SaveChanges()
        return {"group": group_table, "name": name, "expression": expression, "ordinal": ordinal}

    def calc_item_delete(self, group_table: str, name: str) -> None:
        self._require_connection()
        t = self._model.Tables.Find(group_table)
        if not t or not t.CalculationGroup:
            raise ValueError(f"Calculation group '{group_table}' not found.")
        ci = t.CalculationGroup.CalculationItems.Find(name)
        if ci:
            t.CalculationGroup.CalculationItems.Remove(ci)
            self._model.SaveChanges()

    # --- RLS Roles ---

    def role_list(self) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for role in self._model.Roles:
            table_perms = [
                {"table": tp.Table.Name, "filterExpression": tp.FilterExpression or ""}
                for tp in role.TablePermissions
            ]
            results.append({
                "name": role.Name,
                "modelPermission": role.ModelPermission.ToString(),
                "tablePermissions": table_perms,
            })
        return results

    def role_add(self, name: str, table: str, filter_expression: str) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import (  # type: ignore[import]
            ModelRole, ModelPermission, TablePermission,
        )
        role = ModelRole()
        role.Name = name
        role.ModelPermission = ModelPermission.Read
        tp = TablePermission()
        tp.Table = self._model.Tables.Find(table)
        if tp.Table is None:
            raise ValueError(f"Table '{table}' not found.")
        tp.FilterExpression = filter_expression
        role.TablePermissions.Add(tp)
        self._model.Roles.Add(role)
        self._model.SaveChanges()
        return {"name": name, "table": table, "filterExpression": filter_expression}

    def role_delete(self, name: str) -> None:
        self._require_connection()
        role = self._model.Roles.Find(name)
        if role:
            self._model.Roles.Remove(role)
            self._model.SaveChanges()

    def role_test(self, role_name: str, dax_expression: str) -> dict[str, Any]:
        """Execute a DAX query with a specific role applied to verify RLS filtering."""
        self._require_connection()
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection, AdomdCommand  # type: ignore[import]
        conn_str = f"Data Source=localhost:{self._port};Roles={role_name}"
        conn = AdomdConnection(conn_str)
        try:
            conn.Open()
            cmd = AdomdCommand(dax_expression, conn)
            reader = cmd.ExecuteReader()
            cols = [reader.GetName(i).strip("[]") for i in range(reader.FieldCount)]
            rows = []
            while reader.Read():
                row: dict[str, Any] = {}
                for i, c in enumerate(cols):
                    try:
                        val = reader.GetValue(i)
                        row[c] = float(val) if hasattr(val, "ToString") and not isinstance(val, str) else val
                    except Exception:
                        row[c] = None
                rows.append(row)
            reader.Close()
            return {"role": role_name, "rowCount": len(rows), "rows": rows}
        finally:
            conn.Close()

    # --- Partitions ---

    def partition_list(self, table: str | None = None) -> list[dict[str, Any]]:
        self._require_connection()
        results = []
        for t in self._model.Tables:
            if table and t.Name != table:
                continue
            for p in t.Partitions:
                source_expr = ""
                src = p.Source
                if src is not None:
                    source_expr = getattr(src, "Expression", "") or getattr(src, "Query", "") or ""
                results.append({
                    "table": t.Name,
                    "name": p.Name,
                    "mode": p.Mode.ToString(),
                    "state": p.State.ToString(),
                    "source": source_expr,
                })
        return results

    def partition_add(self, table: str, name: str, query: str) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import Partition, MPartitionSource  # type: ignore[import]
        t = self._model.Tables.Find(table)
        if not t:
            raise ValueError(f"Table '{table}' not found.")
        p = Partition()
        p.Name = name
        src = MPartitionSource()
        src.Expression = query
        p.Source = src
        t.Partitions.Add(p)
        self._model.SaveChanges()
        return {"table": table, "name": name, "query": query}

    def partition_delete(self, table: str, name: str) -> None:
        self._require_connection()
        t = self._model.Tables.Find(table)
        if t:
            p = t.Partitions.Find(name)
            if p:
                t.Partitions.Remove(p)
                self._model.SaveChanges()

    def partition_refresh(self, table: str, name: str) -> dict[str, Any]:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import RefreshType  # type: ignore[import]
        t = self._model.Tables.Find(table)
        if not t:
            raise ValueError(f"Table '{table}' not found.")
        p = t.Partitions.Find(name)
        if not p:
            raise KeyError(f"Partition '{name}' not found in '{table}'.")
        p.RequestRefresh(RefreshType.Full)
        self._model.SaveChanges()
        return {"table": table, "partition": name, "status": "refresh_requested"}

    # --- Model Diff ---

    def model_diff(self, snapshot_path: str) -> dict[str, Any]:
        """Compare the current model against a TMDL snapshot directory."""
        import tempfile, pathlib
        snap = pathlib.Path(snapshot_path)
        if not snap.exists():
            raise FileNotFoundError(f"Snapshot path not found: {snapshot_path}")

        with tempfile.TemporaryDirectory() as tmp:
            self.tmdl_export(tmp)
            current: dict[str, str] = {
                f.name: f.read_text(encoding="utf-8")
                for f in pathlib.Path(tmp).rglob("*.tmdl")
            }

        baseline: dict[str, str] = {
            f.name: f.read_text(encoding="utf-8")
            for f in snap.rglob("*.tmdl")
        }

        added = sorted(k for k in current if k not in baseline)
        removed = sorted(k for k in baseline if k not in current)
        changed = sorted(k for k in current if k in baseline and current[k] != baseline[k])
        unchanged = sorted(k for k in current if k in baseline and current[k] == baseline[k])

        return {
            "snapshot": str(snap),
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged_count": len(unchanged),
            "has_changes": bool(added or removed or changed),
        }

    # --- TMDL ---

    def tmdl_export(self, path: str) -> None:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import TmdlSerializer  # type: ignore[import]
        TmdlSerializer.SerializeDatabaseToFolder(self._db, path)

    def tmdl_import(self, path: str) -> None:
        self._require_connection()
        from Microsoft.AnalysisServices.Tabular import TmdlSerializer  # type: ignore[import]
        TmdlSerializer.DeserializeDatabaseFromFolder(path, self._db)
        self._model.SaveChanges()

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError("Not connected to Power BI Desktop. Run 'pbi connect' first.")
