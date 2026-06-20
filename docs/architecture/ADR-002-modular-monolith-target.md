# ADR-002 Modular Monolith Target

## Status

Accepted

## Context

The project needs clear ownership boundaries across API, application, domain,
and infrastructure without the operational cost of microservices.

## Decision

Target a module-first modular monolith:

- backend modules live under `backend/src/cold_storage/modules/<module>/`
- dependency direction is `API -> Application -> Domain`
- infrastructure implements persistence and external adapters behind module
  boundaries

## Alternatives Considered

- Microservices:
  rejected because current scope and team cadence do not justify the complexity.
- Flat layered global directories:
  rejected because they make business ownership and gradual refactoring harder.

## Consequences

- Incremental refactoring can proceed module by module.
- Architecture tests can enforce dependency rules.
- Existing code that violates these rules must be moved gradually rather than
  rewritten wholesale.
