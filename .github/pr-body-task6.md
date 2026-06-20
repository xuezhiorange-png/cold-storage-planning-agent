# Task 6: Formalize cold-room scheme generation and comparison

## Scope
Replace hardcoded scheme data (86/82/79 scores, static room counts) with deterministic, auditable, versioned scheme generation and comparison.

## Domain model
17 frozen dataclasses in `schemes/domain/models.py`:
- SchemeGenerationInput, ZoneResult, InvestmentResult, CoolingLoadResult, EquipmentResult
- SchemeProfile, SchemeRoomModule, SchemeCandidate
- SchemeConstraintResult, SchemeMetric, SchemeCriterionScore, SchemeScoreBreakdown
- SchemeComparisonResult, SchemeWeightSet, WeightCriterion, SchemeRun

## Scheme profiles
1. **balanced** — one room per Task 4 zone, preserves baseline
2. **consolidated_large_rooms** — merges temperature/process/hygiene-compatible zones
3. **segmented_small_rooms** — splits zones exceeding max_positions_per_room or max_area_per_room_m2

## Hard constraints
throughput_adequacy, storage_capacity_adequacy, pallet_position_adequacy, temperature_compatibility, process_separation, hygiene_separation, cooling_capacity_adequacy, compressor_capacity_adequacy, electrical_capacity_traceability, project_version_consistency

## Metrics
total_area_m2, total_position_count, room_module_count, door_count, partition_length_proxy_m, investment_cny, installed_power_kw_e, design_cooling_load_kw_r, compressor_installed_capacity_kw_r, condenser_heat_rejection_kw

## Weight governance
- SchemeWeightSet with explicit versioning
- Non-hard-constraint weights sum to exactly 1.0 (Decimal)
- Demo weight set: unverified, requires_review=true
- Withdrawn weight sets rejected

## Normalization and scoring
- higher_is_better: 100 × (x - min) / (max - min)
- lower_is_better: 100 × (max - x) / (max - min)
- All identical: score = 100
- Total score: 3 decimal places, ROUND_HALF_UP
- Stable tie-break: score → investment → power → scheme_code

## Persistence
- scheme_weight_sets (id, code, name, criteria JSONB)
- scheme_runs (project_id, version_id, status, snapshots, recommended)
- scheme_candidates (run_id, scheme_code, feasible, rank, score, result_snapshot)
- Alembic migration 0005

## API
- POST /api/v1/projects/{id}/versions/{v}/scheme-runs
- GET /api/v1/projects/{id}/versions/{v}/scheme-runs
- GET /api/v1/projects/{id}/versions/{v}/scheme-runs/{run_id}
- GET /api/v1/projects/{id}/versions/{v}/scheme-runs/{run_id}/comparison
- GET /api/v1/demo/scheme-comparison (demo endpoint)

## Frontend minimal integration
- Replaced hardcoded schemeRows with API-fetched data
- Replaced hardcoded comparisonRows with dynamic computation
- Removed static 86/82/79 scores
- Added recommended scheme marker (★)
- Added requires_review indicator
- Added feasibility status

## SQLite verification
457 passed, 12 skipped, 0 failed

## PostgreSQL verification
12 integration tests (scheme_weight_sets, scheme_runs, scheme_candidates, JSONB, FK, unique)

## Regression baselines
- Task 4: 1813.57 m², 346 positions, 1352.63 kW(e), 6150420.50 CNY — unchanged
- Task 5: compressor_input_power = operating / COP, condenser formula — unchanged

## Security scan
git grep secret scan: zero hits

## Not included
- Knowledge base retrieval
- OCR
- Agent conversation orchestration
- LLM-generated engineering data
- Word/Excel reports
- Construction drawings
- Manufacturer SKU selection
