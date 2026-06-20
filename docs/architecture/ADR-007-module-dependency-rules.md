# ADR-007 Module Dependency Rules

- Status: Accepted
- Context: V1 has several business modules and needs guardrails against cross-layer erosion.
- Decision: Enforce API to Application to Domain dependencies; infrastructure implements ports only.
- Alternatives: Allow direct cross-module ORM access.
- Consequences: More application services and tests, but less coupling and safer refactoring.
