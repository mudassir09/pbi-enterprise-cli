"""Append-only audit log for all pbi-cli write operations (Epic D6)."""

from __future__ import annotations

import datetime
import getpass
import json
from pathlib import Path
from typing import Any

_AUDIT_FILE = Path.home() / ".pbi-cli" / "audit.jsonl"


def write_audit_entry(
    command: str,
    before: Any = None,
    after: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one JSON line to ~/.pbi-cli/audit.jsonl."""
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry: dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "user": _get_user(),
        "command": command,
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after
    if extra:
        entry.update(extra)
    with _AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return the last *limit* audit entries (most-recent last)."""
    if not _AUDIT_FILE.exists():
        return []
    lines = _AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries[-limit:]


def _get_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"
