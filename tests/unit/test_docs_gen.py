"""Unit tests for docs_gen generators."""

from __future__ import annotations

import pytest

from pbi_cli.backends.mock_backend import MockTomBackend
from pbi_cli.docs_gen.confluence import ConfluenceDocsGenerator
from pbi_cli.docs_gen.markdown import MarkdownDocsGenerator


@pytest.fixture()
def backend() -> MockTomBackend:
    b = MockTomBackend()
    b.connect()
    return b


# ── MarkdownDocsGenerator ─────────────────────────────────────────────────────


class TestMarkdownDocsGenerator:
    def test_generates_h1_title(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        assert "# Data Dictionary" in content

    def test_includes_all_table_names(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        for table in backend.table_list():
            assert table["name"] in content

    def test_includes_column_names(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        assert "Revenue" in content
        assert "Decimal" in content

    def test_includes_measures(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        assert "Total Revenue" in content
        assert "SUM(Sales[Revenue])" in content

    def test_table_markdown_format(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        assert "| Column |" in content
        assert "|--------|" in content

    def test_measure_format_string_shown(self, backend):
        gen = MarkdownDocsGenerator(backend)
        content = gen.generate()
        assert "#,0.00" in content


# ── ConfluenceDocsGenerator ───────────────────────────────────────────────────


class TestConfluenceDocsGenerator:
    def test_generates_content(self, backend):
        gen = ConfluenceDocsGenerator(backend)
        content = gen.generate()
        assert content is not None
        assert len(content) > 0

    def test_includes_table_names(self, backend):
        gen = ConfluenceDocsGenerator(backend)
        content = gen.generate()
        assert "Sales" in content

    def test_is_string(self, backend):
        gen = ConfluenceDocsGenerator(backend)
        content = gen.generate()
        assert isinstance(content, str)
