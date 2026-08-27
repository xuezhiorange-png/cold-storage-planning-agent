# V0.9 P7 — Controlled Acceptance Contract

**Status:** Definition freeze R1 — V0.9 five-KEY controlled acceptance on unmodified `create_app`  
**Authority:** `docs/tasks/V0_9-P0-version-contract.md` §7.8 and §11; version-plan §1 / §6 P7  
**Parent:** P0 #213 + P1 #216 + P2 #217 + P3 #218 + P4 #215 + P5 #214 + P6 #219 on `main`  
**Previous release:** `v0.8.0`  
**Proposed future release:** `v0.9.0` (record only; do not tag)  
**Target branch:** `cursor/v09-p7-controlled-acceptance-6c68`

P7 is **controlled acceptance only**. It records repeatable SQLite + PostgreSQL
evidence that version-plan §1 / P0 §1.1 judgement holds on unmodified
`create_app` using the frozen `v09-process-input` sample. P7 does not mutate
P1–P6 production code, formulas, coefficients, Vue, Makefile, live Aily,
production RBAC claims, or authorize tag / Release / issue closure via `gh`.

Companion documents:

- Overall plan: `docs/tasks/V0_9-version-plan.md`
- P0 contract: `docs/tasks/V0_9-P0-version-contract.md`
- P6 sample (read-only): `docs/tasks/V0_9-P6-operator-sample-runbook-contract.md`
- V0.8 P4 pattern (read-only): `docs/tasks/V0_8-P4-controlled-acceptance-contract.md`

## 0. Contract identity and governance

```text
TASK=V09_P7_CONTROLLED_ACCEPTANCE_R1
PARENT_ISSUE=213
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=c10c7e29a7a4f084ba2ac161c9d0fff8402a72d0
BASE_TREE=d0b7b945e921173369e34d683fe285d0ded520b1
BASE_SUBJECT=V0.9 P6: operator five-KEY sample, seed/verify, and runbook (#219)
PREVIOUS_RELEASE=v0.8.0
PROPOSED_FUTURE_RELEASE=v0.9.0
TARGET_BRANCH=cursor/v09-p7-controlled-acceptance-6c68
TARGET_FILE=docs/tasks/V0_9-P7-controlled-acceptance-contract.md
TARGET_PR_STATE=DRAFT

V09_P7_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=YES
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
P7_MUTATES_P1_P6_PRODUCTION=NO
P7_OWNS_MAKEFILE=NO
P7_CLOSES_ISSUES_NOW=NO
P7_CREATES_TAG_NOW=NO
P7_CREATES_GITHUB_RELEASE_NOW=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 may still record `V09_P7_IMPLEMENTATION_AUTHORIZED=NO`. This file
overrides that for the controlled-acceptance package only. Do not edit P0.

Upstream packages consumed at `BASE_MAIN_SHA`:

| Package | Role in P7 |
| --- | --- |
| P0 #213 | Frozen V0.9 KEY, DAG, §11 global gates |
| P1 #216 | Assembler expands V0.9 five KEY (`OperatorProcessInputV1` 1.1.0) |
| P2 #217 | Zone planner version-plan §4; `shipping_channel`; dual precool schemes |
| P3 #218 | Calculations UI reads persisted zone fields (file-scan only in P7) |
| P4 #215 | Draft export independent of review; formal stays approved/archived |
| P5 #214 | Workbench layout + banners (file-scan only in P7) |
| P6 #219 | Frozen `v09-process-input` sample, loader, fixtures |

## 1. Objective

On **unmodified** `create_app`, prove P0 §11 / version-plan §1 judgement for
the V0.9 operator path:

```text
OperatorProcessInputV1 1.1.0 (five KEY only)
 → POST .../five-stage-execution { operator_process_input, idempotency_key }
 → P1 assembler expands catalog + identity including shipping_channel
 → canonical five persist (calculator identity cold_room_zone_plan@1.0.0)
 → persisted zone JSON includes shipping_channel and two precooling schemes
 → POST .../production-scheme-runs (balanced / wsr-production-default-v1)
 → report create/generate JSON (project_summary + scheme_comparison.review_authority)
 → draft export zh-CN/en-US × docx/pdf BEFORE mark_reviewed
 → formal export fail-closed BEFORE mark_reviewed / approve
 → submit-review 200
 → trusted TestClient mark-reviewed 200 (actor v09-local-trusted-reviewer)
 → untrusted actor system mark-reviewed fail-closed (non-200)
 → after approve: zh-CN/en-US DOCX+PDF formal render 200
 → missing operator KEY → MISSING_ENGINEERING_PARAMETER and zero canonical rows
 → demo catalog leaves remain requires_review=true
```

Judgement for P7 is **not** feature expansion, calculator recut, coefficient
promotion, tag publication, or Release. It is repeatable SQLite + PostgreSQL
evidence only.

### 1.1 Non-goals (hard boundaries)

```text
P1_P6_PRODUCTION_CODE_MUTATION=NO
V09_LOADER_MUTATION=NO
V09_P6_FIXTURE_MUTATION=NO
V05_V06_V07_V08_TEST_ASSERTION_MUTATION=NO
FORMULA_CHANGE=NO
ZONE_PLANNING_PY_EDIT=NO
COOLING_LOAD_FORMULA_RECUT=NO
COEFFICIENT_PROMOTION=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_AILY_ENABLEMENT=NO
PRODUCTION_RBAC_CLAIM=NO
TAG_PUBLICATION=NO
GITHUB_RELEASE=NO
ISSUE_CLOSURE_VIA_GH=NO
MAKEFILE_OWNERSHIP=NO
VUE_MUTATION=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
```

Operators run the two P7 pytest modules directly. P7 does **not** add
`verify-v09-p7` Makefile targets (P6 owns Makefile).

## 2. Frozen operator sample identity

Reuse P6 frozen sample without mutation:

| Item | Frozen value |
| --- | --- |
| Sample id | `v09-process-input` |
| Manifest | `samples/v09-process-input/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v09_sample_loader.py` |
| Trusted actor (TestClient seam) | `v09-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Idempotency key | `v09-process-input-initial` |
| Project name | `V0.9 算子最小输入示例项目` |
| Schema | `OperatorProcessInputV1` / `1.1.0` |
| Production weight revision | `wsr-production-default-v1` |
| Production scheme profile | `balanced` |
| Zone calculator identity | `cold_room_zone_plan@1.0.0` (formula recut did not bump identity) |

Operator-visible KEY leaves (exactly five):

```text
zone_planning_inputs.daily_inbound_mass_kg               20000  kg/day
zone_planning_inputs.finished_storage_days               7      day
zone_planning_inputs.frozen_storage_days                 10     day
zone_planning_inputs.main_packaging_storage_days         4      day
zone_planning_inputs.auxiliary_packaging_storage_days    12     day
```

Submit shape (Path B):

```json
{ "operator_process_input": OperatorProcessInputV1, "idempotency_key": "..." }
```

Do **not** post `engineering_input_bundle` from the V0.9 operator sample path.

Manifest must **not** contain:

```text
engineering_input_bundle
working_time_h_per_day
packaging_storage_days
precooling_required_ratio
```

## 3. P0 §11 acceptance gate matrix

| Gate ID | Assertion | Evidence |
| --- | --- | --- |
| P7-G-01 | Manifest has only the V0.9 five KEY leaves; schema 1.1.0; no bundle; no V0.8 removed KEY | `test_v09_p7_manifest_has_five_operator_keys_only` |
| P7-G-02 | Seed / POST `operator_process_input` on unmodified `create_app` persists canonical five with `calculation_id` and `result_hash`; zone calculator version `1.0.0` | sqlite/pg controlled acceptance |
| P7-G-03 | Persisted `cold_room_zone_plan` JSON includes `shipping_channel` and primary/secondary precooling `schemes` length 2 | `assert_v09_zone_snapshot` (import P6 fixture; do not copy formulas) |
| P7-G-04 | `POST .../production-scheme-runs` `source_mode=production`; report JSON `project_summary` + `scheme_comparison.review_authority` bind `source_binding_id` and `combined_source_hash` | trust-loop lifecycle |
| P7-G-05 | Report JSON `input_conditions` / `assumptions` / `citations` bind persisted `calculation_id`s; report does not recalculate formulas | `assert_report_reads_persisted_without_recalc` |
| P7-G-06 | `workflow.calculations.runs[].result_hash` == calculations API `result_hash` for canonical five | `assert_workflow_result_hash_parity` |
| P7-G-07 | Draft `mode=draft` zh-CN/en-US × docx/pdf HTTP 200 **before** `mark_reviewed` | draft exports in lifecycle before review |
| P7-G-08 | Formal `mode=formal` fail-closed (non-200) **before** trusted review/approve | dedicated assert in P7 tests |
| P7-G-09 | `submit-review` 200; trusted `mark-reviewed` 200; untrusted `system` fail-closed; four formal exports after approve | trust loop + untrusted client |
| P7-G-10 | Missing V0.9 operator KEY → `MISSING_ENGINEERING_PARAMETER` and zero `CalculationRunRecord` / `SourceBindingRecord` | missing-key tests |
| P7-G-11 | Demo catalog / assembled leaves remain `source_type=demo` (or `coefficient` with conflict metadata), `validity_status` unverified or conflict, `requires_review=true` | `assert_demo_catalog_leaves_remain_unverified` |
| P7-G-12 | Vue file-scan: five V0.9 KEY; posts `operator_process_input`; no Vue formulas; draft copy independent of review; formal statuses not weakened; workbench grid layout | `test_v09_p7_vue_operator_workbench_file_scan` |
| P7-G-13 | `FULL_BUNDLE_COMPAT_PRESERVED`: V0.5/V0.6/V0.7/V0.8 acceptance test files still exist | `test_v09_p7_full_bundle_compat_test_files_exist` |
| P7-G-14 | `AILY_LIVE_IMPLEMENTATION=NO` in this contract, P0, and P6 | contract scan |
| P7-G-15 | `TAG_PUBLICATION_AUTHORIZED=NO`; no git tag; no `gh release create`; no `gh issue close` | contract scan + forbidden pattern scan |

Missing-key cases for P7-G-10 use **V0.9 operator KEY** leaves only:

```text
daily_inbound_mass_kg
frozen_storage_days
```

Do **not** reuse V0.7 `condensing_temperature_c` or V0.8
`precooling_required_ratio` / `working_time_h_per_day` /
`packaging_storage_days` as the missing-key cases.

## 4. Integration test matrix

Authoritative P7 test surface:

```text
backend/tests/integration/test_v09_p7_controlled_acceptance_sqlite.py
backend/tests/integration/test_v09_p7_controlled_acceptance_postgresql.py
```

| AC ID | Assertion | SQLite test | PostgreSQL test |
| --- | --- | --- | --- |
| P7-AC-01 | Contract records source identity; forbids tag/release/merge | `test_v09_p7_contract_exists` | — |
| P7-AC-02 | P0 + P6 + this contract record `AILY_LIVE_IMPLEMENTATION=NO` | `test_v09_p7_contract_records_aily_boundary` | — |
| P7-AC-03 | Issues #11/#13/#17/#176/#20 evidence recorded; not closed via `gh` | `test_v09_p7_contract_records_issue_evidence_only` | — |
| P7-AC-04 | Allowlist is exactly the three P0 §7.8 files | `test_v09_p7_contract_allowlist` | — |
| P7-AC-05 | Manifest V0.9 five KEY only | `test_v09_p7_manifest_has_five_operator_keys_only` | — |
| P7-AC-06 | Vue file-scan gates (P7-G-12) | `test_v09_p7_vue_operator_workbench_file_scan` | — |
| P7-AC-07 | Full-bundle compat test files exist (P7-G-13) | `test_v09_p7_full_bundle_compat_test_files_exist` | — |
| P7-AC-08 | Full operator trust loop on unmodified `create_app` including G-07/G-08 | `test_v09_p7_sqlite_controlled_acceptance` | `test_v09_p7_pg_controlled_acceptance` |
| P7-AC-09 | Missing operator KEY fail-closed + zero canonical rows | `test_v09_p7_sqlite_missing_operator_key_fail_closed` | `test_v09_p7_pg_missing_operator_key_fail_closed` |
| P7-AC-10 | Demo catalog leaves remain unverified | `test_v09_p7_sqlite_demo_catalog_leaves_remain_unverified` | `test_v09_p7_pg_demo_catalog_leaves_remain_unverified` |

Database matrix:

- **SQLite:** `@pytest.mark.sqlite`, skip when `DATABASE_BACKEND=postgresql`.
- **PostgreSQL:** `@pytest.mark.postgresql`, skip unless `DATABASE_BACKEND=postgresql`.
- PostgreSQL fixtures use `isolated_process_state`, `configure_postgresql_env`, and
  `assert_reports_engine_dialect("postgresql")` from P6 operator fixtures.
- Contract scans: unmarked, no database required.

Importable, **not** modifiable:

- `cold_storage.bootstrap.v09_sample_loader`
- `tests.integration.v09_p6_operator_fixtures`
- `tests.integration.v05_p4_acceptance_fixtures`
- Shared helpers from `test_v07_p7_controlled_acceptance_sqlite.py`
  (`assert_production_scheme_source_mode`,
  `assert_report_reads_persisted_without_recalc`,
  `assert_workflow_result_hash_parity`) where applicable
- `tests.integration.v07_p2_consistency_evidence.assert_zero_canonical_rows`

Do **not** import `execute_missing_key_bundle` / `MISSING_KEY_CASES` from V0.7.
Do **not** import `tests.evaluation.v06_p3_lifecycle_helpers`.
Do **not** mutate `v09_sample_loader.py` or `v09_p6_operator_fixtures.py`.

### 4.1 Vue file-scan (no browser; no Vue edits)

Scan these files on disk. Do not compute engineering values in the test.

| File | Must observe |
| --- | --- |
| `EngineeringInputBundleForm.vue` | `field-key` values are exactly the five V0.9 keys (`zonePlanning.dailyInboundMassKg`, `finishedStorageDays`, `frozenStorageDays`, `mainPackagingStorageDays`, `auxiliaryPackagingStorageDays`). Must not contain `workingTimeHPerDay` / `precoolingRequiredRatio` / `packagingStorageDays` as operator field-keys. |
| `frontend/src/stores/fiveStageExecution.ts` | posts `operator_process_input`; must not post `engineering_input_bundle` |
| `CalculationsPage.vue` | empty-state keeps `暂无完整五阶段计算结果。` and points to `OperatorProcessInputV1`; must not tell operators to fill `EngineeringInputBundleV1` |
| `ZoneResultsTable.vue` | no `1.56`, no `n ×`, no local area/dock formula; display persisted fields only |
| `useReportExport.ts` | `DRAFT_EXPORT_STATUSES` still includes `draft`/`generated`; `FORMAL_EXPORT_STATUSES` is only `approved`/`archived`; `DRAFT_EXPORT_POLICY_COPY` present |
| `ReportExportPanel.vue` | contains `DRAFT_EXPORT_POLICY_COPY`; separate draft vs formal |
| `WorkbenchLayout.vue` | `workbench-layout__body` uses `display: grid` and `grid-template-columns` |

### 4.2 Draft vs formal in the HTTP lifecycle

P6 `run_trust_loop_lifecycle` already drafts before review then formals after
approve. P7 **must** additionally assert formal render is non-200 after generate
and **before** `mark_reviewed` / `approve`. Implement that assert in the P7
sqlite module and reuse it from PostgreSQL. Do not change P6 fixtures to do it.

## 5. Issue-closure evidence (record only; do not close via `gh`)

| Issue | Status at P7 freeze | P7 evidence | Remaining |
| --- | --- | --- | --- |
| #11 TASK-009A report JSON | CLOSED (human, after `v0.7.0`) | Operator `project_summary`, persisted `source_result_id` lineage, submit-review 200 on v09 path | Do not reopen; do not close via `gh` |
| #13 TASK-009B DOCX/PDF | CLOSED (human, after `v0.7.0`) | Operator formal zh-CN/en-US DOCX/PDF 200 after trusted review on v09 path | Do not reopen; do not close via `gh` |
| #17 | CLOSED (human, after `v0.7.0`) | Record only | Do not close via `gh` |
| #176 | CLOSED (human, after `v0.7.0`) | V0.7 umbrella delivered; v09 five-KEY path completes trust loop | Do not auto-close or reopen via `gh` |
| #20 | CLOSED (2026-07-22) | Record only. Do not reopen. | — |

P7 MUST NOT invoke `gh issue close` for #11, #13, #17, #176, or #20.

P7 completion may **propose** `v0.9.0` in this contract only.
`TAG_PUBLICATION_AUTHORIZED=NO`. Do not `git tag`. Do not `gh release create`.

## 6. Exclusive allowlist

P7 allowlist = P0 §7.8 (exactly these three files unless a leftover skipif
requires adding that leftover test file in the same commit):

```text
V09_P7_FILE_ALLOWLIST
docs/tasks/V0_9-P7-controlled-acceptance-contract.md
backend/tests/integration/test_v09_p7_controlled_acceptance_sqlite.py
backend/tests/integration/test_v09_p7_controlled_acceptance_postgresql.py
```

Forbidden without separate authorization: `backend/src/**`, `frontend/**`,
`samples/**`, `Makefile`, `docs/tasks/V0_8-*`, `docs/tasks/V0_7-*`,
`docs/tasks/V0_6-*`, `docs/tasks/V0_5-*`, P0–P6 contract files,
`v09_sample_loader.py`, `v09_p6_operator_fixtures.py`, `zone_planning.py`,
`cooling_load.py`, `test_v05_*` / `test_v06_*` / `test_v07_*` / `test_v08_*`
assertion bodies, evaluation helpers.

If a merged architecture test still requires a previous package’s diff shape,
skipif-gate it to that package’s branch and add **that leftover test file** to
this allowlist in the same commit. Wrap long `skipif` reasons so ruff E501
cannot fail. Do not weaken on-disk formula identity checks
(`cold_room_zone_plan` `VERSION = "1.0.0"`, `shipping_channel` emit).

If Makefile/living tests / mypy / ruff fail on P7 files, fix on this PR
(standing 红了就修). Do not take Makefile ownership.

## 7. Acceptance criteria

```text
P7_CONTRACT_EXISTS=PASS
P0_SECTION_11_GATES_RECORDED=PASS
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
CANONICAL_FIVE_PERSISTED=PASS
ZONE_CALCULATOR_IDENTITY_1_0_0=PASS
SHIPPING_CHANNEL_AND_DUAL_PRECOOL_SCHEMES=PASS
PRODUCTION_SCHEME_RUN_ON_VERSION=PASS
REPORT_PROJECT_SUMMARY_BOUND=PASS
REPORT_SCHEME_COMPARISON_BOUND=PASS
INPUT_CONDITIONS_ASSUMPTIONS_FROM_PERSISTED=PASS
WORKFLOW_SCHEME_REPORT_PARITY=PASS
DRAFT_EXPORT_BEFORE_REVIEW_200=PASS
FORMAL_EXPORT_BEFORE_REVIEW_FAIL_CLOSED=PASS
OPERATOR_SUBMIT_REVIEW_200=PASS
TRUSTED_MARK_REVIEWED_200=PASS
UNTRUSTED_MARK_REVIEWED_FAIL_CLOSED=PASS
FORMAL_ZH_CN_EN_US_DOCX_PDF_200=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DEMO_CATALOG_LEAVES_REQUIRE_REVIEW=PASS
VUE_OPERATOR_PATH_FILE_SCAN=PASS
FULL_BUNDLE_COMPAT_PRESERVED=PASS
ISSUE_EVIDENCE_RECORDED_NOT_CLOSED=PASS
P7_OWNS_MAKEFILE=NO
RUFF_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 8. Contract closure state

```text
TASK=V09_P7_CONTROLLED_ACCEPTANCE_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_9-P7-controlled-acceptance-contract.md
V09_P7_CONTRACT_FROZEN=YES
V09_P7_IMPLEMENTATION_AUTHORIZED=YES
V09_P7_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 9. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | Initial P7 controlled acceptance contract at `c10c7e2` |
