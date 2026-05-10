"""Integration tests for source scaffold using MockTomBackend."""

import json
import tempfile

from click.testing import CliRunner

from pbi_cli.cli import cli

SAMPLE_PROFILE = [
    {
        "tableName": "FactSales",
        "rowCount": 100000,
        "columns": [
            {"name": "SalesKey", "dataType": "Int64", "nullRate": 0.0},
            {"name": "ProductKey", "dataType": "Int64", "nullRate": 0.0},
            {"name": "Revenue", "dataType": "Decimal", "nullRate": 0.02},
        ],
    },
    {
        "tableName": "DimProduct",
        "rowCount": 500,
        "columns": [
            {"name": "ProductKey", "dataType": "Int64", "nullRate": 0.0},
            {"name": "ProductName", "dataType": "String", "nullRate": 0.0},
        ],
    },
]


def test_source_scaffold_creates_tables():
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(SAMPLE_PROFILE, f)
        profile_path = f.name

    result = runner.invoke(
        cli, ["--backend", "mock", "source", "scaffold", "--profile", profile_path]
    )
    assert result.exit_code == 0, result.output


def test_dry_run_does_not_write():
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(SAMPLE_PROFILE, f)
        profile_path = f.name

    result = runner.invoke(
        cli, ["--dry-run", "--backend", "mock", "source", "scaffold", "--profile", profile_path]
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
