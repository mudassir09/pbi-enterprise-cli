"""Tests for atomic TMDL file writes (no half-written/corrupted repo files)."""

from __future__ import annotations

import pytest

import pbi_cli.tmdl_util as tu
from pbi_cli.tmdl_util import atomic_write_text


def test_writes_content(tmp_path):
    p = tmp_path / "model.tmdl"
    atomic_write_text(p, "table Sales\n")
    assert p.read_text(encoding="utf-8") == "table Sales\n"


def test_overwrites_existing(tmp_path):
    p = tmp_path / "model.tmdl"
    p.write_text("OLD", encoding="utf-8")
    atomic_write_text(p, "NEW")
    assert p.read_text(encoding="utf-8") == "NEW"


def test_creates_parent_dirs(tmp_path):
    p = tmp_path / "definition" / "tables" / "Sales.tmdl"
    atomic_write_text(p, "table Sales\n")
    assert p.read_text(encoding="utf-8") == "table Sales\n"


def test_preserves_original_when_replace_fails(tmp_path, monkeypatch):
    """A crash during the swap must leave the original intact, not truncated."""
    p = tmp_path / "model.tmdl"
    p.write_text("ORIGINAL", encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated disk-full during replace")

    monkeypatch.setattr(tu.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(p, "NEW CONTENT")

    # Original content survives untouched...
    assert p.read_text(encoding="utf-8") == "ORIGINAL"
    # ...and the temp file is cleaned up (no .model.tmdl.*.tmp left behind).
    leftovers = [f.name for f in tmp_path.iterdir() if f.name != "model.tmdl"]
    assert leftovers == []


def test_temp_file_in_same_dir_for_atomic_rename(tmp_path, monkeypatch):
    """The temp file must live in the destination directory so the rename is atomic
    (a cross-filesystem rename is a copy, which is not atomic)."""
    p = tmp_path / "sub" / "model.tmdl"
    p.parent.mkdir()
    seen: dict[str, str] = {}
    real_replace = tu.os.replace

    def spy(src, dst):
        seen["src_dir"] = str(tu.Path(src).parent)
        return real_replace(src, dst)

    monkeypatch.setattr(tu.os, "replace", spy)
    atomic_write_text(p, "x")
    assert seen["src_dir"] == str(p.parent)
