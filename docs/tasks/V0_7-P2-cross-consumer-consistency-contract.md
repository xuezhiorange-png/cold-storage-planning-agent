# V0.7 P2 Cross-Consumer Consistency Contract

**Status:** Implementation R1 — logic proof and CI evidence
**Authority:** Child of `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Parent contract SHA:** `f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba`
**Target branch:** `cursor/v07-p2-cross-consumer-consistency-6c68`

This package **proves** that canonical five-stage results are consumed
consistently across API persistence, SourceBinding, scheme, workflow, and
report surfaces. It does **not** repair production consumer hash helpers
(that is P2b). It does **not** change calculator formulas, `bootstrap/app.py`,
or scheme production routes.

## 0. Contract identity and governance

```text
TASK=V07_P2_CROSS_CONSUMER_CONSISTENCY_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
P0_TRACKING_ISSUE=PENDING
P2_TRACKING_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
TARGET_BRANCH=cursor/v07-p2-cross-consumer-consistency-6c68
TARGET_FILE=docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=IMPLEMENTATION_R1
V07_P0_IMPLEMENTATION_AUTHORIZED=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
V07_P2_IMPLEMENTATION_AUTHORIZED=YES
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=NO
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
PRODUCTION_HASH_REPAIR_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective and non-goals

### 1.1 Objective

CI-prove the following for the frozen canonical five-stage chain
(`zone → cooling_load → equipment → power → investment`):

| Surface | Identity parity | Authoritative hash parity | Selected numeric parity |
| --- | --- | --- | --- |
| API `GET /calculations` | `calculation_id` | `result_hash` | snapshot fields |
| SourceBinding ORM | slot `*_calculation_id` | `per_calculation_result_hashes` | — |
| Production SchemeRun | `*_calculation_id` columns | `*_result_hash` columns | scheme numeric outputs |
| Workflow `calculations.runs` | `calculation_run_id` | see KNOWN_DRIFT | — |
| Scheme `canonical_source_reads` | `source_calculation_ids` | see KNOWN_DRIFT | mapped numerics |
| Report `RealReportDataProvider` | `result_id` / citations | `persisted_content_hash` | v1 projected fields |

Additional proof surfaces:

- Same input repeated execution returns stable authoritative hashes.
- Idempotent replay with the same key and bundle does not duplicate rows.
- SQLite and PostgreSQL produce identical payload snapshot hashes and
  numeric projections for the frozen `samples/v07-consistency` inputs.
  Authoritative `fingerprint.result_hash` values bind per-execution
  provenance and are asserted across consumers within each run.
- Missing required bundle KEY leaves fail closed with zero canonical rows.

Reports MUST NOT recalculate formulas. Numeric projection mapping for
tests lives only in `backend/tests/integration/v07_p2_numeric_projection_map.py`.

### 1.2 Non-goals (hard boundaries)

```text
FORMULA_RECUT_AUTHORIZED=NO
PRODUCTION_HASH_REPAIR_AUTHORIZED=NO
MODULES_CALCULATIONS_EDIT=NO
BOOTSTRAP_APP_PY_EDIT=NO
SCHEMES_API_ROUTES_EDIT=NO
TEST_V05_ASSERTION_BODY_EDIT=NO
TEST_V06_ASSERTION_BODY_EDIT=NO
REPORT_FORMULA_RECALCULATION=NO
RELAX_INVARIANT_FOR_GREEN=NO
```

P2 must not:

- edit `backend/src/cold_storage/modules/calculations/**`;
- edit `bootstrap/app.py` or `schemes/api/routes.py`;
- modify assertion bodies in `test_v05_*` or `test_v06_*`;
- repair workflow `_result_hash` or scheme `_per_calc_hash` production code;
- weaken fail-closed or hash invariants to obtain green CI.

## 2. KNOWN_DRIFT register (detection only)

Aligned with P0 gap **V07-GAP-005**. Production helper hashes are recorded
as drift; authoritative `fingerprint.result_hash` on persisted rows remains
the contract authority.

| ID | Consumer | Helper | Authoritative | P2 action |
| --- | --- | --- | --- | --- |
| KNOWN_DRIFT-WF-001 | Workflow `_result_hash` | Raw `result_snapshot` via `json.dumps(..., default=str)` | `SourceSnapshotContentV1` envelope via `fingerprint.result_hash` | Detect + document; do not repair in P2 |
| KNOWN_DRIFT-SC-001 | Scheme `canonical_source_reads._per_calc_hash` | Raw `result_snapshot` | `fingerprint.result_hash` on `CalculationRunRecord` | Detect + document; do not repair in P2 |
| KNOWN_DRIFT-WF-002 | Workflow stale `scheme_source_snapshot_mismatch` | Combined raw snapshots dict | `combined_source_hash` on SourceBinding / production SchemeRun | Detect + document; do not repair in P2 |

Authoritative consumers **must** match:

- API `result_hash`
- SourceBinding `per_calculation_result_hashes`
- Report `persisted_content_hash`
- Production SchemeRun `*_result_hash` columns (after production scheme generation)

## 3. Exclusive allowlist

```text
V07_P2_FILE_ALLOWLIST
docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md
backend/tests/integration/v07_p2_consistency_evidence.py
backend/tests/integration/v07_p2_numeric_projection_map.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_sqlite.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_postgresql.py
backend/tests/architecture/test_v07_p2_consumer_hash_alignment.py
samples/v07-consistency/**
backend/tests/golden/v07_cross_consumer_v1.json
```

## 4. Frozen inputs

| Artifact | Role |
| --- | --- |
| `samples/v07-consistency/manifest.json` | Frozen EngineeringInputBundleV1 + idempotency key |
| `backend/tests/golden/v07_cross_consumer_v1.json` | Cross-backend payload hash + numeric golden |

Sample idempotency key: `v07-consistency-initial`.

## 5. P2 acceptance criteria (P2-AC)

```text
P2_CONTRACT_EXISTS=PASS
P2_ALLOWLIST_RESPECTED=PASS
CANONICAL_FIVE_PERSISTED=PASS
API_BINDING_REPORT_SCHEME_AUTHORITATIVE_HASH_PARITY=PASS
API_BINDING_REPORT_SCHEME_IDENTITY_PARITY=PASS
WORKFLOW_SCHEME_HELPER_HASH_KNOWN_DRIFT_RECORDED=PASS
NUMERIC_PROJECTION_TEST_MAP_ONLY=PASS
IDEMPOTENT_REPLAY_STABLE=PASS
RESTART_REOPEN_STABLE=PASS
MISSING_KEY_LEAF_FAIL_CLOSED=PASS
SQLITE_POSTGRESQL_AUTHORITATIVE_HASH_PARITY=PASS
NO_FORMULA_RECALC_IN_REPORT=PASS
PRODUCTION_HASH_REPAIR=NO
FORMULA_RECUT=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative test surfaces:

```text
backend/tests/architecture/test_v07_p2_consumer_hash_alignment.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_sqlite.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_postgresql.py
```

## 6. Contract closure state

```text
TASK=V07_P2_CROSS_CONSUMER_CONSISTENCY_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md

V07_P2_IMPLEMENTATION_AUTHORIZED=YES
V07_P2_CONTRACT_EXECUTED=YES
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 7. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P2 cross-consumer consistency proof package |
