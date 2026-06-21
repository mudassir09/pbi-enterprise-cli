"""Helpers for the TMDL `model.tmdl` reference block.

TMDL does *not* auto-discover table files: a semantic model only loads a table
if `model.tmdl` carries a matching top-level `ref table <name>` line (and a
`ref cultureInfo <c>` line for each culture under `definition/cultures/`). A
table `.tmdl` file with no `ref table` line loads with that table silently
missing in Power BI Desktop.

Any pure-Python path that writes or removes a table `.tmdl` file must keep these
references in sync. These helpers are idempotent so callers can apply them
unconditionally. `project_scaffold._write_model` is the reference shape.
"""

from __future__ import annotations

import re
from pathlib import Path

_REF_TABLE_RE = re.compile(r"^ref\s+table\s+(?P<name>.+?)\s*$")
_REF_CULTURE_RE = re.compile(r"^ref\s+cultureInfo\s+(?P<name>.+?)\s*$")


def quote_tmdl_name(name: str) -> str:
    """Quote a TMDL object name the same way table declarations are quoted.

    Bare identifiers (letters, digits, underscore) are left unquoted; anything
    else is single-quoted with embedded quotes doubled — e.g. `Units Sold`
    becomes `'Units Sold'`.
    """
    if re.fullmatch(r"[A-Za-z0-9_]+", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _unquote_tmdl_name(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def ensure_ref_table(model_tmdl_path: str | Path, table_name: str) -> bool:
    """Ensure `model.tmdl` contains a `ref table <table_name>` line.

    Inserts the line after the model's annotation block (alongside any existing
    `ref table` lines, before the `ref cultureInfo` block) if absent. Idempotent.
    Returns True if the file was modified.
    """
    path = Path(model_tmdl_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    last_ref_table: int | None = None
    first_ref_culture: int | None = None
    for i, ln in enumerate(lines):
        m = _REF_TABLE_RE.match(ln)
        if m:
            if _unquote_tmdl_name(m.group("name")) == table_name:
                return False  # already referenced
            last_ref_table = i
        elif first_ref_culture is None and _REF_CULTURE_RE.match(ln):
            first_ref_culture = i

    new_line = f"ref table {quote_tmdl_name(table_name)}"
    if last_ref_table is not None:
        lines[last_ref_table + 1 : last_ref_table + 1] = ["", new_line]
    elif first_ref_culture is not None:
        lines[first_ref_culture:first_ref_culture] = [new_line, ""]
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(new_line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def remove_ref_table(model_tmdl_path: str | Path, table_name: str) -> bool:
    """Remove the `ref table <table_name>` line from `model.tmdl` if present.

    Also drops a blank line left adjacent to the removed reference so the ref
    block stays single-blank-line separated. Idempotent. Returns True if the
    file was modified.
    """
    path = Path(model_tmdl_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    target = None
    for i, ln in enumerate(lines):
        m = _REF_TABLE_RE.match(ln)
        if m and _unquote_tmdl_name(m.group("name")) == table_name:
            target = i
            break
    if target is None:
        return False

    # Drop the ref line plus one adjacent blank line to avoid doubled blanks.
    end = target + 1
    if end < len(lines) and lines[end].strip() == "":
        end += 1
    elif target > 0 and lines[target - 1].strip() == "":
        target -= 1
    del lines[target:end]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def ensure_ref_culture(model_tmdl_path: str | Path, culture: str = "en-US") -> bool:
    """Ensure `model.tmdl` contains a `ref cultureInfo <culture>` line.

    Appended after the ref-table block. Idempotent. Returns True if modified.
    """
    path = Path(model_tmdl_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    for ln in lines:
        m = _REF_CULTURE_RE.match(ln)
        if m and _unquote_tmdl_name(m.group("name")) == culture:
            return False

    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"ref cultureInfo {culture}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
