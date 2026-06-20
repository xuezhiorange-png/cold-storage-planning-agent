# ADR-012 Deterministic Core Calculation Kernel

- Status: Accepted
- Date: 2026-06-20

## Context

The Cold Storage Planning Agent needs a stable, traceable, deterministic calculation kernel for core planning parameters. Previous calculations were scattered across multiple modules with inconsistent input handling, rounding, and error management. The system must produce auditable engineering results that can be traced to specific inputs, coefficients, and calculation steps.

## Decision

### Deterministic Calculation Boundary

All engineering calculations are performed by pure Python calculators:
- **No database access** in calculators
- **No network access** in calculators
- **No FastAPI dependency** in calculators
- **No environment variable access** in calculators
- **Input相同 → Output完全相同** (deterministic)

### Input and Output Models

**CalculationInput** (frozen dataclass):
- All values as `Decimal` for precision
- Clear unit annotations
- Source tracking (project input, coefficient, default)

**CalculationResult** (frozen dataclass):
- `calculator_name`: identifies the calculator
- `calculator_version`: for reproducibility
- `input_snapshot`: exact inputs used
- `result`: computed outputs
- `steps`: step-by-step traceability
- `coefficient_references`: which coefficients were used
- `warnings`: non-blocking issues
- `requires_review`: flag for unverified inputs

### Decimal Strategy

All engineering values use `decimal.Decimal`:
- Quantities (kg, t)
- Time (h, day)
- Efficiency ratios
- Area (m²)
- Power (kW)
- Cost (CNY)

Binary `float` is only used for API serialization, never in calculation logic.

### Unit Management

Centralized unit conversions in `units.py`:
```python
class Unit(StrEnum):
    KG = "kg"
    TONNE = "t"
    HOUR = "h"
    DAY = "day"
    PERSON = "person"
    PALLETS = "pallet"
    SQUARE_METRE = "m2"
    RATIO = "ratio"
    PERCENT = "percent"
```

Conversions: `tonnes_to_kg`, `kg_to_tonnes`, `hours_to_days`, `days_to_hours`

### Rounding Policy

| Value Type | Rounding | Example |
|------------|----------|---------|
| Position counts | `math.ceil()` | 63.2 → 64 |
| Area display | `round(..., 2)` | 1813.571 → 1813.57 |
| Tonnage display | `round(..., 2)` | 25.123 → 25.12 |
| Worker count | `math.ceil()` | 4.3 → 5 |
| Pallet count | `math.ceil()` | 187.2 → 188 |
| Batch count | `math.ceil()` | 2.1 → 3 |
| Room count | `math.ceil()` | 1.8 → 2 |
| Intermediate values | No rounding | Keep full precision |

### CoefficientSet Integration

Calculators receive an immutable `CoefficientSet`:
```python
@dataclass(frozen=True)
class CoefficientSet:
    items: dict[str, CoefficientValue]
    schema_version: str
    captured_at: datetime
```

Rules:
- Calculators only use explicitly provided coefficients
- Missing coefficients raise `CoefficientMissingError`
- Non-approved coefficients trigger `requires_review=true`
- No hidden defaults in calculators

### ProjectVersion Snapshots

Each calculation saves to ProjectVersion:
```json
{
  "schema_version": "1.0",
  "calculated_at": "ISO-8601",
  "calculator_version": "core-planning-1.0",
  "inputs": {},
  "coefficients": {},
  "results": {
    "throughput": {},
    "inventory": {},
    "pallets": {},
    "precooling": {},
    "areas": {}
  },
  "warnings": [],
  "requires_review": true
}
```

### Calculation Flow

```
Read ProjectVersion inputs
→ Validate required fields
→ Resolve CoefficientSet
→ Throughput calculation
→ Inventory calculation
→ Pallet calculation
→ Precooling calculation
→ Area calculations (per zone)
→ Area summary
→ Consistency checks
→ Save snapshot
```

### Error and Warning Types

**Blocking Errors:**
- `MissingCalculationInputError`: required field missing
- `InvalidCalculationInputError`: field value invalid
- `CoefficientMissingError`: required coefficient not in set
- `CoefficientConflictError`: multiple approved coefficients at same scope
- `CapacityShortfallError`: capacity cannot meet demand
- `LockedProjectVersionError`: version is approved/archived

**Non-blocking Warnings:**
- Using demo/unverified coefficients
- Capacity utilization too high
- Precooling margin insufficient
- Worker count exceeds range
- Area utilization abnormal
- Supporting facilities not included

### Consistency Checks

After calculation:
- Total area = sum of zone design areas
- Pallet positions ≥ design pallet requirement
- Precooling capacity ≥ design precooling requirement
- Processing capacity ≥ peak demand (or report shortfall)
- Worker count matches efficiency assumptions
- Result units consistent
- Coefficient references complete

## Consequences

### Positive
- Fully traceable calculations with step-by-step audit
- Deterministic results enable regression testing
- Decimal precision prevents floating-point errors
- CoefficientSet injection ensures auditable parameter usage
- Snapshots preserve exact calculation context

### Negative
- More verbose than simple float calculations
- Requires governance for coefficient management
- Additional model complexity for input/output

### Risks
- Performance impact of Decimal arithmetic (acceptable for planning)
- Governance overhead for maintaining coefficient accuracy

## Alternatives Considered

1. **Float arithmetic**: Simpler but prone to precision errors
2. **Configuration-driven formulas**: More flexible but harder to audit
3. **Spreadsheet-based**: Familiar but not version-controlled

## References

- ADR-010: Project Versioning and Immutability
- ADR-011: Engineering Coefficient Registry
- docs/calculations/core-calculation-specification.md
- docs/calculations/rounding-policy.md
