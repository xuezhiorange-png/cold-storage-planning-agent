# ADR-005 Project Versioning

## Status

Accepted

## Context

Cold-storage planning outputs must remain traceable across project iterations,
parameter changes, approvals, and report generation.

## Decision

Use immutable project versions as the core unit of planning state.

- projects have many versions
- approved versions are read-only
- calculation runs and reports attach to explicit project versions
- audit events record state transitions and attempted violations

## Alternatives Considered

- Mutable in-place project snapshots:
  rejected because they weaken traceability and reviewability.
- Ad hoc version strings without lifecycle rules:
  rejected because they are not enforceable enough for audit needs.

## Consequences

- Version approval rules become a central business invariant.
- Schema, service, and API work should be organized around version ownership.
- Future agent/report features must respect version immutability.
