# ADR-014: Scheme Generation and Comparison

## Status

Accepted

## Context

Task 5 established traceable cooling-load and equipment-capability calculations. Task 6 builds on this by formalizing cold-room scheme generation and comparison — replacing the previous static hardcoded scheme data with deterministic, auditable, versioned scheme candidates.

The previous implementation had:
- Static scheme names ("平衡方案", "大冷间方案", "小冷间方案")
- Hardcoded scores (86, 82, 79)
- No domain logic for scheme generation
- No persistence of scheme runs
- No weight governance

## Decision

Implement a scheme generation and comparison module with:

### Three Deterministic Profiles

1. **balanced** — preserves Task 4 zone planning as-is, one room per zone
2. **consolidated_large_rooms** — merges temperature-compatible, process-compatible, hygiene-compatible zones to reduce room count
3. **segmented_small_rooms** — splits oversized zones by explicit thresholds (max_positions_per_room, max_area_per_room_m2)

### Hard Constraints

Each candidate must pass:
- throughput_adequacy
- storage_capacity_adequacy
- pallet_position_adequacy
- temperature_compatibility
- process_separation
- hygiene_separation
- cooling_capacity_adequacy
- compressor_capacity_adequacy
- electrical_capacity_traceability
- project_version_consistency

### Weight Governance

- Weights stored in `SchemeWeightSet` with explicit versioning
- Non-hard-constraint weights must sum to exactly 1.0 (Decimal)
- Demo weight set marked as "unverified"
- Withdrawn weight sets cannot be used

### Scoring

- Min-max normalization to 0-100 scale
- Decimal precision throughout
- Stable tie-break: score → investment → power → scheme_code
- Infeasible candidates excluded from recommendation

### Architecture Boundaries

- Domain: no FastAPI, SQLAlchemy, network, file system, LLM, knowledge base
- API: thin routing layer, no scoring formulas
- Frontend: fetches from backend, no score computation

## Consequences

- All scheme results are reproducible from input data
- Weight changes are auditable and version-controlled
- No hidden defaults in the scoring function
- Frontend displays real backend-computed results
