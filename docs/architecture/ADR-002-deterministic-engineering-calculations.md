# ADR-002 Deterministic Engineering Calculations

- Status: Accepted
- Context: Engineering values must be traceable and reproducible.
- Decision: All numerical engineering calculations are performed by deterministic Python calculators.
- Alternatives: Model-generated calculations or formulas embedded in prompts.
- Consequences: Agent output remains explainable; calculators require more explicit schemas and tests.
