"""Generate WCAG-compliant Power BI theme JSON from a brand colour."""

from __future__ import annotations

import colorsys
import re
from typing import Any


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _relative_luminance(r: float, g: float, b: float) -> float:
    def linearise(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearise(r) + 0.7152 * linearise(g) + 0.0722 * linearise(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = _relative_luminance(*_hex_to_rgb(hex1))
    l2 = _relative_luminance(*_hex_to_rgb(hex2))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _darken(hex_color: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    v = max(0.0, v - amount)
    return _rgb_to_hex(*colorsys.hsv_to_rgb(h, s, v))


def _lighten(hex_color: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    v = min(1.0, v + amount)
    return _rgb_to_hex(*colorsys.hsv_to_rgb(h, s, v))


class ThemeGenerator:
    def generate(self, brand_color: str, style: str = "corporate") -> dict[str, Any]:
        primary = brand_color
        p_dark1 = _darken(primary, 0.15)  # slot 2: darker variant
        p_dark2 = _darken(primary, 0.30)  # slot 5: deep dark
        p_light1 = _lighten(primary, 0.25)  # slot 3: medium light
        p_light2 = _lighten(primary, 0.50)  # slot 4: light tint

        # Complementary accent — rotate hue 150 degrees
        r, g, b = _hex_to_rgb(primary)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        accent = _rgb_to_hex(
            *colorsys.hsv_to_rgb((h + 150 / 360) % 1.0, s * 0.8, min(v + 0.1, 1.0))
        )

        neutral = "#605E5C"
        warning = "#FFB900"

        is_dark = style == "dark"
        background = "#1A1A2E" if is_dark else "#FFFFFF"
        foreground = "#F0F0F0" if is_dark else "#252423"
        bg_light = "#2A2A3E" if is_dark else "#F3F2F1"

        data_colors = [primary, p_dark1, p_light1, accent, p_light2, p_dark2, neutral, warning]

        # Build style-specific visualStyles
        card_label_color = "#F0F0F0" if is_dark else primary
        header_bg = primary

        return {
            "name": f"pbi-cli {style}",
            "dataColors": data_colors,
            "background": background,
            "backgroundLight": bg_light,
            "foreground": foreground,
            "tableAccent": primary,
            "visualStyles": {
                "*": {
                    "*": {
                        "fontSize": [{"value": 11}],
                        "fontFamily": [{"value": "Segoe UI"}],
                        "background": [{"color": {"solid": {"color": background}}}],
                    }
                },
                "card": {
                    "*": {
                        "labels": [
                            {
                                "color": {"solid": {"color": card_label_color}},
                                "fontSize": 28,
                                "fontFamily": "Segoe UI Light",
                            }
                        ],
                        "categoryLabels": [
                            {
                                "color": {"solid": {"color": neutral}},
                                "fontSize": 10,
                            }
                        ],
                    }
                },
                "tableEx": {
                    "*": {
                        "header": [
                            {
                                "fontColor": {"solid": {"color": "#FFFFFF"}},
                                "backColor": {"solid": {"color": header_bg}},
                                "fontSize": 10,
                                "fontFamily": "Segoe UI",
                                "bold": True,
                            }
                        ],
                        "values": [
                            {
                                "fontSize": 9,
                                "fontFamily": "Segoe UI",
                            }
                        ],
                    }
                },
                "slicer": {
                    "*": {
                        "header": [
                            {
                                "fontColor": {"solid": {"color": primary}},
                                "fontSize": 10,
                                "bold": True,
                            }
                        ],
                    }
                },
                "barChart": {
                    "*": {
                        "categoryAxis": [{"fontSize": 9, "fontFamily": "Segoe UI"}],
                        "valueAxis": [{"fontSize": 9, "fontFamily": "Segoe UI"}],
                    }
                },
                "lineChart": {
                    "*": {
                        "categoryAxis": [{"fontSize": 9, "fontFamily": "Segoe UI"}],
                        "valueAxis": [{"fontSize": 9, "fontFamily": "Segoe UI"}],
                    }
                },
            },
        }

    def validate_wcag(self, theme: dict[str, Any]) -> dict[str, Any]:
        failures = []
        bg = theme.get("background", "#FFFFFF")
        fg = theme.get("foreground", "#000000")
        ratio = _contrast_ratio(fg, bg)
        if ratio < 4.5:
            failures.append(
                {
                    "pair": f"{fg} on {bg}",
                    "ratio": round(ratio, 2),
                    "required": 4.5,
                    "element": "body text",
                }
            )
        for i, color in enumerate(theme.get("dataColors", [])):
            r = _contrast_ratio(color, bg)
            if r < 3.0:
                failures.append(
                    {
                        "pair": f"dataColor[{i}] {color} on {bg}",
                        "ratio": round(r, 2),
                        "required": 3.0,
                        "element": "UI component",
                    }
                )
        return {"passes": len(failures) == 0, "failures": failures}

    def fix_contrast(self, theme: dict[str, Any], failures: list[dict]) -> dict[str, Any]:
        bg = theme.get("background", "#FFFFFF")
        fixed_colors = list(theme.get("dataColors", []))
        for failure in failures:
            if "dataColor" in failure.get("element", ""):
                idx = int(re.search(r"\[(\d+)\]", failure["pair"]).group(1))  # type: ignore[union-attr]
                color = fixed_colors[idx]
                for _ in range(20):
                    if _contrast_ratio(color, bg) >= 3.0:
                        break
                    color = _darken(color, 0.05)
                fixed_colors[idx] = color
        return {**theme, "dataColors": fixed_colors}
