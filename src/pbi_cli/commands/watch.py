"""pbi watch — file watcher for continuous governance checking."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--path", default=".", help="Directory to watch for TMDL/PBIP changes.")
@click.option(
    "--on",
    "events",
    multiple=True,
    type=click.Choice(["govern", "dax-test", "all"]),
    default=["all"],
    show_default=True,
    help="Which checks to run on each change (can repeat).",
)
@click.option(
    "--debounce",
    default=2.0,
    show_default=True,
    help="Seconds to wait after a change before running checks.",
)
@click.option(
    "--patterns",
    default="*.tmdl,*.json",
    help="Comma-separated glob patterns to watch (default: *.tmdl,*.json).",
)
def watch(path: str, events: tuple[str, ...], debounce: float, patterns: str) -> None:
    """Watch for TMDL / PBIP file changes and auto-run govern check and/or dax test.

    \b
    Requires: pip install watchdog

    \b
    Examples:
      pbi watch                          # watch current dir, run all checks
      pbi watch --path ./MyModel --on govern
      pbi watch --path . --on govern --on dax-test --debounce 3
    """
    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler  # type: ignore[import]
        from watchdog.observers import Observer  # type: ignore[import]
    except ImportError:
        console.print("[red]watchdog not installed.[/red] Run: [bold]pip install watchdog[/bold]")
        raise SystemExit(1)

    watch_path = Path(path).resolve()
    if not watch_path.exists():
        console.print(f"[red]Path not found:[/red] {watch_path}")
        raise SystemExit(1)

    run_govern = "govern" in events or "all" in events
    run_dax = "dax-test" in events or "all" in events

    pat_list = [p.strip() for p in patterns.split(",") if p.strip()]
    console.print(f"[cyan]Watching:[/cyan] {watch_path}")
    console.print(f"  Patterns : {', '.join(pat_list)}")
    console.print(
        f"  Checks   : {'govern' if run_govern else ''} {'dax-test' if run_dax else ''}".strip()
    )
    console.print(f"  Debounce : {debounce}s")
    console.print("Press [bold]Ctrl+C[/bold] to stop.\n")

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            self._last_trigger = 0.0

        def on_any_event(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            src = str(event.src_path)
            if not any(Path(src).match(pat) for pat in pat_list):
                return
            now = time.monotonic()
            if now - self._last_trigger < debounce:
                return
            self._last_trigger = now
            console.print(f"[yellow]Change detected:[/yellow] {src}")
            _run_checks(watch_path, run_govern, run_dax)

    def _run_checks(cwd: Path, do_govern: bool, do_dax: bool) -> None:
        pbi_cmd = [sys.executable, "-m", "pbi_cli"]
        # Use the installed `pbi` entry-point if available
        import shutil

        pbi_exe = shutil.which("pbi")
        base_cmd: list[str] = [pbi_exe] if pbi_exe else pbi_cmd

        if do_govern:
            console.print("[cyan]Running:[/cyan] pbi govern check")
            result = subprocess.run(
                base_cmd + ["govern", "check"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            _print_result(result, "govern check")

        if do_dax:
            console.print("[cyan]Running:[/cyan] pbi dax test")
            result = subprocess.run(
                base_cmd + ["dax", "test"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            _print_result(result, "dax test")

    def _print_result(result: subprocess.CompletedProcess, label: str) -> None:
        if result.returncode == 0:
            console.print(f"  [green]OK[/green] {label}")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    console.print(f"    {line}")
        else:
            console.print(f"  [red]FAIL[/red] {label} (exit {result.returncode})")
            for line in (result.stdout + result.stderr).strip().splitlines():
                console.print(f"    [red]{line}[/red]")

    handler = _Handler()
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    # Run checks immediately on start
    console.print("[cyan]Running initial checks...[/cyan]")
    _run_checks(watch_path, run_govern, run_dax)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]Watch stopped.[/yellow]")
    observer.join()
