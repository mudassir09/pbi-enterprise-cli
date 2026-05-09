"""Unit tests for PbirBackend._find_projection and _find_projection_query_ref."""

from __future__ import annotations

from pbi_cli.backends.pbir_backend import PbirBackend


def _make_visual(projections: list[dict]) -> dict:
    """Build a minimal visual data dict with the given projections under 'Values'."""
    return {"visual": {"query": {"queryState": {"Values": {"projections": projections}}}}}


class TestFindProjection:
    """Tests for PbirBackend._find_projection (returns queryRef + field dict)."""

    def test_finds_aggregated_column(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Aggregation": {
                            "Expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "financials"}},
                                    "Property": "Sales",
                                }
                            },
                            "Function": 0,
                        }
                    },
                    "queryRef": "Sum(financials[Sales])",
                }
            ]
        )
        result = PbirBackend._find_projection(visual, "financials", "Sales")
        assert result is not None
        qr, field = result
        assert qr == "Sum(financials[Sales])"
        assert "Aggregation" in field

    def test_finds_plain_column(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": "financials"}},
                            "Property": "Segment",
                        }
                    },
                    "queryRef": "financials.Segment",
                }
            ]
        )
        result = PbirBackend._find_projection(visual, "financials", "Segment")
        assert result is not None
        qr, field = result
        assert qr == "financials.Segment"
        assert "Column" in field

    def test_finds_explicit_measure(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Measure": {
                            "Expression": {"SourceRef": {"Entity": "financials"}},
                            "Property": "Total Sales",
                        }
                    },
                    "queryRef": "[Total Sales]",
                }
            ]
        )
        result = PbirBackend._find_projection(visual, "financials", "Total Sales")
        assert result is not None
        qr, field = result
        assert qr == "[Total Sales]"
        assert "Measure" in field

    def test_returns_none_for_missing_field(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": "financials"}},
                            "Property": "Segment",
                        }
                    },
                    "queryRef": "financials.Segment",
                }
            ]
        )
        result = PbirBackend._find_projection(visual, "financials", "NonExistent")
        assert result is None

    def test_case_insensitive_match(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Aggregation": {
                            "Expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "Financials"}},
                                    "Property": "Sales",
                                }
                            },
                            "Function": 0,
                        }
                    },
                    "queryRef": "Sum(Financials[Sales])",
                }
            ]
        )
        result = PbirBackend._find_projection(visual, "financials", "sales")
        assert result is not None, "lookup must be case-insensitive"

    def test_finds_field_in_correct_role_among_multiple(self):
        """With multiple query roles (Category, Values), finds the right projection."""
        visual = {
            "visual": {
                "query": {
                    "queryState": {
                        "Category": {
                            "projections": [
                                {
                                    "field": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Entity": "financials"}},
                                            "Property": "Product",
                                        }
                                    },
                                    "queryRef": "financials.Product",
                                }
                            ]
                        },
                        "Values": {
                            "projections": [
                                {
                                    "field": {
                                        "Aggregation": {
                                            "Expression": {
                                                "Column": {
                                                    "Expression": {
                                                        "SourceRef": {"Entity": "financials"}
                                                    },
                                                    "Property": "Sales",
                                                }
                                            },
                                            "Function": 0,
                                        }
                                    },
                                    "queryRef": "Sum(financials[Sales])",
                                }
                            ]
                        },
                    }
                }
            }
        }
        result = PbirBackend._find_projection(visual, "financials", "Sales")
        assert result is not None
        qr, field = result
        assert qr == "Sum(financials[Sales])"

    def test_returns_none_for_empty_query_state(self):
        visual = {"visual": {"query": {"queryState": {}}}}
        assert PbirBackend._find_projection(visual, "financials", "Sales") is None

    def test_returns_none_for_missing_visual_key(self):
        assert PbirBackend._find_projection({}, "financials", "Sales") is None


class TestFindProjectionQueryRef:
    """Tests for backwards-compatible _find_projection_query_ref wrapper."""

    def test_returns_query_ref_string(self):
        visual = _make_visual(
            [
                {
                    "field": {
                        "Aggregation": {
                            "Expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "financials"}},
                                    "Property": "Profit",
                                }
                            },
                            "Function": 0,
                        }
                    },
                    "queryRef": "Sum(financials[Profit])",
                }
            ]
        )
        result = PbirBackend._find_projection_query_ref(visual, "financials", "Profit")
        assert result == "Sum(financials[Profit])"

    def test_returns_none_for_missing(self):
        result = PbirBackend._find_projection_query_ref({}, "financials", "X")
        assert result is None
