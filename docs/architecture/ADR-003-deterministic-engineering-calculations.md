# ADR-003 Deterministic Engineering Calculations

## Status

Accepted

## Context

Cold-room planning outputs must be explainable, reproducible, and reviewable.
Large-model output alone is not sufficient for engineering values.

## Decision

All engineering numbers must be produced by deterministic Python calculation
services. Model-driven components may extract intent, suggest parameter changes,
or explain results, but they must not be the source of truth for engineering
math.

## Alternatives Considered

- Let the LLM calculate engineering values directly:
  rejected because results would not be deterministic or auditable enough.
- Embed formulas in frontend or report templates:
  rejected because it creates drift and weakens traceability.

## Consequences

- Calculation services become the primary source of engineering truth.
- Every result must carry formula, coefficient, source, and review metadata.
- Refactoring effort must move formula logic out of API/bootstrap helpers.
