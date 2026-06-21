"""Unit tests for tmdl_util — keeping model.tmdl `ref table` / `ref cultureInfo`
lines in sync.

TMDL does not auto-discover table files, so a table .tmdl with no matching
`ref table` line loads silently missing in Desktop. These tests pin the helper
behaviour and assert the canonical model.tmdl shape used by project_scaffold.
"""

from __future__ import annotations

from pbi_cli.tmdl_util import (
    ensure_ref_culture,
    ensure_ref_table,
    quote_tmdl_name,
    remove_ref_table,
)

# Canonical model.tmdl base (annotation block, no ref lines yet) — mirrors the
# known-good shape written by project_scaffold._write_model.
_MODEL_BASE = (
    "model Model\n"
    "\tculture: en-US\n"
    "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
    "\tdiscourageImplicitMeasures\n"
    "\tsourceQueryCulture: en-US\n"
    "\tdataAccessOptions\n"
    "\t\tlegacyRedirects\n"
    "\t\treturnErrorValuesAsNull\n\n"
    '\tannotation PBI_QueryOrder = ["Financials"]\n\n'
    '\tannotation PBI_ProTooling = ["DevMode"]\n'
)


def _model(tmp_path, text=_MODEL_BASE):
    p = tmp_path / "model.tmdl"
    p.write_text(text, encoding="utf-8")
    return p


class TestQuote:
    def test_bare_identifier_unquoted(self):
        assert quote_tmdl_name("Financials") == "Financials"
        assert quote_tmdl_name("Date_Table") == "Date_Table"

    def test_spaces_quoted(self):
        assert quote_tmdl_name("Units Sold") == "'Units Sold'"

    def test_embedded_quote_doubled(self):
        assert quote_tmdl_name("O'Brien") == "'O''Brien'"


class TestEnsureRefTable:
    def test_adds_when_absent(self, tmp_path):
        m = _model(tmp_path)
        assert ensure_ref_table(m, "Financials") is True
        assert "ref table Financials" in m.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path):
        m = _model(tmp_path)
        ensure_ref_table(m, "Financials")
        before = m.read_text(encoding="utf-8")
        assert ensure_ref_table(m, "Financials") is False
        assert m.read_text(encoding="utf-8") == before
        assert before.count("ref table Financials") == 1

    def test_quotes_name_with_spaces(self, tmp_path):
        m = _model(tmp_path)
        ensure_ref_table(m, "Sales Detail")
        assert "ref table 'Sales Detail'" in m.read_text(encoding="utf-8")
        # And recognises the quoted form on the second pass.
        assert ensure_ref_table(m, "Sales Detail") is False

    def test_second_table_joins_block_before_culture(self, tmp_path):
        m = _model(tmp_path)
        ensure_ref_table(m, "Financials")
        ensure_ref_culture(m, "en-US")
        ensure_ref_table(m, "Date")
        text = m.read_text(encoding="utf-8")
        # Both tables referenced, culture line stays last.
        assert text.index("ref table Financials") < text.index("ref table Date")
        assert text.index("ref table Date") < text.index("ref cultureInfo en-US")

    def test_matches_scaffold_output(self, tmp_path):
        """ensure_ref_* on the base must reproduce the canonical scaffold bytes."""
        m = _model(tmp_path)
        ensure_ref_table(m, "Financials")
        ensure_ref_culture(m, "en-US")
        assert m.read_text(encoding="utf-8") == (
            _MODEL_BASE + "\nref table Financials\n\nref cultureInfo en-US\n"
        )


class TestRemoveRefTable:
    def test_removes_line(self, tmp_path):
        m = _model(tmp_path)
        ensure_ref_table(m, "Financials")
        ensure_ref_culture(m, "en-US")
        assert remove_ref_table(m, "Financials") is True
        text = m.read_text(encoding="utf-8")
        assert "ref table Financials" not in text
        # Culture reference survives and no doubled blank lines are left.
        assert "ref cultureInfo en-US" in text
        assert "\n\n\n" not in text

    def test_idempotent_when_absent(self, tmp_path):
        m = _model(tmp_path)
        assert remove_ref_table(m, "Nope") is False

    def test_round_trip_one_of_two(self, tmp_path):
        m = _model(tmp_path)
        ensure_ref_table(m, "Financials")
        ensure_ref_table(m, "Date")
        ensure_ref_culture(m, "en-US")
        remove_ref_table(m, "Financials")
        text = m.read_text(encoding="utf-8")
        assert "ref table Financials" not in text
        assert "ref table Date" in text
        assert "ref cultureInfo en-US" in text
        assert "\n\n\n" not in text


class TestEnsureRefCulture:
    def test_adds_and_idempotent(self, tmp_path):
        m = _model(tmp_path)
        assert ensure_ref_culture(m, "en-US") is True
        assert ensure_ref_culture(m, "en-US") is False
        assert m.read_text(encoding="utf-8").count("ref cultureInfo en-US") == 1
