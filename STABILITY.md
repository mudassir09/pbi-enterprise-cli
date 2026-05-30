# API Stability Policy

Commands marked **[stable]** below are guaranteed stable across all patch and minor
releases within the 4.x series. Breaking changes require a major version bump and a
minimum **90-day deprecation notice** with a `DeprecationWarning` printed at runtime.

## Stable Commands (guaranteed in 4.x)

```
pbi model    [tables|columns|relationships|lint|lineage]
pbi measure  [list|add|update|delete]
pbi dax      [query|validate|test]
pbi source   [profile|scaffold]
pbi report   [pages|bookmarks]
pbi visual   [add|update|delete]
pbi layout   [apply|template]
pbi theme    [generate|apply]
pbi govern   [check|fix|rules|bpa]
pbi security [roles|add|delete|test]
pbi deploy   [snapshot|diff|push]
pbi snapshot [create|list|restore|diff]
pbi database [export|import]
pbi docs     [generate]
pbi skills   [list|install|uninstall|check]
pbi env      [list|use|diff|promote]
pbi connections [list|add|test|remove]
pbi server   [start|generate-key]
```

## Exit Code Contract (stable)

| Code | Meaning |
|------|---------|
| 0 | Success — no violations, no errors |
| 1 | User error — bad arguments, missing flags, unknown command |
| 2 | Connection error — Desktop not open, XMLA unreachable |
| 3 | Validation error — governance violation, schema error |
| 4 | Operation error — TOM write failed, partial completion |

## Deprecation Process

1. A `[DEPRECATED]` notice is printed when the deprecated command is used.
2. A 90-day minimum deprecation window begins at the first release containing the notice.
3. The command is removed in the next major version after the window expires.
4. The CHANGELOG.md documents the removal date.

## Experimental Commands

Commands marked `[experimental]` in `pbi --help` output have no stability guarantee
and may change or be removed in any release without a deprecation window.
