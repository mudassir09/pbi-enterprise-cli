"""pbi mcp / pbi ask / pbi introspect — AI and agent integration surface."""

from __future__ import annotations

import json

import click
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console(legacy_windows=False)


@click.group("mcp")
def mcp_cmd() -> None:
    """Model Context Protocol server — use pbi from Cursor, Copilot, Claude Desktop."""


@mcp_cmd.command("serve")
@click.pass_context
def mcp_serve(ctx: click.Context) -> None:
    """Start the stdio MCP server against the selected backend.

    \b
    Client config (e.g. Claude Desktop / Cursor mcpServers):
      { "pbi": { "command": "pbi",
                 "args": ["--backend", "file", "--path", "C:/repo", "mcp", "serve"] } }

    Exposes: model_info, list_tables/columns/measures/relationships, run_dax,
    govern_check, dax_lint, format_dax, add_measure.
    """
    from pbi_cli.mcp_server import McpServer

    backend = get_backend(ctx)
    # Propagate the active global flags so run_cli passthrough uses the same backend.
    obj = ctx.obj or {}
    cli_prefix: list[str] = ["--backend", obj.get("backend", "desktop")]
    if obj.get("path"):
        cli_prefix += ["--path", str(obj["path"])]
    McpServer(backend, cli_prefix=cli_prefix).serve_forever()


@mcp_cmd.command("tools")
@click.pass_context
def mcp_tools(ctx: click.Context) -> None:
    """List the tools the MCP server exposes (for client configuration docs)."""
    from pbi_cli.mcp_server import TOOLS

    rows = [{"tool": t["name"], "description": t["description"]} for t in TOOLS]
    output_json_or_table(rows, ctx, title="MCP Tools")


@click.command("ask")
@click.argument("question")
@click.option("--run/--no-run", default=True, show_default=True,
              help="Execute the generated DAX and show results.")
@click.option("--model", "model_id", default="claude-sonnet-4-6", show_default=True)
@click.pass_context
def ask_cmd(ctx: click.Context, question: str, run: bool, model_id: str) -> None:
    """Ask a question in plain English; get (and run) the DAX that answers it.

    \b
    Example:
      pbi ask "top 10 customers by total revenue"

    Requires the [ai] extra and ANTHROPIC_API_KEY.
    """
    try:
        import anthropic
    except ImportError:
        raise click.ClickException(
            "The [ai] extra is required: pip install 'pbi-enterprise-cli[ai]' "
            "and set ANTHROPIC_API_KEY."
        )

    backend = get_backend(ctx)
    schema_lines = []
    for t in backend.table_list():
        cols = ", ".join(c["name"] for c in backend.column_list(t["name"]))
        schema_lines.append(f"table {t['name']}: columns [{cols}]")
    for m in backend.measure_list():
        schema_lines.append(f"measure {m['table']}[{m['name']}] = {m.get('expression', '')}")

    client = anthropic.Anthropic()
    prompt = (
        "You translate questions into DAX queries for this semantic model.\n\n"
        "Model schema:\n" + "\n".join(schema_lines) + "\n\n"
        f"Question: {question}\n\n"
        "Reply with ONLY a valid DAX query starting with EVALUATE (use TOPN/SUMMARIZECOLUMNS "
        "where appropriate). No explanation, no code fences."
    )
    message = client.messages.create(
        model=model_id, max_tokens=800, messages=[{"role": "user", "content": prompt}]
    )
    dax_query = str(getattr(message.content[0], "text", "")).strip().strip("`")
    console.print(f"[bold cyan]DAX:[/bold cyan]\n{dax_query}\n")

    if run:
        try:
            rows = backend.dax_query(dax_query)
            output_json_or_table(rows, ctx, title="Results")
        except NotImplementedError as exc:
            console.print(f"[yellow]Not executed:[/yellow] {exc}")


@click.command("introspect")
@click.option("--format", "fmt", type=click.Choice(["json", "llms"]), default="json",
              show_default=True, help="json = machine-readable command map; llms = llms.txt.")
@click.pass_context
def introspect_cmd(ctx: click.Context, fmt: str) -> None:
    """Dump the full command tree machine-readably — built for AI agents.

    `--format llms` emits an llms.txt-style document describing every command;
    pipe it to a file that agents can load as context.
    """
    from pbi_cli.cli import cli as root

    def walk(cmd: click.Command, path: list[str]) -> list[dict]:
        entries = []
        full = " ".join(path)
        params = [
            {"name": p.name, "opts": list(getattr(p, "opts", [])),
             "required": bool(p.required),
             "help": getattr(p, "help", "") or ""}
            for p in cmd.params if p.name not in ("help",)
        ]
        entries.append({
            "command": full,
            "help": (cmd.help or cmd.short_help or "").strip().split("\n")[0],
            "params": params,
        })
        if isinstance(cmd, click.Group):
            for name, sub in sorted(cmd.commands.items()):
                entries.extend(walk(sub, [*path, name]))
        return entries

    entries = walk(root, ["pbi"])

    if fmt == "json":
        click.echo(json.dumps(entries, indent=2))
        return

    from pbi_cli import __version__

    lines = [
        "# pbi-enterprise-cli",
        "",
        f"> Power BI / Microsoft Fabric automation CLI v{__version__}. "
        "All commands support --json for machine-readable output, --dry-run for "
        "write previews, and --backend desktop|xmla|mock|file|rest.",
        "",
        "## Commands",
        "",
    ]
    for e in entries[1:]:
        if e["help"]:
            lines.append(f"- `{e['command']}`: {e['help']}")
    click.echo("\n".join(lines))
