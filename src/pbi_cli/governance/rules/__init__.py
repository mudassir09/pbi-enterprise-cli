"""Governance rule registry — one module per rule.

Built-in rules are always loaded.  User-defined rules are loaded from
``~/.pbi-cli/rules/`` at import time (every *.py file in that directory).

A custom rule file must expose:
  - ``RULE_ID: str``      — unique identifier (e.g. ``"custom.my_rule"``)
  - ``check(backend) -> list[dict]``  — returns list of violation dicts
  - (optional) ``fix(backend, violation) -> bool``  — auto-fix

Example ``~/.pbi-cli/rules/no_spaces_in_columns.py``::

    RULE_ID = "custom.no_spaces_in_columns"

    def check(backend):
        violations = []
        for table in backend.table_list():
            for col in backend.column_list(table["name"]):
                if " " in col["name"]:
                    violations.append({
                        "rule": RULE_ID,
                        "object": f"{table['name']}.{col['name']}",
                        "message": "Column name contains a space.",
                        "autoFixable": False,
                    })
        return violations
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from pbi_cli.governance.rules import (
    measure_brackets,
    measure_description,
    measure_format,
    measure_naming,
    table_pascal_case,
)

_BUILTIN_RULES: list[ModuleType] = [
    table_pascal_case,
    measure_brackets,
    measure_description,
    measure_format,
    measure_naming,
]


def _load_plugin_rules() -> list[ModuleType]:
    """Discover and load user rule plugins from ~/.pbi-cli/rules/."""
    plugin_dir = Path.home() / ".pbi-cli" / "rules"
    if not plugin_dir.exists():
        return []

    loaded: list[ModuleType] = []
    for rule_file in sorted(plugin_dir.glob("*.py")):
        module_name = f"pbi_cli_user_rules.{rule_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, rule_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
            # Validate the module has the required interface
            if callable(getattr(mod, "check", None)) and hasattr(mod, "RULE_ID"):
                loaded.append(mod)
        except Exception as exc:
            # Don't crash the whole tool for a bad plugin — just warn
            import warnings
            warnings.warn(
                f"Could not load governance rule plugin {rule_file}: {exc}",
                stacklevel=1,
            )
    return loaded


ALL_RULES: list[ModuleType] = _BUILTIN_RULES + _load_plugin_rules()

__all__ = ["ALL_RULES"]
