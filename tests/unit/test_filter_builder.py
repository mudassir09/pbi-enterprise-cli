"""Validate generated PBIR filters against Microsoft's *real* published schemas.

The schemas under ``tests/fixtures/pbir_schemas/`` are vendored verbatim from
https://github.com/microsoft/json-schemas (filterConfiguration 1.3.0 and its
cross-file references semanticQuery 1.4.0 + formattingObjectDefinitions 1.5.0).
Validating against them is the strongest guarantee that what we write is exactly
what Power BI Desktop will accept — and it catches schema drift if the vendored
copies are ever refreshed to a newer version.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbi_cli.intelligence import filter_builder as fb

jsonschema = pytest.importorskip("jsonschema")
referencing = pytest.importorskip("referencing")

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "pbir_schemas"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def filter_validator():
    """A Draft-07 validator for a single ``FilterContainer``, with refs resolved
    offline from the vendored semanticQuery + formattingObjectDefinitions files.

    We validate individual containers (not the whole ``filterConfig`` envelope):
    when ``filterConfig`` is embedded in page.json, Power BI Desktop forbids the
    ``$schema`` key that the standalone filterConfiguration schema marks required —
    so the envelope can't satisfy the standalone schema, but each FilterContainer
    can and must. See :func:`pbi_cli.intelligence.filter_builder.add_filter`.
    """
    from referencing import Registry, Resource

    schemas = [
        _load("filterConfiguration-1.3.0.schema.json"),
        _load("semanticQuery-1.4.0.schema.json"),
        _load("formattingObjectDefinitions-1.5.0.schema.json"),
    ]
    registry = Registry().with_resources(
        [(s["$id"], Resource.from_contents(s)) for s in schemas]
    )
    container_ref = {"$ref": schemas[0]["$id"] + "#/definitions/FilterContainer"}
    return jsonschema.Draft7Validator(container_ref, registry=registry)


class TestContainerFieldShape:
    """The FilterContainer `field` must reference the table via Entity, not a
    query alias via Source. Desktop blanks an alias-based field on its next save,
    which then blocks the report from opening (verified live 2026-06-22). The MS
    schema permits either, so only this behavioural check guards against it."""

    def _field_sourceref(self, fc: dict) -> dict:
        node = fc["field"].get("Column") or fc["field"].get("Measure")
        return node["Expression"]["SourceRef"]

    def test_value_filter_field_uses_entity(self):
        fc = fb.build_value_filter("financials", "Segment", ["Enterprise"])
        assert self._field_sourceref(fc) == {"Entity": "financials"}

    def test_advanced_filter_field_uses_entity(self):
        fc = fb.build_advanced_filter("financials", "Profit", [(">=", 0)])
        assert self._field_sourceref(fc) == {"Entity": "financials"}

    def test_relative_date_field_uses_entity(self):
        fc = fb.build_relative_date_filter("Calendar", "Date", 30, "Days")
        assert self._field_sourceref(fc) == {"Entity": "Calendar"}

    def test_where_clause_still_uses_alias(self):
        # The Where/From body still references the query alias — only the
        # container field changed.
        fc = fb.build_value_filter("financials", "Segment", ["Enterprise"])
        in_col = fc["filter"]["Where"][0]["Condition"]["In"]["Expressions"][0]
        assert "Source" in in_col["Column"]["Expression"]["SourceRef"]


class TestSchemaValidation:
    def test_value_filter_validates(self, filter_validator):
        fc = fb.build_value_filter("financials", "Segment", ["Enterprise", "Government"])
        filter_validator.validate(fc)

    def test_exclude_filter_validates(self, filter_validator):
        fc = fb.build_value_filter("financials", "Segment", ["Midmarket"], exclude=True)
        filter_validator.validate(fc)

    def test_advanced_single_validates(self, filter_validator):
        fc = fb.build_advanced_filter("financials", "Profit", [(">=", 1000)])
        filter_validator.validate(fc)

    def test_advanced_range_validates(self, filter_validator):
        fc = fb.build_advanced_filter(
            "financials", "Profit", [(">=", 0), ("<=", 1_000_000)], logic="And"
        )
        filter_validator.validate(fc)

    def test_advanced_measure_validates(self, filter_validator):
        fc = fb.build_advanced_filter("Sales", "Total Sales", [(">", 0)], is_measure=True)
        filter_validator.validate(fc)

    def test_relative_date_validates(self, filter_validator):
        fc = fb.build_relative_date_filter("Calendar", "Date", 30, "Days")
        filter_validator.validate(fc)

    def test_relative_date_exclude_today_validates(self, filter_validator):
        fc = fb.build_relative_date_filter(
            "Calendar", "Date", 6, "Months", include_today=False
        )
        filter_validator.validate(fc)

    def test_locked_hidden_flags_validate(self, filter_validator):
        fc = fb.build_value_filter(
            "financials", "Country", ["USA"], locked=True, hidden=True
        )
        filter_validator.validate(fc)

    def test_all_filters_in_a_config_validate(self, filter_validator):
        cfg = fb.empty_filter_config()
        fb.add_filter(cfg, fb.build_value_filter("f", "Country", ["USA"]))
        fb.add_filter(cfg, fb.build_advanced_filter("f", "Profit", [(">=", 0)]))
        fb.add_filter(cfg, fb.build_relative_date_filter("Calendar", "Date", 7, "Weeks"))
        # Embedded filterConfig must NOT carry $schema (Desktop rejects it).
        assert "$schema" not in cfg
        for container in cfg["filters"]:
            filter_validator.validate(container)


class TestBuilderShapes:
    def test_value_filter_shape(self):
        fc = fb.build_value_filter("financials", "Segment", ["A", "B"])
        assert fc["type"] == "Categorical"
        assert fc["name"] and fb.is_valid_name(fc["name"])
        definition = fc["filter"]
        assert definition["Version"] == 2
        assert definition["From"][0]["Entity"] == "financials"
        in_expr = definition["Where"][0]["Condition"]["In"]
        assert len(in_expr["Values"]) == 2

    def test_exclude_negates(self):
        fc = fb.build_value_filter("f", "x", ["v"], exclude=True)
        assert fc["type"] == "Exclude"
        assert "Not" in fc["filter"]["Where"][0]["Condition"]

    def test_advanced_two_conditions_joined(self):
        fc = fb.build_advanced_filter("f", "x", [(">=", 0), ("<=", 9)], logic="Or")
        cond = fc["filter"]["Where"][0]["Condition"]
        assert "Or" in cond
        assert "Comparison" in cond["Or"]["Left"]

    def test_advanced_rejects_too_many(self):
        with pytest.raises(ValueError):
            fb.build_advanced_filter("f", "x", [(">", 1), ("<", 2), ("=", 3)])

    def test_advanced_rejects_bad_operator(self):
        with pytest.raises(ValueError):
            fb.build_advanced_filter("f", "x", [("!!", 1)])

    def test_relative_date_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            fb.build_relative_date_filter("c", "d", 0, "Days")

    def test_relative_date_uses_dateadd_now(self):
        fc = fb.build_relative_date_filter("Calendar", "Date", 30, "Days")
        cond = fc["filter"]["Where"][0]["Condition"]
        assert cond["Comparison"]["Right"]["DateAdd"]["Amount"] == -30
        assert cond["Comparison"]["Right"]["DateAdd"]["Expression"] == {"Now": {}}

    def test_embedded_config_has_no_schema_key(self):
        cfg = fb.add_filter(None, fb.build_value_filter("f", "x", ["v"]))
        # Desktop rejects $schema inside an embedded filterConfig.
        assert "$schema" not in cfg
        assert len(cfg["filters"]) == 1

    def test_add_filter_strips_stray_schema(self):
        cfg = {"$schema": "anything", "filters": []}
        fb.add_filter(cfg, fb.build_value_filter("f", "x", ["v"]))
        assert "$schema" not in cfg
