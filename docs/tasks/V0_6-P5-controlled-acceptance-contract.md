# V0.6 P5 Controlled Acceptance Contract

**Status:** Definition freeze R1 — operator-path evidence + consumed P3 evaluation bridge
**Authority:** Issue #176 (umbrella), tracked by Issue #177, dispatched by Issue #197
**Parent contract:** `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md`
**Operator runbook (read-only):** `docs/runbooks/v06-pilot-runbook.md`
**Previous release:** `v0.5.0`
**Proposed future release:** `v0.6.0` (tag not authorized by P5)

P5 is controlled acceptance of already-merged V0.6 packages (P0–P4B). It does not
redefine P0–P4B contracts, mutate production code, or authorize merge, tag,
GitHub Release, controlled-acceptance execution dispatch, production deployment,
live MiMo, formula recut, or coefficient promotion.

## 0. Contract identity and governance

```text
TASK=V06_P5_CONTROLLED_ACCEPTANCE_R1
PARENT_ISSUE=176
P5_TRACKING_ISSUE=177
DISPATCH_ISSUE=197
GOVERNANCE_OWNER=V0.6
BASE_MAIN_SHA=d1af4ee29dd4bca1db7ae3d2adfd0f535c1b2be6
BASE_TREE=7f1716ca7abe0d463b87b86b47d09edff2eda490
PREVIOUS_RELEASE=v0.5.0
PROPOSED_FUTURE_RELEASE=v0.6.0
TARGET_BRANCH=cursor/v06-p5-controlled-acceptance-6c68
TARGET_PR_STATE=DRAFT
CI_GATE=main@BASE_MAIN_SHA with BASE_TREE; package CI green is a later gate
```

```text
V06_P5_IMPLEMENTATION_AUTHORIZED=YES
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
P5_MUTATES_P1_P4_PRODUCTION=NO
P5_CLOSES_ISSUES_NOW=NO
P5_CLONES_V03_P5_STAGE_ENGINE=NO
P5_CLONES_V03_SCENARIOS_A_B_C=NO
P5_CREATES_TAG_NOW=NO
P5_CREATES_GITHUB_RELEASE_NOW=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Upstream packages consumed at this base:

| Package | PR / issue | P5 role |
| --- | --- | --- |
| P0 | #176 / contract | Frozen report source mapping and lifecycle |
| P1 | assembly on main | Report JSON binds persisted `source_result_id` |
| P2 | rendering on main | Formal DOCX/PDF render path |
| P3 | #193 / #179 | Evaluation happy-path formal zh-CN/en-US DOCX+PDF (consumed, not reimplemented) |
| P4A | #192 | Frontend report workflow binds public report APIs |
| P4B | #195 / loader | Operator sample seed/verify via `v06_sample_loader` |

P4B duplicate PR #196 is **ignored** (late duplicate of merged #195).

## 1. Two-surface acceptance model

P5 records honest evidence on two surfaces. They are complementary, not contradictory.

### Surface A — operator / public-API path (authoritative for this package)

Reuse `cold_storage.bootstrap.v06_sample_loader` (`seed_v06_sample`,
`verify_v06_sample`, `trusted_sample_client`, `load_manifest`). Seed only through
current public APIs:

```text
POST /api/v1/projects
POST /api/v1/projects/{id}/versions/{n}/five-stage-execution
POST /api/v1/reports
POST /api/v1/reports/{id}/generate
POST /api/v1/reports/{id}/submit-review
POST /api/v1/reports/{id}/mark-reviewed
POST /api/v1/reports/{id}/approve
POST /api/v1/reports/{id}/revisions/{n}/render   mode=formal locale=zh-CN|en-US format=docx|pdf
```

Never `planning-run`. Never Alembic inside the loader (tests may run
`alembic upgrade head` in a subprocess with an isolated env copy). Never guess
missing engineering values. Never recalculate formulas.

On current `main@BASE_MAIN_SHA`, unmodified report assembly on the v06 sample
**fail-closes** `submit-review` (missing `project_summary` / `scheme_comparison`)
and therefore formal zh-CN/en-US DOCX/PDF stay **409 ExportPermissionError**.
That is **acceptable P5 evidence**. P5 does not force a 200 happy path on the
operator surface.

Operator-path assertions:

1. Canonical five persist: `cold_room_zone_plan`, `cooling_load`, `equipment`,
   `installed_power`, `investment_estimate`.
2. `power_configuration` is supplemental and must not satisfy `installed_power`
   / `electrical_and_energy` authority.
3. `calculation_id` and `result_hash` present; restart/reopen returns the same
   ids/hashes and the same report revision `content_hash`.
4. Report create + generate succeed; generated JSON binds persisted
   `source_result_id` for the canonical five mapping frozen in P0.
5. `input_conditions` / `assumptions` come from persisted snapshots when present;
   missing required sources produce explicit blockers, never silent defaults.
6. Demo coefficients remain `source_type=demo`, `validity_status` in
   `{unverified, conflict}`, `requires_review=true`.
7. Untrusted actor `system` cannot satisfy `mark-reviewed` (non-200).
8. Formal render without trusted `mark_reviewed` proof is 409.
9. If `submit-review` is 409, **all four** formal renders (zh-CN/en-US ×
   docx/pdf) must also be 409 fail-closed;
   `report_lifecycle_fail_closed=true`.
10. `GET /api/v1/demo/scheme-comparison` may succeed but is a **separate** demo
    project; do not treat it as `scheme_comparison` bound to the v06 sample
    version. Do not `POST .../scheme-runs` on the sample version.
11. Core path works without model API keys; workflow `agent_assistance` must not
    claim fake available Agent.

### Surface B — evaluation bridge (consumed, not duplicated)

P3 tests on `main` already prove evaluation-only happy-path formal zh-CN/en-US
DOCX+PDF via:

```text
backend/tests/evaluation/test_v06_p3_review_formal_evaluation.py
backend/tests/evaluation/v06_p3_lifecycle_helpers.py
```

P5 **does not import** P3 helpers (process-global isolation requirements).
P5 records P3-AC-01..08 as consumed merged evidence.

| P3 AC | Assertion | P3 test function |
| --- | --- | --- |
| P3-AC-01 | Canonical five; `power_configuration` not canonical power | `test_p3_canonical_calculator_names_after_five_stage_seed` |
| P3-AC-02 | Report generate binds persisted `source_result_id` | `test_p3_report_generate_binds_persisted_source_result_ids` |
| P3-AC-03 | `input_conditions` / `assumptions` from persisted snapshots | `test_p3_input_conditions_and_assumptions_from_persisted_snapshots` |
| P3-AC-04 | Happy path formal zh-CN/en-US DOCX+PDF with provenance | `test_p3_happy_path_formal_exports_bind_provenance` |
| P3-AC-05 | Formal render without trusted `mark_reviewed` fails closed (409) | `test_p3_formal_render_without_mark_reviewed_fails_closed` |
| P3-AC-06 | Missing canonical source fails closed for formal export | `test_p3_missing_canonical_source_fails_closed_for_formal_export` |
| P3-AC-07 | Restart/reopen preserves calculation ids/hashes and revision hash | `test_p3_restart_reopen_preserves_calculation_and_revision_hashes` |
| P3-AC-08 | `high_throughput_review` label-only; review authority unchanged | `test_p3_high_throughput_review_label_does_not_mutate_review_authority` |

`high_throughput_review` remains a label only. P5 does not rewrite TASK-011 goldens.

### Surface C — frontend contract scan (read-only)

Scan `frontend/src/features/reports/api/reportsApi.ts` and related P4A files.
Assert public report routes (create, generate, submit-review, mark-reviewed,
approve). Scan `ReportExportPanel` / `useReportExport` for `projectVersionId`
from `workbench.workflow.project_context.project_version_id`; formal control
disabled when ineligible; copy that trusted-operator review buttons are not
production RBAC. Do not fail P5 because `exportJson` is unused.

## 2. Frozen P0 report source mapping (operator assertions)

| Persisted calculator | Report JSON section key |
| --- | --- |
| `cold_room_zone_plan` | `throughput_inventory_area` |
| `cooling_load` | `cooling_load` |
| `equipment` | `equipment_selection` |
| `installed_power` | `electrical_and_energy` |
| `investment_estimate` | `investment_estimate` |

Every `measured_value` must carry `source_result_id`, `source_tool`,
`source_tool_version` bound to persisted `calculation_id`.

## 3. Integration matrix

Authoritative P5 test surface (single file):

```text
backend/tests/integration/test_v06_p5_controlled_acceptance.py
```

| AC ID | Assertion | Test function |
| --- | --- | --- |
| P5-AC-01 | Contract records source identity; forbids tag/release | `test_p5_contract_records_source_identity_and_forbids_tag_release` |
| P5-AC-02 | Loader allowlist; no planning-run or Alembic in loader | `test_p5_allowlist_and_loader_do_not_call_planning_run_or_alembic` |
| P5-AC-03 | Frontend binds public report APIs and formal eligibility | `test_p5_frontend_report_workflow_binds_public_report_apis` |
| P5-AC-04 | Operator sample canonical five + lineage (sqlite) | `test_p5_sqlite_operator_sample_canonical_five_and_lineage` |
| P5-AC-05 | Restart preserves hashes (sqlite) | `test_p5_sqlite_restart_preserves_hashes` |
| P5-AC-06 | Report lifecycle fail-closed or formal artifacts (sqlite) | `test_p5_sqlite_report_lifecycle_fail_closed_or_formal_artifacts` |
| P5-AC-07 | Formal without mark-reviewed is 409 (sqlite) | `test_p5_sqlite_formal_without_mark_reviewed_is_409` |
| P5-AC-08 | Untrusted actor cannot mark-reviewed (sqlite) | `test_p5_sqlite_untrusted_actor_cannot_mark_reviewed` |
| P5-AC-09 | Demo coefficients remain unverified (sqlite) | `test_p5_sqlite_demo_coefficients_remain_unverified` |
| P5-AC-10 | Agent assistance not fake-available (sqlite) | `test_p5_sqlite_agent_assistance_not_fake_available` |
| P5-AC-11 | Missing KEY leaf fail-closed (sqlite) | `test_p5_sqlite_missing_key_leaf_fails_closed_atomically` |
| P5-AC-12..18 | PostgreSQL mirrors of P5-AC-04..11 | `test_p5_pg_*` |

Database matrix:

- **SQLite CI job:** `DATABASE_BACKEND=sqlite uv run pytest` (full suite).
- **PostgreSQL CI job:** `pytest -m postgresql` and
  `pytest -k "not architecture and not postgresql and not sqlite"`.
- Sqlite cases: `@pytest.mark.sqlite`, skip when `DATABASE_BACKEND=postgresql`.
- PostgreSQL cases: `@pytest.mark.postgresql`, function names use `pg` not
  `postgresql`, skip unless `DATABASE_BACKEND=postgresql`.
- Contract/frontend scans: unmarked, no database required.
- PostgreSQL operator fixtures bind `COLD_STORAGE_DATABASE_BACKEND=postgresql`
  and `COLD_STORAGE_DATABASE_URL` to the isolated `pg_database` URL before
  `trusted_sample_client` / `verify_v06_sample` so reports `get_engine()` matches
  five-stage persistence (test-harness only; not a production change).

P5 reuses read-only fixtures:

- `cold_storage.bootstrap.v06_sample_loader`
- `tests.integration.v05_p4_acceptance_fixtures`
- `tests.integration.v05_p5_acceptance_evidence` (missing-key cells only)

No V0.3 stage engine. No `v06_p5_acceptance_evidence.py` helper module.

## 4. Operator runbook (existing P4B; not duplicated)

Operator commands on `main`:

```bash
make migrate
make seed-v06-sample
make verify-v06-sample
```

Authoritative runbook: `docs/runbooks/v06-pilot-runbook.md`

Pytest must call `verify_v06_sample` / `seed_v06_sample` against isolated URLs so
GitHub sqlite+pg jobs execute the matrix (not `make verify-v06-sample` alone).

## 5. Issue-closure evidence (record only; do not close via gh)

| Issue | Status | P5 evidence | Remaining |
| --- | --- | --- | --- |
| #11 TASK-009A report JSON | OPEN | P1 assembly on main + P5 report generate/`source_result_id`/blocker tests | Operator-path submit-review/formal may stay 409 on v06 sample (`project_summary`/`scheme_comparison` absent on unmodified `create_app`) |
| #13 TASK-009B DOCX/PDF | OPEN | P2 rendering on main + P3 evaluation happy-path formal artifacts | Operator-path formal 409 on v06 sample until review closure exists |
| #17 rendering follow-ups | OPEN | P2 long-format scheme tables + P4A workflow | P5 does not re-litigate PDF row-binding |
| #20 | CLOSED (2026-07-22) | Record only. Do not reopen. | — |
| #72 | CLOSED | Record only. `high_throughput_review` stays label-only. Do not reopen. | — |
| #176 | OPEN | Umbrella; P5 does not claim v0.6.0 published | Release gate later |
| #177 | OPEN | P5 tracking; evidence in this contract + integration matrix | Coordinator closure later |

## 6. Implementation allowlist

```text
docs/tasks/V0_6-P5-controlled-acceptance-contract.md
backend/tests/integration/test_v06_p5_controlled_acceptance.py
```

Forbidden without separate authorization: `backend/src/**`, `frontend/**`,
`samples/**`, `Makefile`, runbooks, P0/P3 contracts, evaluation tests,
architecture tests, workflows, tag/Release automation.

## 7. Acceptance criteria

V0.6 P5 R1 is complete when:

```text
P5_CONTRACT_EXISTS=PASS
SOURCE_IDENTITY_FIELDS_RECORDED=PASS
LOADER_ALLOWLIST_SCAN=PASS
FRONTEND_CONTRACT_SCAN=PASS
SQLITE_OPERATOR_MATRIX=PASS
POSTGRESQL_OPERATOR_MATRIX=PASS
P3_EVALUATION_CONSUMED_NOT_REIMPLEMENTED=PASS
CI_GREEN=PASS (later gate on merge)
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

If operator-path `submit-review` is 409 on the v06 sample,
`report_lifecycle_fail_closed=true` is **PASS**, not a defect to patch in P5.
