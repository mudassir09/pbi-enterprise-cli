"""pbi ops — refresh orchestration, health checks, webhook notifications."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import click
import yaml  # type: ignore[import-untyped]
from rich.console import Console

from pbi_cli import fabric_api
from pbi_cli.commands._shared import output_json_or_table

console = Console(legacy_windows=False)


def send_webhook(url: str, message: str) -> None:
    """Post a simple text payload — works for Teams and Slack incoming webhooks."""
    req = urllib.request.Request(
        url,
        data=json.dumps({"text": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):  # noqa: S310
        pass


@click.group("ops")
def ops_cmd() -> None:
    """Operations: chained refreshes, health checks, notifications."""


@ops_cmd.command("refresh")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--dataset", "dataset_id", required=True)
@click.option("--type", "refresh_type", default="full", show_default=True)
@click.option("--wait/--no-wait", default=True, show_default=True,
              help="Poll until the refresh completes.")
@click.option("--timeout", default=3600, show_default=True)
@click.option("--notify", default=None, help="Webhook URL to notify on failure (Teams/Slack).")
@click.pass_context
def ops_refresh(ctx: click.Context, workspace_id: str, dataset_id: str, refresh_type: str,
                wait: bool, timeout: int, notify: str | None) -> None:
    """Trigger a dataset refresh and (by default) wait for the outcome."""
    token = fabric_api.get_token()
    result = _run_refresh(token, workspace_id, dataset_id, refresh_type, wait, timeout)
    if result["status"] == "Failed" and notify:
        send_webhook(notify, f"❌ Power BI refresh failed: dataset {dataset_id} "
                             f"in workspace {workspace_id} — {result.get('error', '')}")
    output_json_or_table(result, ctx, title="Refresh")
    if result["status"] == "Failed":
        raise SystemExit(4)


def _run_refresh(token: str, workspace_id: str, dataset_id: str, refresh_type: str,
                 wait: bool, timeout: int) -> dict[str, Any]:
    base = f"{fabric_api.POWERBI_API_BASE}/groups/{workspace_id}/datasets/{dataset_id}"
    fabric_api.post(f"{base}/refreshes", token,
                    payload={"type": refresh_type, "commitMode": "transactional"})
    if not wait:
        return {"dataset": dataset_id, "status": "Requested"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history = fabric_api.get(f"{base}/refreshes?$top=1", token).get("value", [])
        if history:
            status = history[0].get("status", "Unknown")
            if status == "Completed":
                return {"dataset": dataset_id, "status": "Completed",
                        "endTime": history[0].get("endTime", "")}
            if status == "Failed":
                detail = history[0].get("serviceExceptionJson", "")
                return {"dataset": dataset_id, "status": "Failed", "error": detail[:300]}
        time.sleep(10)
    return {"dataset": dataset_id, "status": "Timeout"}


@ops_cmd.command("refresh-chain")
@click.option("--plan", required=True, type=click.Path(exists=True),
              help="YAML chain plan.")
@click.option("--notify", default=None, help="Webhook URL for failure notifications.")
@click.pass_context
def ops_refresh_chain(ctx: click.Context, plan: str, notify: str | None) -> None:
    """Run refreshes in order, short-circuiting on failure.

    \b
    Plan format:
      steps:
        - {workspace: <ws-id>, dataset: <staging-id>, type: full}
        - {workspace: <ws-id>, dataset: <mart-id>}
    """
    token = fabric_api.get_token()
    spec = yaml.safe_load(Path(plan).read_text(encoding="utf-8")) or {}
    results: list[dict[str, Any]] = []
    quiet = bool(ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")))

    for step in spec.get("steps", []):
        ds = step["dataset"]
        if not quiet:
            console.print(f"[cyan]Refreshing {ds}...[/cyan]")
        result = _run_refresh(token, step["workspace"], ds,
                              step.get("type", "full"), wait=True,
                              timeout=step.get("timeout", 3600))
        results.append(result)
        if result["status"] != "Completed":
            if notify:
                send_webhook(notify, f"❌ Refresh chain stopped at dataset {ds}: "
                                     f"{result['status']} {result.get('error', '')}")
            output_json_or_table(results, ctx, title="Refresh Chain (stopped)")
            raise SystemExit(4)

    output_json_or_table(results, ctx, title="Refresh Chain")


@ops_cmd.command("health")
@click.option("--workspace", "workspace_id", required=True)
@click.option("--hours", default=24, show_default=True,
              help="Look-back window for failed refreshes.")
@click.option("--notify", default=None, help="Webhook URL — notify when problems are found.")
@click.pass_context
def ops_health(ctx: click.Context, workspace_id: str, hours: int, notify: str | None) -> None:
    """Workspace health: failed/never-run refreshes across all datasets."""
    from datetime import datetime, timedelta, timezone

    token = fabric_api.get_token()
    base = f"{fabric_api.POWERBI_API_BASE}/groups/{workspace_id}"
    datasets = fabric_api.get(f"{base}/datasets", token).get("value", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    problems: list[dict[str, str]] = []

    for ds in datasets:
        if not ds.get("isRefreshable"):
            continue
        history = fabric_api.get(
            f"{base}/datasets/{ds['id']}/refreshes?$top=5", token).get("value", [])
        for refresh in history:
            if refresh.get("status") != "Failed":
                continue
            end = refresh.get("endTime", "")
            try:
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
            except ValueError:
                end_dt = None
            if end_dt is None or end_dt >= cutoff:
                problems.append({
                    "dataset": ds.get("name", ds["id"]),
                    "status": "Failed",
                    "endTime": end,
                    "error": (refresh.get("serviceExceptionJson") or "")[:120],
                })
                break

    output_json_or_table(problems, ctx, title=f"Refresh failures (last {hours}h)")
    if not problems and not (ctx.obj or {}).get("output_json"):
        console.print("[green]No refresh failures.[/green]")
    if problems and notify:
        names = ", ".join(p["dataset"] for p in problems)
        send_webhook(notify, f"⚠️ {len(problems)} dataset(s) failing refresh "
                             f"in workspace {workspace_id}: {names}")
    if problems:
        raise SystemExit(4)
