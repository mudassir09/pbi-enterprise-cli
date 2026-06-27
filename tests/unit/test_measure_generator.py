"""Tests for the Claude-backed DAX measure generator (no network calls)."""

from __future__ import annotations

import sys
import types

from pbi_cli.intelligence.measure_generator import MeasureGenerator

_SCHEMA = [
    {"table": "Sales", "name": "Revenue", "dataType": "Decimal"},
    {"table": "Sales", "name": "Units", "dataType": "Int64"},
]


def _fake_anthropic(text: str | None = None, raise_exc: Exception | None = None):
    """A stand-in `anthropic` module whose client returns *text* (or raises)."""
    mod = types.ModuleType("anthropic")

    class _Block:
        def __init__(self, t: str) -> None:
            self.text = t

    class _Message:
        def __init__(self, blocks: list) -> None:
            self.content = blocks

    class _Messages:
        def create(self, **kwargs):
            if raise_exc is not None:
                raise raise_exc
            return _Message([_Block(text or "")])

    class Anthropic:
        def __init__(self, *a, **k) -> None:
            self.messages = _Messages()

    mod.Anthropic = Anthropic  # type: ignore[attr-defined]
    return mod


def test_generate_without_anthropic_returns_todo(monkeypatch):
    # None in sys.modules makes `import anthropic` raise ImportError.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    result = MeasureGenerator().generate("total revenue", _SCHEMA)
    assert result["valid"] is False
    assert "anthropic" in result["error"].lower()
    assert "TODO" in result["expression"]


def test_generate_success(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(text="SUM(Sales[Revenue])"))
    result = MeasureGenerator().generate("total revenue", _SCHEMA)
    assert result["valid"] is True
    assert result["expression"] == "SUM(Sales[Revenue])"


def test_generate_strips_whitespace(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(text="  SUM(Sales[Units])\n"))
    result = MeasureGenerator().generate("units", _SCHEMA)
    assert result["expression"] == "SUM(Sales[Units])"


def test_generate_api_error_is_caught(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "anthropic", _fake_anthropic(raise_exc=RuntimeError("rate limited"))
    )
    result = MeasureGenerator().generate("x", _SCHEMA)
    assert result["valid"] is False
    assert "rate limited" in result["error"]
    assert result["expression"] == ""


def test_generate_handles_empty_schema(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(text="BLANK()"))
    result = MeasureGenerator().generate("placeholder", [])
    assert result["valid"] is True
    assert result["expression"] == "BLANK()"
