"""Tests for pbi snapshot command group."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _run(runner, *args, **kw):
    return runner.invoke(cli, ["--backend", "mock"] + list(args), **kw)


class TestSnapshotCreate:
    def test_create_exits_cleanly(self, runner, tmp_path):
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=tmp_path / "snaps"):
            result = _run(runner, "snapshot", "create", "--label", "test-label")
        assert result.exit_code == 0

    def test_create_writes_meta_file(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            _run(runner, "snapshot", "create", "--label", "my-label")
        meta_files = list(snap_dir.rglob(".snapshot-meta.json"))
        assert len(meta_files) == 1
        meta = json.loads(meta_files[0].read_text())
        assert meta["label"] == "my-label"
        assert "created_at" in meta

    def test_create_without_label_uses_timestamp(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "create")
        assert result.exit_code == 0
        assert snap_dir.exists()

    def test_create_dry_run_does_not_write(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = runner.invoke(
                cli, ["--backend", "mock", "--dry-run", "snapshot", "create", "--label", "x"]
            )
        assert result.exit_code == 0
        assert not snap_dir.exists()

    def test_create_prints_restore_hint(self, runner, tmp_path):
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=tmp_path / "snaps"):
            result = _run(runner, "snapshot", "create", "--label", "hint-test")
        assert "Restore with" in result.output or "snapshot restore" in result.output


class TestSnapshotList:
    def test_list_empty_dir(self, runner, tmp_path):
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=tmp_path / "nosnaps"):
            result = _run(runner, "snapshot", "list")
        assert result.exit_code == 0
        assert "No snapshots" in result.output

    def test_list_shows_snapshots(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir(parents=True)
        snap = snap_dir / "20260531_120000_test"
        snap.mkdir()
        (snap / ".snapshot-meta.json").write_text(
            json.dumps({"created_at": "2026-05-31T12:00:00", "label": "test"}),
            encoding="utf-8",
        )
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "list")
        assert result.exit_code == 0
        assert "20260531_120000_test" in result.output

    def test_list_with_tmdl_files_counts_correctly(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "20260531_120000_count"
        snap.mkdir(parents=True)
        (snap / "model.tmdl").write_text("model", encoding="utf-8")
        (snap / "table.tmdl").write_text("table", encoding="utf-8")
        (snap / ".snapshot-meta.json").write_text(
            json.dumps({"created_at": "2026-05-31", "label": "count"}),
            encoding="utf-8",
        )
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "list")
        assert result.exit_code == 0
        assert "2" in result.output


class TestSnapshotRestore:
    def test_restore_requires_confirm(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "snap1"
        snap.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "restore", "snap1")
        assert result.exit_code != 0
        assert "--confirm" in result.output or "confirm" in result.output.lower()

    def test_restore_missing_snapshot(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "restore", "does-not-exist", "--confirm")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_restore_with_confirm_succeeds(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "snap1"
        snap.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "restore", "snap1", "--confirm")
        assert result.exit_code == 0
        assert "Restored" in result.output

    def test_restore_dry_run(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "snap-dr"
        snap.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = runner.invoke(
                cli,
                ["--backend", "mock", "--dry-run", "snapshot", "restore", "snap-dr", "--confirm"],
            )
        assert result.exit_code == 0


class TestSnapshotDiff:
    def test_diff_missing_snapshot(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "diff", "missing-snap")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_diff_no_changes(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "snap-nochange"
        snap.mkdir(parents=True)
        with patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir):
            result = _run(runner, "snapshot", "diff", "snap-nochange")
        assert result.exit_code == 0

    def test_diff_shows_changes(self, runner, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap = snap_dir / "snap-changed"
        snap.mkdir(parents=True)
        mock_diff = {
            "has_changes": True,
            "added": ["measure.NewMeasure"],
            "removed": [],
            "changed": ["table.Sales"],
        }
        with (
            patch("pbi_cli.commands.snapshot._snapshot_dir", return_value=snap_dir),
            patch(
                "pbi_cli.backends.mock_backend.MockTomBackend.model_diff",
                return_value=mock_diff,
            ),
        ):
            result = _run(runner, "snapshot", "diff", "snap-changed")
        assert result.exit_code == 0
        assert "+1" in result.output or "added" in result.output.lower()
