"""Unit tests for pbi fabric report commands.

Tests use Click's CliRunner with mocked _fab.* calls to verify the CLI
behaviour without hitting real Fabric REST endpoints.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from pbi_cli.commands.fabric_cmd import fabric_cmd
from pbi_cli.fabric_api import FabricApiError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKSPACE_ID = "11111111-0000-0000-0000-000000000000"
_REPORT_ID = "22222222-0000-0000-0000-000000000000"
_DATASET_ID = "33333333-0000-0000-0000-000000000000"
_REPORT_NAME = "Sales Dashboard"

_REPORT_META = {
    "id": _REPORT_ID,
    "displayName": _REPORT_NAME,
    "datasetId": _DATASET_ID,
    "description": "",
}

# Mirrors real PBIR GA visual.json — table refs live in SourceRef.Entity inside
# projection queries, NOT in a top-level From clause.
_VISUAL_JSON = {
    "$schema": "https://...",
    "name": "abc123",
    "position": {"x": 0, "y": 0, "width": 200, "height": 200},
    "visual": {
        "visualType": "barChart",
        "query": {
            "queryState": {
                "Category": {
                    "projections": [
                        {
                            "field": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "Sales"}},
                                    "Property": "Month",
                                }
                            }
                        }
                    ]
                }
            }
        },
    },
}


def _make_pbir_folder(tmp_path: Path) -> Path:
    """Create a minimal PBIR folder structure for push/pull tests."""
    report_dir = tmp_path / "Sales.Report"
    pages_dir = report_dir / "definition" / "pages" / "Page1"
    visuals_dir = pages_dir / "visuals" / "abc123.visual"
    visuals_dir.mkdir(parents=True)
    (report_dir / "definition").mkdir(exist_ok=True)
    (report_dir / "definition" / "report.json").write_text(
        json.dumps({"id": _REPORT_ID}), encoding="utf-8"
    )
    (pages_dir / "page.json").write_text(
        json.dumps({"name": "Page1", "displayName": "Page 1"}), encoding="utf-8"
    )
    (visuals_dir / "visual.json").write_text(
        json.dumps(_VISUAL_JSON), encoding="utf-8"
    )
    return report_dir


def _add_bypath_pbir(report_dir: Path) -> None:
    """Add a definition.pbir with a local byPath model reference (as a .pbip would)."""
    (report_dir / "definition.pbir").write_text(
        json.dumps({
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}},
        }),
        encoding="utf-8",
    )


def _pushed_parts(post_mock) -> list[dict] | None:
    """Extract the definition parts from the create/update POST payload."""
    for call in post_mock.call_args_list:
        url = call.args[0]
        if "updateDefinition" in url or url.endswith("/reports"):
            return call.kwargs["payload"]["definition"]["parts"]
    return None


def _decode_part(parts: list[dict], suffix: str) -> dict:
    part = next(p for p in parts if p["path"].endswith(suffix))
    return json.loads(base64.b64decode(part["payload"]))


# ---------------------------------------------------------------------------
# report list
# ---------------------------------------------------------------------------

def test_list_reports() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        result = runner.invoke(
            fabric_cmd,
            ["report", "list", "--workspace", _WORKSPACE_ID],
        )
    assert result.exit_code == 0, result.output
    assert _REPORT_NAME in result.output
    mock_fab.get_paged.assert_called_once()


def test_list_reports_json() -> None:
    # --json lives on the top-level 'pbi' group; test via the full CLI entry point
    from pbi_cli.cli import cli

    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        result = runner.invoke(
            cli,
            ["--json", "fabric", "report", "list", "--workspace", _WORKSPACE_ID],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["id"] == _REPORT_ID


# ---------------------------------------------------------------------------
# report get
# ---------------------------------------------------------------------------

def test_get_report_by_name() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]  # for name resolution
        mock_fab.get.return_value = _REPORT_META
        result = runner.invoke(
            fabric_cmd,
            ["report", "get", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME],
        )
    assert result.exit_code == 0, result.output
    assert _REPORT_ID in result.output


def test_get_report_not_found() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = []
        result = runner.invoke(
            fabric_cmd,
            ["report", "get", "--workspace", _WORKSPACE_ID, "--report", "Nonexistent"],
        )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# report pull
# ---------------------------------------------------------------------------

def test_pull_report(tmp_path: Path) -> None:
    """pull: getDefinition LRO + decode parts to local folder."""
    import base64
    encoded_part = base64.b64encode(b'{"test":1}').decode()
    parts = [{
        "path": "definition/report.json",
        "payload": encoded_part,
        "payloadType": "InlineBase64",
    }]
    lro_result = {"definition": {"parts": parts}}

    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.post.return_value = {"operationId": "op1"}
        mock_fab.poll_lro.return_value = lro_result
        result = runner.invoke(
            fabric_cmd,
            [
                "report", "pull",
                "--workspace", _WORKSPACE_ID,
                "--report", _REPORT_NAME,
                "--output", str(tmp_path / "out"),
            ],
        )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "definition" / "report.json").exists()
    mock_fab.poll_lro.assert_called_once()


def test_pull_report_rejects_legacy(tmp_path: Path) -> None:
    """pull: empty parts = PBIR-Legacy → clear error."""
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.post.return_value = {}
        mock_fab.poll_lro.return_value = {"definition": {"parts": []}}
        result = runner.invoke(
            fabric_cmd,
            ["report", "pull", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--output", str(tmp_path / "out")],
        )
    assert result.exit_code != 0
    assert "PBIR-Legacy" in result.output


# ---------------------------------------------------------------------------
# report push
# ---------------------------------------------------------------------------

def test_push_creates_new_report(tmp_path: Path) -> None:
    """push: report doesn't exist → POST create."""
    folder = _make_pbir_folder(tmp_path)
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        # _resolve_report raises ClickException (not found) → create path
        mock_fab.get_paged.return_value = []
        mock_fab.post.return_value = {"operationId": "op1"}
        mock_fab.poll_lro.return_value = {"id": _REPORT_ID, "displayName": _REPORT_NAME}
        result = runner.invoke(
            fabric_cmd,
            [
                "report", "push",
                "--workspace", _WORKSPACE_ID,
                "--report", _REPORT_NAME,
                "--definition", str(folder),
                "--dataset-id", _DATASET_ID,
            ],
        )
    assert result.exit_code == 0, result.output
    # Should have called POST on /reports (create), not /updateDefinition
    call_url = mock_fab.post.call_args[0][0]
    assert "/reports" in call_url
    assert "updateDefinition" not in call_url


def test_push_updates_existing_report(tmp_path: Path) -> None:
    """push: report already exists → POST updateDefinition."""
    folder = _make_pbir_folder(tmp_path)
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]  # report found → update
        mock_fab.post.return_value = {"operationId": "op2"}
        mock_fab.poll_lro.return_value = {"status": "Succeeded"}
        result = runner.invoke(
            fabric_cmd,
            [
                "report", "push",
                "--workspace", _WORKSPACE_ID,
                "--report", _REPORT_NAME,
                "--definition", str(folder),
            ],
        )
    assert result.exit_code == 0, result.output
    call_url = mock_fab.post.call_args[0][0]
    assert "updateDefinition" in call_url


def test_push_requires_dataset_id_for_new(tmp_path: Path) -> None:
    """push: creating a new report without --dataset-id → error."""
    folder = _make_pbir_folder(tmp_path)
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = []  # not found → would create
        result = CliRunner().invoke(
            fabric_cmd,
            [
                "report", "push",
                "--workspace", _WORKSPACE_ID,
                "--report", "New Report",
                "--definition", str(folder),
                # no --dataset-id
            ],
        )
    assert result.exit_code != 0
    assert "dataset-id" in result.output.lower()


# ---------------------------------------------------------------------------
# push --bind-verify
# ---------------------------------------------------------------------------

def _inv(tables, columns=(), measures=()) -> dict:
    """A model-inventory dict as returned by _model_inventory."""
    return {"tables": set(tables), "columns": set(columns), "measures": set(measures)}


_INV_PATH = "pbi_cli.commands.fabric_cmd._model_inventory"


def test_push_bind_verify_passes(tmp_path: Path) -> None:
    """bind-verify: table 'Sales' + column [Month] exist in model → proceed."""
    folder = _make_pbir_folder(tmp_path)  # references Sales[Month]
    inv = _inv(["Sales", "Calendar"], [("Sales", "Month"), ("Sales", "Amount")])
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab, \
            patch(_INV_PATH, return_value=inv):
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.get.return_value = {"displayName": "DP600"}
        mock_fab.post.return_value = {}
        mock_fab.poll_lro.return_value = {"status": "Succeeded"}
        result = CliRunner().invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--dataset-id", _DATASET_ID, "--bind-verify"],
        )
    assert result.exit_code == 0, result.output
    assert "Binding check passed" in result.output


def test_push_bind_verify_fails(tmp_path: Path) -> None:
    """bind-verify: table 'Sales' missing from model → abort with clear error."""
    folder = _make_pbir_folder(tmp_path)
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab, \
            patch(_INV_PATH, return_value=_inv(["SalesFact", "Calendar"])):  # no 'Sales'
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.get.return_value = {"displayName": "DP600"}
        result = CliRunner().invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--dataset-id", _DATASET_ID, "--bind-verify"],
        )
    assert result.exit_code != 0
    assert "Binding check failed" in result.output
    assert "table 'Sales'" in result.output
    mock_fab.poll_lro.assert_not_called()  # not published


def test_push_bind_verify_detects_missing_column(tmp_path: Path) -> None:
    """bind-verify: table exists but referenced column does not → column mismatch."""
    folder = _make_pbir_folder(tmp_path)  # references Sales[Month]
    inv = _inv(["Sales"], [("Sales", "Amount")])  # 'Month' missing
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab, \
            patch(_INV_PATH, return_value=inv):
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.get.return_value = {"displayName": "DP600"}
        result = CliRunner().invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--dataset-id", _DATASET_ID, "--bind-verify"],
        )
    assert result.exit_code != 0
    assert "column Sales[Month]" in result.output
    mock_fab.poll_lro.assert_not_called()


def test_push_bind_verify_fails_closed_on_api_error(tmp_path: Path) -> None:
    """bind-verify: model unreachable → abort (never silently 'pass')."""
    folder = _make_pbir_folder(tmp_path)
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab, \
            patch(_INV_PATH, side_effect=FabricApiError(403, "Forbidden")):
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.get.return_value = {"displayName": "DP600"}
        result = CliRunner().invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--dataset-id", _DATASET_ID, "--bind-verify"],
        )
    assert result.exit_code != 0
    assert "Could not verify bindings" in result.output
    assert "Binding check passed" not in result.output
    mock_fab.poll_lro.assert_not_called()


def test_model_inventory_parses_tmdl(tmp_path: Path) -> None:
    """_model_inventory downloads the model TMDL and reads its schema with FileBackend."""
    from pbi_cli.commands.fabric_cmd import _model_inventory

    def _decode(parts, folder):  # emulate decode_parts writing a tiny TMDL model
        d = Path(folder) / "definition"
        (d / "tables").mkdir(parents=True)
        (d / "model.tmdl").write_text("model M\n\nref table Sales\n", encoding="utf-8")
        (d / "tables" / "Sales.tmdl").write_text(
            "table Sales\n\n\tcolumn Amount\n\t\tdataType: double\n\t\tsourceColumn: Amount\n"
            "\n\tmeasure Revenue = SUM(Sales[Amount])\n",
            encoding="utf-8",
        )

    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.poll_lro.return_value = {"definition": {"parts": [{"path": "x"}]}}
        mock_fab.decode_parts.side_effect = _decode
        inv = _model_inventory(_WORKSPACE_ID, _DATASET_ID, "tok")
    assert "Sales" in inv["tables"]
    assert ("Sales", "Amount") in inv["columns"]
    assert "Revenue" in inv["measures"]


# ---------------------------------------------------------------------------
# push --dataset-id rebind (byPath → byConnection) and --remap
# ---------------------------------------------------------------------------

def test_push_rebinds_bypath_to_byconnection(tmp_path: Path) -> None:
    """--dataset-id rewrites a local byPath model ref to a Fabric byConnection ref."""
    folder = _make_pbir_folder(tmp_path)
    _add_bypath_pbir(folder)
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]  # exists → updateDefinition
        mock_fab.get.return_value = {"displayName": "DP600"}  # ws/model name resolution
        mock_fab.post.return_value = {}
        mock_fab.poll_lro.return_value = {"status": "Succeeded"}
        result = runner.invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--dataset-id", _DATASET_ID],
        )
    assert result.exit_code == 0, result.output
    assert "Rebound report to semantic model" in result.output
    parts = _pushed_parts(mock_fab.post)
    pbir = _decode_part(parts, "definition.pbir")
    # Real Fabric byConnection shape: a connectionString keyed by semanticmodelid.
    conn = pbir["datasetReference"]["byConnection"]["connectionString"]
    assert f"semanticmodelid={_DATASET_ID}" in conn
    assert "byPath" not in pbir["datasetReference"]
    # Local file is NOT mutated (transform happened on a temp copy).
    local = json.loads((folder / "definition.pbir").read_text(encoding="utf-8"))
    assert "byPath" in local["datasetReference"]


def test_rebind_fills_missing_schema(tmp_path: Path) -> None:
    """A byPath definition.pbir lacking $schema gets one (Fabric import requires it)."""
    from pbi_cli.commands.fabric_cmd import _rebind_pbir

    folder = tmp_path / "R.Report"
    folder.mkdir()
    (folder / "definition.pbir").write_text(  # no $schema, as a thin .pbip might
        json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": "../X"}}}),
        encoding="utf-8",
    )
    assert _rebind_pbir(folder, _DATASET_ID, "DP600", "statement bi") is True
    data = json.loads((folder / "definition.pbir").read_text(encoding="utf-8"))
    assert data["$schema"].endswith("definitionProperties/2.0.0/schema.json")
    assert f"semanticmodelid={_DATASET_ID}" in data["datasetReference"]["byConnection"][
        "connectionString"
    ]


def test_push_remap_renames_entity(tmp_path: Path) -> None:
    """--remap rewrites table Entity references in the uploaded visuals."""
    folder = _make_pbir_folder(tmp_path)  # visual references Entity 'Sales'
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.post.return_value = {}
        mock_fab.poll_lro.return_value = {"status": "Succeeded"}
        result = runner.invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--remap", "Sales=SalesV2"],
        )
    assert result.exit_code == 0, result.output
    assert "Remapped 1 table reference" in result.output
    parts = _pushed_parts(mock_fab.post)
    visual = _decode_part(parts, "visual.json")
    assert "SalesV2" in json.dumps(visual)
    # Local file untouched.
    local_visual = json.dumps(json.loads(
        (folder / "definition" / "pages" / "Page1" / "visuals" / "abc123.visual"
         / "visual.json").read_text(encoding="utf-8")
    ))
    assert "SalesV2" not in local_visual


def test_push_bad_remap_format_errors(tmp_path: Path) -> None:
    folder = _make_pbir_folder(tmp_path)
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        result = CliRunner().invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder), "--remap", "NoEqualsSign"],
        )
    assert result.exit_code != 0
    assert "Old=New" in result.output


def test_push_warns_on_bypath_without_dataset_id(tmp_path: Path) -> None:
    """Pushing a local byPath report without --dataset-id warns but still publishes."""
    folder = _make_pbir_folder(tmp_path)
    _add_bypath_pbir(folder)
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.post.return_value = {}
        mock_fab.poll_lro.return_value = {"status": "Succeeded"}
        result = runner.invoke(
            fabric_cmd,
            ["report", "push", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME,
             "--definition", str(folder)],
        )
    assert result.exit_code == 0, result.output
    assert "Warning" in result.output
    assert "byPath" in result.output


# ---------------------------------------------------------------------------
# _verify_bindings — measure-level checks
# ---------------------------------------------------------------------------

def _make_measure_pbir(tmp_path: Path, measure_name: str) -> Path:
    """A minimal PBIR folder whose single visual references one measure."""
    rd = tmp_path / "M.Report"
    vd = rd / "definition" / "pages" / "P" / "visuals" / "v.visual"
    vd.mkdir(parents=True)
    visual = {"visual": {"query": {"queryState": {"Values": {"projections": [
        {"field": {"Measure": {
            "Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": measure_name,
        }}}
    ]}}}}}
    (vd / "visual.json").write_text(json.dumps(visual), encoding="utf-8")
    return rd


def test_verify_bindings_detects_missing_measure(tmp_path: Path) -> None:
    from pbi_cli.commands.fabric_cmd import _verify_bindings

    folder = _make_measure_pbir(tmp_path, "Revenue")
    with patch(_INV_PATH, return_value=_inv(["Sales"], measures=["Profit"])):
        mismatches = _verify_bindings(folder, _WORKSPACE_ID, _DATASET_ID, "tok")
    assert "measure 'Revenue'" in mismatches


def test_verify_bindings_honors_report_level_measures(tmp_path: Path) -> None:
    """A report-level measure (reportExtensions.json) is valid even if not in the model."""
    from pbi_cli.commands.fabric_cmd import _verify_bindings

    folder = _make_measure_pbir(tmp_path, "RL Measure")
    (folder / "definition" / "reportExtensions.json").write_text(
        json.dumps({"entities": [{"measures": [{"name": "RL Measure"}]}]}), encoding="utf-8"
    )
    with patch(_INV_PATH, return_value=_inv(["Sales"], measures=["Profit"])):
        mismatches = _verify_bindings(folder, _WORKSPACE_ID, _DATASET_ID, "tok")
    assert mismatches == []


# ---------------------------------------------------------------------------
# report update (metadata)
# ---------------------------------------------------------------------------

def test_update_report_name() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.patch.return_value = {"displayName": "New Name"}
        result = runner.invoke(
            fabric_cmd,
            [
                "report", "update",
                "--workspace", _WORKSPACE_ID,
                "--report", _REPORT_NAME,
                "--name", "New Name",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_fab.patch.assert_called_once()


def test_update_requires_at_least_one_option() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        result = runner.invoke(
            fabric_cmd,
            ["report", "update", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME],
        )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# report delete
# ---------------------------------------------------------------------------

def test_delete_requires_yes_flag() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        # Invoke without --yes and answering 'n' → should abort
        runner.invoke(
            fabric_cmd,
            ["report", "delete", "--workspace", _WORKSPACE_ID, "--report", _REPORT_NAME],
            input="n\n",
        )
    mock_fab.delete.assert_not_called()


def test_delete_with_yes_flag() -> None:
    runner = CliRunner()
    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        mock_fab.get_paged.return_value = [_REPORT_META]
        mock_fab.delete.return_value = None
        result = runner.invoke(
            fabric_cmd,
            [
                "report", "delete",
                "--workspace", _WORKSPACE_ID,
                "--report", _REPORT_NAME,
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_fab.delete.assert_called_once()
    assert "Deleted" in result.output


# ---------------------------------------------------------------------------
# _resolve_report helper
# ---------------------------------------------------------------------------

def test_resolve_report_by_guid() -> None:
    """A GUID-shaped string is returned directly without an API call."""
    from pbi_cli.commands.fabric_cmd import _resolve_report

    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_token.return_value = "tok"
        result = _resolve_report(_WORKSPACE_ID, _REPORT_ID, "tok")
    assert result == _REPORT_ID
    mock_fab.get_paged.assert_not_called()


def test_resolve_report_by_name() -> None:
    from pbi_cli.commands.fabric_cmd import _resolve_report

    with patch("pbi_cli.commands.fabric_cmd._fab") as mock_fab:
        mock_fab.get_paged.return_value = [_REPORT_META]
        result = _resolve_report(_WORKSPACE_ID, _REPORT_NAME, "tok")
    assert result == _REPORT_ID
