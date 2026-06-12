"""pbi trace — query trace start/stop/fetch/export and benchmarking."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console(legacy_windows=False)

_TRACE_DIR = Path.home() / ".pbi-cli" / "trace"
_TRACE_ACTIVE_FILE = _TRACE_DIR / "active"
_TRACE_EVENTS_FILE = _TRACE_DIR / "events.jsonl"


def _is_trace_active() -> bool:
    return _TRACE_ACTIVE_FILE.exists()


def _append_event(event: dict[str, Any]) -> None:
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)
    with _TRACE_EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def _read_events() -> list[dict[str, Any]]:
    if not _TRACE_EVENTS_FILE.exists():
        return []
    events = []
    for line in _TRACE_EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def _clear_events() -> None:
    if _TRACE_EVENTS_FILE.exists():
        _TRACE_EVENTS_FILE.unlink()


def record_trace_event(event_class: str, text: str, duration_ms: float | None = None) -> None:
    """Record a DAX query event to the trace file if a session is active."""
    if not _is_trace_active():
        return
    entry: dict[str, Any] = {
        "event_class": event_class,
        "text": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    _append_event(entry)


@click.group()
def trace() -> None:
    """Capture and analyse DAX query execution traces."""


@trace.command("start")
@click.option(
    "--events",
    default="QueryBegin,QueryEnd,ProgressReportEnd",
    help="Comma-separated trace event classes to capture.",
)
@click.pass_context
def trace_start(ctx: click.Context, events: str) -> None:
    """Start capturing DAX query trace events.

    \b
    Example:
      pbi trace start
      pbi dax query "EVALUATE TOPN(10, Sales)"
      pbi trace fetch
      pbi trace stop
    """
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)
    _TRACE_ACTIVE_FILE.write_text(events, encoding="utf-8")
    _clear_events()
    console.print(f"[green]Trace started.[/green] Capturing: {events}")
    console.print("[dim]Run DAX queries, then use 'pbi trace fetch' to view events.[/dim]")


@trace.command("stop")
def trace_stop() -> None:
    """Stop the active trace session."""
    count = len(_read_events())
    if _TRACE_ACTIVE_FILE.exists():
        _TRACE_ACTIVE_FILE.unlink()
    console.print(f"[yellow]Trace stopped.[/yellow] {count} events captured.")
    console.print("Use 'pbi trace fetch' to view or 'pbi trace export' to save.")


@trace.command("fetch")
@click.option("--limit", default=50, show_default=True, help="Max events to display.")
@click.pass_context
def trace_fetch(ctx: click.Context, limit: int) -> None:
    """Display captured trace events (most recent first)."""
    events = _read_events()
    if not events:
        console.print("[yellow]No trace events captured.[/yellow]")
        if not _is_trace_active():
            console.print("Run 'pbi trace start' first, execute some DAX queries, then fetch.")
        return
    output_json_or_table(events[-limit:], ctx, title=f"Trace Events (last {min(limit, len(events))})")


@trace.command("export")
@click.option("--output", required=True, type=click.Path(), help="Output JSON file path.")
def trace_export(output: str) -> None:
    """Export captured trace events to a JSON file."""
    events = _read_events()
    if not events:
        console.print("[yellow]No trace events to export.[/yellow]")
        return
    Path(output).write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")
    console.print(f"[green]Exported {len(events)} events to:[/green] {output}")


@trace.command("clear")
def trace_clear() -> None:
    """Clear the trace buffer without stopping the session."""
    count = len(_read_events())
    _clear_events()
    console.print(f"[green]Cleared {count} events from trace buffer.[/green]")


# ── Benchmarking ───────────────────────────────────────────────────────────────


@click.command("benchmark")
@click.argument("expression")
@click.option("--runs", default=5, show_default=True, help="Number of executions to average.")
@click.option("--warmup", default=1, show_default=True, help="Warm-up runs (not counted).")
@click.pass_context
def benchmark(ctx: click.Context, expression: str, runs: int, warmup: int) -> None:
    """Benchmark a DAX expression — run it N times and report timing statistics.

    \b
    Example:
      pbi benchmark "EVALUATE SUMMARIZE(Sales, Sales[Year])" --runs 10
    """
    backend = get_backend(ctx)
    timings: list[float] = []

    console.print(
        f"[cyan]Benchmarking DAX:[/cyan] {expression[:80]}{'...' if len(expression) > 80 else ''}"
    )

    if warmup:
        console.print(f"[dim]Warm-up ({warmup} run(s))...[/dim]")
        for _ in range(warmup):
            backend.dax_query(expression)

    console.print(f"[dim]Measuring ({runs} run(s))...[/dim]")
    for i in range(runs):
        t0 = time.perf_counter()
        backend.dax_query(expression)
        elapsed = (time.perf_counter() - t0) * 1000
        timings.append(elapsed)
        console.print(f"  Run {i + 1}: {elapsed:.1f} ms")

    avg = sum(timings) / len(timings)
    mn = min(timings)
    mx = max(timings)
    p95 = sorted(timings)[int(len(timings) * 0.95)]

    table = Table(title="Benchmark Results")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Runs", str(runs))
    table.add_row("Average", f"{avg:.1f} ms")
    table.add_row("Min", f"{mn:.1f} ms")
    table.add_row("Max", f"{mx:.1f} ms")
    table.add_row("P95", f"{p95:.1f} ms")
    console.print(table)
