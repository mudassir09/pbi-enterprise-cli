"""Recommend Power BI visual types for a given set of measures."""

from __future__ import annotations

VISUAL_RULES = [
    (
        {"revenue", "sales", "amount", "total"},
        "Clustered Bar Chart",
        "Good for comparing amounts across categories",
    ),
    ({"ytd", "yoy", "mom", "trend", "growth"}, "Line Chart", "Time series and trend analysis"),
    ({"kpi", "target", "actual", "vs"}, "KPI Card", "Show performance against a target"),
    ({"rate", "ratio", "%", "percent"}, "Gauge", "Proportion and completion rates"),
    ({"region", "country", "city", "location"}, "Map", "Geographic distribution"),
    ({"rank", "top", "bottom"}, "Bar Chart (sorted)", "Ranking visualisation"),
]


class VisualRecommender:
    def recommend(self, measures: list[str]) -> list[dict]:
        measure_text = " ".join(measures).lower()
        recommendations = []
        for keywords, visual_type, rationale in VISUAL_RULES:
            if any(kw in measure_text for kw in keywords):
                recommendations.append(
                    {
                        "visual": visual_type,
                        "rationale": rationale,
                        "matchedMeasures": [
                            m for m in measures if any(kw in m.lower() for kw in keywords)
                        ],
                    }
                )
        if not recommendations:
            recommendations.append(
                {
                    "visual": "Table",
                    "rationale": "Default fallback for tabular data",
                    "matchedMeasures": measures,
                }
            )
        return recommendations
