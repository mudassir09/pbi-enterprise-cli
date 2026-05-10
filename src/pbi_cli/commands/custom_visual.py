"""pbi custom-visual — TypeScript custom visual SDK scaffolding, build, package, import."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group("custom-visual")
def custom_visual() -> None:
    """Scaffold, build, package, and import Power BI custom visuals (TypeScript SDK)."""


@custom_visual.command("scaffold")
@click.option("--name", required=True, help="Visual name (PascalCase, e.g. MyBarChart).")
@click.option(
    "--display", default=None, help="Display name shown in Power BI (defaults to --name)."
)
@click.option("--guid", default=None, help="Visual GUID (auto-generated if omitted).")
@click.option(
    "--output", default=".", type=click.Path(), help="Parent directory for the new project."
)
@click.option("--author", default="", help="Author name for package.json.")
def custom_visual_scaffold(
    name: str, display: str | None, guid: str | None, output: str, author: str
) -> None:
    """Create a new custom visual TypeScript project from the pbi-cli template.

    \b
    Produces the standard pbiviz project structure:
      <name>/
        package.json
        pbiviz.json
        tsconfig.json
        src/
          visual.ts
          settings.ts
        style/
          visual.less
        assets/
          icon.png  (placeholder)
        capabilities.json

    \b
    Example:
      pbi custom-visual scaffold --name MyBarChart --author "Mudassir"
    """
    import uuid

    display_name = display or name
    visual_guid = guid or str(uuid.uuid4())
    project_dir = Path(output) / name
    if project_dir.exists():
        console.print(f"[yellow]Directory already exists:[/yellow] {project_dir}")
        raise SystemExit(1)

    project_dir.mkdir(parents=True)
    (project_dir / "src").mkdir()
    (project_dir / "style").mkdir()
    (project_dir / "assets").mkdir()

    # pbiviz.json
    (project_dir / "pbiviz.json").write_text(
        json.dumps(
            {
                "visual": {
                    "name": name,
                    "displayName": display_name,
                    "guid": visual_guid,
                    "visualClassName": name,
                    "version": "1.0.0",
                    "description": f"{display_name} Power BI custom visual",
                    "supportUrl": "",
                    "gitHubUrl": "",
                },
                "apiVersion": "5.3.0",
                "author": {"name": author, "email": ""},
                "assets": {"icon": "assets/icon.png"},
                "stringResources": [],
                "capabilities": "capabilities.json",
                "stringResourcesPath": "",
                "externalJS": [],
                "style": "style/visual.less",
                "sources": ["src/visual.ts"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # package.json
    (project_dir / "package.json").write_text(
        json.dumps(
            {
                "name": name.lower(),
                "version": "1.0.0",
                "description": f"{display_name} custom visual",
                "scripts": {
                    "build": "tsc --noEmit",
                    "package": "pbiviz package",
                    "start": "pbiviz start",
                },
                "devDependencies": {
                    "powerbi-visuals-tools": "^5.2.0",
                    "typescript": "^5.0.0",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # tsconfig.json
    (project_dir / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES6",
                    "module": "commonjs",
                    "lib": ["es2015", "dom"],
                    "strict": True,
                    "outDir": ".tmp/build",
                    "declaration": True,
                    "sourceMap": True,
                },
                "include": ["src/**/*.ts"],
                "exclude": ["node_modules"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # capabilities.json
    (project_dir / "capabilities.json").write_text(
        json.dumps(
            {
                "dataRoles": [{"name": "Values", "kind": "Measure", "displayName": "Values"}],
                "dataViewMappings": [{"single": {"role": "Values"}}],
                "objects": {},
                "supportsHighlight": True,
                "sorting": {"default": {}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # src/visual.ts
    (project_dir / "src" / "visual.ts").write_text(
        f"""\
"use strict";

import powerbi from "powerbi-visuals-api";
import VisualConstructorOptions = powerbi.extensibility.visual.VisualConstructorOptions;
import VisualUpdateOptions = powerbi.extensibility.visual.VisualUpdateOptions;
import IVisual = powerbi.extensibility.visual.IVisual;

export class {name} implements IVisual {{
    private target: HTMLElement;

    constructor(options: VisualConstructorOptions) {{
        this.target = options.element;
    }}

    public update(options: VisualUpdateOptions): void {{
        const dataView = options.dataViews?.[0];
        if (!dataView?.single?.value) return;
        this.target.innerHTML = `<p style="font-size:24px">${{dataView.single.value}}</p>`;
    }}
}}
""",
        encoding="utf-8",
    )

    # style/visual.less
    (project_dir / "style" / "visual.less").write_text(
        f"/** {display_name} styles */\n.visual-container {{\n  font-family: 'Segoe UI', sans-serif;\n}}\n",  # noqa: E501
        encoding="utf-8",
    )

    # assets/icon.png placeholder (empty file)
    (project_dir / "assets" / "icon.png").write_bytes(b"")

    console.print(f"[green]Scaffolded:[/green] {project_dir}")
    console.print(f"  GUID:    {visual_guid}")
    console.print("  Version: 1.0.0")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print(f"  cd {project_dir}")
    console.print("  npm install")
    console.print("  pbi custom-visual build --path .")
    console.print("  pbi custom-visual package --path .")


@custom_visual.command("build")
@click.option("--path", default=".", type=click.Path(exists=True), help="Visual project directory.")
@click.option("--watch", is_flag=True, help="Watch for changes and rebuild automatically.")
def custom_visual_build(path: str, watch: bool) -> None:
    """Run tsc --noEmit to type-check the visual TypeScript source.

    Requires Node.js and the devDependencies installed (npm install).

    \b
    Example:
      pbi custom-visual build --path ./MyBarChart
    """
    cmd = ["npx", "tsc", "--noEmit"]
    if watch:
        cmd.append("--watch")
    console.print(f"[cyan]Type-checking:[/cyan] {path}")
    try:
        result = subprocess.run(cmd, cwd=path)
        if result.returncode == 0:
            console.print("[green]Type check passed.[/green]")
        else:
            console.print("[red]Type errors found.[/red] Fix the issues above and re-run.")
            raise SystemExit(result.returncode)
    except FileNotFoundError:
        console.print("[red]npx / Node.js not found.[/red] Install Node.js from https://nodejs.org")
        raise SystemExit(1)


@custom_visual.command("package")
@click.option("--path", default=".", type=click.Path(exists=True), help="Visual project directory.")
@click.option(
    "--output", default=None, type=click.Path(), help="Output .pbiviz path (default: dist/)."
)
def custom_visual_package(path: str, output: str | None) -> None:
    """Package the visual into a .pbiviz file ready for Power BI import.

    Requires powerbi-visuals-tools (pbiviz) installed:  npm install -g powerbi-visuals-tools

    \b
    Example:
      pbi custom-visual package --path ./MyBarChart
    """
    project = Path(path)
    pbiviz_json = project / "pbiviz.json"
    if not pbiviz_json.exists():
        console.print("[red]pbiviz.json not found.[/red] Run 'pbi custom-visual scaffold' first.")
        raise SystemExit(1)

    meta = json.loads(pbiviz_json.read_text(encoding="utf-8"))
    name = meta["visual"]["name"]
    version = meta["visual"]["version"]

    console.print(f"[cyan]Packaging:[/cyan] {name} v{version}")
    try:
        result = subprocess.run(["pbiviz", "package"], cwd=path)
        if result.returncode == 0:
            dist_file = project / "dist" / f"{name}.pbiviz"
            if output and dist_file.exists():
                shutil.copy(dist_file, output)
                console.print(f"[green]Packaged →[/green] {output}")
            else:
                console.print(f"[green]Packaged →[/green] {dist_file}")
        else:
            console.print("[red]Packaging failed.[/red]")
            raise SystemExit(result.returncode)
    except FileNotFoundError:
        console.print("[red]pbiviz not found.[/red] Run: npm install -g powerbi-visuals-tools")
        raise SystemExit(1)


@custom_visual.command("import")
@click.option("--pbip", required=True, help="Path to the .pbip report project.")
@click.option(
    "--pbiviz",
    required=True,
    type=click.Path(exists=True),
    help="Path to the .pbiviz package file.",
)
@click.pass_context
def custom_visual_import(ctx: click.Context, pbip: str, pbiviz: str) -> None:
    """Import a .pbiviz package into a .pbip report project.

    Registers the custom visual in the report so it can be used on any page.

    \b
    Example:
      pbi custom-visual import --pbip ./MyReport --pbiviz ./MyBarChart/dist/MyBarChart.pbiviz
    """
    from pbi_cli.commands._shared import dry_run_echo

    if dry_run_echo(ctx, f"import custom visual '{pbiviz}' into '{pbip}'"):
        return

    pbiviz_path = Path(pbiviz)
    if not pbiviz_path.suffix == ".pbiviz":
        console.print("[red]File must have .pbiviz extension.[/red]")
        raise SystemExit(1)

    # Extract the pbiviz (it's a zip) to find the visual GUID
    import zipfile

    with zipfile.ZipFile(pbiviz_path) as z:
        names = z.namelist()
        pbiviz_json_name = next((n for n in names if n.endswith("pbiviz.json")), None)
        if not pbiviz_json_name:
            console.print("[red]Invalid .pbiviz file — pbiviz.json not found inside archive.[/red]")
            raise SystemExit(1)
        meta = json.loads(z.read(pbiviz_json_name).decode("utf-8"))

    visual_name = meta.get("visual", {}).get("name", pbiviz_path.stem)
    visual_guid = meta.get("visual", {}).get("guid", "unknown")
    version = meta.get("visual", {}).get("version", "1.0.0")

    # Copy pbiviz into report's custom visuals folder
    report_path = Path(pbip)
    cv_dir = report_path / "definition" / "customVisuals"
    cv_dir.mkdir(parents=True, exist_ok=True)
    dest = cv_dir / pbiviz_path.name
    shutil.copy(pbiviz_path, dest)

    console.print(f"[green]Custom visual imported:[/green] {visual_name} v{version}")
    console.print(f"  GUID:   {visual_guid}")
    console.print(f"  Stored: {dest}")
    console.print("[dim]Reload the report in Power BI Desktop to use the visual.[/dim]")
