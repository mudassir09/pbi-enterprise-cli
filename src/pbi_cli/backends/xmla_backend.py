"""XMLA backend — connects to Power BI Service/Fabric via XMLA over HTTPS.

Connection string format (Power BI Premium / Fabric):
    powerbi://api.powerbi.com/v1.0/myorg/<WorkspaceName>

Authentication modes
--------------------
``device_flow``         Interactive browser login via MSAL device-code flow.
``service_principal``   Non-interactive; requires ``client_id``, ``client_secret``,
                        and ``tenant_id``.
``token``               Pass a pre-acquired Bearer token directly.

Example::

    from pbi_cli.backends.xmla_backend import XmlaBackend
    b = XmlaBackend()
    b.connect(
        "powerbi://api.powerbi.com/v1.0/myorg/MySales",
        catalog="MySalesDataset",
        auth_mode="service_principal",
        client_id="...", client_secret="...", tenant_id="...",
    )
    print(b.table_list())

Requires ``pythonnet`` (in core deps) plus ``msal`` for token-based auth.
Install the optional extra for the full stack::

    pip install pbi-cli-tool[xmla]

The .NET AMO/ADOMD assemblies ship with Power BI Desktop (Windows) or can be
installed via the NuGet packages ``Microsoft.AnalysisServices.retail.amd64`` and
``Microsoft.AnalysisServices.AdomdClient.retail.amd64``.
"""

from __future__ import annotations

import threading
from typing import Any

# ---------------------------------------------------------------------------
# Connection pool — keyed by (data_source, catalog).  Protected by _pool_lock.
# ---------------------------------------------------------------------------
_pool_lock = threading.Lock()
_connection_pool: dict[tuple[str, str], Any] = {}  # value: AMO Server object


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class XmlaAuth:
    """Acquires and caches an MSAL access token for the XMLA endpoint.

    Parameters
    ----------
    mode:
        ``"device_flow"`` | ``"service_principal"`` | ``"token"``
    client_id:
        AAD application (client) ID.  Defaults to the Power BI Desktop app ID
        when using ``device_flow``.
    client_secret:
        Required for ``service_principal``.
    tenant_id:
        AAD tenant ID.  Defaults to ``"common"`` for ``device_flow``.
    access_token:
        Pre-acquired Bearer token string; used directly when ``mode="token"``.
    """

    #: The AAD scope for Power BI XMLA endpoints.
    _PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
    #: Default public client ID (Power BI Desktop app) for device-flow.
    _DEFAULT_CLIENT_ID = "ea0616ba-638b-4df5-95b9-636659ae5121"

    def __init__(
        self,
        mode: str = "device_flow",
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        access_token: str | None = None,
    ) -> None:
        if mode not in ("device_flow", "service_principal", "token"):
            raise ValueError(
                f"Unknown auth mode {mode!r}. "
                "Expected: 'device_flow', 'service_principal', or 'token'."
            )
        self.mode = mode
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self._access_token = access_token
        self._cached_token: str | None = None

    # ------------------------------------------------------------------
    def get_token(self) -> str:
        """Return a valid access token, acquiring one if necessary."""
        if self._cached_token:
            return self._cached_token

        if self.mode == "token":
            if not self._access_token:
                raise ValueError("access_token must be provided when mode='token'.")
            self._cached_token = self._access_token
            return self._cached_token

        self._cached_token = self._acquire_via_msal()
        return self._cached_token

    def _acquire_via_msal(self) -> str:
        try:
            import msal  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "msal is required for device_flow / service_principal auth.\n"
                "Install with: pip install pbi-cli-tool[xmla]"
            ) from None

        authority = f"https://login.microsoftonline.com/{self.tenant_id or 'common'}"

        if self.mode == "service_principal":
            if not (self.client_id and self.client_secret and self.tenant_id):
                raise ValueError(
                    "client_id, client_secret, and tenant_id are all required "
                    "for service_principal auth."
                )
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )
            result = app.acquire_token_for_client(scopes=[self._PBI_SCOPE])

        else:  # device_flow
            app = msal.PublicClientApplication(
                self.client_id or self._DEFAULT_CLIENT_ID,
                authority=authority,
            )
            flow = app.initiate_device_flow(scopes=[self._PBI_SCOPE])
            print(flow.get("message", "Open a browser and authenticate."))
            result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            err = result.get("error_description") or result.get("error") or str(result)
            raise RuntimeError(f"XMLA authentication failed: {err}")
        return str(result["access_token"])


# ---------------------------------------------------------------------------
# AMO helpers (lazy-imported so tests can patch them)
# ---------------------------------------------------------------------------


def _load_amo():  # type: ignore[return]
    """Import and return the AMO Server class via pythonnet.

    Raises ImportError with install instructions if pythonnet or the AMO
    assemblies are not available.
    """
    try:
        import clr  # type: ignore[import]  # noqa: PLC0415

        clr.AddReference("Microsoft.AnalysisServices.Core")
        clr.AddReference("Microsoft.AnalysisServices.Tabular")
        from Microsoft.AnalysisServices.Tabular import Server  # type: ignore[import]

        return Server
    except Exception as exc:
        raise ImportError(
            "The XMLA backend requires pythonnet and the AMO .NET assemblies.\n"
            "Install with: pip install pbi-cli-tool[xmla]\n"
            "The AMO assemblies ship with Power BI Desktop (Windows) or can be\n"
            "installed via NuGet: Microsoft.AnalysisServices.retail.amd64"
        ) from exc


def _load_adomd():  # type: ignore[return]
    """Import and return AdomdConnection + AdomdCommand via pythonnet."""
    try:
        import clr  # type: ignore[import]  # noqa: PLC0415

        clr.AddReference("Microsoft.AnalysisServices.AdomdClient")
        from Microsoft.AnalysisServices.AdomdClient import (  # type: ignore[import]
            AdomdCommand,
            AdomdConnection,
        )

        return AdomdConnection, AdomdCommand
    except Exception as exc:
        raise ImportError(
            "AdomdClient .NET assembly not found.\nInstall with: pip install pbi-cli-tool[xmla]"
        ) from exc


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class XmlaBackend:
    """Power BI Premium / Fabric XMLA backend.

    All read operations use the AMO tabular object model via pythonnet.
    DAX queries use ADOMD.NET (also via pythonnet).
    Both paths require Windows + the AMO/ADOMD NuGet assemblies; on other
    platforms every method raises ``ImportError``.

    Connection pool
    ~~~~~~~~~~~~~~~
    A module-level pool reuses live ``Server`` connections across
    ``XmlaBackend`` instances that share the same ``(data_source, catalog)``
    pair.  Call :meth:`clear_pool` to drain it (e.g. between tests).
    """

    def __init__(self) -> None:
        self._connected = False
        self._data_source: str = ""
        self._catalog: str = ""
        self._server: Any = None  # AMO Server object
        self._auth: XmlaAuth | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(
        self,
        data_source: str,
        *,
        catalog: str = "",
        auth_mode: str = "device_flow",
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        access_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Open (or reuse a pooled) connection to an XMLA endpoint.

        Parameters
        ----------
        data_source:
            XMLA endpoint URL, e.g.
            ``powerbi://api.powerbi.com/v1.0/myorg/MySalesWorkspace``
        catalog:
            The dataset / semantic model name.
        auth_mode:
            ``"device_flow"``, ``"service_principal"``, or ``"token"``.
        """
        self._auth = XmlaAuth(
            mode=auth_mode,
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            access_token=access_token,
        )
        self._data_source = data_source.rstrip("/")
        self._catalog = catalog

        pool_key = (self._data_source, self._catalog)
        with _pool_lock:
            server = _connection_pool.get(pool_key)
            if server is None or not server.Connected:
                server = self._open_server(pool_key)
            self._server = server

        self._connected = True

    def _open_server(self, pool_key: tuple[str, str]) -> Any:
        """Create a new AMO Server, connect, and store it in the pool."""
        Server = _load_amo()
        server = Server()
        token = self._auth.get_token()  # type: ignore[union-attr]
        conn_str = f"Data Source={self._data_source};Password={token};" + (
            f"Initial Catalog={self._catalog};" if self._catalog else ""
        )
        server.Connect(conn_str)
        _connection_pool[pool_key] = server
        return server

    def disconnect(self) -> None:
        """Disconnect from the XMLA endpoint and remove from pool."""
        if self._server is not None:
            pool_key = (self._data_source, self._catalog)
            with _pool_lock:
                _connection_pool.pop(pool_key, None)
            try:
                self._server.Disconnect()
            except Exception:
                pass
            self._server = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def clear_pool() -> None:
        """Drain the connection pool (useful in tests and CLI --reset)."""
        with _pool_lock:
            for server in _connection_pool.values():
                try:
                    server.Disconnect()
                except Exception:
                    pass
            _connection_pool.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connection(self) -> None:
        if not self._connected or self._server is None:
            raise RuntimeError("Not connected to an XMLA endpoint. Call connect() first.")

    @property
    def _model(self) -> Any:
        """Return the AMO Tabular database model for the active catalog."""
        self._require_connection()
        if self._catalog:
            db = self._server.Databases[self._catalog]
        else:
            if self._server.Databases.Count == 0:
                raise RuntimeError("No databases found on the XMLA endpoint.")
            db = self._server.Databases[0]
        return db.Model

    # ------------------------------------------------------------------
    # Model metadata
    # ------------------------------------------------------------------

    def model_info(self) -> dict[str, Any]:
        model = self._model
        return {
            "name": str(model.Database.Name),
            "compatibility_level": int(model.Database.CompatibilityLevel),
            "catalog": self._catalog,
            "data_source": self._data_source,
        }

    def table_list(self) -> list[dict[str, Any]]:
        model = self._model
        result = []
        for tbl in model.Tables:
            result.append(
                {
                    "name": str(tbl.Name),
                    "isHidden": bool(tbl.IsHidden),
                    "description": str(tbl.Description or ""),
                }
            )
        return result

    def column_list(self, table: str | None = None) -> list[dict[str, Any]]:
        model = self._model
        result = []
        tables = [model.Tables[table]] if table else list(model.Tables)
        for tbl in tables:
            for col in tbl.Columns:
                result.append(
                    {
                        "table": str(tbl.Name),
                        "name": str(col.Name),
                        "dataType": str(col.DataType),
                        "isHidden": bool(col.IsHidden),
                        "description": str(col.Description or ""),
                    }
                )
        return result

    def relationship_list(self) -> list[dict[str, Any]]:
        model = self._model
        result = []
        for rel in model.Relationships:
            result.append(
                {
                    "from": f"{rel.FromTable.Name}[{rel.FromColumn.Name}]",
                    "to": f"{rel.ToTable.Name}[{rel.ToColumn.Name}]",
                    "cardinality": str(rel.FromCardinality),
                    "isActive": bool(rel.IsActive),
                }
            )
        return result

    # ------------------------------------------------------------------
    # Measures
    # ------------------------------------------------------------------

    def measure_list(self, table: str | None = None) -> list[dict[str, Any]]:
        model = self._model
        result = []
        tables = [model.Tables[table]] if table else list(model.Tables)
        for tbl in tables:
            for m in tbl.Measures:
                result.append(
                    {
                        "table": str(tbl.Name),
                        "name": str(m.Name),
                        "expression": str(m.Expression),
                        "formatString": str(m.FormatString or ""),
                        "description": str(m.Description or ""),
                        "isHidden": bool(m.IsHidden),
                    }
                )
        return result

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        from Microsoft.AnalysisServices.Tabular import Measure  # type: ignore[import]

        model = self._model
        tbl = model.Tables[table]
        m = Measure()
        m.Name = name
        m.Expression = expression
        if "formatString" in kwargs:
            m.FormatString = kwargs["formatString"]
        if "description" in kwargs:
            m.Description = kwargs["description"]
        tbl.Measures.Add(m)
        model.SaveChanges()
        return {"table": table, "name": name, "expression": expression, **kwargs}

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        model = self._model
        m = model.Tables[table].Measures[name]
        new_name = kwargs.pop("new_name", None)
        if new_name:
            m.Name = new_name
        if "expression" in kwargs:
            m.Expression = kwargs["expression"]
        if "formatString" in kwargs:
            m.FormatString = kwargs["formatString"]
        if "description" in kwargs:
            m.Description = kwargs["description"]
        model.SaveChanges()
        return {"table": table, "name": new_name or name, **kwargs}

    def measure_delete(self, table: str, name: str) -> None:
        model = self._model
        tbl = model.Tables[table]
        tbl.Measures.Remove(tbl.Measures[name])
        model.SaveChanges()

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def table_add(self, name: str, **kwargs: Any) -> dict[str, Any]:
        from Microsoft.AnalysisServices.Tabular import Table  # type: ignore[import]

        model = self._model
        tbl = Table()
        tbl.Name = name
        model.Tables.Add(tbl)
        model.SaveChanges()
        return {"name": name, **kwargs}

    def table_delete(self, name: str) -> None:
        model = self._model
        model.Tables.Remove(model.Tables[name])
        model.SaveChanges()

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def column_add(self, table: str, name: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        from Microsoft.AnalysisServices.Tabular import (  # type: ignore[import]
            DataColumn,
            DataType,
        )

        model = self._model
        col = DataColumn()
        col.Name = name
        col.DataType = getattr(DataType, data_type, DataType.String)
        model.Tables[table].Columns.Add(col)
        model.SaveChanges()
        return {"table": table, "name": name, "dataType": data_type, **kwargs}

    def column_delete(self, table: str, name: str) -> None:
        model = self._model
        tbl = model.Tables[table]
        tbl.Columns.Remove(tbl.Columns[name])
        model.SaveChanges()

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def relationship_add(
        self,
        from_table: str,
        from_column: str,
        to_table: str,
        to_column: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from Microsoft.AnalysisServices.Tabular import (  # type: ignore[import]
            RelationshipEndCardinality,
            SingleColumnRelationship,
        )

        model = self._model
        rel = SingleColumnRelationship()
        rel.FromTable = model.Tables[from_table]
        rel.FromColumn = model.Tables[from_table].Columns[from_column]
        rel.ToTable = model.Tables[to_table]
        rel.ToColumn = model.Tables[to_table].Columns[to_column]
        cardinality = kwargs.get("cardinality", "ManyToOne")
        rel.FromCardinality = getattr(
            RelationshipEndCardinality, cardinality, RelationshipEndCardinality.Many
        )
        model.Relationships.Add(rel)
        model.SaveChanges()
        return {
            "from": f"{from_table}[{from_column}]",
            "to": f"{to_table}[{to_column}]",
            "cardinality": cardinality,
        }

    # ------------------------------------------------------------------
    # DAX
    # ------------------------------------------------------------------

    def dax_query(self, expression: str) -> list[dict[str, Any]]:
        """Execute a DAX query via ADOMD.NET and return rows as dicts."""
        self._require_connection()
        AdomdConnection, AdomdCommand = _load_adomd()

        token = self._auth.get_token()  # type: ignore[union-attr]
        conn_str = f"Data Source={self._data_source};Password={token};" + (
            f"Initial Catalog={self._catalog};" if self._catalog else ""
        )

        rows: list[dict[str, Any]] = []
        with AdomdConnection(conn_str) as conn:
            conn.Open()
            cmd = AdomdCommand(expression, conn)
            reader = cmd.ExecuteReader()
            field_count = reader.FieldCount
            columns = [reader.GetName(i) for i in range(field_count)]
            while reader.Read():
                rows.append({col: reader[col] for col in columns})
            reader.Close()
        return rows

    def dax_validate(self, expression: str) -> dict[str, Any]:
        """Lightweight syntax check: run EVALUATE with a row limit of 0."""
        try:
            # Wrap in an always-false filter so no data is transferred
            self.dax_query(f"EVALUATE TOPN(0, ({expression}))")
            return {"valid": True, "expression": expression}
        except Exception as exc:
            return {"valid": False, "expression": expression, "error": str(exc)}

    # ------------------------------------------------------------------
    # TMDL
    # ------------------------------------------------------------------

    def tmdl_export(self, path: str) -> None:
        """Export the model as TMDL files to *path* via AMO serialisation."""
        from Microsoft.AnalysisServices.Tabular import TmdlSerializer  # type: ignore[import]

        model = self._model
        TmdlSerializer.SerializeDatabase(model.Database, path)

    def tmdl_import(self, path: str) -> None:
        """Import TMDL from *path* and deploy to the connected endpoint."""
        from Microsoft.AnalysisServices.Tabular import TmdlSerializer  # type: ignore[import]

        model = self._model
        TmdlSerializer.DeserializeDatabase(path, model.Database)
        model.SaveChanges()

    # ------------------------------------------------------------------
    # Hierarchies (bonus — not in base protocol but mirrors TomBackend)
    # ------------------------------------------------------------------

    def hierarchy_list(self, table: str | None = None) -> list[dict[str, Any]]:
        model = self._model
        result = []
        tables = [model.Tables[table]] if table else list(model.Tables)
        for tbl in tables:
            for h in tbl.Hierarchies:
                result.append(
                    {
                        "table": str(tbl.Name),
                        "name": str(h.Name),
                        "levels": [
                            {
                                "ordinal": int(lv.Ordinal),
                                "name": str(lv.Name),
                                "column": str(lv.Column.Name),
                            }
                            for lv in h.Levels
                        ],
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Roles (bonus)
    # ------------------------------------------------------------------

    def role_list(self) -> list[dict[str, Any]]:
        model = self._model
        result = []
        for role in model.Roles:
            perms = []
            for tp in role.TablePermissions:
                perms.append(
                    {
                        "table": str(tp.Table.Name),
                        "filterExpression": str(tp.FilterExpression or ""),
                    }
                )
            result.append(
                {
                    "name": str(role.Name),
                    "modelPermission": str(role.ModelPermission),
                    "tablePermissions": perms,
                }
            )
        return result
