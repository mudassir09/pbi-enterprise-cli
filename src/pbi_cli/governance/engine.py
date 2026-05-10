"""Governance rule engine — runs all rules and coordinates auto-fix."""

from __future__ import annotations

from typing import Any

from pbi_cli.governance.rules import ALL_RULES


class GovernanceEngine:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def run_all(self) -> list[dict[str, Any]]:
        """Run every registered rule and return the combined violation list."""
        violations: list[dict[str, Any]] = []
        for rule_module in ALL_RULES:
            violations.extend(rule_module.check(self._backend))
        return violations

    def run_naming_rules(self) -> list[dict[str, Any]]:
        from pbi_cli.governance.rules import measure_brackets, table_pascal_case

        violations: list[dict[str, Any]] = []
        violations.extend(table_pascal_case.check(self._backend))
        violations.extend(measure_brackets.check(self._backend))
        return violations

    def run_metadata_rules(self) -> list[dict[str, Any]]:
        from pbi_cli.governance.rules import measure_description, measure_format

        violations: list[dict[str, Any]] = []
        violations.extend(measure_description.check(self._backend))
        violations.extend(measure_format.check(self._backend))
        return violations

    def auto_fix(self, violations: list[dict[str, Any]]) -> int:
        """Apply auto-fix for all fixable violations. Returns count of fixes applied."""
        # Build a map from rule ID → fix function for all fixable rules
        fix_map = {
            getattr(m, "RULE_ID", None): m.fix
            for m in ALL_RULES
            if hasattr(m, "fix") and hasattr(m, "RULE_ID")
        }
        fixed = 0
        for v in violations:
            if not v.get("autoFixable"):
                continue
            fix_fn = fix_map.get(v.get("rule"))
            if fix_fn and fix_fn(self._backend, v):
                fixed += 1
        return fixed

    @staticmethod
    def list_rules() -> list[dict[str, Any]]:
        """Return metadata for all registered rules (built-in + plugins)."""
        from pbi_cli.governance.rules import _BUILTIN_RULES

        builtin_ids = {id(m) for m in _BUILTIN_RULES}
        rules_info: list[dict[str, Any]] = []
        for m in ALL_RULES:
            rules_info.append(
                {
                    "rule_id": getattr(m, "RULE_ID", m.__name__),
                    "source": "built-in" if id(m) in builtin_ids else "plugin",
                    "fixable": hasattr(m, "fix"),
                    "module": getattr(m, "__file__", ""),
                }
            )
        return rules_info
