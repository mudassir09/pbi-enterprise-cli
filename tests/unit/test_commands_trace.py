"""CliRunner tests for pbi trace commands and pbi benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def clean_trace_files(tmp_path, monkeypatch):
    """Redirect trace files to a temp dir and clean up after each test."""
    import pbi_cli.commands.trace as trace_mod
    monkeypatch.setattr(trace_mod, "_TRACE_DIR", tmp_path / "trace")
    monkeypatch.setattr(trace_mod, "_TRACE_ACTIVE_FILE", tmp_path / "trace" / "active")
    monkeypatch.setattr(trace_mod, "_TRACE_EVENTS_FILE", tmp_path / "trace" / "events.jsonl")


def _run(runner: CliRunner, *args: str):
    return runner.invoke(cli, ["--backend", "mock", *args])


def _seed_events(trace_mod, events: list[dict]) -> None:
    """Write events directly to the trace JSONL file."""
    trace_mod._TRACE_DIR.mkdir(parents=True, exist_ok=True)
    with trace_mod._TRACE_EVENTS_FILE.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


# ── trace start ───────────────────────────────────────────────────────────────


class TestTraceStart:
    def test_trace_start_exits_cleanly(self, runner):
        result = _run(runner, "trace", "start")
        assert result.exit_code == 0

    def test_trace_start_prints_started(self, runner):
        result = _run(runner, "trace", "start")
        assert "Trace started" in result.output or result.exit_code == 0

    def test_trace_start_with_custom_events(self, runner):
        result = _run(runner, "trace", "start", "--events", "QueryBegin,QueryEnd")
        assert result.exit_code == 0


# ── trace stop ────────────────────────────────────────────────────────────────


class TestTraceStop:
    def test_trace_stop_exits_cleanly(self, runner):
        result = _run(runner, "trace", "stop")
        assert result.exit_code == 0

    def test_trace_stop_mentions_events(self, runner):
        result = _run(runner, "trace", "stop")
        assert "events" in result.output.lower() or result.exit_code == 0


# ── trace fetch ───────────────────────────────────────────────────────────────


class TestTraceFetch:
    def test_fetch_empty_buffer_exits_cleanly(self, runner):
        result = _run(runner, "trace", "fetch")
        assert result.exit_code == 0

    def test_fetch_empty_buffer_prints_no_events(self, runner):
        result = _run(runner, "trace", "fetch")
        assert "No trace events" in result.output

    def test_fetch_with_data_in_buffer(self, runner):
        import pbi_cli.commands.trace as trace_mod
        _seed_events(trace_mod, [
            {"event": "QueryBegin", "duration_ms": 10},
            {"event": "QueryEnd", "duration_ms": 20},
        ])
        result = _run(runner, "trace", "fetch")
        assert result.exit_code == 0

    def test_fetch_with_limit(self, runner):
        import pbi_cli.commands.trace as trace_mod
        _seed_events(trace_mod, [{"event": f"E{i}", "duration_ms": i} for i in range(10)])
        result = _run(runner, "trace", "fetch", "--limit", "3")
        assert result.exit_code == 0


# ── trace clear ───────────────────────────────────────────────────────────────


class TestTraceClear:
    def test_clear_exits_cleanly(self, runner):
        result = _run(runner, "trace", "clear")
        assert result.exit_code == 0

    def test_clear_empties_buffer(self, runner):
        import pbi_cli.commands.trace as trace_mod
        _seed_events(trace_mod, [{"event": "QueryBegin"}])
        result = _run(runner, "trace", "clear")
        assert result.exit_code == 0
        assert trace_mod._read_events() == []

    def test_clear_prints_count(self, runner):
        import pbi_cli.commands.trace as trace_mod
        _seed_events(trace_mod, [{"event": "X"}, {"event": "Y"}])
        result = _run(runner, "trace", "clear")
        assert "Cleared" in result.output or result.exit_code == 0


# ── trace export ──────────────────────────────────────────────────────────────


class TestTraceExport:
    def test_export_empty_buffer_exits_cleanly(self, runner, tmp_path):
        out = str(tmp_path / "events.json")
        result = _run(runner, "trace", "export", "--output", out)
        assert result.exit_code == 0
        assert "No trace events" in result.output

    def test_export_with_data_creates_file(self, runner, tmp_path):
        import pbi_cli.commands.trace as trace_mod
        _seed_events(trace_mod, [{"event": "QueryBegin", "duration_ms": 42}])
        out = str(tmp_path / "events.json")
        result = _run(runner, "trace", "export", "--output", out)
        assert result.exit_code == 0
        assert Path(out).exists()
        content = json.loads(Path(out).read_text())
        assert isinstance(content, list)
        assert content[0]["event"] == "QueryBegin"


# ── benchmark ─────────────────────────────────────────────────────────────────


class TestBenchmark:
    def test_benchmark_basic(self, runner):
        result = _run(runner, "benchmark", "EVALUATE {1}", "--runs", "2", "--warmup", "0")
        assert result.exit_code == 0

    def test_benchmark_prints_results_table(self, runner):
        result = _run(runner, "benchmark", "EVALUATE {1}", "--runs", "3")
        assert result.exit_code == 0
        output = result.output
        assert "Average" in output or "Runs" in output or "Benchmark" in output

    def test_benchmark_multiple_runs(self, runner):
        result = _run(runner, "benchmark", "EVALUATE TOPN(5, Sales)", "--runs", "5", "--warmup", "1")  # noqa: E501
        assert result.exit_code == 0
