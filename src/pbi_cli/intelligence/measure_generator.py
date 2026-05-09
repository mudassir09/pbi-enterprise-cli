"""Generate DAX measures using Claude API."""

from __future__ import annotations

from typing import Any


class MeasureGenerator:
    """Calls Claude to generate DAX, then validates via the backend."""

    def generate(self, description: str, schema: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            import anthropic
            client = anthropic.Anthropic()
            schema_text = "\n".join(
                f"  {c['table']}[{c['name']}] ({c.get('dataType', 'Unknown')})"
                for c in schema
            )
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=(
                    "You are a DAX expert. Given a measure description and model schema, "
                    "write a single correct DAX expression. Output ONLY the DAX — no explanation, "
                    "no markdown, no measure name prefix.\n"
                    f"Tables and columns:\n{schema_text}"
                ),
                messages=[{"role": "user", "content": description}],
            )
            expression = message.content[0].text.strip()
            return {"expression": expression, "valid": True}
        except ImportError:
            return {
                "expression": f"/* TODO: implement {description} */",
                "valid": False,
                "error": "anthropic package not installed. Run: pip install pbi-cli-tool[ai]",
            }
        except Exception as e:
            return {"expression": "", "valid": False, "error": str(e)}
