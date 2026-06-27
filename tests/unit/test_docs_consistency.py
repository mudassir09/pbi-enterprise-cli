"""Guard against README ↔ code drift.

The bundled-skill registry and the CLI's --backend choices are the single source
of truth. These tests fail if the docs claim a different skill count, omit a
bundled skill, or omit a backend — the exact drift that had crept in (README
said "10 skills / five backends" while the code shipped 12 skills / six backends).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pbi_cli.cli import cli
from pbi_cli.commands.skills_cmd import _BUNDLED_SKILLS, _skills_source_dir

_ROOT = Path(__file__).resolve().parents[2]
_READMES = [_ROOT / "README.md", _ROOT / "README.pypi.md"]


def _backend_choices() -> list[str]:
    for p in cli.params:
        if p.name == "backend":
            return list(p.type.choices)  # type: ignore[attr-defined]
    raise AssertionError("--backend option not found on the CLI group")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_bundled_skill_dir_exists():
    """Each registered skill must actually ship (so `--all` install can't 404)."""
    src = _skills_source_dir()
    missing = [s["name"] for s in _BUNDLED_SKILLS if not (src / s["name"] / "SKILL.md").exists()]
    assert not missing, f"Bundled skills missing SKILL.md on disk: {missing}"


def test_no_skill_requires_a_future_cli_version():
    """A skill must not pin min_cli_version above the current package version, or
    `pbi skills check` reports it incompatible (the bug the new report skills had)."""
    import re

    from pbi_cli import __version__
    from pbi_cli.commands.skills_cmd import _skills_source_dir as _src
    from pbi_cli.commands.skills_cmd import _version_tuple

    cli_ver = _version_tuple(__version__)
    offenders = []
    for s in _BUNDLED_SKILLS:
        md = _src() / s["name"] / "SKILL.md"
        m = re.search(r'^min_cli_version:\s*"?([0-9.]+)"?', md.read_text(encoding="utf-8"),
                      re.MULTILINE)
        if m and _version_tuple(m.group(1)) > cli_ver:
            offenders.append(f"{s['name']} requires {m.group(1)} > CLI {__version__}")
    assert not offenders, "Skills pin a future CLI version: " + "; ".join(offenders)


def test_readme_lists_every_bundled_skill():
    readme = _read(_ROOT / "README.md")
    missing = [s["name"] for s in _BUNDLED_SKILLS if s["name"] not in readme]
    assert not missing, f"README.md skill table is missing: {missing}"


@pytest.mark.parametrize("readme", _READMES, ids=lambda p: p.name)
def test_readme_skill_count_matches_registry(readme: Path):
    n = len(_BUNDLED_SKILLS)
    text = _read(readme)
    assert f"{n} bundled Claude Code skills" in text or f"{n} Claude Code skills" in text, (
        f"{readme.name} does not state the real skill count ({n})"
    )
    # No stale count lingering (the bug this test exists to prevent).
    for stale in range(8, 40):
        if stale == n:
            continue
        assert f"{stale} Claude Code skills" not in text, (
            f"{readme.name} still claims {stale} Claude Code skills (should be {n})"
        )


@pytest.mark.parametrize("readme", _READMES, ids=lambda p: p.name)
def test_readme_documents_every_backend(readme: Path):
    text = _read(readme)
    missing = [c for c in _backend_choices() if f"`{c}`" not in text]
    assert not missing, f"{readme.name} does not document backends: {missing}"


@pytest.mark.parametrize("readme", _READMES, ids=lambda p: p.name)
def test_no_stale_five_backends_claim(readme: Path):
    text = _read(readme).lower()
    assert "five backend" not in text, f"{readme.name} still says 'five backends' (there are 6)"
