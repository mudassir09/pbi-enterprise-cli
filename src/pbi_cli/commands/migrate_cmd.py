"""pbi migrate — Direct Lake readiness, PBIX extraction, dbt interop."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from pbi_cli.commands._shared import get_backend, output_json_or_table

console = Console()


@click.group("migrate")
def migrate_cmd() -> None:
    """Migration tooling: Import to Direct Lake, PBIX extraction, dbt interop."""


@migrate_cmd.command("direct-lake")
@click.option("--analyze", is_flag=True, default=True,
              help="Report blockers preventing a Direct Lake conversion.")
@click.pass_context
def migrate_direct_lake(ctx: click.Context, analyze: bool) -> None:
    """Analyze an Import model for Direct Lake blockers.

    Direct Lake does not support calculated columns, calculated tables, or
    non-lakehouse sources; this reports every blocker with the object name.
    """
    backend = get_backend(ctx)
    blockers: list[dict[str, str]] = []

    for c in backend.column_list():
        if (c.get("expression") or "").strip() and not c.get("sourceColumn"):
            blockers.append({
                "blocker": "calculated-column",
                "object": f"{c['table']}[{c['name']}]",
                "action": "Materialize in the lakehouse (dbt/notebook) or drop.",
            })

    for p in backend.partition_list():
        source = (p.get("source") or "").strip()
        mode = str(p.get("mode", "")).lower()
        kind = str(p.get("kind", "")).lower()
        if (kind == "calculated" or mode == "calculated"
                or source.upper().startswith(("CALENDAR", "EVALUATE", "VAR"))):
            blockers.append({
                "blocker": "calculated-table",
                "object": p["table"],
                "action": "Materialize as a delta table in the lakehouse.",
            })
        elif source and not any(
            fn in source for fn in ("Lakehouse.Contents", "Fabric.Warehouse")
        ):
            blockers.append({
                "blocker": "non-lakehouse-source",
                "object": f"{p['table']} ({p['name']})",
                "action": "Land this data in OneLake (Dataflow Gen2 / pipeline / shortcut).",
            })

    tables = backend.table_list()
    result_summary = {
        "tables": len(tables),
        "blockers": len(blockers),
        "ready": not blockers,
    }
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table({"summary": result_summary, "blockers": blockers}, ctx)
        return
    if not blockers:
        console.print("[green]No Direct Lake blockers found — the schema is convertible.[/green]")
    else:
        output_json_or_table(blockers, ctx, title="Direct Lake Blockers")
        console.print(f"\n[bold]{len(blockers)} blocker(s)[/bold] across {len(tables)} tables")


@migrate_cmd.command("pbix-extract")
@click.argument("pbix_file", type=click.Path(exists=True))
@click.option("--output", "output_dir", required=True, type=click.Path(),
              help="Folder to extract layout/metadata into.")
@click.pass_context
def migrate_pbix_extract(ctx: click.Context, pbix_file: str, output_dir: str) -> None:
    """Extract report layout and metadata from a legacy .pbix/.pbit for inventory.

    Writes Layout.json (report structure), DataModelSchema.json (pbit only),
    and a summary. Full model extraction needs the file re-saved as .pbip in
    Desktop — this command is for auditing legacy estates at scale.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Any] = {"file": pbix_file, "parts": []}

    with zipfile.ZipFile(pbix_file) as z:
        names = z.namelist()
        for name in names:
            if name in ("Report/Layout", "Report/LinguisticSchema"):
                raw = z.read(name)
                try:
                    text = raw.decode("utf-16-le")
                except UnicodeDecodeError:
                    text = raw.decode("utf-8", errors="replace")
                target = out / (Path(name).name + ".json")
                try:
                    target.write_text(
                        json.dumps(json.loads(text), indent=2), encoding="utf-8")
                except json.JSONDecodeError:
                    target.write_text(text, encoding="utf-8")
                extracted["parts"].append(target.name)
            elif name == "DataModelSchema":
                raw = z.read(name)
                text = raw.decode("utf-16-le", errors="replace")
                (out / "DataModelSchema.json").write_text(text, encoding="utf-8")
                extracted["parts"].append("DataModelSchema.json")
            elif name in ("Version", "Settings", "Metadata"):
                extracted["parts"].append(name)
        extracted["hasDataModel"] = "DataModel" in names
        if extracted["hasDataModel"]:
            extracted["note"] = (
                "DataModel is a compressed VertiPaq store — open in Desktop and save "
                "as .pbip for full TMDL extraction."
            )

    layout = out / "Layout.json"
    if layout.exists():
        data = json.loads(layout.read_text(encoding="utf-8"))
        sections = data.get("sections", [])
        extracted["pages"] = len(sections)
        extracted["visuals"] = sum(len(s.get("visualContainers", [])) for s in sections)

    output_json_or_table(extracted, ctx, title="PBIX Extraction")


@migrate_cmd.command("dbt")
@click.option("--manifest", required=True, type=click.Path(exists=True),
              help="Path to a dbt manifest.json.")
@click.option("--contract-out", default=None, type=click.Path(),
              help="Write a pbi test schema contract generated from dbt models.")
@click.pass_context
def migrate_dbt(ctx: click.Context, manifest: str, contract_out: str | None) -> None:
    """Map dbt models to semantic-model tables; generate a schema contract.

    Reads the dbt manifest, matches model names against the connected semantic
    model's tables, and reports coverage. With --contract-out, emits a YAML
    contract (pbi test schema) so dbt column changes fail the BI gate.
    """
    import yaml  # type: ignore[import-untyped]

    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    dbt_models = {
        node.get("name", ""): node
        for key, node in (data.get("nodes") or {}).items()
        if key.startswith("model.")
    }

    backend = get_backend(ctx)
    tables = {t["name"].lower(): t["name"] for t in backend.table_list()}

    rows = []
    contract: dict[str, Any] = {"tables": {}}
    for name, node in sorted(dbt_models.items()):
        match = tables.get(name.lower())
        rows.append({
            "dbt_model": name,
            "semantic_table": match or "(unmapped)",
            "schema": node.get("schema", ""),
            "columns": len(node.get("columns") or {}),
        })
        if match:
            cols: dict[str, dict] = {
                cname: {} for cname in (node.get("columns") or {})
            }
            contract["tables"][match] = {"columns": cols} if cols else {}

    output_json_or_table(rows, ctx, title="dbt → Semantic Model Mapping")
    mapped = sum(1 for r in rows if r["semantic_table"] != "(unmapped)")
    if not (ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml"))):
        console.print(f"\n[bold]{mapped}/{len(rows)} dbt models mapped to tables[/bold]")

    if contract_out:
        Path(contract_out).write_text(
            yaml.dump(contract, sort_keys=False), encoding="utf-8")
        if not (ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml"))):
            console.print(f"[green]Schema contract written:[/green] {contract_out}")
