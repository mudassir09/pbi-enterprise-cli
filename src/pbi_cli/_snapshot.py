"""Snapshot capture and restore for pbi undo (Epic F2)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

_SNAPSHOT_DIR = Path.home() / ".pbi-cli" / "snapshots"
_MAX_SNAPSHOTS = 20


def capture_snapshot(backend: Any) -> Path:
    """Capture the current backend state to a timestamped JSON file.

    Returns the path of the written snapshot.
    """
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {}
    try:
        state["model"] = backend.model_info()
    except Exception:
        state["model"] = {}
    try:
        state["tables"] = backend.table_list()
    except Exception:
        state["tables"] = []
    try:
        state["columns"] = backend.column_list()
    except Exception:
        state["columns"] = []
    try:
        state["relationships"] = backend.relationship_list()
    except Exception:
        state["relationships"] = []
    try:
        state["measures"] = backend.measure_list()
    except Exception:
        state["measures"] = []

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%f")
    snapshot_path = _SNAPSHOT_DIR / f"{ts}.json"
    snapshot_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    _prune_old_snapshots()
    return snapshot_path


def latest_snapshot() -> Path | None:
    """Return the path of the most recent snapshot, or None."""
    if not _SNAPSHOT_DIR.exists():
        return None
    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"))
    return snapshots[-1] if snapshots else None


def restore_snapshot(snapshot_path: Path, backend: Any) -> dict[str, Any]:
    """Apply the measures from a snapshot to the backend.

    Returns a summary of what was restored.
    """
    state = json.loads(snapshot_path.read_text(encoding="utf-8"))
    restored: dict[str, Any] = {"measures_restored": 0, "tables_restored": 0}

    # Restore measures — safest operation: delete all current, re-add from snapshot
    try:
        current = backend.measure_list()
        for m in current:
            try:
                backend.measure_delete(m["table"], m["name"])
            except Exception:
                pass
        for m in state.get("measures", []):
            kwargs = {k: v for k, v in m.items() if k not in ("table", "name", "expression")}
            try:
                backend.measure_add(m["table"], m["name"], m["expression"], **kwargs)
                restored["measures_restored"] += 1
            except Exception:
                pass
    except Exception:
        pass

    return restored


def _prune_old_snapshots() -> None:
    """Keep only the most recent _MAX_SNAPSHOTS snapshots."""
    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"))
    for old in snapshots[:-_MAX_SNAPSHOTS]:
        try:
            old.unlink()
        except Exception:
            pass
