"""Unit tests for new pbi report commands: bookmarks, drillthrough, tooltip."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from pbi_cli.cli import cli

_PBIP_PATH = Path(r"C:\Users\GGPC\Documents\financials.pbip")
_REPORT_DIR = Path(r"C:\Users\GGPC\Documents\financials.Report")

# ── helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def pbip_copy(tmp_path) -> str:
    """Writable copy of the live financials report."""
    pytest.importorskip("json")  # always available
    if not _REPORT_DIR.exists():
        pytest.skip("financials.Report not found")
    report_copy = tmp_path / "financials.Report"
    shutil.copytree(_REPORT_DIR, report_copy)
    pbip_file = tmp_path / "financials.pbip"
    pbip_file.write_text(
        json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "financials.Report"}}]}),
        encoding="utf-8",
    )
    return str(pbip_file)


def _run(runner, *args):
    return runner.invoke(cli, list(args))


# ── Bookmark tests ─────────────────────────────────────────────────────────────


class TestBookmarkCommands:
    def test_bookmark_list_no_bookmarks(self, runner, pbip_copy):
        result = _run(runner, "report", "bookmark-list", "--pbip", pbip_copy)
        assert result.exit_code == 0
        # Either "No bookmarks" or a table — just no crash
        assert result.output

    def test_bookmark_add_and_list(self, runner, pbip_copy):
        add = _run(runner, "report", "bookmark-add", "--pbip", pbip_copy, "--name", "Test Bookmark")
        assert add.exit_code == 0
        assert "Test Bookmark" in add.output

        lst = _run(runner, "--json", "report", "bookmark-list", "--pbip", pbip_copy)
        assert lst.exit_code == 0
        data = json.loads(lst.output)
        assert any(b["displayName"] == "Test Bookmark" for b in data)

    def test_bookmark_add_with_page(self, runner, pbip_copy):
        result = _run(
            runner,
            "report",
            "bookmark-add",
            "--pbip",
            pbip_copy,
            "--name",
            "Q4 View",
            "--page",
            "Executive Summary",
        )
        assert result.exit_code == 0
        assert "Q4 View" in result.output

    def test_bookmark_delete(self, runner, pbip_copy):
        _run(runner, "report", "bookmark-add", "--pbip", pbip_copy, "--name", "ToDelete")
        result = _run(
            runner, "report", "bookmark-delete", "--pbip", pbip_copy, "--name", "ToDelete"
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_bookmark_delete_missing(self, runner, pbip_copy):
        result = _run(
            runner, "report", "bookmark-delete", "--pbip", pbip_copy, "--name", "DoesNotExist_XYZ"
        )
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_bookmark_add_dry_run(self, runner, pbip_copy):
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "report",
                "bookmark-add",
                "--pbip",
                pbip_copy,
                "--name",
                "DryRunBM",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output


# ── Bookmark file-format assertions ──────────────────────────────────────────


class TestBookmarkFileFormat:
    """Assert the on-disk PBIR format matches what Power BI Desktop expects."""

    def test_bookmark_is_flat_file_not_subfolder(self, runner, pbip_copy):
        """bookmark must be written as {id}.bookmark.json, not {id}/bookmark.json."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        result = b.bookmark_add("Format Check BM")
        bm_id = result["name"]
        bdir = b._ga_bookmarks_dir()

        flat_file = bdir / f"{bm_id}.bookmark.json"
        old_subfolder = bdir / bm_id
        assert flat_file.exists(), "bookmark must be a flat .bookmark.json file"
        assert not old_subfolder.exists(), "bookmark must NOT be a subfolder"

    def test_bookmark_schema_version_is_2_1_0(self, runner, pbip_copy):
        """Desktop uses schema 2.1.0, not 1.0.0."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        b.bookmark_add("Schema Version BM")
        bdir = b._ga_bookmarks_dir()
        bm_files = list(bdir.glob("*.bookmark.json"))
        assert bm_files, "no .bookmark.json files found"
        data = json.loads(bm_files[0].read_text(encoding="utf-8"))
        assert "2.1.0" in data["$schema"], f"expected 2.1.0 schema, got: {data['$schema']}"

    def test_bookmark_exploration_state_version_is_1_3(self, runner, pbip_copy):
        """explorationState.version must be '1.3', not '0.0'."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        b.bookmark_add("Version Check BM")
        bdir = b._ga_bookmarks_dir()
        bm_files = list(bdir.glob("*.bookmark.json"))
        data = json.loads(bm_files[0].read_text(encoding="utf-8"))
        assert data["explorationState"]["version"] == "1.3", (
            f"expected version '1.3', got '{data['explorationState']['version']}'"
        )

    def test_bookmark_has_options_field(self, runner, pbip_copy):
        """Desktop always writes options.targetVisualNames."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        b.bookmark_add("Options Check BM")
        bdir = b._ga_bookmarks_dir()
        bm_files = list(bdir.glob("*.bookmark.json"))
        data = json.loads(bm_files[0].read_text(encoding="utf-8"))
        assert "options" in data, "bookmark must have 'options' field"
        assert "targetVisualNames" in data["options"], "options must have 'targetVisualNames'"

    def test_bookmarks_index_uses_items_not_bookmark_order(self, runner, pbip_copy):
        """bookmarks.json must use 'items' array, not 'bookmarkOrder'."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        b.bookmark_add("Index Check BM")
        bdir = b._ga_bookmarks_dir()
        index = json.loads((bdir / "bookmarks.json").read_text(encoding="utf-8"))
        assert "items" in index, "bookmarks.json must have 'items' key"
        assert "bookmarkOrder" not in index, "bookmarks.json must NOT have 'bookmarkOrder'"

    def test_bookmark_delete_removes_flat_file(self, runner, pbip_copy):
        """Deleting a bookmark must remove the flat .bookmark.json file."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        result = b.bookmark_add("Delete Me BM")
        bm_id = result["name"]
        bdir = b._ga_bookmarks_dir()
        flat_file = bdir / f"{bm_id}.bookmark.json"
        assert flat_file.exists()
        b.bookmark_delete("Delete Me BM")
        assert not flat_file.exists(), "flat file must be deleted"

    def test_bookmark_active_section_resolves_to_page_id(self, runner, pbip_copy):
        """activeSection must be the page GUID, not the display name."""
        from pbi_cli.backends.pbir_backend import PbirBackend

        b = PbirBackend(pbip_copy)
        pages = b.page_list()
        target = pages[0]
        result = b.bookmark_add("Section BM", page=target["displayName"])
        bm_id = result["name"]
        bdir = b._ga_bookmarks_dir()
        # Read the specific file we just created, not any pre-existing bookmark
        bm_file = bdir / f"{bm_id}.bookmark.json"
        assert bm_file.exists(), f"bookmark file not found: {bm_file}"
        data = json.loads(bm_file.read_text(encoding="utf-8"))
        active = data["explorationState"]["activeSection"]
        assert active == target["name"], (
            f"activeSection should be page GUID '{target['name']}', got '{active}'"
        )


# ── Drillthrough / Tooltip tests ──────────────────────────────────────────────


class TestDrillthroughTooltip:
    def test_drillthrough_setup(self, runner, pbip_copy):
        result = _run(
            runner,
            "report",
            "drillthrough-setup",
            "--pbip",
            pbip_copy,
            "--page",
            "Profit Analysis",
            "--table",
            "financials",
        )
        assert result.exit_code == 0
        assert "Drillthrough" in result.output

    def test_tooltip_setup(self, runner, pbip_copy):
        result = _run(
            runner, "report", "tooltip-setup", "--pbip", pbip_copy, "--page", "Sales Analysis"
        )
        assert result.exit_code == 0
        assert "tooltip" in result.output.lower()

    def test_page_type_reset(self, runner, pbip_copy):
        # First set as tooltip, then reset
        _run(runner, "report", "tooltip-setup", "--pbip", pbip_copy, "--page", "Sales Analysis")
        result = _run(
            runner, "report", "page-type-reset", "--pbip", pbip_copy, "--page", "Sales Analysis"
        )
        assert result.exit_code == 0
        assert "reset" in result.output.lower()

    def test_drillthrough_setup_dry_run(self, runner, pbip_copy):
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "report",
                "drillthrough-setup",
                "--pbip",
                pbip_copy,
                "--page",
                "Profit Analysis",
                "--table",
                "financials",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_drillthrough_setup_invalid_page(self, runner, pbip_copy):
        result = _run(
            runner,
            "report",
            "drillthrough-setup",
            "--pbip",
            pbip_copy,
            "--page",
            "NonExistentPage_XYZ",
            "--table",
            "financials",
        )
        assert result.exit_code != 0
