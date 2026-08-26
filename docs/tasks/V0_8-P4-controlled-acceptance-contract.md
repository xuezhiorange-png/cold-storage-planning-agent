# V0.8 P4 Controlled Acceptance Contract

**Status:** Definition freeze R1 — operator-minimal five-KEY controlled acceptance on unmodified `create_app`
**Authority:** `docs/tasks/V0_8-P0-operator-minimal-input-contract.md` §6.5 and §10
**Parent contract:** `docs/tasks/V0_8-P0-operator-minimal-input-contract.md`
**Requires:** P0–P3 merged on `main`; P1 assembler; P2 Vue workbench; P3 operator sample
**Previous release:** `v0.7.0`
**Proposed future release:** `v0.8.0` (record only; do not tag)
**Target branch:** `cursor/v08-p4-controlled-acceptance-6c68`

P4 is **controlled acceptance only**. It records repeatable SQLite + PostgreSQL evidence that the
V0.8 operator-minimal five-KEY path completes P0 §10 global acceptance gates on unmodified
`create_app`. P4 does not mutate P1–P3 production code, formulas, coefficients, live Aily,
production RBAC claims, `Makefile`, or authorize tag / Release / issue closure via `gh`.

## 0. Contract identity and governance

```text
TASK=V08_P4_CONTROLLED_ACCEPTANCE_R1
PARENT_CONTRACT=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
GOVERNANCE_OWNER=V0.8
BASE_MAIN_SHA=489b8941205a74d24b0c2df50346d5a6809d5d3c
PREVIOUS_RELEASE=v0.7.0
PROPOSED_FUTURE_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v08-p4-controlled-acceptance-6c68
TARGET_FILE=docs/tasks/V0_8-P4-controlled-acceptance-contract.md
TARGET_PR_STATE=DRAFT
```

```text
V08_P4_IMPLEMENTATION_AUTHORIZED=YES
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
P4_MUTATES_P1_P3_PRODUCTION=NO
P4_OWNS_MAKEFILE=NO
P4_CLOSES_ISSUES_NOW=NO
P4_CREATES_TAG_NOW=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Upstream packages consumed at `BASE_MAIN_SHA`:

| Package | Role in P4 |
| --- | --- |
| P0 | Frozen operator-minimal contract and §10 global acceptance gate |
| P1 | `OperatorProcessInputV1` assembler expands catalog + identity |
| P2 | Vue workbench posts `operator_process_input` (file-scan evidence only) |
| P3 | Frozen `v08-process-input` sample, loader, and operator fixtures |

## 1. Objective

On **unmodified** `create_app`, prove P0 §10 global acceptance gates for the V0.8
operator-minimal path:

```text
OperatorProcessInputV1 (five KEY only)
 → POST .../five-stage-execution { operator_process_input, idempotency_key }
 → application assembler expands catalog + identity (P1)
 → canonical five persist: cold_room_zone_plan, cooling_load, equipment, installed_power, investment_estimate
 → POST .../production-scheme-runs (balanced / wsr-production-default-v1)
 → report create/generate JSON (project_summary + scheme_comparison.review_authority)
 → submit-review 200
 → trusted TestClient mark-reviewed 200 (actor v08-local-trusted-reviewer)
 → untrusted actor system mark-reviewed fail-closed (non-200)
 → zh-CN/en-US DOCX+PDF formal render 200
 → missing operator KEY → MISSING_ENGINEERING_PARAMETER and zero canonical rows
 → demo catalog leaves remain requires_review=true
```

Judgement for P4 is **not** feature expansion, calculator recut, coefficient promotion, tag
publication, or Release. It is repeatable SQLite + PostgreSQL evidence only.

### 1.1 Non-goals (hard boundaries)

```text
P1_P3_PRODUCTION_CODE_MUTATION=NO
V05_V06_V07_TEST_ASSERTION_MUTATION=NO
FORMULA_CHANGE=NO
COEFFICIENT_PROMOTION=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_AILY_ENABLEMENT=NO
PRODUCTION_RBAC_CLAIM=NO
TAG_PUBLICATION=NO
GITHUB_RELEASE=NO
ISSUE_CLOSURE_VIA_GH=NO
MAKEFILE_OWNERSHIP=NO
```

Operators run the two P4 pytest modules directly. P4 does **not** add `seed-v08`,
`verify-v08-p4`, or `verify-v08-p4-controlled-acceptance` Makefile targets (P3 owns Makefile).

## 2. Frozen operator sample identity

Reuse P3 frozen sample without mutation:

| Item | Frozen value |
| --- | --- |
| Sample id | `v08-process-input` |
| Manifest | `samples/v08-process-input/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v08_sample_loader.py` |
| Trusted actor (TestClient seam) | `v08-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Idempotency key | `v08-process-input-initial` |
| Project name | `V0.8 算子最小输入示例项目` |
| Schema | `OperatorProcessInputV1` / `1.0.0` |
| Production weight revision | `wsr-production-default-v1` |
| Production scheme route | `POST /api/v1/projects/{project_id}/versions/{version}/production-scheme-runs` |

Operator-visible KEY leaves (exactly five):

```text
zone_planning_inputs.daily_inbound_mass_kg          20000  kg/day
zone_planning_inputs.working_time_h_per_day         16     h/day
zone_planning_inputs.finished_storage_days          7      day
zone_planning_inputs.packaging_storage_days         1      day
zone_planning_inputs.precooling_required_ratio      0.6    ratio
```

Submit shape (Path B):

```json
{ "operator_process_input": OperatorProcessInputV1, "idempotency_key": "..." }
```

Do **not** post `engineering_input_bundle` from the V0.8 operator sample path.

V0.5 auto-feed amendment (operator-minimal path only):

```text
OPERATOR_PROCESS_INPUT_FIVE_KEY_LEAVES_ONLY=YES
ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES
ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO
PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES
DEMO_CATALOG_TO_EXPLICIT_BUNDLE_LEAF=YES
DEMO_DEFAULT_TO_AUTHORITATIVE_INPUT_WITHOUT_BUNDLE_LEAF=NO
POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

`power_configuration` is supplemental only and must not satisfy `installed_power`.

## 3. P0 §10 acceptance gate matrix

| Gate ID | Assertion | Evidence |
| --- | --- | --- |
| P4-G-01 | Manifest `samples/v08-process-input/manifest.json` has only the five KEY leaves; no `engineering_input_bundle` | `test_v08_p4_manifest_has_five_operator_keys_only` |
| P4-G-02 | `seed_v08_sample` / POST `operator_process_input` on unmodified `create_app` persists canonical five with `calculation_id` and `result_hash` | `test_v08_p4_sqlite_controlled_acceptance` / `test_v08_p4_pg_controlled_acceptance` |
| P4-G-03 | `POST .../production-scheme-runs` `source_mode=production`; report JSON `project_summary` + `scheme_comparison.review_authority` bind `source_binding_id` and `combined_source_hash` | trust-loop lifecycle in controlled acceptance tests |
| P4-G-04 | Report JSON `input_conditions` / `assumptions` / `citations` bind persisted `calculation_id`s; report does not recalculate formulas | `assert_report_reads_persisted_without_recalc` |
| P4-G-05 | `workflow.calculations.runs[].result_hash` == calculations API `result_hash` for canonical five | `assert_workflow_result_hash_parity` |
| P4-G-06 | `submit-review` 200; trusted `mark-reviewed` 200; untrusted `system` `mark-reviewed` fail-closed; four formal exports zh-CN/en-US × docx/pdf | `run_trust_loop_lifecycle` + `assert_untrusted_mark_reviewed_fail_closed` |
| P4-G-07 | Missing operator KEY → `MISSING_ENGINEERING_PARAMETER` and zero `CalculationRunRecord` / `SourceBindingRecord` | `test_v08_p4_sqlite_missing_operator_key_fail_closed` / `test_v08_p4_pg_missing_operator_key_fail_closed` |
| P4-G-08 | Demo catalog / assembled leaves remain `source_type=demo` (or `coefficient` with conflict metadata), `validity_status` unverified or conflict, `requires_review=true` | `assert_demo_catalog_leaves_remain_unverified` (from persisted calculations; v08 manifest has no `demo_coefficient_leaves`) |
| P4-G-09 | Vue operator workbench on main posts `operator_process_input`, not `engineering_input_bundle` (file-scan only) | `test_v08_p4_vue_operator_workbench_file_scan` |
| P4-G-10 | `FULL_BUNDLE_COMPAT_PRESERVED`: V0.5/V0.6/V0.7 acceptance test files still exist; Path A `{ engineering_input_bundle, idempotency_key }` remains for full-bundle clients | `test_v08_p4_full_bundle_compat_test_files_exist` |
| P4-G-11 | `AILY_LIVE_IMPLEMENTATION=NO` in this contract and in V0.7 P6 / V0.8 P0 | contract scan |
| P4-G-12 | `TAG_PUBLICATION_AUTHORIZED=NO`; no git tag; no `gh release create`; no `gh issue close` | contract scan + forbidden pattern scan |

Missing-key cases for P4-G-07 use **operator KEY** leaves only (`daily_inbound_mass_kg`, etc.).
Do **not** reuse V0.7 cases such as `condensing_temperature_c` or cooling geometry `zone_area`.

## 4. Integration test matrix

Authoritative P4 test surface:

```text
backend/tests/integration/test_v08_p4_controlled_acceptance_sqlite.py
backend/tests/integration/test_v08_p4_controlled_acceptance_postgresql.py
```

| AC ID | Assertion | SQLite test | PostgreSQL test |
| --- | --- | --- | --- |
| P4-AC-01 | Contract records source identity; forbids tag/release/merge | `test_v08_p4_contract_exists` | — |
| P4-AC-02 | P0 + P6 record `AILY_LIVE_IMPLEMENTATION=NO` | `test_v08_p4_contract_records_aily_boundary` | — |
| P4-AC-03 | Issues #11/#13/#17/#176/#20 evidence recorded; not closed via `gh` | `test_v08_p4_contract_records_issue_evidence_only` | — |
| P4-AC-04 | Allowlist is exactly three files | `test_v08_p4_contract_allowlist` | — |
| P4-AC-05 | Manifest five KEY only | `test_v08_p4_manifest_has_five_operator_keys_only` | — |
| P4-AC-06 | Vue file-scan gates (P4-G-09) | `test_v08_p4_vue_operator_workbench_file_scan` | — |
| P4-AC-07 | Full-bundle compat test files exist (P4-G-10) | `test_v08_p4_full_bundle_compat_test_files_exist` | — |
| P4-AC-08 | Full operator trust loop on unmodified `create_app` | `test_v08_p4_sqlite_controlled_acceptance` | `test_v08_p4_pg_controlled_acceptance` |
| P4-AC-09 | Missing operator KEY fail-closed + zero canonical rows | `test_v08_p4_sqlite_missing_operator_key_fail_closed` | `test_v08_p4_pg_missing_operator_key_fail_closed` |
| P4-AC-10 | Demo catalog leaves remain unverified | `test_v08_p4_sqlite_demo_catalog_leaves_remain_unverified` | `test_v08_p4_pg_demo_catalog_leaves_remain_unverified` |

Database matrix:

- **SQLite:** `@pytest.mark.sqlite`, skip when `DATABASE_BACKEND=postgresql`.
- **PostgreSQL:** `@pytest.mark.postgresql`, skip unless `DATABASE_BACKEND=postgresql`.
- PostgreSQL fixtures use `isolated_process_state`, `configure_postgresql_env`, and
  `assert_reports_engine_dialect("postgresql")` aligned with P3 operator sample tests.
- Contract scans: unmarked, no database required.

Importable, not modifiable:

- `cold_storage.bootstrap.v08_sample_loader`
- `tests.integration.v08_p3_operator_fixtures`
- `tests.integration.v05_p4_acceptance_fixtures`
- Shared helpers from `test_v07_p7_controlled_acceptance_sqlite.py` where applicable

Do **not** import `execute_missing_key_bundle` / `MISSING_KEY_CASES` from V0.7.
Do **not** import `tests.evaluation.v06_p3_lifecycle_helpers`.

## 5. Issue-closure evidence (record only; do not close via `gh`)

| Issue | Status at P4 freeze | P4 evidence | Remaining |
| --- | --- | --- | --- |
| #11 TASK-009A report JSON | CLOSED (human, 2026-08-26, after `v0.7.0`) | Operator `project_summary`, persisted `source_result_id` lineage, submit-review 200 on v08 path | Do not reopen as V0.8 umbrella; do not close via `gh` |
| #13 TASK-009B DOCX/PDF | CLOSED (human, 2026-08-26, after `v0.7.0`) | Operator formal zh-CN/en-US DOCX/PDF 200 after trusted review on v08 path | Do not reopen; do not close via `gh` |
| #17 | CLOSED (human, 2026-08-26, after `v0.7.0`) | Record only; V0.8 operator path does not reopen | Do not close via `gh` |
| #176 | CLOSED (human, 2026-08-26, after `v0.7.0`) | V0.7 umbrella delivered; v08 five-KEY path completes trust loop | Release gate later; do not auto-close or reopen via `gh` |
| #20 | CLOSED (2026-07-22) | Record only. Do not reopen. | — |

P4 MUST NOT invoke `gh issue close` for #11, #13, #17, #176, or #20.

## 6. Exclusive allowlist

```text
V08_P4_FILE_ALLOWLIST
docs/tasks/V0_8-P4-controlled-acceptance-contract.md
backend/tests/integration/test_v08_p4_controlled_acceptance_sqlite.py
backend/tests/integration/test_v08_p4_controlled_acceptance_postgresql.py
```

Forbidden without separate authorization: `backend/src/**`, `frontend/**`, `samples/**`,
`Makefile`, `docs/tasks/V0_7-*`, `docs/tasks/V0_6-*`, `docs/tasks/V0_5-*`, P0–P3 contract files,
`test_v05_*`, `test_v06_*`, `test_v07_*` assertion bodies, evaluation helpers.

## 7. Acceptance criteria

```text
P4_CONTRACT_EXISTS=PASS
P0_SECTION_10_GATES_RECORDED=PASS
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
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
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DEMO_CATALOG_LEAVES_REQUIRE_REVIEW=PASS
VUE_OPERATOR_PATH_FILE_SCAN=PASS
FULL_BUNDLE_COMPAT_PRESERVED=PASS
ISSUE_EVIDENCE_RECORDED_NOT_CLOSED=PASS
P4_OWNS_MAKEFILE=NO
RUFF_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 8. Contract closure state

```text
TASK=V08_P4_CONTROLLED_ACCEPTANCE_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_8-P4-controlled-acceptance-contract.md
V08_P4_CONTRACT_FROZEN=YES
V08_P4_IMPLEMENTATION_AUTHORIZED=YES
V08_P4_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 9. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P4 controlled acceptance contract at `489b894` |
