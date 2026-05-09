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

console = Console()

# In-memory trace buffer (per process)
_trace_buffer: list[dict[str, Any]] = []
_trace_active: bool = False


@click.group()
def trace() -> None:
    """Capture and analyse DAX query execution traces."""


@trace.command("start")
@click.option("--events", default="QueryBegin,QueryEnd,ProgressReportEnd",
              help="Comma-separated trace event classes to capture.")
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
    global _trace_active, _trace_buffer
    _trace_buffer = []
    _trace_active = True
    console.print(f"[green]Trace started.[/green] Capturing: {events}")
    console.print("[dim]Run DAX queries, then use 'pbi trace fetch' to view events.[/dim]")


@trace.command("stop")
def trace_stop() -> None:
    """Stop the active trace session."""
    global _trace_active
    _trace_active = False
    console.print(f"[yellow]Trace stopped.[/yellow] {len(_trace_buffer)} events captured.")
    console.print("Use 'pbi trace fetch' to view or 'pbi trace export' to save.")


@trace.command("fetch")
@click.option("--limit", default=50, show_default=True, help="Max events to display.")
@click.pass_context
def trace_fetch(ctx: click.Context, limit: int) -> None:
    """Display captured trace events (most recent first)."""
    if not _trace_buffer:
        console.print("[yellow]No trace events captured.[/yellow]")
        console.print("Run 'pbi trace start' first, execute some DAX queries, then fetch.")
        return
    events = _trace_buffer[-limit:]
    output_json_or_table(events, ctx, title=f"Trace Events (last {len(events)})")


@trace.command("export")
@click.option("--output", required=True, type=click.Path(), help="Output JSON file path.")
def trace_export(output: str) -> None:
    """Export captured trace events to a JSON file."""
    if not _trace_buffer:
        console.print("[yellow]No trace events to export.[/yellow]")
        return
    Path(output).write_text(json.dumps(_trace_buffer, indent=2, default=str), encoding="utf-8")
    console.print(f"[green]Exported {len(_trace_buffer)} events to:[/green] {output}")


@trace.command("clear")
def trace_clear() -> None:
    """Clear the trace buffer without stopping the session."""
    global _trace_buffer
    count = len(_trace_buffer)
    _trace_buffer = []
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

    console.print(f"[cyan]Benchmarking DAX:[/cyan] {expression[:80]}{'...' if len(expression) > 80 else ''}")

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
        console.print(f"  Run {i+1}: {elapsed:.1f} ms")

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
