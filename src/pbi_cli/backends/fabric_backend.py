"""FabricDefinitionBackend — edit a *live* Fabric semantic model from any OS.

The `rest` backend can read a published model and run DAX, but it cannot
*write*; live writes otherwise need Windows + XMLA + TOM. This backend closes
that gap for the common case (measure add/update/delete) using the Fabric Item
Definition API: it downloads the model's TMDL definition into a temp folder,
reuses the pure-Python `FileBackend` to read and edit it, then pushes the result
back with ``updateDefinition`` (a long-running operation). No Windows, no .NET.

Heavier structural edits (tables, relationships, partitions) are intentionally
out of scope — use the desktop/xmla backends for those.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from pbi_cli import fabric_api as _fab
from pbi_cli.backends.file_backend import FileBackend


class FabricDefinitionBackend(FileBackend):
    """Round-trip a Fabric semantic model's TMDL definition over REST."""

    def __init__(self, workspace_id: str, item_id: str, token: str | None = None) -> None:
        if not workspace_id or not item_id:
            raise ValueError("FabricDefinitionBackend requires workspace_id and item_id.")
        self.workspace_id = workspace_id
        self.item_id = item_id
        self._token = token or _fab.get_token()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="pbi-fabric-"))
        try:
            self._download_definition()
            super().__init__(path=self._tmpdir)
        except Exception:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            raise

    # --- REST plumbing ---

    def _base(self) -> str:
        return (
            f"{_fab.FABRIC_API_BASE}/workspaces/{self.workspace_id}"
            f"/semanticModels/{self.item_id}"
        )

    def _download_definition(self) -> None:
        result = _fab.poll_lro(
            _fab.post(f"{self._base()}/getDefinition?format=TMDL", self._token, payload={}),
            self._token,
        )
        definition = result.get("definition") if isinstance(result, dict) else None
        parts = (definition or {}).get("parts", [])
        if not parts:
            raise ConnectionError(
                f"Semantic model {self.item_id} returned no TMDL definition parts. "
                "Confirm the workspace/dataset ids and that it is a semantic model."
            )
        _fab.decode_parts(parts, self._tmpdir)

    def _push_definition(self) -> None:
        parts = _fab.encode_parts(self._tmpdir)
        _fab.poll_lro(
            _fab.post(
                f"{self._base()}/updateDefinition?updateMetadata=true",
                self._token,
                payload={"definition": {"parts": parts}},
            ),
            self._token,
        )

    # --- Writes: edit local TMDL, then push the whole definition back ---

    def measure_add(self, table: str, name: str, expression: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_add(table, name, expression, **kwargs)
        self._push_definition()
        return record

    def measure_update(self, table: str, name: str, **kwargs: Any) -> dict[str, Any]:
        record = super().measure_update(table, name, **kwargs)
        self._push_definition()
        return record

    def measure_delete(self, table: str, name: str) -> None:
        super().measure_delete(table, name)
        self._push_definition()

    # --- Lifecycle ---

    def disconnect(self) -> None:
        self._connected = False
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __del__(self) -> None:  # best-effort temp cleanup
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass
