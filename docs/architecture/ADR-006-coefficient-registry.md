# ADR-006 Coefficient Registry

## Status

Accepted

## Context

The current baseline keeps many planning coefficients as embedded demo constants.
That is sufficient for a local prototype but not for governed engineering use.

## Decision

Introduce a coefficient registry with explicit metadata:

- code, name, value, unit, category
- source type and source reference
- version
- validity status
- approval status
- `requires_review`

Calculators should eventually read coefficient inputs through this registry
instead of relying on scattered embedded literals.

## Alternatives Considered

- Leave coefficients only in code:
  rejected because review, provenance, and change tracking are too weak.
- Move all coefficients into prompts or frontend config:
  rejected because that breaks deterministic governance.

## Consequences

- Coefficient changes become auditable.
- Demo coefficients can coexist with reviewed coefficients without ambiguity.
- Current embedded coefficients remain temporary debt until Task 3 lands.
