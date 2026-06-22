#!/usr/bin/env python
"""Detect PBIR schema-version drift.

Compares the versions pinned in ``pbi_cli.backends.pbir_schemas`` against the
latest versions published in the official Microsoft schema repository:

    https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition

Usage::

    python scripts/check_pbir_schemas.py            # human-readable report
    python scripts/check_pbir_schemas.py --strict   # exit 1 if any pin is stale

Requires the GitHub CLI (``gh``) to be installed and authenticated, or a
``GITHUB_TOKEN`` in the environment. Network access is required; this is a
maintenance helper, not part of the test suite.
"""

from __future__ import annotations

import json
import subprocess
import sys

from pbi_cli.backends import pbir_schemas as schemas

_REPO = "microsoft/json-schemas"
_PATH = "fabric/item/report/definition"


def _semver_key(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.split("."))
    except ValueError:
        return (0,)


def _list_versions(name: str) -> list[str]:
    out = subprocess.check_output(
        ["gh", "api", f"repos/{_REPO}/contents/{_PATH}/{name}", "--jq", "[.[].name]"],
        text=True,
    )
    names = json.loads(out)
    return sorted((n for n in names if n[0].isdigit()), key=_semver_key)


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    drift = False
    print(f"{'schema':<32} {'pinned':<10} {'latest':<10} status")
    print("-" * 64)
    for name, pinned in sorted(schemas.DEFINITION_SCHEMA_VERSIONS.items()):
        try:
            versions = _list_versions(name)
        except Exception as exc:  # noqa: BLE001 - reporting tool
            print(f"{name:<32} {pinned:<10} {'?':<10} ERROR: {exc}")
            drift = True
            continue
        latest = versions[-1] if versions else "?"
        status = "ok" if latest == pinned else "STALE"
        if status == "STALE":
            drift = True
        print(f"{name:<32} {pinned:<10} {latest:<10} {status}")

    if drift and strict:
        print("\nSchema drift detected. Update pbir_schemas.DEFINITION_SCHEMA_VERSIONS.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
