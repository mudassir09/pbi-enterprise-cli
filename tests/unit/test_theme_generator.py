"""Unit tests for the WCAG theme generator."""

import pytest

from pbi_cli.intelligence.theme_generator import ThemeGenerator, _contrast_ratio


def test_contrast_ratio_white_on_black():
    ratio = _contrast_ratio("#FFFFFF", "#000000")
    assert ratio == pytest.approx(21.0, abs=0.1)


def test_contrast_ratio_wcag_aa():
    ratio = _contrast_ratio("#1A1A1A", "#FFFFFF")
    assert ratio >= 4.5


def test_theme_generate_returns_required_keys():
    gen = ThemeGenerator()
    theme = gen.generate("#0078D4", style="corporate")
    assert "dataColors" in theme
    assert "background" in theme
    assert "foreground" in theme
    assert "tableAccent" in theme


def test_theme_validate_clean_theme():
    gen = ThemeGenerator()
    theme = gen.generate("#0078D4", style="corporate")
    result = gen.validate_wcag(theme)
    assert "passes" in result
    assert "failures" in result
