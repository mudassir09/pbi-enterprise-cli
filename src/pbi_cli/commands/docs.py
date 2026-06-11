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

        gen = ConfluenceDocsGenerator(backend)  # type: ignore[assignment]
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


@docs.command("erd")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Write the Mermaid ERD to a file (default: stdout).")
@click.pass_context
def docs_erd(ctx: click.Context, output_path: str | None) -> None:
    """Generate a Mermaid er-diagram of the model (paste into markdown/GitHub)."""
    from pathlib import Path as _P

    backend = get_backend(ctx)
    tables = backend.table_list()
    columns = backend.column_list()
    relationships = backend.relationship_list()

    def _safe(name: str) -> str:
        import re as _re

        return _re.sub(r"[^A-Za-z0-9_]", "_", name)

    lines = ["erDiagram"]
    for t in tables:
        lines.append(f"    {_safe(t['name'])} {{")
        for c in columns:
            if c["table"] == t["name"]:
                dtype = _safe(str(c.get("dataType", "any")) or "any")
                lines.append(f"        {dtype} {_safe(c['name'])}")
        lines.append("    }")
    for r in relationships:
        import re as _re

        m_from = _re.match(r"^(.*)\[(.*)\]$", r.get("from", ""))
        m_to = _re.match(r"^(.*)\[(.*)\]$", r.get("to", ""))
        if not (m_from and m_to):
            continue
        label = m_from.group(2)
        cardinality = "}o--||" if r.get("cardinality", "ManyToOne") == "ManyToOne" else "||--||"
        lines.append(
            f"    {_safe(m_from.group(1))} {cardinality} {_safe(m_to.group(1))} : {_safe(label)}"
        )
    mermaid = "\n".join(lines)

    if output_path:
        _P(output_path).write_text(mermaid, encoding="utf-8")
        console.print(f"[green]ERD written:[/green] {output_path}")
    else:
        click.echo(mermaid)


@docs.command("site")
@click.option("--output", "output_dir", default="docs-site", show_default=True,
              type=click.Path(), help="Folder for the MkDocs site source.")
@click.pass_context
def docs_site(ctx: click.Context, output_dir: str) -> None:
    """Generate a browsable MkDocs documentation site for the model.

    Produces mkdocs.yml + markdown pages (overview, ERD, tables, measures with
    formatted DAX). Publish with: pip install mkdocs && mkdocs build/gh-deploy.
    """
    from pathlib import Path as _P

    from pbi_cli.dax_tools import format_dax

    backend = get_backend(ctx)
    info = backend.model_info()
    tables = backend.table_list()
    columns = backend.column_list()
    measures = backend.measure_list()
    relationships = backend.relationship_list()

    out = _P(output_dir)
    docs_dir = out / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    model_name = info.get("name", "Semantic Model")
    (out / "mkdocs.yml").write_text(
        f"site_name: {model_name} — Data Dictionary\n"
        "theme: readthedocs\n"
        "nav:\n"
        "  - Overview: index.md\n"
        "  - Tables: tables.md\n"
        "  - Measures: measures.md\n",
        encoding="utf-8",
    )

    index = [
        f"# {model_name}",
        "",
        f"- **Tables:** {len(tables)}",
        f"- **Columns:** {len(columns)}",
        f"- **Measures:** {len(measures)}",
        f"- **Relationships:** {len(relationships)}",
        "",
        "## Entity Relationship Diagram",
        "",
        "```mermaid",
    ]
    import re as _re

    def _safe(name: str) -> str:
        return _re.sub(r"[^A-Za-z0-9_]", "_", name)

    index.append("erDiagram")
    for r in relationships:
        m_from = _re.match(r"^(.*)\[(.*)\]$", r.get("from", ""))
        m_to = _re.match(r"^(.*)\[(.*)\]$", r.get("to", ""))
        if m_from and m_to:
            index.append(f"    {_safe(m_from.group(1))} }}o--|| {_safe(m_to.group(1))} : "
                         f"{_safe(m_from.group(2))}")
    index += ["```", ""]
    (docs_dir / "index.md").write_text("\n".join(index), encoding="utf-8")

    table_lines = ["# Tables", ""]
    for t in tables:
        table_lines += [f"## {t['name']}", ""]
        if t.get("description"):
            table_lines += [t["description"], ""]
        table_lines += ["| Column | Type | Hidden |", "|---|---|---|"]
        for c in columns:
            if c["table"] == t["name"]:
                table_lines.append(
                    f"| {c['name']} | {c.get('dataType', '')} | "
                    f"{'yes' if c.get('isHidden') else ''} |")
        table_lines.append("")
    (docs_dir / "tables.md").write_text("\n".join(table_lines), encoding="utf-8")

    measure_lines = ["# Measures", ""]
    for m in sorted(measures, key=lambda x: (x["table"], x["name"])):
        measure_lines += [f"## {m['table']}[{m['name']}]", ""]
        if m.get("description"):
            measure_lines += [m["description"], ""]
        try:
            formatted = format_dax(m.get("expression", ""))
        except Exception:
            formatted = m.get("expression", "")
        measure_lines += ["```dax", formatted, "```", ""]
        if m.get("formatString"):
            measure_lines += [f"Format: `{m['formatString']}`", ""]
    (docs_dir / "measures.md").write_text("\n".join(measure_lines), encoding="utf-8")

    console.print(f"[green]MkDocs site source written:[/green] {out}")
    console.print("  mkdocs serve   — preview locally")
    console.print("  mkdocs gh-deploy — publish to GitHub Pages")
