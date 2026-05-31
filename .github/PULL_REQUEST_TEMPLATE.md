## Summary

<!-- What does this PR do? One paragraph is enough. Link to the issue it closes if applicable. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New command / feature
- [ ] Skill update (SKILL.md)
- [ ] Governance rule
- [ ] CI/CD / tooling
- [ ] Documentation

## Checklist

- [ ] `ruff check src/ tests/` passes with no errors
- [ ] `mypy src/` passes (or new ignores are documented)
- [ ] Tests added or updated for the change
- [ ] `pytest -m "not e2e"` passes locally
- [ ] `pbi --backend mock <affected-commands>` tested manually
- [ ] CHANGELOG.md updated under `[Unreleased]`

## For skill changes

- [ ] SKILL.md frontmatter updated (`version` bumped, `min_cli_version` correct)
- [ ] New worked examples added if scope expanded
- [ ] Cross-skill handoffs reviewed

## Testing notes

<!-- How did you test this? What edge cases did you check? -->
