# ADR-004 Incremental Refactoring

## Status

Accepted

## Context

The repository already contains runnable code and tests. Replacing everything at
once would create unnecessary risk and destroy the audit trail.

## Decision

Use incremental replacement only.

- Do not do a one-shot rewrite.
- Replace behavior module by module.
- Keep old behavior working until the new implementation is validated.
- Delete old code only after searching callers and adding regression tests.
- Move one bounded module or responsibility area per task/PR.

## Alternatives Considered

- Full rewrite before stabilization:
  rejected because it would erase valuable baseline behavior and inflate risk.
- Large horizontal refactor across all layers:
  rejected because it would make validation and rollback too broad.

## Consequences

- Review scope stays manageable.
- Regression testing becomes a required gate for code removal.
- Temporary duplication is acceptable when it is explicitly tracked and time-boxed.
