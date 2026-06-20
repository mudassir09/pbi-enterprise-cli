"""Guards against the packaging regression where data files (skills, DLLs,
static UI) were declared nowhere and shipped in no wheel — breaking
`pbi skills install`, `pbi connect`, the xmla/desktop backends, and `pbi server`
on a clean `pip install`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pbi_cli
from pbi_cli.commands.skills_cmd import _skills_source_dir

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - 3.10 fallback
    tomllib = None  # type: ignore[assignment]

_PKG_ROOT = Path(pbi_cli.__file__).parent
_REPO_ROOT = _PKG_ROOT.parent.parent


def test_skills_dir_is_inside_the_package() -> None:
    """Skills must live under pbi_cli/ so package-data ships them in the wheel."""
    src = _skills_source_dir()
    assert src.is_dir(), f"skills source dir missing: {src}"
    assert _PKG_ROOT in src.parents or src == _PKG_ROOT / "skills", (
        f"skills dir {src} is not inside the package — it will not ship in the wheel"
    )


def test_skills_dir_has_skill_files() -> None:
    src = _skills_source_dir()
    skill_files = list(src.glob("*/SKILL.md"))
    assert len(skill_files) >= 10, f"expected bundled skills, found {len(skill_files)}"


@pytest.mark.skipif(tomllib is None, reason="tomllib requires Python 3.11+")
def test_pyproject_declares_package_data() -> None:
    """package-data must list the non-.py files the runtime loads."""
    with open(_REPO_ROOT / "pyproject.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    pkg_data = cfg["tool"]["setuptools"]["package-data"]["pbi_cli"]
    joined = " ".join(pkg_data)
    assert "dlls" in joined, "DLLs not declared in package-data (xmla/desktop will break)"
    assert "skills" in joined, "skills not declared in package-data"
    assert "static" in joined, "server static UI not declared in package-data"
