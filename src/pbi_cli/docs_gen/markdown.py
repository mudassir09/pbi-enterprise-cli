"""Markdown data dictionary generator."""

from __future__ import annotations

from typing import Any


class MarkdownDocsGenerator:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def generate(self) -> str:
        lines = ["# Data Dictionary\n"]
        tables = self._backend.table_list()
        measures = self._backend.measure_list()
        for table in tables:
            name = table["name"]
            lines.append(f"## {name}\n")
            cols = self._backend.column_list(table=name)
            if cols:
                lines.append("| Column | Type | Notes |")
                lines.append("|--------|------|-------|")
                for col in cols:
                    lines.append(f"| {col['name']} | {col.get('dataType', '')} | |")
                lines.append("")
            table_measures = [m for m in measures if m.get("table") == name]
            if table_measures:
                lines.append("### Measures\n")
                lines.append("| Measure | Expression | Format |")
                lines.append("|---------|------------|--------|")
                for m in table_measures:
                    lines.append(f"| {m['name']} | `{m.get('expression', '')}` | {m.get('formatString', '')} |")
                lines.append("")
        return "\n".join(lines)
