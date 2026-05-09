# ADR-005: Ship Viz Intelligence as an optional install extra

**Status:** Accepted  
**Date:** 2026-05-05  
**Deciders:** pbi-cli architecture team

## Context

The Viz Intelligence layer (Epic C) — layout engine, theme generator with WCAG checking, visual recommender, and screenshot capture — requires heavy dependencies: Pillow (image processing), wcag-contrast-ratio (accessibility), and Playwright (headless browser for screenshots).

These dependencies add significant install weight (~200 MB with Playwright browser binaries) and are irrelevant to users who only need semantic model manipulation.

## Decision

Ship the Viz Intelligence dependencies as an optional install extra: `pip install pbi-cli-tool[viz]`. The base package does not include them.

## Rationale

- **Lean base install:** `pip install pbi-cli-tool` installs in seconds with no heavy binaries. This is appropriate for CI/CD pipelines, server environments, and semantic-model-only workflows.
- **Explicit opt-in:** Users who need visual layout, theme generation, or screenshot capabilities know they need the extra. The CLI provides clear error messages when viz commands are invoked without the extra installed.
- **Precedent:** This follows the established Python pattern for optional feature sets (e.g., `sqlalchemy[asyncio]`, `fastapi[all]`).

## Trade-offs

- **Discovery friction:** Users may not immediately know to install `[viz]` when they try a visual command. Mitigated by: informative error messages that print the exact `pip install` command needed.
- **Two install paths to document.** README and CONTRIBUTING.md must clearly describe the extras.

## Consequences

- `pyproject.toml` defines `viz = ["Pillow>=10.0", "python-wcag-contrast-ratio>=1.0"]` as an optional extra.
- `pbi layout auto`, `pbi theme generate`, `pbi visual screenshot` check for the extra at runtime and print install instructions if missing.
- `pbi-cli-tool[all]` installs all extras for development.
- Playwright browser installation (`playwright install chromium`) is a separate manual step documented in the README.
