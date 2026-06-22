"""Unit tests for field-parameter generation (pbi model field-parameter)."""

from __future__ import annotations

import pytest

from pbi_cli.intelligence.field_parameter import (
    FieldParamItem,
    add_field_parameter,
    build_field_parameter_tmdl,
)
from pbi_cli.project_scaffold import create_project


def _items() -> list[FieldParamItem]:
    return [
        FieldParamItem("Sales", "financials", "Sales", is_measure=True),
        FieldParamItem("Profit", "financials", "Profit", is_measure=True),
        FieldParamItem("Units", "financials", "Units Sold", is_measure=True),
    ]


class TestBuildTmdl:
    def test_structure(self):
        tmdl = build_field_parameter_tmdl("Metric", _items())
        # Three columns: label, Fields, Order.
        assert "column Metric\n" in tmdl
        assert "column 'Metric Fields'" in tmdl
        assert "column 'Metric Order'" in tmdl
        # Label column is sorted by Order and grouped by Fields.
        assert "sortByColumn: 'Metric Order'" in tmdl
        assert "groupByColumn: 'Metric Fields'" in tmdl
        # ParameterMetadata marks it as a parameter.
        assert "ParameterMetadata" in tmdl
        # Calculated partition with NAMEOF rows in order.
        assert "partition Metric = calculated" in tmdl
        assert '("Sales", NAMEOF(\'financials\'[Sales]), 0)' in tmdl
        assert '("Units", NAMEOF(\'financials\'[Units Sold]), 2)' in tmdl

    def test_empty_items_raises(self):
        with pytest.raises(ValueError):
            build_field_parameter_tmdl("Metric", [])

    def test_bracket_in_name_raises(self):
        with pytest.raises(ValueError):
            build_field_parameter_tmdl("Bad[Name]", _items())


class TestAddToProject:
    def test_writes_table_and_ref(self, tmp_path):
        pbip = create_project(tmp_path, name="FP", table="financials")
        result = add_field_parameter(str(pbip), "Metric", _items())
        assert result["items"] == 3

        sm = tmp_path / "FP" / "FP.SemanticModel"
        table_file = sm / "definition" / "tables" / "Metric.tmdl"
        assert table_file.exists()
        # model.tmdl now references the new table so Desktop loads it.
        model_tmdl = (sm / "definition" / "model.tmdl").read_text(encoding="utf-8")
        assert "ref table Metric" in model_tmdl

    def test_no_model_raises(self, tmp_path):
        # A bare report folder with no *.SemanticModel.
        (tmp_path / "R.Report").mkdir()
        with pytest.raises(FileNotFoundError):
            add_field_parameter(str(tmp_path), "Metric", _items())
