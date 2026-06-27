"""FabricDefinitionBackend — edit a *live* Fabric semantic model from any OS.

The `rest` backend can read a published model and run DAX, but it cannot
*write*; live writes otherwise need Windows + XMLA + TOM. This backend closes
that gap for the common case (measure add/update/delete) using the Fabric Item
Definition API: it downloads the model's TMDL definition into a temp folder,
reuses the pure-Python `FileBackend` to read and edit it, then pushes the result
back with ``updateDefinition`` (a long-running operation). No Windows, no .NET.

Heavier structural edits (tables, relationships, partitions) are intentionally
out of scope — use the desktop/xmla backends for those.

**Cost & concurrency.** ``updateDefinition`` always uploads the *whole* model
definition, so each individual write is a full round-trip. Use :meth:`batch` to
coalesce several edits into a single push. The Item Definition API is
last-writer-wins — it has no ETag/optimistic-concurrency guard — so a concurrent
editor's change can be overwritten; serialise writes to one model accordingly.

The temp folder is owned by the backend: use it as a context manager, or call
:meth:`disconnect` when done, so it is cleaned up deterministically rather than
at GC time.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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
        # When deferring (inside a batch), local edits are applied to the temp
        # TMDL but the expensive remote push is held back until the batch exits.
        self._defer_push = False
        self._dirty = False
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
        # Inside a batch we only mark the model dirty; the single push happens
        # when the batch exits (or flush() is called explicitly).
        if self._defer_push:
            self._dirty = True
            return
        parts = _fab.encode_parts(self._tmpdir)
        _fab.poll_lro(
            _fab.post(
                f"{self._base()}/updateDefinition?updateMetadata=true",
                self._token,
                payload={"definition": {"parts": parts}},
            ),
            self._token,
        )
        self._dirty = False

    def flush(self) -> None:
        """Push pending local edits if a batch deferred them. No-op when clean."""
        if not self._dirty:
            return
        was_deferring = self._defer_push
        self._defer_push = False
        try:
            self._push_definition()
        finally:
            self._defer_push = was_deferring

    @contextmanager
    def batch(self) -> Iterator[FabricDefinitionBackend]:
        """Coalesce multiple edits into a single ``updateDefinition`` round-trip.

        ``updateDefinition`` re-uploads the entire model, so adding ten measures
        one-by-one is ten full pushes. Inside this context each edit is applied to
        the local TMDL only; one push happens on exit::

            with backend.batch():
                backend.measure_add("Sales", "A", "...")
                backend.measure_add("Sales", "B", "...")
            # single push here
        """
        previous = self._defer_push
        self._defer_push = True
        try:
            yield self
        finally:
            self._defer_push = previous
            if not self._defer_push:
                self.flush()

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
        # Flush any deferred edits before tearing down so a batch that exited via
        # disconnect() (rather than the context manager) is not silently dropped.
        try:
            self.flush()
        finally:
            self._connected = False
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __enter__(self) -> FabricDefinitionBackend:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    def __del__(self) -> None:  # best-effort safety net only; prefer disconnect()
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass
