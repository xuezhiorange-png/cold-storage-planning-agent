# V0.7 P4 Targeted Hash Repair Contract

**Status:** Implementation R1 — proven consumer hash alignment
**Authority:** Child of `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Parent contract SHA:** `e6ad66eef6da66117bd6f0c3bbb67d5179780ebb`
**Target branch:** `cursor/v07-p4-targeted-hash-repair-6c68`

This package **repairs** the three P2-documented consumer hash drifts
registered as **V07-GAP-005**. It does **not** guess expert decisions
E1–E8, change calculator formulas, promote coefficients, or widen
production surfaces beyond the frozen allowlist.

## 0. Contract identity and governance

```text
TASK=V07_P4_TARGETED_HASH_REPAIR_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
P2_EVIDENCE_CONTRACT=docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md
P0_TRACKING_ISSUE=PENDING
P4_TRACKING_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=e6ad66eef6da66117bd6f0c3bbb67d5179780ebb
TARGET_BRANCH=cursor/v07-p4-targeted-hash-repair-6c68
TARGET_FILE=docs/tasks/V0_7-P4-targeted-repair-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=IMPLEMENTATION_R1
V07_P0_IMPLEMENTATION_AUTHORIZED=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
V07_P2_IMPLEMENTATION_AUTHORIZED=YES
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=YES
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
PRODUCTION_HASH_REPAIR_AUTHORIZED=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective and non-goals

### 1.1 Objective

Close **V07-GAP-005** by aligning workflow and scheme consumer surfaces to
the persisted authoritative `fingerprint.result_hash` and
`combined_source_hash` already exposed by API / SourceBinding /
production SchemeRun.

| Repair ID | Location | Before (P2 drift) | After (P4 authority) |
| --- | --- | --- | --- |
| P4-REP-001 | `workflow/application/service.py` `_project_calculations` | `_result_hash(result_snapshot)` | persisted `record.result_hash` |
| P4-REP-002 | `schemes/application/canonical_source_reads.py` `require_canonical_scheme_sources` | `_per_calc_hash(result_snapshot)` | `indexed[stage].result_hash` |
| P4-REP-003 | `workflow/application/service.py` `_collect_stale_reasons` | combined raw `result_snapshot` `json.dumps` hash | `SourceBinding.combined_source_hash` vs production `SchemeRun.combined_source_hash` |

Preserved helper functions (P2 evidence only — not production authority):

- `_result_hash()` remains in `workflow/application/service.py`
- `_per_calc_hash()` remains in `schemes/application/canonical_source_reads.py`

Fail-closed rules:

- Canonical five-stage workflow projection MUST NOT synthesize hashes from
  raw snapshots when `result_hash` is absent.
- Canonical scheme source reads MUST NOT synthesize hashes from raw
  snapshots when `result_hash` is absent.
- Workflow stale detection MUST NOT compare raw snapshot digests against
  production `combined_source_hash`.

### 1.2 Non-goals (hard boundaries)

```text
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
MODULES_CALCULATIONS_EDIT=NO
BOOTSTRAP_APP_PY_EDIT=NO
SCHEMES_API_ROUTES_EDIT=NO
V06_SAMPLE_LOADER_EDIT=NO
TEST_V05_ASSERTION_BODY_EDIT=NO
TEST_V06_ASSERTION_BODY_EDIT=NO
E1_E8_GUESSING=NO
RELAX_INVARIANT_FOR_GREEN=NO
```

P4 must not:

- edit `backend/src/cold_storage/modules/calculations/**`;
- edit `bootstrap/app.py`, `schemes/api/routes.py`, or `v06_sample_loader.py`;
- modify assertion bodies in `test_v05_*` or `test_v06_*`;
- guess or resolve expert decisions E1–E8;
- promote demo coefficients or change formulas;
- remove `_result_hash()` / `_per_calc_hash()` helpers used by P2 drift evidence.

## 2. Gap closure register

| Gap | P2 status | P4 action |
| --- | --- | --- |
| V07-GAP-005 | KNOWN_DRIFT-WF-001 / KNOWN_DRIFT-SC-001 / KNOWN_DRIFT-WF-002 recorded | **CLOSED** by P4-REP-001..003 |

P2 KNOWN_DRIFT entries remain documented for historical evidence; P4
production consumers now use authoritative persisted hashes.

## 3. Exclusive allowlist

```text
V07_P4_FILE_ALLOWLIST
docs/tasks/V0_7-P4-targeted-repair-contract.md
backend/src/cold_storage/modules/workflow/application/service.py
backend/src/cold_storage/modules/schemes/application/canonical_source_reads.py
backend/tests/architecture/test_v07_p4_hash_alignment.py
backend/tests/integration/test_v07_p4_consumer_hash_repair_sqlite.py
backend/tests/integration/test_v07_p4_consumer_hash_repair_postgresql.py
```

Conditional minimal exception (only if P2 `assert_known_drift_recorded`
fails because scheme bundle hashes now align):

- `backend/tests/integration/v07_p2_consistency_evidence.py` —
  `assert_known_drift_recorded` only, with comment that P4 closed
  V07-GAP-005 scheme-side drift.

## 4. P4 acceptance criteria (P4-AC)

```text
P4_CONTRACT_EXISTS=PASS
P4_ALLOWLIST_RESPECTED=PASS
WORKFLOW_RUNS_USE_PERSISTED_RESULT_HASH=PASS
SCHEME_CANONICAL_READS_USE_PERSISTED_RESULT_HASH=PASS
WORKFLOW_STALE_USES_COMBINED_SOURCE_HASH=PASS
HELPER_HASH_FUNCTIONS_PRESERVED_FOR_P2_EVIDENCE=PASS
V07_GAP_005_CLOSED=PASS
SQLITE_POSTGRESQL_CONSUMER_HASH_PARITY=PASS
NO_FALSE_SCHEME_SOURCE_SNAPSHOT_MISMATCH_WHEN_ALIGNED=PASS
FORMULA_RECUT=NO
COEFFICIENT_PROMOTION=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative test surfaces:

```text
backend/tests/architecture/test_v07_p4_hash_alignment.py
backend/tests/integration/test_v07_p4_consumer_hash_repair_sqlite.py
backend/tests/integration/test_v07_p4_consumer_hash_repair_postgresql.py
```

## 5. Contract closure state

```text
TASK=V07_P4_TARGETED_HASH_REPAIR_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P4-targeted-repair-contract.md

V07_P4_IMPLEMENTATION_AUTHORIZED=YES
V07_P4_CONTRACT_EXECUTED=YES
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 6. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P4 targeted hash repair for V07-GAP-005 |
