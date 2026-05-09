"""pbi docs — data dictionary generation and audit log (Epic D)."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console()


@click.group()
def docs() -> None:
    """Generate data dictionaries, documentation, and view the audit log."""


@docs.command("generate")
@click.option("--format", "fmt", type=click.Choice(["markdown", "confluence"]), default="markdown")
@click.option("--output", default=None, help="Output file path.")
@click.pass_context
def docs_generate(ctx: click.Context, fmt: str, output: str | None) -> None:
    """Generate a full data dictionary for the model."""
    backend = get_backend(ctx)
    if fmt == "markdown":
        from pbi_cli.docs_gen.markdown import MarkdownDocsGenerator

        gen = MarkdownDocsGenerator(backend)
    else:
        from pbi_cli.docs_gen.confluence import ConfluenceDocsGenerator

        gen = ConfluenceDocsGenerator(backend)
    content = gen.generate()
    if output:
        from pathlib import Path

        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]Written:[/green] {output}")
    else:
        console.print(content)


@docs.command("audit-log")
@click.option("--limit", default=50, show_default=True, help="Number of recent entries to show.")
@click.pass_context
def docs_audit_log(ctx: click.Context, limit: int) -> None:
    """Display the audit log of all write operations (~/.pbi-cli/audit.jsonl)."""
    from pbi_cli._audit import read_audit_log

    entries = read_audit_log(limit=limit)
    if not entries:
        console.print("[yellow]Audit log is empty.[/yellow]")
        console.print(
            "Write operations (measure add/update/delete, scaffold, deploy) are logged automatically."  # noqa: E501
        )
        return
    output_json_or_table(entries, ctx, title="Audit Log")
