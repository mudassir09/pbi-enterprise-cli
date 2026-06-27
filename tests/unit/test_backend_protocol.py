"""Backends must satisfy their declared protocol — enforced, not aspirational.

This pins the read/write contract so a backend can't silently drop a method the
CLI and MCP server rely on. The core ``TomBackendProtocol`` is the universal
surface every backend implements (including the AMO-based ``xmla`` backend); the
``ExtendedTomBackendProtocol`` adds the structural ops (partitions, roles,
calculation groups, hierarchy writes) that only the in-memory/TMDL backends
(mock/file/fabric) implement.
"""

from __future__ import annotations

import pytest

from pbi_cli.backends.fabric_backend import FabricDefinitionBackend
from pbi_cli.backends.file_backend import FileBackend
from pbi_cli.backends.mock_backend import MockTomBackend
from pbi_cli.backends.protocol import ExtendedTomBackendProtocol, TomBackendProtocol
from pbi_cli.backends.xmla_backend import XmlaBackend

CORE_METHODS = sorted(n for n in dir(TomBackendProtocol) if not n.startswith("_"))
EXTENDED_METHODS = sorted(n for n in dir(ExtendedTomBackendProtocol) if not n.startswith("_"))

# Every backend implements the core contract...
CORE_BACKENDS = [MockTomBackend, FileBackend, FabricDefinitionBackend, XmlaBackend]
# ...but only the in-memory / TMDL backends implement the full structural surface.
EXTENDED_BACKENDS = [MockTomBackend, FileBackend, FabricDefinitionBackend]


@pytest.mark.parametrize("cls", CORE_BACKENDS, ids=lambda c: c.__name__)
def test_backend_satisfies_core_protocol(cls):
    missing = [m for m in CORE_METHODS if not callable(getattr(cls, m, None))]
    assert not missing, f"{cls.__name__} is missing core protocol methods: {missing}"
    assert issubclass(cls, TomBackendProtocol)


@pytest.mark.parametrize("cls", EXTENDED_BACKENDS, ids=lambda c: c.__name__)
def test_structural_backend_satisfies_extended_protocol(cls):
    missing = [m for m in EXTENDED_METHODS if not callable(getattr(cls, m, None))]
    assert not missing, f"{cls.__name__} is missing extended protocol methods: {missing}"
    assert issubclass(cls, ExtendedTomBackendProtocol)


def test_protocols_are_non_trivial():
    # Guard against a contract silently shrinking to nothing.
    assert len(CORE_METHODS) >= 18
    assert len(EXTENDED_METHODS) > len(CORE_METHODS)
    for core in ("measure_add", "measure_update", "measure_delete", "dax_query", "tmdl_export"):
        assert core in CORE_METHODS
    for ext in ("partition_add", "role_add", "calc_group_add", "hierarchy_add"):
        assert ext in EXTENDED_METHODS


def test_mock_instance_is_protocol_instance():
    assert isinstance(MockTomBackend(), TomBackendProtocol)
    assert isinstance(MockTomBackend(), ExtendedTomBackendProtocol)
