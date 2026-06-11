"""Governance violation exporters: SARIF 2.1.0 and GitHub-flavoured markdown.

SARIF output plugs into GitHub code scanning (`upload-sarif` action) so
violations annotate PRs natively. The markdown rendering powers
`govern check --comment-pr`.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from pbi_cli import __version__

_SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


def to_sarif(violations: list[dict[str, Any]], tool_name: str = "pbi-enterprise-cli") -> dict:
    """Render violations as a SARIF 2.1.0 log."""
    rules_seen: dict[str, dict] = {}
    results = []
    for v in violations:
        rule_id = v.get("rule", "unknown")
        rules_seen.setdefault(rule_id, {
            "id": rule_id,
            "shortDescription": {"text": rule_id},
            "defaultConfiguration": {"level": _SARIF_LEVEL.get(v.get("severity", "warning"), "warning")},  # noqa: E501
        })
        results.append({
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(v.get("severity", "warning"), "warning"),
            "message": {"text": v.get("message", "")},
            "locations": [{
                "logicalLocations": [{
                    "fullyQualifiedName": v.get("object", ""),
                    "kind": "member",
                }]
            }],
        })
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": tool_name,
                    "informationUri": "https://github.com/mudassir09/pbi-enterprise-cli",
                    "version": __version__,
                    "rules": list(rules_seen.values()),
                }
            },
            "results": results,
        }],
    }


def to_markdown(violations: list[dict[str, Any]], title: str = "Power BI Governance") -> str:
    """Render violations as a PR-comment-ready markdown summary."""
    errors = [v for v in violations if v.get("severity") == "error"]
    warnings = [v for v in violations if v.get("severity") == "warning"]
    infos = [v for v in violations if v.get("severity") == "info"]

    lines = [f"## {title}", ""]
    if not violations:
        lines.append("✅ **All governance checks pass.**")
        return "\n".join(lines)

    lines.append(
        f"❌ **{len(errors)} errors** · ⚠️ {len(warnings)} warnings · ℹ️ {len(infos)} info"
        if errors
        else f"⚠️ **{len(warnings)} warnings** · ℹ️ {len(infos)} info"
    )
    lines += ["", "| Severity | Rule | Object | Message |", "|---|---|---|---|"]
    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    for v in sorted(violations, key=lambda x: ("error", "warning", "info").index(
            x.get("severity", "info"))):
        lines.append(
            f"| {icon.get(v.get('severity', 'info'), '')} {v.get('severity', '')} "
            f"| `{v.get('rule', '')}` | {v.get('object', '')} | {v.get('message', '')} |"
        )
    fixable = sum(1 for v in violations if v.get("autoFixable"))
    if fixable:
        lines += ["", f"🔧 {fixable} violation(s) are auto-fixable: run `pbi govern fix --auto`."]
    lines += ["", f"<sub>pbi-enterprise-cli v{__version__}</sub>"]
    return "\n".join(lines)


def _detect_pr_number() -> int | None:
    """Resolve the PR number from GitHub Actions environment."""
    ref = os.environ.get("GITHUB_REF", "")  # refs/pull/123/merge
    parts = ref.split("/")
    if len(parts) >= 3 and parts[1] == "pull" and parts[2].isdigit():
        return int(parts[2])
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        with open(event_path, encoding="utf-8") as f:
            event = json.load(f)
        number = event.get("pull_request", {}).get("number") or event.get("number")
        if number:
            return int(number)
    return None


def post_pr_comment(markdown: str) -> dict[str, Any]:
    """Post a comment on the current PR using GITHUB_TOKEN (GitHub Actions)."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        raise RuntimeError(
            "GITHUB_TOKEN and GITHUB_REPOSITORY must be set (run inside GitHub Actions, "
            "with `permissions: pull-requests: write`)."
        )
    pr = _detect_pr_number()
    if not pr:
        raise RuntimeError("Could not determine the PR number from GITHUB_REF/GITHUB_EVENT_PATH.")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        data=json.dumps({"body": markdown}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode())
