"""pbi server — FastAPI REST server (Epic E)."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def server() -> None:
    """Start the pbi-cli REST server for pipeline integration."""


@server.command("start")
@click.option("--port", default=7788, show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
def server_start(port: int, host: str) -> None:
    """Start the FastAPI REST server on the specified port."""
    try:
        import uvicorn
        from pbi_cli.server.api import app
        console.print(f"[green]Starting pbi-server[/green] on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        console.print("[red]Server dependencies not installed.[/red]")
        console.print("Run: pip install pbi-cli-tool[server]")
