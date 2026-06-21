"""Run T-SQL against a Fabric Warehouse or Lakehouse SQL analytics endpoint.

This is the data-engineering primitive the CLI was missing: the model/DAX
surface could query semantic models (DAX), but nothing could run *SQL* against a
Warehouse or a Lakehouse SQL endpoint — table stakes for data engineering work.

Endpoint discovery is pure REST (the Fabric item exposes its server FQDN). The
query itself runs over TDS via pyodbc with an Azure AD access token, so it needs
the ``[sql]`` extra and a Microsoft ODBC driver. Discovery is unit-testable with
mocked REST; the live query path is isolated in :func:`run_query`.
"""

from __future__ import annotations

import struct
from typing import Any

from pbi_cli import fabric_api as _fab

# Azure SQL / Fabric SQL endpoint token audience (not the Power BI audience).
SQL_SCOPE = "https://database.windows.net/.default"
# pyodbc connection attribute for passing an AAD access token (SQL_COPT_SS_ACCESS_TOKEN).
_SQL_COPT_SS_ACCESS_TOKEN = 1256


class SqlEndpointError(RuntimeError):
    """Raised when an item has no SQL endpoint or the driver/extra is missing."""


def resolve_endpoint(workspace_id: str, item_id: str, token: str) -> tuple[str, str]:
    """Return ``(server, database)`` for a Warehouse / Lakehouse / SQLEndpoint item.

    Warehouses and SQL endpoints expose ``properties.connectionString`` directly;
    Lakehouses nest it under ``properties.sqlEndpointProperties.connectionString``.
    The database name is the item's display name in every case.
    """
    item = _fab.get(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}", token
    )
    props = item.get("properties") or {}
    item_type = item.get("type", "")
    name = item.get("displayName") or item.get("name") or ""

    server = props.get("connectionString")
    if not server:
        server = (props.get("sqlEndpointProperties") or {}).get("connectionString")
    if not server:
        raise SqlEndpointError(
            f"Item '{name}' ({item_type or 'unknown type'}) exposes no SQL connection "
            "string. Only Warehouse, Lakehouse, and SQLEndpoint items have a T-SQL "
            "endpoint — check the id and item type."
        )
    return server, name


def _token_struct(token: str) -> bytes:
    """Pack a bearer token into the SQL_COPT_SS_ACCESS_TOKEN structure pyodbc expects."""
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


def _detect_driver(pyodbc: Any) -> str:
    """Pick the newest installed 'ODBC Driver NN for SQL Server', or a sane default."""
    candidates = [d for d in pyodbc.drivers() if "ODBC Driver" in d and "SQL Server" in d]
    return sorted(candidates)[-1] if candidates else "ODBC Driver 18 for SQL Server"


def _coerce(value: Any) -> Any:
    """Make a cell JSON-serialisable (dates, decimals, bytes)."""
    import datetime
    import decimal

    if isinstance(value, (datetime.date, datetime.datetime, datetime.time, decimal.Decimal)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def run_query(
    server: str,
    database: str,
    query: str,
    token: str,
    driver: str | None = None,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Execute *query* and return rows as dicts. Non-SELECT statements return ``[]``."""
    try:
        import pyodbc  # type: ignore[import-untyped]
    except ImportError:
        raise SqlEndpointError(
            "Running T-SQL needs the [sql] extra and a Microsoft ODBC driver: "
            "pip install 'pbi-enterprise-cli[sql]' and install 'ODBC Driver 18 for "
            "SQL Server' (https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver)."
        )

    driver = driver or _detect_driver(pyodbc)
    conn_str = (
        f"Driver={{{driver}}};Server={server};Database={database};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout={timeout};"
    )
    conn = pyodbc.connect(
        conn_str, attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: _token_struct(token)}
    )
    try:
        cur = conn.cursor()
        cur.execute(query)
        if cur.description is None:  # INSERT/UPDATE/DDL — no result set
            conn.commit()
            return []
        columns = [d[0] for d in cur.description]
        return [
            {col: _coerce(val) for col, val in zip(columns, row)}
            for row in cur.fetchall()
        ]
    finally:
        conn.close()
