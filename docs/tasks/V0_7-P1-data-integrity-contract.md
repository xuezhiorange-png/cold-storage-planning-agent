# V0.7 P1 Data Integrity Proof Contract

**Status:** Implementation R1 — data integrity proof and metadata matrix
**Authority:** Contract document is the freeze authority for P1 scope
**Parent contract:** `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Contract definition source SHA:** `468354dc13b7b5c5708095d4a766b4d42c9e3834`
**Contract definition source tree:** `468354dc13b7b5c5708095d4a766b4d42c9e3834`
**Previous release:** `v0.6.0`
**Target branch:** `cursor/v07-p1-data-integrity-6c68`

This document authorizes V0.7 P1 **data integrity proof** only. P1 proves
traceability and metadata completeness. It does not repair consumer hash
alignment, report DI, production-scheme routes, or calculator formulas.

## 0. Contract identity and governance

```text
TASK=V07_P1_DATA_INTEGRITY_PROOF_R1
PARENT_ISSUE=PENDING
P1_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
BASE_P0_SHA=468354dc13b7b5c5708095d4a766b4d42c9e3834
PREVIOUS_RELEASE=v0.6.0
TARGET_BRANCH=cursor/v07-p1-data-integrity-6c68
TARGET_FILE=docs/tasks/V0_7-P1-data-integrity-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=IMPLEMENTATION_R1
V07_P0_IMPLEMENTATION_AUTHORIZED=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=YES
V07_P2_IMPLEMENTATION_AUTHORIZED=NO
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=NO
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective and non-goals

### 1.1 Objective

Prove that the following chain is traceable on the existing five-stage
execution path without changing formulas or report assembly:

```text
EngineeringInputBundleV1
 → project_execution_snapshot_from_bundle
 → Phase2AdapterCalculatorPort / ZonePlanningAdapter typed input
 → persisted CalculationRunRecord (coefficients, assumptions, warnings, requires_review)
```

Establish a **default / unit / coefficient metadata integrity matrix** in
`docs/audit/data-integrity-matrix.md` and lock it with architecture and
integration tests.

For expert items **E1–E8** (from P0 §6), P1 MUST register `KNOWN_CONFLICT`
rows only. P1 MUST NOT choose conflicting values or promote demo coefficients.

### 1.2 Non-goals (hard boundaries)

```text
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
REPORT_FORMULA_RECALCULATION=NO
CALCULATOR_FORMULA_EDITS=NO
REPORT_ASSEMBLER_EDITS=NO
SCHEME_ROUTE_EDITS=NO
BOOTSTRAP_APP_EDITS=NO
FRONTEND_FORMULA_EDITS=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

P1 must not:

- edit `backend/src/cold_storage/modules/calculations/domain/**` formulas;
- edit report assembler mapping or templates;
- edit `schemes/api/routes.py` or `bootstrap/app.py`;
- resolve E1–E8 by picking a winning value;
- change zone planner gold-standard numeric expectations.

## 2. Inherited authority

| Frozen item | Authority |
| --- | --- |
| P0 package DAG and Wave 1 disjoint allowlists | `V0_7-P0-trust-loop-contract.md` |
| `EngineeringInputBundleV1` KEY zone projection | `engineering_input_bundle.py` `_KEY_ZONE_FIELDS` |
| Five-stage execution snapshot authority | `five_stage_execution.py` |
| Demo coefficient audit metadata | `DemoZoneCoefficient.to_reference()` |
| Dual seed tracks | `seed_catalog` vs `seed_demo_coefficients` |

## 3. Proof surfaces

### 3.1 Bundle → execution snapshot

`project_execution_snapshot_from_bundle` MUST project bundle KEY zone leaves
onto `execution_snapshot["zone"]` with stable decimal string values.

### 3.2 Execution snapshot → calculator input

`ZonePlanningAdapter` MUST receive only dataclass-allowed fields from the zone
stage snapshot. Unspecified fields MUST fall back to `ColdRoomZonePlanInput`
defaults (not silently rewritten by P1).

### 3.3 Persisted audit metadata

Zone stage `CalculationRunRecord` MUST persist:

- `coefficients` with `source_type=demo`, `validity_status=unverified`,
  `requires_review=true` for embedded demo coefficients;
- `assumptions` and `warnings` from calculator output;
- `requires_review=true` on the run row.

### 3.4 Metadata integrity matrix

`docs/audit/data-integrity-matrix.md` MUST list every demo/conflict leaf with
either:

- `consumer=<path>` — an explicit runtime consumer; or
- `non_consumer=<reason>` — metadata-only or unused-by-formula.

### 3.5 KNOWN_CONFLICT register (E1–E8)

| ID | Conflict | P1 action |
| --- | --- | --- |
| E1 | `frozen_fruit_ratio` Input default vs `DemoZoneCoefficient` | `KNOWN_CONFLICT` only |
| E2 | `frozen_storage_days` Input default vs `DemoZoneCoefficient` | `KNOWN_CONFLICT` only |
| E3 | `storage_position_capacity_kg` Input default vs `DemoZoneCoefficient` | `KNOWN_CONFLICT` only |
| E4 | `packaging_storage_days` legacy fallback vs orchestration KEY path | `KNOWN_CONFLICT` only |
| E5 | `precooling_required_ratio` legacy fallback vs orchestration KEY path | `KNOWN_CONFLICT` only |
| E6 | `investment.electrical_installation_ratio` registry vs embedded `power_distribution_cost_cny_kw` | `KNOWN_CONFLICT` only |
| E7 | `seed_catalog` vs `seed_demo_coefficients` runtime authority | `KNOWN_CONFLICT` only |
| E8 | `raw_holding_hours` in input/metadata but unused by zone formula | `non_consumer` registration |

### 3.6 Seed dual-track lock

`seed_catalog` (domain catalog manifest, `source_type=standard`, approved
placeholder `1.0`) and `seed_demo_coefficients` (`source_type=demo`,
`status=unverified`) MUST remain separate tracks. P1 tests MUST lock both
without merging them.

## 4. Exclusive allowlist

```text
V07_P1_FILE_ALLOWLIST
docs/tasks/V0_7-P1-data-integrity-contract.md
docs/audit/coefficient-inventory.md
docs/audit/data-integrity-matrix.md
backend/tests/architecture/test_v07_p1_data_integrity_contract.py
backend/tests/architecture/test_v07_p1_default_alignment_matrix.py
backend/tests/architecture/test_v07_p1_coefficient_metadata_alignment.py
backend/tests/integration/test_v07_p1_bundle_execution_traceability.py
backend/tests/integration/test_v07_p1_version_snapshot_authority.py
backend/tests/integration/test_v07_p1_seed_authority.py
```

## 5. Acceptance criteria

```text
P1_CONTRACT_EXISTS=PASS
BUNDLE_EXECUTION_SNAPSHOT_TRACEABLE=PASS
CALCULATOR_INPUT_TRACEABLE=PASS
PERSISTED_COEFFICIENTS_ASSUMPTIONS_WARNINGS_TRACEABLE=PASS
DEFAULT_UNIT_COEFFICIENT_MATRIX_EXISTS=PASS
E1_E8_KNOWN_CONFLICT_REGISTERED=PASS
DEMO_CONFLICT_LEAF_CONSUMER_OR_NON_CONSUMER=PASS
SEED_CATALOG_DEMO_DUAL_TRACK_LOCKED=PASS
ZONE_PLANNER_GOLD_NUMERIC_UNCHANGED=PASS
ARCHITECTURE_TESTS_PASS=PASS
INTEGRATION_TESTS_PASS=PASS
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative test surfaces:

```text
backend/tests/architecture/test_v07_p1_data_integrity_contract.py
backend/tests/architecture/test_v07_p1_default_alignment_matrix.py
backend/tests/architecture/test_v07_p1_coefficient_metadata_alignment.py
backend/tests/integration/test_v07_p1_bundle_execution_traceability.py
backend/tests/integration/test_v07_p1_version_snapshot_authority.py
backend/tests/integration/test_v07_p1_seed_authority.py
```

## 6. Contract closure state

```text
TASK=V07_P1_DATA_INTEGRITY_PROOF_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P1-data-integrity-contract.md

V07_P1_CONTRACT_FROZEN=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=YES
V07_P1_CONTRACT_EXECUTED=YES
FORMULA_RECUT_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 7. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P1 data integrity proof contract on P0 branch `468354dc` |
