"""Confluence wiki markup data dictionary generator."""

from __future__ import annotations

from typing import Any


class ConfluenceDocsGenerator:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def generate(self) -> str:
        lines = ["h1. Data Dictionary\n"]
        tables = self._backend.table_list()
        measures = self._backend.measure_list()
        for table in tables:
            name = table["name"]
            lines.append(f"h2. {name}\n")
            cols = self._backend.column_list(table=name)
            if cols:
                lines.append("|| Column || Type || Notes ||")
                for col in cols:
                    lines.append(f"| {col['name']} | {col.get('dataType', '')} | |")
                lines.append("")
        return "\n".join(lines)
