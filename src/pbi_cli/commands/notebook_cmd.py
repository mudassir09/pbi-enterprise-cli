"""pbi notebook — run Fabric notebooks and round-trip .ipynb (data engineering).

First-class notebook ergonomics beyond generic ``fabric item`` CRUD: run a
notebook with typed parameters and optionally wait for completion, check a run's
status, and export/import the notebook as a real ``.ipynb`` file.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, output_json_or_table

console = Console(legacy_windows=False)

_IPYNB_PART = "notebook-content.ipynb"


@click.group("notebook")
def notebook_cmd() -> None:
    """Fabric notebooks: run with parameters, check status, export/import .ipynb."""


def _parse_param(raw: str) -> tuple[str, dict]:
    """Parse 'name=value' into the Fabric parameter shape with an inferred type."""
    if "=" not in raw:
        raise click.ClickException(f"--param must be name=value, got: {raw!r}")
    name, _, value = raw.partition("=")
    name = name.strip()
    value = value.strip()
    lowered = value.lower()
    if lowered in ("true", "false"):
        return name, {"value": lowered == "true", "type": "bool"}
    try:
        return name, {"value": int(value), "type": "int"}
    except ValueError:
        pass
    try:
        return name, {"value": float(value), "type": "float"}
    except ValueError:
        pass
    return name, {"value": value, "type": "string"}


@notebook_cmd.command("run")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--notebook", "notebook_id", required=True, help="Notebook item id.")
@click.option("--param", "params", multiple=True,
              help="Parameter as name=value (repeatable; types inferred).")
@click.option("--wait/--no-wait", default=False, show_default=True,
              help="Poll the run to completion and return final status.")
@click.option("--timeout", default=600, show_default=True, help="Wait timeout in seconds.")
@click.pass_context
def notebook_run(  # noqa: PLR0913
    ctx: click.Context,
    workspace_id: str,
    notebook_id: str,
    params: tuple[str, ...],
    wait: bool,
    timeout: int,
) -> None:
    """Run a notebook on demand, optionally passing parameters.

    \b
    Fire-and-forget:
      pbi notebook run --workspace <ws> --notebook <id>
    Parameterised and wait for the result:
      pbi notebook run --workspace <ws> --notebook <id> \\
        --param window=7 --param rebuild=true --wait
    """
    from pbi_cli import fabric_api as _fab

    parameters = dict(_parse_param(p) for p in params)
    exec_data = {"parameters": parameters} if parameters else None

    if dry_run_echo(ctx, "run notebook",
                    f"params={list(parameters)}" if parameters else "no params"):
        return

    token = _fab.get_token()
    result = _fab.run_item_job(
        workspace_id, notebook_id, "RunNotebook", token,
        execution_data=exec_data, wait=wait, timeout=timeout,
    )
    state = result.get("status", "Accepted")
    colour = "green" if state in ("Completed", "Succeeded", "NotStarted") else "yellow"
    console.print(f"[{colour}]Notebook run: {state}[/{colour}]")
    output_json_or_table(result, ctx, title="Notebook Run")


@notebook_cmd.command("status")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--notebook", "notebook_id", required=True)
@click.option("--job", "job_id", required=True, help="Job instance id from `notebook run`.")
@click.pass_context
def notebook_status(ctx: click.Context, workspace_id: str, notebook_id: str,
                    job_id: str) -> None:
    """Get the status of a notebook run."""
    from pbi_cli import fabric_api as _fab

    token = _fab.get_token()
    result = _fab.get(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/items/{notebook_id}"
        f"/jobs/instances/{job_id}", token)
    output_json_or_table(result, ctx, title="Notebook Run Status")


@notebook_cmd.command("export")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--notebook", "notebook_id", required=True)
@click.option("--output", "output_file", required=True, type=click.Path(),
              help="Destination .ipynb path.")
@click.pass_context
def notebook_export(ctx: click.Context, workspace_id: str, notebook_id: str,
                    output_file: str) -> None:
    """Export a notebook to a local .ipynb file."""
    from pbi_cli import fabric_api as _fab

    token = _fab.get_token()
    base = f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/notebooks/{notebook_id}"
    result = _fab.poll_lro(
        _fab.post(f"{base}/getDefinition?format=ipynb", token, payload={}), token)
    parts = (result.get("definition") or {}).get("parts", [])
    part = next((p for p in parts if p.get("path", "").endswith(".ipynb")), None)
    if part is None:
        raise click.ClickException("No .ipynb part found in the notebook definition.")
    Path(output_file).write_bytes(base64.b64decode(part["payload"]))
    console.print(f"[green]Notebook exported to {output_file}[/green]")


@notebook_cmd.command("import")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--name", "display_name", required=True, help="Display name for the new notebook.")
@click.option("--file", "ipynb_file", required=True, type=click.Path(exists=True),
              help="Source .ipynb file.")
@click.option("--description", default=None)
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.pass_context
def notebook_import(  # noqa: PLR0913
    ctx: click.Context,
    workspace_id: str,
    display_name: str,
    ipynb_file: str,
    description: str | None,
    wait: bool,
) -> None:
    """Create a notebook in a workspace from a local .ipynb file."""
    from pbi_cli import fabric_api as _fab

    raw = Path(ipynb_file).read_bytes()
    try:
        json.loads(raw)  # fail fast on a non-JSON file
    except ValueError:
        raise click.ClickException(f"{ipynb_file} is not valid JSON (.ipynb).")

    if dry_run_echo(ctx, f"create notebook '{display_name}' from {ipynb_file}"):
        return

    payload: dict = {
        "displayName": display_name,
        "definition": {
            "format": "ipynb",
            "parts": [{
                "path": _IPYNB_PART,
                "payload": base64.b64encode(raw).decode(),
                "payloadType": "InlineBase64",
            }],
        },
    }
    if description:
        payload["description"] = description

    token = _fab.get_token()
    resp = _fab.post(
        f"{_fab.FABRIC_API_BASE}/workspaces/{workspace_id}/notebooks", token, payload=payload)
    if wait:
        resp = _fab.poll_lro(resp, token)
    console.print(f"[green]Notebook '{display_name}' created.[/green]")
    output_json_or_table(resp if isinstance(resp, dict) else {"status": "Accepted"},
                         ctx, title="Notebook Created")
