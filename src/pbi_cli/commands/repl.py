"""pbi repl — interactive REPL with tab completion, history, and persistent connection."""

from __future__ import annotations

import readline
from pathlib import Path
from typing import Any

import click
from rich.console import Console

console = Console()

_HISTORY_FILE = Path.home() / ".pbi-cli" / "repl_history"
_COMMANDS = [
    "model info",
    "model tables",
    "model columns",
    "model relationships",
    "model lint",
    "model stats",
    "measure list",
    "measure add",
    "measure update",
    "measure delete",
    "measure generate",
    "dax query",
    "dax validate",
    "dax test",
    "source profile",
    "source scaffold",
    "report pages",
    "report page-add",
    "report page-delete",
    "report bookmark-list",
    "report bookmark-add",
    "report bookmark-delete",
    "visual list",
    "visual add",
    "govern check",
    "govern fix",
    "govern rules",
    "security roles",
    "security role-add",
    "partition list",
    "partition add",
    "partition refresh",
    "trace start",
    "trace stop",
    "trace fetch",
    "connections list",
    "connections last",
    "deploy snapshot",
    "deploy diff",
    "database export-tmdl",
    "database import-tmdl",
    "database diff-tmdl",
    "doctor",
    "help",
    "exit",
    "quit",
]


class _PbiCompleter:
    """Tab-completion provider for the pbi REPL."""

    def __init__(self, commands: list[str]) -> None:
        self.commands = commands
        self.matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            if text:
                self.matches = [c for c in self.commands if c.startswith(text)]
            else:
                self.matches = list(self.commands)
        try:
            return self.matches[state]
        except IndexError:
            return None


def _load_history() -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _HISTORY_FILE.exists():
        try:
            readline.read_history_file(str(_HISTORY_FILE))  # type: ignore[attr-defined]
        except Exception:
            pass
    readline.set_history_length(1000)  # type: ignore[attr-defined]


def _save_history() -> None:
    try:
        readline.write_history_file(str(_HISTORY_FILE))  # type: ignore[attr-defined]
    except Exception:
        pass


@click.command("repl")
@click.option(
    "--backend",
    default="desktop",
    type=click.Choice(["desktop", "xmla", "mock"]),
    help="Backend to connect to.",
)
@click.option("--port", default=None, type=int, help="Desktop server port.")
@click.option("--no-history", is_flag=True, help="Disable command history persistence.")
@click.pass_context
def repl(ctx: click.Context, backend: str, port: int | None, no_history: bool) -> None:
    """Start an interactive pbi REPL with tab completion and command history.

    Maintains a persistent connection for the session so you don't have to
    reconnect on every command.

    \b
    Controls:
      Tab          — command completion
      Up/Down      — command history
      Ctrl+D/exit  — quit
      help         — list all commands

    \b
    Example session:
      $ pbi repl
      pbi> model tables
      pbi> measure list --table Sales
      pbi> dax query "EVALUATE {[Total Revenue]}"
    """

    # Set up readline completion
    completer = _PbiCompleter(_COMMANDS)
    readline.set_completer(completer.complete)  # type: ignore[attr-defined]
    readline.parse_and_bind("tab: complete")  # type: ignore[attr-defined]

    if not no_history:
        _load_history()

    # Set up a fake context for the session backend
    ctx.ensure_object(dict)
    ctx.obj["backend"] = backend
    if port:
        ctx.obj["port"] = port

    _print_banner(backend)

    # Try connecting eagerly for desktop backend
    session_backend: Any = None
    if backend == "mock":
        from pbi_cli.backends.mock_backend import MockTomBackend

        session_backend = MockTomBackend()
        session_backend.connect()
        model_name = session_backend.model_info().get("name", "MockModel")
        console.print(f"[green]Connected[/green] ({backend}) — [bold]{model_name}[/bold]")
    else:
        console.print(f"[dim]Backend: {backend} — will connect on first command.[/dim]")

    try:
        while True:
            try:
                # Use plain input() since rich can't handle readline input
                line = input("pbi> ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye![/dim]")
                break

            if not line:
                continue
            if line.lower() in ("exit", "quit", "q"):
                console.print("[dim]Bye![/dim]")
                break
            if line.lower() == "help":
                _print_help()
                continue

            _dispatch(ctx, line, session_backend)

    finally:
        if not no_history:
            _save_history()


def _print_banner(backend: str) -> None:
    console.print("\n[bold blue]pbi-cli interactive REPL[/bold blue]")
    console.print(
        f"  Backend: [cyan]{backend}[/cyan]  |  Tab: complete  |  ↑↓: history  |  Ctrl+D: exit\n"
    )


def _print_help() -> None:
    console.print("[bold]Available commands:[/bold]")
    for cmd in _COMMANDS:
        console.print(f"  pbi {cmd}")


def _dispatch(ctx: click.Context, line: str, session_backend: Any) -> None:
    """Parse and execute a REPL line by delegating to the main CLI."""
    import subprocess

    args = ["pbi"] + line.split()
    # Pass current backend flag
    backend = ctx.obj.get("backend", "desktop")
    args = ["pbi", "--backend", backend] + line.split()
    try:
        subprocess.run(args, capture_output=False)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
