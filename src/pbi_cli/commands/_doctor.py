"""pbi doctor — diagnose setup issues."""

from __future__ import annotations

import json
import sys

from rich.console import Console
from rich.table import Table

console = Console()


def run_doctor(output_json: bool) -> None:
    checks = []

    # Python version
    checks.append(
        {
            "check": "Python version",
            "status": "pass" if sys.version_info >= (3, 10) else "fail",
            "detail": f"{sys.version}",
        }
    )

    # pythonnet
    try:
        import clr  # type: ignore[import]  # noqa: F401

        checks.append({"check": "pythonnet", "status": "pass", "detail": "Available"})
    except ImportError:
        checks.append(
            {"check": "pythonnet", "status": "fail", "detail": "Not installed (Windows only)"}
        )

    # sqlalchemy
    try:
        import sqlalchemy

        checks.append(
            {"check": "sqlalchemy [sources]", "status": "pass", "detail": sqlalchemy.__version__}
        )
    except ImportError:
        checks.append(
            {
                "check": "sqlalchemy [sources]",
                "status": "warn",
                "detail": "Not installed (optional)",
            }
        )

    # fastapi
    try:
        import fastapi

        checks.append(
            {"check": "fastapi [server]", "status": "pass", "detail": fastapi.__version__}
        )
    except ImportError:
        checks.append(
            {"check": "fastapi [server]", "status": "warn", "detail": "Not installed (optional)"}
        )

    # Platform
    checks.append(
        {
            "check": "Platform",
            "status": "pass" if sys.platform == "win32" else "warn",
            "detail": f"{sys.platform} (TOM backend requires Windows)",
        }
    )

    if output_json:
        print(json.dumps(checks, indent=2))
        return

    table = Table(title="pbi doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for c in checks:
        color = {"pass": "green", "warn": "yellow", "fail": "red"}.get(c["status"], "white")
        table.add_row(c["check"], f"[{color}]{c['status']}[/{color}]", c["detail"])
    console.print(table)
