# ADR-004 Coefficient Registry

- Status: Accepted
- Context: Key engineering coefficients must not be magic numbers.
- Decision: Coefficients carry code, version, source, approval status, validity status, and review flags.
- Alternatives: Constants in calculator code.
- Consequences: Demo values are visible and reviewable; calculator inputs are more verbose.
