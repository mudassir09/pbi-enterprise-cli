"""Tests for the centralised PBIR schema-version registry."""

from __future__ import annotations

import pytest

from pbi_cli.backends import pbir_schemas as schemas


def test_definition_schema_builds_expected_url():
    url = schemas.definition_schema("visualContainer")
    assert url == (
        "https://developer.microsoft.com/json-schemas/fabric/item/report/"
        "definition/visualContainer/2.9.0/schema.json"
    )


def test_item_schema_builds_expected_url():
    url = schemas.item_schema("definitionProperties")
    assert url.endswith("report/definitionProperties/2.0.0/schema.json")


def test_unknown_definition_schema_raises():
    with pytest.raises(KeyError):
        schemas.definition_schema("doesNotExist")


def test_unknown_item_schema_raises():
    with pytest.raises(KeyError):
        schemas.item_schema("doesNotExist")


@pytest.mark.parametrize("name", list(schemas.DEFINITION_SCHEMA_VERSIONS))
def test_all_registered_definition_schemas_resolve(name):
    url = schemas.definition_schema(name)
    assert url.startswith("https://developer.microsoft.com/json-schemas/")
    assert url.endswith("/schema.json")
    # version segment is present and looks like x.y.z
    version = schemas.DEFINITION_SCHEMA_VERSIONS[name]
    assert version.count(".") == 2
    assert f"/{name}/{version}/" in url


def test_backend_and_builder_use_the_registry():
    """Backend constants and the visual builder schema come from the registry, so
    a version bump here propagates everywhere."""
    from pbi_cli.backends.pbir_backend import PbirBackend
    from pbi_cli.intelligence.visual_builder import VISUAL_CONTAINER_SCHEMA

    assert VISUAL_CONTAINER_SCHEMA == schemas.definition_schema("visualContainer")
    assert PbirBackend.MOBILE_STATE_SCHEMA == schemas.definition_schema(
        "visualContainerMobileState"
    )


def test_report_version_at_import_present():
    rvi = schemas.REPORT_VERSION_AT_IMPORT
    assert set(rvi) == {"visual", "report", "page"}
