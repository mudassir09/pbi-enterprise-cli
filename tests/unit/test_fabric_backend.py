"""Tests for the FabricDefinitionBackend (live model writes via Item Definition API)."""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli

MODEL_TMDL = "model Model\n\tculture: en-US\n"
SALES_TMDL = (
    "table Sales\n"
    "\n"
    "\tcolumn Amount\n"
    "\t\tdataType: double\n"
    "\n"
    "\tmeasure Revenue = SUM(Sales[Amount])\n"
    "\t\tformatString: 0.00\n"
)


def _part(path: str, text: str) -> dict:
    return {
        "path": path,
        "payload": base64.b64encode(text.encode()).decode(),
        "payloadType": "InlineBase64",
    }


def _definition() -> dict:
    return {"definition": {"parts": [
        _part("definition/model.tmdl", MODEL_TMDL),
        _part("definition/tables/Sales.tmdl", SALES_TMDL),
        _part(".platform", '{"metadata": {"type": "SemanticModel"}}'),
    ]}}


def _mock_rest(push_result: dict | None = None):
    """Patch fabric_api so getDefinition returns our TMDL and updateDefinition is captured."""
    token = patch("pbi_cli.fabric_api.get_token", return_value="tok")
    post = patch("pbi_cli.fabric_api.post", return_value={"status": 202, "headers": {}})

    def _poll(resp, tok, **kw):
        # First call (download) gets the definition; later calls (push) succeed.
        _poll.calls += 1
        return _definition() if _poll.calls == 1 else (push_result or {"status": "Succeeded"})

    _poll.calls = 0
    poll = patch("pbi_cli.fabric_api.poll_lro", side_effect=_poll)
    return token, post, poll


def _make_backend():
    from pbi_cli.backends.fabric_backend import FabricDefinitionBackend

    return FabricDefinitionBackend("ws-1", "ds-1")


class TestDownloadAndRead:
    def test_reads_measures_from_downloaded_tmdl(self):
        token, post, poll = _mock_rest()
        with token, post, poll:
            b = _make_backend()
            measures = b.measure_list()
            b.disconnect()
        assert any(m["name"] == "Revenue" for m in measures)

    def test_no_parts_raises_connection_error(self):
        with patch("pbi_cli.fabric_api.get_token", return_value="tok"), \
                patch("pbi_cli.fabric_api.post", return_value={}), \
                patch("pbi_cli.fabric_api.poll_lro", return_value={"definition": {"parts": []}}):
            with pytest.raises(ConnectionError, match="no TMDL definition"):
                _make_backend()


class TestWritesPushDefinition:
    def _pushed_parts(self, post_mock):
        for call in post_mock.call_args_list:
            url = call.args[0]
            if "updateDefinition" in url:
                return call.kwargs["payload"]["definition"]["parts"]
        return None

    def test_measure_add_pushes_updated_definition(self):
        token, post, poll = _mock_rest()
        with token, post as post_mock, poll:
            b = _make_backend()
            b.measure_add("Sales", "Margin", "DIVIDE([Revenue], 100)")
            parts = self._pushed_parts(post_mock)
            b.disconnect()
        assert parts is not None, "updateDefinition was not called"
        sales = next(p for p in parts if p["path"].endswith("tables/Sales.tmdl"))
        decoded = base64.b64decode(sales["payload"]).decode()
        assert "Margin" in decoded
        # .platform round-trips (not dropped as a dotfile)
        assert any(p["path"] == ".platform" for p in parts)

    def test_measure_delete_pushes(self):
        token, post, poll = _mock_rest()
        with token, post as post_mock, poll:
            b = _make_backend()
            b.measure_delete("Sales", "Revenue")
            urls = [c.args[0] for c in post_mock.call_args_list]
            b.disconnect()
        assert any("updateDefinition" in u for u in urls)


class TestDisconnectCleansUp:
    def test_disconnect_removes_tmpdir(self):
        token, post, poll = _mock_rest()
        with token, post, poll:
            b = _make_backend()
            tmp = b._tmpdir
            assert tmp.exists()
            b.disconnect()
        assert not tmp.exists()


class TestCliWiring:
    def test_missing_ids_errors(self):
        result = CliRunner().invoke(cli, ["--backend", "fabric", "measure", "list"])
        assert result.exit_code != 0
        assert "needs a workspace" in result.output

    def test_measure_list_through_cli(self):
        token, post, poll = _mock_rest()
        with token, post, poll:
            result = CliRunner().invoke(
                cli, ["--backend", "fabric", "--workspace", "ws", "--dataset", "ds",
                      "measure", "list"])
        assert result.exit_code == 0
        assert "Revenue" in result.output
