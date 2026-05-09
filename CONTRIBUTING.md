# Contributing to pbi-cli

## Quick Start

```bash
git clone https://github.com/yourusername/pbi-cli
cd pbi-cli
pip install -e ".[dev]"
pytest -m "not e2e"
```

## Writing Tests Without Power BI Desktop

Use `MockTomBackend` for all unit and integration tests. No Windows or Power BI Desktop required.

```python
from pbi_cli.backends.mock_backend import MockTomBackend

def test_my_command():
    backend = MockTomBackend()
    backend.connect()
    result = backend.measure_add("Sales", "My Measure", "SUM(Sales[Revenue])")
    assert result["name"] == "My Measure"
```

Use the CLI runner for integration tests:

```python
from click.testing import CliRunner
from pbi_cli.cli import cli

def test_measure_add_cli():
    runner = CliRunner()
    result = runner.invoke(cli, ["--backend", "mock", "measure", "add",
                                  "--table", "Sales", "--name", "Test",
                                  "--expression", "1"])
    assert result.exit_code == 0
```

## Skill Authoring Guide

Skills live in `skills/<skill-name>/SKILL.md`. Required frontmatter:

```yaml
---
name: power-bi-<domain>
description: >
  Use when <specific trigger conditions>. Triggers on: <comma-separated keywords>.
  Do NOT trigger for <exclusions>.
version: "1.0"
---
```

Rules:
- `description` must include `Use when`, `Triggers on:`, and `Do NOT trigger for` sections
- All `pbi` commands referenced must exist and be tested
- Include at least 3 concrete usage examples

## Adding a Governance Rule

1. Create `src/pbi_cli/governance/rules/<rule_name>.py`
2. Implement the `check(backend) -> list[dict]` function
3. Register in `src/pbi_cli/governance/engine.py`
4. Add a test in `tests/unit/test_governance_<rule_name>.py` using `MockTomBackend`

Rule dict format:
```python
{
    "rule": "rule-name-kebab-case",
    "object": "Table 'Sales'",
    "message": "Human-readable violation description",
    "severity": "error" | "warning" | "info",
    "autoFixable": True | False,
}
```

## ADR Template

Create `docs/adr/NNN-short-title.md` when:
- Choosing between two viable technical approaches
- Accepting a significant trade-off (licensing, performance, compatibility)
- Reversing a previous decision

Required sections: **Context**, **Decision**, **Rationale**, **Trade-offs**, **Consequences**.

## DAX Test Fixture Guide

Test fixtures live in `tests/fixtures/measures/*.yaml`. Format:

```yaml
suite: "Suite Name"
connection: mock  # always mock for CI; use desktop for e2e
tests:
  - name: "Descriptive test name"
    measure: "TableName[MeasureName]"
    filters: []
    expected: 12345
    tolerance: 0.01  # 1% for float; omit for exact integer match
```

Run: `pbi dax test --suite tests/fixtures/measures/my_suite.yaml`
