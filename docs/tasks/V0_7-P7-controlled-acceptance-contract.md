# V0.7 P7 Controlled Acceptance Contract

**Status:** Definition freeze R1 — operator trust-loop controlled acceptance on unmodified `create_app`
**Authority:** `docs/tasks/V0_7-P0-trust-loop-contract.md` §10
**Parent contract:** `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Requires:** P0–P6 merged on `main`; P5 operator sample; P4 consumer hash repair
**Previous release:** `v0.6.0`
**Proposed future release:** `v0.7.0` (tag not authorized by P7)
**Target branch:** `cursor/v07-p7-controlled-acceptance-6c68`

P7 is **controlled acceptance only**. It records evidence that the V0.7 trust loop
completes on the unmodified operator `create_app` path using the frozen
`v07-trust-loop` sample. P7 does not mutate P1–P6 production code, formulas,
coefficients, live Aily, or production RBAC claims.

## 0. Contract identity and governance

```text
TASK=V07_P7_CONTROLLED_ACCEPTANCE_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=c01d35e393effbd33db23b660d46899c10d3f459
PREVIOUS_RELEASE=v0.6.0
PROPOSED_FUTURE_RELEASE=v0.7.0
TARGET_BRANCH=cursor/v07-p7-controlled-acceptance-6c68
TARGET_FILE=docs/tasks/V0_7-P7-controlled-acceptance-contract.md
TARGET_PR_STATE=DRAFT
```

```text
V07_P7_IMPLEMENTATION_AUTHORIZED=YES
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=YES
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
P7_MUTATES_P1_P6_PRODUCTION=NO
P7_CLOSES_ISSUES_NOW=NO
P7_CREATES_TAG_NOW=NO
P7_CREATES_GITHUB_RELEASE_NOW=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Upstream packages consumed at `BASE_MAIN_SHA`:

| Package | Role in P7 |
| --- | --- |
| P0 | Frozen trust-loop contract and §10 global acceptance gate |
| P1 | Version snapshot / coefficient metadata authority |
| P2 | Cross-consumer consistency and missing-key fail-closed |
| P3A | Operator `project_summary` on unmodified `create_app` |
| P3B | `POST .../production-scheme-runs` with `source_mode=production` |
| P4 | Workflow/scheme `result_hash` parity with API `fingerprint.result_hash` |
| P5 | Operator sample loader and trust-loop lifecycle |
| P6 | Feishu Aily boundary contract (`AILY_LIVE_IMPLEMENTATION=NO`) |

## 1. Objective

On **unmodified** `create_app`, prove P0 §10 global acceptance gates using the
frozen V0.7 operator sample:

```text
EngineeringInputBundleV1
 → five-stage-execution (canonical five persisted)
 → POST .../production-scheme-runs (source_mode=production)
 → workflow / scheme / report read same persisted hashes
 → report JSON (project_summary + scheme_comparison.review_authority)
 → submit-review HTTP 200
 → trusted TestClient mark-reviewed HTTP 200
 → untrusted actor mark-reviewed fail-closed
 → zh-CN/en-US DOCX/PDF formal render HTTP 200
```

Judgement for P7 is **not** feature expansion. It is repeatable, SQLite +
PostgreSQL parity evidence that the operator path closes the trust loop without
weakening V0.6 fail-closed history.

### 1.1 Non-goals (hard boundaries)

```text
P1_P6_PRODUCTION_CODE_MUTATION=NO
V06_P3_EVALUATION_HELPERS_IN_OPERATOR_TESTS=NO
V05_V06_TEST_ASSERTION_MUTATION=NO
FORMULA_CHANGE=NO
COEFFICIENT_PROMOTION=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_AILY_ENABLEMENT=NO
PRODUCTION_RBAC_CLAIM=NO
TAG_PUBLICATION=NO
GITHUB_RELEASE=NO
ISSUE_CLOSURE_VIA_GH=NO
```

## 2. Frozen operator sample identity

Reuse P5 frozen sample without mutation:

| Item | Frozen value |
| --- | --- |
| Sample id | `v07-trust-loop` |
| Manifest | `samples/v07-trust-loop/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v07_sample_loader.py` |
| Trusted actor (TestClient seam) | `v07-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Production weight revision | `wsr-production-default-v1` |
| Production scheme route | `POST /api/v1/projects/{project_id}/versions/{version}/production-scheme-runs` |

P7 tests call `seed_v07_sample`, `trusted_sample_client`, and P5 operator
fixtures. They must **not** import `tests/evaluation/v06_p3_lifecycle_helpers.py`.

## 3. P0 §10 acceptance gate matrix

| Gate ID | Assertion | Evidence |
| --- | --- | --- |
| P7-G-01 | Canonical five persisted: `zone → cooling_load → equipment → power → investment` | calculations API after five-stage seed |
| P7-G-02 | `POST .../production-scheme-runs` persists `source_mode=production` | scheme run GET / POST response |
| P7-G-03 | Report JSON has `project_summary` | report export after generate |
| P7-G-04 | `scheme_comparison.review_authority` binds `source_binding_id` and `combined_source_hash` | report export after production scheme run |
| P7-G-05 | `input_conditions` / `assumptions` from persisted snapshots; report does not recalculate formulas | report export `source_result_id` lineage |
| P7-G-06 | `workflow.calculations.runs[].result_hash` == API `fingerprint.result_hash` | workflow + calculations API parity (P4) |
| P7-G-07 | `submit-review` HTTP 200 on operator sample | trusted lifecycle |
| P7-G-08 | Trusted TestClient `mark-reviewed` HTTP 200 | trusted lifecycle |
| P7-G-09 | Untrusted actor `mark-reviewed` fail-closed (non-200) | separate untrusted `create_app` client |
| P7-G-10 | After submit-review 200: zh-CN/en-US DOCX/PDF formal render HTTP 200 | four formal exports |
| P7-G-11 | Missing KEY leaf fail-closed; zero canonical rows | v07 manifest bundle with removed KEY leaf |
| P7-G-12 | Demo coefficients remain `source_type=demo`, `validity_status=unverified`, `requires_review=true` | v07 manifest `demo_coefficient_leaves` |
| P7-G-13 | `AILY_LIVE_IMPLEMENTATION=NO` recorded in P6 contract | contract scan only |
| P7-G-14 | `TAG_PUBLICATION_AUTHORIZED=NO` | this contract + P0 |

`power_configuration` remains supplemental only and must not satisfy
`installed_power` / `electrical_and_energy` authority.

## 4. Integration test matrix

Authoritative P7 test surface:

```text
backend/tests/integration/test_v07_p7_controlled_acceptance_sqlite.py
backend/tests/integration/test_v07_p7_controlled_acceptance_postgresql.py
```

| AC ID | Assertion | SQLite test | PostgreSQL test |
| --- | --- | --- | --- |
| P7-AC-01 | Contract records source identity; forbids tag/release/merge | `test_v07_p7_contract_exists` | — |
| P7-AC-02 | P6 contract records `AILY_LIVE_IMPLEMENTATION=NO` | `test_v07_p7_contract_records_aily_boundary` | — |
| P7-AC-03 | Issues #11/#13/#176 evidence recorded; not closed | `test_v07_p7_contract_records_issue_evidence_only` | — |
| P7-AC-04 | Full operator trust loop on unmodified `create_app` | `test_v07_p7_sqlite_controlled_acceptance` | `test_v07_p7_pg_controlled_acceptance` |
| P7-AC-05 | Missing KEY leaf fail-closed + zero canonical rows | `test_v07_p7_sqlite_missing_key_leaf_fail_closed` | `test_v07_p7_pg_missing_key_leaf_fail_closed` |
| P7-AC-06 | Demo coefficients remain unverified | `test_v07_p7_sqlite_demo_coefficients_remain_unverified` | `test_v07_p7_pg_demo_coefficients_remain_unverified` |

Database matrix:

- **SQLite:** `@pytest.mark.sqlite`, skip when `DATABASE_BACKEND=postgresql`.
- **PostgreSQL:** `@pytest.mark.postgresql`, skip unless `DATABASE_BACKEND=postgresql`.
- PostgreSQL fixtures use `isolated_process_state`, `configure_postgresql_env`, and
  `assert_reports_engine_dialect` aligned with `test_v07_p5_operator_sample_postgresql.py`.
- Contract scans: unmarked, no database required.

Importable, not modifiable:

- `cold_storage.bootstrap.v07_sample_loader`
- `tests.integration.v07_p5_operator_fixtures`
- `backend/tests/architecture/test_v07_p6_aily_contract.py` (contract reference only)

## 5. Makefile target

```text
verify-v07-p7-controlled-acceptance
  → pytest test_v07_p7_controlled_acceptance_sqlite.py
  → pytest test_v07_p7_controlled_acceptance_postgresql.py (when DATABASE_BACKEND=postgresql)
```

Existing `seed-v06-sample`, `verify-v06-sample`, `seed-v07-sample`, and
`verify-v07-sample` targets must remain unchanged.

## 6. Issue-closure evidence (record only; do not close via `gh`)

| Issue | Status at P7 freeze | P7 evidence | Remaining |
| --- | --- | --- | --- |
| #11 TASK-009A report JSON | OPEN | Operator `project_summary`, persisted `source_result_id` lineage, submit-review 200 | Human closure after review |
| #13 TASK-009B DOCX/PDF | OPEN | Operator formal zh-CN/en-US DOCX/PDF 200 after trusted review | Human closure after review |
| #176 | OPEN | V0.7 umbrella; operator path now completes trust loop on v07 sample | Release gate later; do not auto-close |
| #20 | CLOSED (2026-07-22) | Record only. Do not reopen. | — |

P7 MUST NOT invoke `gh issue close` for #11, #13, or #176.

## 7. Exclusive allowlist

```text
V07_P7_FILE_ALLOWLIST
docs/tasks/V0_7-P7-controlled-acceptance-contract.md
backend/tests/integration/test_v07_p7_controlled_acceptance_sqlite.py
backend/tests/integration/test_v07_p7_controlled_acceptance_postgresql.py
Makefile
```

Forbidden without separate authorization: `backend/src/**`, `frontend/**`,
`samples/**`, `docs/tasks/V0_6-*`, `docs/tasks/V0_5-*`, P1–P6 contract files,
`test_v05_*`, `test_v06_*`, evaluation helpers.

## 8. Acceptance criteria

```text
P7_CONTRACT_EXISTS=PASS
P0_SECTION_10_GATES_RECORDED=PASS
TAG_PUBLICATION_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
CANONICAL_FIVE_PERSISTED=PASS
PRODUCTION_SCHEME_RUN_ON_VERSION=PASS
REPORT_PROJECT_SUMMARY_BOUND=PASS
REPORT_SCHEME_COMPARISON_BOUND=PASS
INPUT_CONDITIONS_ASSUMPTIONS_FROM_PERSISTED=PASS
WORKFLOW_SCHEME_REPORT_PARITY=PASS
OPERATOR_SUBMIT_REVIEW_200=PASS
TRUSTED_MARK_REVIEWED_200=PASS
UNTRUSTED_MARK_REVIEWED_FAIL_CLOSED=PASS
FORMAL_ZH_CN_EN_US_DOCX_PDF_200=PASS
MISSING_KEY_LEAF_FAIL_CLOSED=PASS
DEMO_COEFFICIENTS_REMAIN_UNVERIFIED=PASS
ISSUE_EVIDENCE_RECORDED_NOT_CLOSED=PASS
MAKEFILE_V07_P7_TARGET=PASS
V06_V07_SAMPLE_TARGETS_UNCHANGED=PASS
RUFF_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 9. Contract closure state

```text
TASK=V07_P7_CONTROLLED_ACCEPTANCE_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P7-controlled-acceptance-contract.md
V07_P7_CONTRACT_FROZEN=YES
V07_P7_IMPLEMENTATION_AUTHORIZED=YES
V07_P7_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 10. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P7 controlled acceptance contract at `c01d35e` |
