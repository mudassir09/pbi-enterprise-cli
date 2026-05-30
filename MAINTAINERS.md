# Maintainers

## Core Team

| Name | GitHub | Role |
|------|--------|------|
| Mudassir | @mudassir09 | Creator & Lead Maintainer |

## Support Policy

- **Issues:** Best-effort response within 7 days.
- **Security issues:** See [SECURITY.md](SECURITY.md) — 48-hour acknowledgement SLA.
- **Breaking changes:** 90-day deprecation notice required (see [STABILITY.md](STABILITY.md)).

## Becoming a Maintainer

Contributors with 3+ merged PRs that include tests may be invited to maintainer status.
Open an issue titled "Maintainer nomination: <GitHub username>" to start the process.

## Release Process

1. All CI checks must pass on `main`.
2. `CHANGELOG.md` updated with release notes.
3. Version bumped in `pyproject.toml`.
4. Tag pushed: `git tag vX.Y.Z && git push --tags`.
5. GitHub Actions `release.yml` publishes to PyPI automatically.
