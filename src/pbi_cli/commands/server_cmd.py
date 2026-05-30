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
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Host to bind. Use 0.0.0.0 only behind a firewall.",
)
def server_start(port: int, host: str) -> None:
    """Start the FastAPI REST server (requires PBI_SERVER_KEY env var).

    \b
    Quick start:
      export PBI_SERVER_KEY=$(pbi server generate-key)
      pbi server start

    \b
    Call the API:
      curl -H "X-PBI-API-Key: $PBI_SERVER_KEY" http://localhost:7788/api/status
    """
    import os

    if not os.environ.get("PBI_SERVER_KEY"):
        console.print("[red]PBI_SERVER_KEY is not set.[/red]")
        console.print("Generate one with:  pbi server generate-key")
        console.print("Then set it:        export PBI_SERVER_KEY=<key>")
        raise SystemExit(1)

    if host != "127.0.0.1":
        console.print(
            f"[yellow]WARNING:[/yellow] Binding to {host} exposes the server on the network. "
            "Ensure a firewall or VPN is in place."
        )

    try:
        import uvicorn

        from pbi_cli.server.api import app

        console.print(f"[green]Starting pbi-server[/green] on {host}:{port}")
        console.print("[dim]Authentication: X-PBI-API-Key header required[/dim]")
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        console.print("[red]Server dependencies not installed.[/red]")
        console.print("Run: pip install pbi-cli-tool[server]")


@server.command("generate-key")
def server_generate_key() -> None:
    """Generate a cryptographically random API key for PBI_SERVER_KEY.

    \b
    Usage:
      export PBI_SERVER_KEY=$(pbi server generate-key)
      pbi server start
    """
    from pbi_cli.server.auth import generate_key

    click.echo(generate_key())
