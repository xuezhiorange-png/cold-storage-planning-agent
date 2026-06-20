# ADR-011 Engineering Coefficient Registry

- Status: Accepted
- Date: 2026-06-20

## Context

Engineering coefficients (area ratios, power factors, cost parameters) were previously hardcoded across multiple modules. This made them difficult to govern, audit, and version. Different code paths used inconsistent values, and there was no mechanism to track which coefficients were used in historical calculations.

## Decision

### Project Input vs Engineering Coefficient

**Project Input**: Values specific to a project instance (daily throughput, storage days, electricity price). These vary per project and are stored in ProjectVersion.input_snapshot.

**Engineering Coefficient**: Global or scoped engineering parameters (area ratios, power factors, cost per m²). These are shared across projects and managed in the coefficient registry.

**Formula Constant**: Mathematical constants and unit conversions (1000 W/kW, 24 hours/day). These remain in code and are NOT stored in the registry.

### Definition / Revision Split

**CoefficientDefinition** holds stable identity:
- code: unique identifier (e.g., "area.circulation_allowance_ratio")
- name, description, category, canonical_unit
- value_type (decimal or json)
- scope_type (global, product, zone, process, project, project_version)

**CoefficientRevision** holds versioned values:
- value_decimal or value_json
- status (draft → unverified → reviewed → approved → withdrawn)
- source metadata (type, title, reference, page)
- applicability filters (product_type, zone_type, process_type)
- supersedes_revision_id for version lineage

### State Machine

```
draft → unverified → reviewed → approved → withdrawn
draft → reviewed → approved → withdrawn
```

Rules:
- **Approved revisions cannot be modified**
- **Withdrawn revisions cannot be reactivated**
- revision_number unique per definition
- supersedes_revision_id cannot cross definitions

### Source Tracking

Every revision must record:
- source_type: standard, book, manufacturer, enterprise_standard, historical_project, engineering_judgement, demo, unknown
- source_title, source_reference, source_page
- valid_from, valid_to (temporal validity)
- requires_review flag (auto-set for non-approved)

### Scope Resolution Priority

When resolving coefficients for calculations:
1. Project version explicit specification
2. Project-level specification
3. Product + zone + process match
4. Product match
5. Global default

Conflict detection: multiple approved revisions at the same scope level raise error.

### CoefficientSet Boundary

Deterministic calculators receive an immutable CoefficientSet:
```python
CoefficientSet(
    items={"area.circulation_allowance_ratio": CoefficientValue(...)},
    schema_version="1.0",
    captured_at=datetime.now(UTC)
)
```

**Calculators NEVER access the database directly.** The call chain is:
```
API → Application Service → Coefficient Resolver → CoefficientSet → Calculator
```

### Project Version Snapshot Integration

Each calculation records the CoefficientSet used:
```json
{
  "schema_version": "1.0",
  "captured_at": "ISO-8601",
  "items": {
    "area.circulation_allowance_ratio": {
      "code": "area.circulation_allowance_ratio",
      "revision_id": "...",
      "revision_number": 1,
      "value": "1.15",
      "unit": "ratio",
      "status": "unverified",
      "source_type": "demo",
      "requires_review": true
    }
  }
}
```

Historical snapshots remain valid even if coefficients are later withdrawn.

### Demo and Unknown Parameters

Demo coefficients are explicitly marked:
- source_type=demo
- status=unverified
- requires_review=true

They are usable for demonstrations but always return warnings.

## Consequences

### Positive
- Centralized coefficient governance with full audit trail
- Temporal validity tracking for regulatory compliance
- Scope-aware resolution for different product types
- Immutable snapshots ensure calculation reproducibility
- Clear separation between identity (Definition) and state (Revision)

### Negative
- More complex than hardcoded constants
- Requires governance workflow for coefficient updates
- Additional database tables and migration complexity

### Risks
- Performance impact of resolving coefficients for each calculation
- Governance overhead for maintaining accurate source references

## Alternatives Considered

1. **Hardcoded constants**: Simple but ungovernable
2. **Configuration files**: Easier than DB but loses audit trail
3. **Environment variables**: No versioning or governance

## References

- ADR-010: Project Versioning and Immutability
- docs/audit/coefficient-inventory.md
