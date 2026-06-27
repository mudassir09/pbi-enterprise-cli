"""Shared Microsoft Fabric / Power BI REST API client.

Used by the `rest` backend, `pbi fabric`, `pbi govern scan`, `pbi ops`, and
`pbi audit usage`. Auth resolution order: explicit token argument,
PBI_REST_BEARER / FABRIC_TOKEN env vars, service principal (PBI_CLIENT_SECRET +
AZURE_TENANT_ID + AZURE_CLIENT_ID), then MSAL device flow.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"
ONELAKE_DFS_BASE = "https://onelake.dfs.fabric.microsoft.com"

_POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
# Azure CLI public client id — same default the device flow in fabric_cmd uses
_DEFAULT_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


class FabricApiError(RuntimeError):
    """Raised for non-2xx REST responses."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"API error {status}: {message}")
        self.status = status
        self.message = message


def get_token(scope: str = _POWERBI_SCOPE, interactive: bool = True) -> str:
    """Acquire a bearer token for the Fabric / Power BI REST API."""
    token = os.environ.get("PBI_REST_BEARER") or os.environ.get("FABRIC_TOKEN")
    if token:
        return token

    tenant = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("PBI_CLIENT_SECRET")

    try:
        import msal  # type: ignore[import-untyped]
    except ImportError:
        raise FabricApiError(
            0,
            "No token found. Set PBI_REST_BEARER, or install the [xmla] extra "
            "for MSAL auth: pip install 'pbi-enterprise-cli[xmla]'",
        )

    if tenant and client_id and client_secret:
        app = msal.ConfidentialClientApplication(
            client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant}",
        )
        result = app.acquire_token_for_client(scopes=[scope])
        if "access_token" in result:
            return result["access_token"]
        raise FabricApiError(0, f"Service principal auth failed: {result.get('error_description')}")

    if not interactive:
        raise FabricApiError(0, "No token found and interactive auth disabled.")

    app = msal.PublicClientApplication(
        client_id or _DEFAULT_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{tenant or 'common'}",
    )
    flow = app.initiate_device_flow(scopes=[scope])
    print(f"\n{flow['message']}\n")
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        return result["access_token"]
    raise FabricApiError(0, f"Device flow failed: {result.get('error_description')}")


def request(
    method: str,
    url: str,
    token: str,
    payload: dict | list | None = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 60,
) -> Any:
    """Perform an authenticated REST call. Returns parsed JSON (or raw bytes)."""
    body = data if data is not None else (
        json.dumps(payload).encode() if payload is not None else None
    )
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
            envelope = {"status": resp.status, "headers": dict(resp.headers)}
            # A 202 starts a long-running operation: Fabric returns an empty or
            # literal-`null` body with the operation URL in the Location header.
            # Always hand back the envelope (status + headers) so poll_lro can find
            # the Location — otherwise json.loads("null") returns None and the
            # status/headers are silently lost (breaks every LRO).
            if resp.status == 202 or not raw:
                return envelope
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type or raw[:1] in (b"{", b"["):
                parsed = json.loads(raw.decode())
                return parsed if parsed is not None else envelope
            return raw
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise FabricApiError(exc.code, detail[:500])


def get(url: str, token: str, **kw: Any) -> Any:
    return request("GET", url, token, **kw)


def post(url: str, token: str, payload: dict | list | None = None, **kw: Any) -> Any:
    return request("POST", url, token, payload=payload, **kw)


def patch(url: str, token: str, payload: dict | list | None = None, **kw: Any) -> Any:
    return request("PATCH", url, token, payload=payload, **kw)


def put(url: str, token: str, payload: dict | list | None = None, **kw: Any) -> Any:
    return request("PUT", url, token, payload=payload, **kw)


def delete(url: str, token: str, **kw: Any) -> Any:
    return request("DELETE", url, token, **kw)


def poll_lro(response: Any, token: str, timeout: int = 300) -> Any:
    """Poll a Fabric long-running operation (202 + Location header) to completion.

    On success, result-bearing operations (e.g. ``getDefinition``) expose their
    payload at ``{operation}/result``; status-only operations (e.g.
    ``updateDefinition``) have no such sub-resource. We fetch ``/result`` when it
    carries real content and otherwise return the operation-status object — so a
    caller of ``getDefinition`` gets ``{"definition": ...}`` while ``push``/update
    still gets a status summary.
    """
    import time

    if not isinstance(response, dict) or response.get("status") != 202:
        return response  # synchronous completion
    headers = response.get("headers") or {}
    location = headers.get("Location") or headers.get("location")
    if not location:
        return response
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        op = get(location, token)
        state = op.get("status") or op.get("state")
        if state in ("Succeeded", "Completed"):
            try:
                result = get(location.rstrip("/") + "/result", token)
            except FabricApiError:
                result = None
            # Return /result only when it has real content beyond the bare
            # {status, headers} envelope; otherwise the status object is the result.
            if isinstance(result, dict) and set(result) - {"status", "headers"}:
                return result
            return op
        if state in ("Failed", "Cancelled"):
            raise FabricApiError(0, f"Operation failed: {json.dumps(op)[:300]}")
        time.sleep(2)
    raise FabricApiError(0, f"Operation did not complete within {timeout}s.")


def get_paged(url: str, token: str, value_key: str = "value") -> list[dict[str, Any]]:
    """GET with continuation-token paging (Fabric list endpoints)."""
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        page = get(next_url, token)
        items.extend(page.get(value_key, []))
        next_url = page.get("continuationUri")
    return items


def encode_parts(folder: Any) -> list[dict[str, Any]]:
    """Encode every file under *folder* as InlineBase64 item-definition parts.

    Unlike the older command-level helper this keeps dotfiles (notably the
    required ``.platform``) so a getDefinition → edit → updateDefinition round
    trip stays faithful.
    """
    import base64
    from pathlib import Path

    folder = Path(folder)
    parts: list[dict[str, Any]] = []
    for f in sorted(folder.rglob("*")):
        if f.is_file():
            parts.append({
                "path": f.relative_to(folder).as_posix(),
                "payload": base64.b64encode(f.read_bytes()).decode(),
                "payloadType": "InlineBase64",
            })
    return parts


def decode_parts(parts: list[dict[str, Any]], folder: Any) -> list[str]:
    """Write item-definition parts under *folder*, recreating the path tree."""
    import base64
    from pathlib import Path

    folder = Path(folder)
    written: list[str] = []
    for part in parts:
        target = folder / part["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(part["payload"]))
        written.append(part["path"])
    return written


# Terminal states for a Fabric job instance.
_JOB_TERMINAL = {"Completed", "Succeeded", "Failed", "Cancelled", "Deduped"}


def run_item_job(
    workspace_id: str,
    item_id: str,
    job_type: str,
    token: str,
    execution_data: dict | None = None,
    wait: bool = False,
    timeout: int = 600,
) -> dict[str, Any]:
    """Start an on-demand item job; optionally poll the instance to completion.

    Returns the job-instance dict. The job-creation call answers 202 with a
    ``Location`` header pointing at the instance; we surface its id (and poll it
    when ``wait`` is set) so callers get a real status rather than a bare 202.
    """
    import time

    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}"
        f"/jobs/instances?jobType={job_type}"
    )
    payload = {"executionData": execution_data} if execution_data else {}
    resp = post(url, token, payload=payload)

    # A 202 wrapper carries the instance URL in its Location header; anything else
    # is a synchronous result we just hand back.
    location = None
    if isinstance(resp, dict):
        if resp.get("status") == 202:
            location = (resp.get("headers") or {}).get("Location")
        else:
            return resp
    if not location:
        return {"status": "Accepted"}
    job_id = location.rstrip("/").rsplit("/", 1)[-1]

    if not wait:
        return {"jobInstanceId": job_id, "status": "NotStarted", "location": location}

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance = get(location, token)
        if instance.get("status") in _JOB_TERMINAL:
            if instance.get("status") in ("Failed", "Cancelled"):
                reason = (instance.get("failureReason") or {}).get("message", "")
                raise FabricApiError(0, f"Job {instance.get('status')}: {reason}"[:300])
            return instance
        time.sleep(3)
    raise FabricApiError(0, f"Job {job_id} did not complete within {timeout}s.")
