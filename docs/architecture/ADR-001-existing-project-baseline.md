# ADR-001 Existing Project Baseline

## Status

Accepted

## Context

The repository already contained a local cold-storage planning implementation,
but its Git remote history was previously misconfigured and could not be pushed
directly to the target GitHub repository without carrying unrelated history.

## Decision

Preserve the existing local code as the baseline snapshot while:

- recording the original local HEAD on a local preservation branch
- rebasing the baseline push strategy onto the target repository's current
  `main`
- creating a clean baseline commit that preserves the current code tree without
  force-pushing or rewriting remote history

## Alternatives Considered

- Push the existing local `main` directly:
  rejected because it would carry unrelated Git history.
- Reinitialize the repository:
  rejected because it would discard useful local history and violate the
  preservation requirement.

## Consequences

- The current code tree is preserved on GitHub.
- The incorrect historical remote relationship is not propagated into the target
  repository's visible mainline.
- Local preservation references remain available for audit and rollback.
