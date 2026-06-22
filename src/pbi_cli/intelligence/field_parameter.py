"""Generate Power BI *field parameters* — a model-side calculated table that lets
report users swap which measure or dimension a visual shows.

A field parameter is a calculated table with three columns:

  * ``<Name>``        — the display label the slicer shows (sorted by Order)
  * ``<Name> Fields`` — the actual field reference (hidden), grouped under the label
  * ``<Name> Order``  — sort order (hidden)

and a calculated partition whose DAX is a table constructor of
``("Label", NAMEOF('Table'[Field]), order)`` rows. The label/Fields columns carry
the ``ParameterMetadata`` extended property that marks the table as a parameter so
Power BI Desktop renders the "Fields" authoring UI. ``NAMEOF`` is valid for both
columns and measures, so a single builder covers both.

This writes TMDL into the project's ``*.SemanticModel`` folder and registers the
table in ``model.tmdl`` (TMDL does not auto-discover table files — see
:mod:`pbi_cli.tmdl_util`). The generated shape mirrors Desktop's output; reload
the model in Desktop to confirm before publishing.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from pbi_cli.tmdl_util import ensure_ref_table, quote_tmdl_name


@dataclass
class FieldParamItem:
    """One choice in a field parameter: a label and the field it maps to."""

    label: str
    table: str
    field: str
    is_measure: bool = False  # informational only; NAMEOF syntax is identical


def _lineage() -> str:
    return str(uuid.uuid4())


def _nameof(item: FieldParamItem) -> str:
    return f"NAMEOF('{item.table}'[{item.field}])"


def build_field_parameter_tmdl(param_name: str, items: list[FieldParamItem]) -> str:
    """Return the TMDL text for a field-parameter calculated table.

    ``param_name`` is the table/label name (e.g. "Metric"); ``items`` are the
    selectable fields in display order. Raises ValueError on empty input.
    """
    if not items:
        raise ValueError("a field parameter needs at least one item")
    if not re.fullmatch(r"[^\[\]]+", param_name):
        raise ValueError("param_name must not contain square brackets")

    q = quote_tmdl_name(param_name)
    fields_col = quote_tmdl_name(f"{param_name} Fields")
    order_col = quote_tmdl_name(f"{param_name} Order")
    meta = 'extendedProperty ParameterMetadata = {"version":3,"kind":2}'

    rows = ",\n".join(
        f'\t\t\t\t("{it.label}", {_nameof(it)}, {i})' for i, it in enumerate(items)
    )

    return (
        f"table {q}\n"
        f"\tlineageTag: {_lineage()}\n"
        # ── label column (visible, sorted by Order, grouped by Fields) ──
        f"\n\tcolumn {q}\n"
        f"\t\tdataType: string\n"
        f"\t\tlineageTag: {_lineage()}\n"
        f"\t\tsummarizeBy: none\n"
        f"\t\tsourceColumn: [Value1]\n"
        f"\t\tsortByColumn: {order_col}\n"
        f"\n\t\trelatedColumnDetails\n"
        f"\t\t\tgroupByColumn: {fields_col}\n"
        f"\n\t\t{meta}\n"
        # ── Fields column (hidden, the actual field reference) ──
        f"\n\tcolumn {fields_col}\n"
        f"\t\tdataType: string\n"
        f"\t\tisHidden\n"
        f"\t\tlineageTag: {_lineage()}\n"
        f"\t\tsummarizeBy: none\n"
        f"\t\tsourceColumn: [Value2]\n"
        f"\n\t\t{meta}\n"
        # ── Order column (hidden, sort key) ──
        f"\n\tcolumn {order_col}\n"
        f"\t\tdataType: int64\n"
        f"\t\tformatString: 0\n"
        f"\t\tisHidden\n"
        f"\t\tlineageTag: {_lineage()}\n"
        f"\t\tsummarizeBy: sum\n"
        f"\t\tsourceColumn: [Value3]\n"
        # ── calculated partition: the table constructor ──
        f"\n\tpartition {q} = calculated\n"
        f"\t\tmode: import\n"
        f"\t\tsource =\n"
        f"\t\t\t\t{{\n"
        f"{rows}\n"
        f"\t\t\t\t}}\n"
    )


def _semantic_model_dir(pbip_path: str | Path) -> Path:
    """Locate the *.SemanticModel folder for a .pbip project."""
    p = Path(pbip_path)
    root = p.parent if p.is_file() and p.suffix == ".pbip" else p
    candidates = sorted(root.glob("*.SemanticModel"))
    if not candidates:
        # The .pbip may sit beside the model; try one level up too.
        candidates = sorted(root.parent.glob("*.SemanticModel"))
    if not candidates:
        raise FileNotFoundError(
            f"No *.SemanticModel folder found near {root}. Field parameters need a "
            "local model (a live-connection report stores no model on disk)."
        )
    return candidates[0]


def add_field_parameter(
    pbip_path: str | Path, param_name: str, items: list[FieldParamItem]
) -> dict[str, object]:
    """Write a field-parameter table into the project's semantic model.

    Creates ``definition/tables/<name>.tmdl`` and registers it in ``model.tmdl``.
    Returns {table, path, items}. Raises FileNotFoundError if no local model,
    ValueError on bad input.
    """
    sm = _semantic_model_dir(pbip_path)
    tables_dir = sm / "definition" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    model_tmdl = sm / "definition" / "model.tmdl"
    if not model_tmdl.exists():
        raise FileNotFoundError(f"model.tmdl not found in {sm / 'definition'}.")

    tmdl = build_field_parameter_tmdl(param_name, items)
    out = tables_dir / f"{param_name}.tmdl"
    out.write_text(tmdl, encoding="utf-8")
    ensure_ref_table(model_tmdl, param_name)
    return {"table": param_name, "path": str(out), "items": len(items)}
