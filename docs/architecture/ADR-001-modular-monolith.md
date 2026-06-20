# ADR-001 Modular Monolith

- Status: Accepted
- Context: V1 needs clear module boundaries without microservice overhead.
- Decision: Use a module-first modular monolith under `backend/src/cold_storage/modules`.
- Alternatives: Microservices, layered global directories.
- Consequences: Faster local development with explicit dependency rules enforced by architecture tests.
