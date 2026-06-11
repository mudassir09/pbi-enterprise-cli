"""pbi tenant — org-wide administration: usage analytics, access review, labels.

All commands use the Power BI admin REST APIs and need a token with admin
consent (Tenant.Read.All / Tenant.ReadWrite.All or a service principal in an
admin-API-enabled security group).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import click
from rich.console import Console

from pbi_cli import fabric_api
from pbi_cli.commands._shared import output_json_or_table

console = Console()


@click.group("tenant")
def tenant_cmd() -> None:
    """Tenant-wide administration: usage, access review, sensitivity labels."""


@tenant_cmd.command("usage")
@click.option("--days", default=7, show_default=True,
              help="Days of activity to analyze (admin API keeps 30).")
@click.option("--activity", default=None,
              help="Filter to one activity type, e.g. ViewReport, RefreshDataset.")
@click.option("--user", default=None, help="Filter to one user (email).")
@click.option("--top", default=20, show_default=True, help="Rows in the summary tables.")
@click.pass_context
def tenant_usage(
    ctx: click.Context, days: int, activity: str | None, user: str | None, top: int
) -> None:
    """Adoption report from the activity log: top reports, top users, stale candidates."""
    token = fabric_api.get_token()
    base = fabric_api.POWERBI_API_BASE
    events: list[dict] = []

    for day_offset in range(min(days, 30)):
        day = datetime.now(timezone.utc).date() - timedelta(days=day_offset)
        start = f"'{day.isoformat()}T00:00:00'"
        end = f"'{day.isoformat()}T23:59:59'"
        url: str | None = (
            f"{base}/admin/activityevents?startDateTime={start}&endDateTime={end}"
        )
        while url:
            page = fabric_api.get(url, token)
            events.extend(page.get("activityEventEntities", []))
            url = page.get("continuationUri")

    if activity:
        events = [e for e in events if e.get("Activity") == activity]
    if user:
        events = [e for e in events if e.get("UserId", "").lower() == user.lower()]

    by_activity: dict[str, int] = {}
    by_user: dict[str, int] = {}
    by_artifact: dict[str, int] = {}
    for e in events:
        by_activity[e.get("Activity", "?")] = by_activity.get(e.get("Activity", "?"), 0) + 1
        by_user[e.get("UserId", "?")] = by_user.get(e.get("UserId", "?"), 0) + 1
        name = e.get("ReportName") or e.get("DatasetName") or e.get("ItemName") or ""
        if name:
            by_artifact[name] = by_artifact.get(name, 0) + 1

    def _top(d: dict[str, int]) -> list[dict]:
        return [
            {"name": k, "events": v}
            for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:top]
        ]

    result = {
        "days": days,
        "total_events": len(events),
        "by_activity": _top(by_activity),
        "top_users": _top(by_user),
        "top_artifacts": _top(by_artifact),
    }
    if ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml")):
        output_json_or_table(result, ctx)
        return
    console.print(f"[bold]{len(events)} events over {days} day(s)[/bold]\n")
    output_json_or_table(result["by_activity"], ctx, title="Activity Types")
    output_json_or_table(result["top_users"], ctx, title="Top Users")
    output_json_or_table(result["top_artifacts"], ctx, title="Top Reports / Datasets")


@tenant_cmd.command("access")
@click.option("--workspace", "workspace_id", default=None,
              help="Limit to one workspace id (default: all workspaces, admin API).")
@click.option("--external-only", is_flag=True, help="Show only external (guest) users.")
@click.pass_context
def tenant_access(ctx: click.Context, workspace_id: str | None, external_only: bool) -> None:
    """Access review: who has which role in which workspace (export for audits)."""
    token = fabric_api.get_token()
    base = fabric_api.POWERBI_API_BASE

    rows: list[dict] = []
    if workspace_id:
        users = fabric_api.get(f"{base}/groups/{workspace_id}/users", token).get("value", [])
        for u in users:
            rows.append({
                "workspace": workspace_id,
                "user": u.get("emailAddress") or u.get("identifier", ""),
                "role": u.get("groupUserAccessRight", ""),
                "principalType": u.get("principalType", ""),
            })
    else:
        groups = fabric_api.get(
            f"{base}/admin/groups?$top=500&$expand=users", token
        ).get("value", [])
        for g in groups:
            for u in g.get("users", []):
                rows.append({
                    "workspace": g.get("name", g.get("id", "")),
                    "user": u.get("emailAddress") or u.get("identifier", ""),
                    "role": u.get("groupUserAccessRight", ""),
                    "principalType": u.get("principalType", ""),
                })

    if external_only:
        rows = [r for r in rows if "#EXT#" in r["user"] or r["principalType"] == "Guest"]
    output_json_or_table(rows, ctx, title="Workspace Access")
    if not (ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml"))):
        console.print(f"\n[bold]{len(rows)} access entries[/bold]")


@tenant_cmd.group("labels")
def tenant_labels() -> None:
    """Sensitivity (MIP) labels on datasets and reports."""


@tenant_labels.command("set")
@click.option("--label-id", required=True, help="Sensitivity label GUID (from the MIP portal).")
@click.option("--dataset", "datasets", multiple=True, help="Dataset id (repeatable).")
@click.option("--report", "reports", multiple=True, help="Report id (repeatable).")
@click.pass_context
def labels_set(
    ctx: click.Context, label_id: str, datasets: tuple[str, ...], reports: tuple[str, ...]
) -> None:
    """Apply a sensitivity label to datasets/reports (admin information-protection API)."""
    if not datasets and not reports:
        raise click.ClickException("Pass at least one --dataset or --report id.")
    token = fabric_api.get_token()
    payload: dict = {"informationProtectionChangeLabelDetails": {
        "newLabelId": label_id,
        "delegatedUser": None,
    }}
    if datasets:
        payload["dashboards"] = None
        payload["datasets"] = [{"id": d} for d in datasets]
    if reports:
        payload["reports"] = [{"id": r} for r in reports]
    result = fabric_api.post(
        f"{fabric_api.POWERBI_API_BASE}/admin/informationprotection/setLabels",
        token, payload=payload,
    )
    output_json_or_table(result, ctx, title="Set Labels")


@tenant_labels.command("remove")
@click.option("--dataset", "datasets", multiple=True, help="Dataset id (repeatable).")
@click.option("--report", "reports", multiple=True, help="Report id (repeatable).")
@click.pass_context
def labels_remove(ctx: click.Context, datasets: tuple[str, ...], reports: tuple[str, ...]) -> None:
    """Remove sensitivity labels from datasets/reports."""
    if not datasets and not reports:
        raise click.ClickException("Pass at least one --dataset or --report id.")
    token = fabric_api.get_token()
    payload: dict = {}
    if datasets:
        payload["datasets"] = [{"id": d} for d in datasets]
    if reports:
        payload["reports"] = [{"id": r} for r in reports]
    result = fabric_api.post(
        f"{fabric_api.POWERBI_API_BASE}/admin/informationprotection/removeLabels",
        token, payload=payload,
    )
    output_json_or_table(result, ctx, title="Remove Labels")


@tenant_cmd.command("stale")
@click.option("--days", default=90, show_default=True,
              help="Flag datasets not refreshed within this many days.")
@click.pass_context
def tenant_stale(ctx: click.Context, days: int) -> None:
    """Find stale datasets across the tenant (no successful refresh in N days)."""
    token = fabric_api.get_token()
    base = fabric_api.POWERBI_API_BASE
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    datasets = fabric_api.get(f"{base}/admin/datasets?$top=500", token).get("value", [])
    stale: list[dict] = []
    for ds in datasets:
        if not ds.get("isRefreshable"):
            continue
        # contentLastRefreshTime is hydrated by the admin datasets endpoint
        last = ds.get("contentLastRefreshTime") or ""
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
        except ValueError:
            last_dt = None
        if last_dt is None or last_dt < cutoff:
            stale.append({
                "dataset": ds.get("name", ""),
                "id": ds.get("id", ""),
                "workspaceId": ds.get("workspaceId", ""),
                "lastRefresh": last or "never",
            })
    output_json_or_table(stale, ctx, title=f"Datasets stale > {days} days")
    if not (ctx.obj and (ctx.obj.get("output_json") or ctx.obj.get("output_yaml"))):
        console.print(f"\n[bold]{len(stale)} stale dataset(s) of {len(datasets)}[/bold]")
