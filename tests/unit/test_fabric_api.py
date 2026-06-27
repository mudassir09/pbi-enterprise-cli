"""Contract tests for the shared Fabric/Power BI REST client (fabric_api).

These cover the response-shape handling that live commands depend on — paging,
long-running-operation polling, error mapping, and auth resolution — without a
network. This is the plumbing every `pbi fabric`/`pbi tenant`/`pbi ops` command
rides on, so a drift here breaks many commands at once.
"""

from __future__ import annotations

import io
import urllib.error
from unittest.mock import patch

import pytest

from pbi_cli import fabric_api as fa


class _FakeResp:
    """Minimal context-manager stand-in for urllib's response object."""

    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body = body
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self.length = len(body)

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestRequest:
    def test_parses_json_response(self):
        with patch("urllib.request.urlopen", return_value=_FakeResp(b'{"a": 1}')):
            assert fa.get("https://x", "tok") == {"a": 1}

    def test_empty_body_returns_status_and_headers(self):
        with patch("urllib.request.urlopen", return_value=_FakeResp(b"", status=200)):
            out = fa.request("POST", "https://x", "tok", payload={"k": "v"})
        assert out["status"] == 200
        assert "headers" in out

    def test_202_null_body_keeps_status_and_location(self):
        # Regression: a Fabric LRO returns 202 with the JSON literal `null` and the
        # operation URL in Location. json.loads("null") is None, which previously
        # discarded the status + headers and broke every LRO (pull/push, fabric backend).
        resp = _FakeResp(
            b"null", status=202,
            headers={"Content-Type": "application/json", "Location": "https://op/1"},
        )
        with patch("urllib.request.urlopen", return_value=resp):
            out = fa.request("POST", "https://x", "tok", payload={})
        assert out is not None
        assert out["status"] == 202
        assert out["headers"]["Location"] == "https://op/1"

    def test_null_json_body_non_202_returns_envelope_not_none(self):
        with patch("urllib.request.urlopen", return_value=_FakeResp(b"null", status=200)):
            out = fa.request("GET", "https://x", "tok")
        assert out is not None
        assert out["status"] == 200

    def test_http_error_maps_to_fabric_api_error(self):
        err = urllib.error.HTTPError(
            "https://x", 403, "Forbidden", {}, io.BytesIO(b'{"error":"denied"}')
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(fa.FabricApiError) as exc:
                fa.get("https://x", "tok")
        assert exc.value.status == 403
        assert "denied" in exc.value.message


class TestGetPaged:
    def test_single_page(self):
        with patch.object(fa, "get", return_value={"value": [{"id": 1}, {"id": 2}]}):
            items = fa.get_paged("https://x", "tok")
        assert [i["id"] for i in items] == [1, 2]

    def test_follows_continuation_uri(self):
        pages = [
            {"value": [{"id": 1}], "continuationUri": "https://x?page=2"},
            {"value": [{"id": 2}], "continuationUri": "https://x?page=3"},
            {"value": [{"id": 3}]},
        ]
        with patch.object(fa, "get", side_effect=pages):
            items = fa.get_paged("https://x", "tok")
        assert [i["id"] for i in items] == [1, 2, 3]


class TestPollLro:
    def test_synchronous_response_passes_through(self):
        assert fa.poll_lro({"id": "done"}, "tok") == {"id": "done"}

    def test_polls_until_succeeded(self):
        accepted = {"status": 202, "headers": {"Location": "https://op/1"}}
        with patch.object(fa, "get", side_effect=[
            {"status": "Running"},
            {"status": "Succeeded", "id": "x"},
            fa.FabricApiError(404, "no result"),  # status-only op has no /result
        ]), patch("time.sleep", return_value=None):
            out = fa.poll_lro(accepted, "tok")
        assert out["status"] == "Succeeded"

    def test_succeeded_fetches_result_subresource(self):
        # getDefinition's payload lives at {operation}/result, not in the status.
        accepted = {"status": 202, "headers": {"Location": "https://op/1"}}
        with patch.object(fa, "get", side_effect=[
            {"status": "Succeeded"},
            {"definition": {"parts": [{"path": "definition.pbir"}]}},  # /result
        ]), patch("time.sleep", return_value=None):
            out = fa.poll_lro(accepted, "tok")
        assert out["definition"]["parts"] == [{"path": "definition.pbir"}]

    def test_succeeded_result_envelope_falls_back_to_status(self):
        # An empty /result (bare status/headers envelope) → return the op status.
        accepted = {"status": 202, "headers": {"Location": "https://op/1"}}
        with patch.object(fa, "get", side_effect=[
            {"status": "Succeeded", "id": "x"},
            {"status": 200, "headers": {}},  # /result with no real content
        ]), patch("time.sleep", return_value=None):
            out = fa.poll_lro(accepted, "tok")
        assert out["id"] == "x"

    def test_failed_operation_raises(self):
        accepted = {"status": 202, "headers": {"Location": "https://op/1"}}
        with patch.object(fa, "get", return_value={"status": "Failed"}), \
                patch("time.sleep", return_value=None):
            with pytest.raises(fa.FabricApiError, match="Operation failed"):
                fa.poll_lro(accepted, "tok")

    def test_202_without_location_returns_as_is(self):
        accepted = {"status": 202, "headers": {}}
        assert fa.poll_lro(accepted, "tok") == accepted


class TestRunItemJob:
    _LOC = "https://api.fabric.microsoft.com/v1/workspaces/ws/items/it/jobs/instances/job-99"

    def test_no_wait_returns_instance_id(self):
        accepted = {"status": 202, "headers": {"Location": self._LOC}}
        with patch.object(fa, "post", return_value=accepted):
            out = fa.run_item_job("ws", "it", "RunNotebook", "tok")
        assert out["jobInstanceId"] == "job-99"
        assert out["status"] == "NotStarted"

    def test_no_location_returns_accepted(self):
        with patch.object(fa, "post", return_value={"status": 202, "headers": {}}):
            out = fa.run_item_job("ws", "it", "RunNotebook", "tok")
        assert out["status"] == "Accepted"

    def test_wait_polls_to_completion(self):
        accepted = {"status": 202, "headers": {"Location": self._LOC}}
        with patch.object(fa, "post", return_value=accepted), \
                patch.object(fa, "get", side_effect=[
                    {"status": "InProgress"}, {"status": "Completed", "id": "job-99"}]), \
                patch("time.sleep", return_value=None):
            out = fa.run_item_job("ws", "it", "RunNotebook", "tok", wait=True)
        assert out["status"] == "Completed"

    def test_wait_failed_raises(self):
        accepted = {"status": 202, "headers": {"Location": self._LOC}}
        with patch.object(fa, "post", return_value=accepted), \
                patch.object(fa, "get", return_value={
                    "status": "Failed", "failureReason": {"message": "boom"}}), \
                patch("time.sleep", return_value=None):
            with pytest.raises(fa.FabricApiError, match="boom"):
                fa.run_item_job("ws", "it", "RunNotebook", "tok", wait=True)

    def test_execution_data_is_posted(self):
        accepted = {"status": 202, "headers": {"Location": self._LOC}}
        with patch.object(fa, "post", return_value=accepted) as mock_post:
            fa.run_item_job("ws", "it", "TableMaintenance", "tok",
                            execution_data={"tableName": "Sales"})
        assert mock_post.call_args.kwargs["payload"] == {
            "executionData": {"tableName": "Sales"}}


class TestGetToken:
    def test_env_bearer_short_circuits(self, monkeypatch):
        monkeypatch.setenv("PBI_REST_BEARER", "env-token")
        assert fa.get_token() == "env-token"

    def test_fabric_token_env_fallback(self, monkeypatch):
        monkeypatch.delenv("PBI_REST_BEARER", raising=False)
        monkeypatch.setenv("FABRIC_TOKEN", "fab-token")
        assert fa.get_token() == "fab-token"
