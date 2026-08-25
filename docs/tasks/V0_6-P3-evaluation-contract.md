# V0.6 P3 Evaluation Contract — Five-Stage Review to Formal-Mode Evaluation

**Status:** Definition freeze R1 — evaluation evidence only (no production mutation)
**Authority:** Issue #176 (umbrella), tracked by Issue #179, dispatched by Issue #190
**Parent contract:** `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md`
**Deferred authority:** Issue #72 (not closed by P3)
**Base (P3 branch from):** `origin/main` SHA `d8e89a4065be53e1652d40590e4787eba848609d`
**Previous release:** `v0.5.0`
**Target branch:** `cursor/v06-p3-review-formal-evaluation-6c68`

P3 proves the V0.5 five-stage persisted path can enter the existing scheme
review and trusted formal-report lifecycle. P3 does **not** mutate production
code, calculator formulas, review thresholds, or TASK-011 goldens.

## 0. Contract identity

```text
TASK=V06_P3_REVIEW_FORMAL_EVALUATION_R1
PARENT_ISSUE=176
P3_TRACKING_ISSUE=179
DISPATCH_ISSUE=190
GOVERNANCE_OWNER=V0.6
BASE_MAIN_SHA=d8e89a4065be53e1652d40590e4787eba848609d
PREVIOUS_RELEASE=v0.5.0
TARGET_BRANCH=cursor/v06-p3-review-formal-evaluation-6c68
TARGET_PR_STATE=DRAFT
V06_P3_IMPLEMENTATION_AUTHORIZED=YES
V06_P3_PRODUCTION_MUTATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
READY_AUTHORIZED=NO
CLOSES_72=NO
CLOSES_176=NO
```

## 1. Objective

Prove (SQLite **and** PostgreSQL):

```text
five-stage persisted results
  -> scheme (deterministic review reasons)
  -> trusted mark_reviewed
  -> report create/generate/submit_review/mark_reviewed/approve
  -> formal zh-CN and en-US DOCX and PDF
```

with fail-closed negatives for:

1. formal export without trusted `mark_reviewed` proof (`ExportPermissionError` / HTTP 409)
2. missing canonical sources blocking formal export (quality blockers / HTTP 409 or 422)

## 2. Frozen scenario labels

| Label | Role | Mutates review rules |
| --- | --- | --- |
| `five_stage_persisted_formal_evaluation` | Primary P3 evaluation scenario | No |
| `high_throughput_review` | Deferred pilot-scope scenario label only | **No** |

`high_throughput_review` is metadata for deferred high-throughput/formal-mode
pilot scope. It does **not** introduce a new review rule, status machine, or
calculator formula recut.

Registry fixture:

- `backend/tests/fixtures/v06/v06_p3_scenario_registry.v1.json`

## 3. Source-definition evidence (required before label goldens)

| Fixture | SHA-256 | Purpose |
| --- | --- | --- |
| `backend/tests/fixtures/v06/v06_p3_high_throughput_review_label_source.v1.json` | `2c99808ba2f34bb052324707fd48b01bb13b294f9af1683afe1fb15eadb42cf8` | Label-only source definition + reviewer evidence |
| `backend/tests/fixtures/v06/v06_p3_v05_seed_manifest_ref.v1.json` | `1251d5799a5ef30c526ae6768167edcafe867235dba6a55fc421bc20df47ebd9` | Public five-stage seed authority |
| `backend/tests/fixtures/v06/v06_p3_investment_translation_overlay.v1.json` | `e128aedea75ed381893e6879c52d3fafe5de2e3d963c422b6a42b553879b7a3e` | Evaluation-only formal-render translation overlay for v05 investment item labels |
| `backend/tests/pilot/data/task011-followup-high-throughput-source.v1.json` | `aaa965a9a5d679c7fe9399579c48c7d7c62484969c1ac82636b8fc7023cfad0d` | Upstream label reference (read-only) |
| `samples/v05-local-workbench/manifest.json` | `f12f37294c52b63f7a8779a86ed89403108974c437576a8ebd64d4af3190c337` | EngineeringInputBundleV1 seed manifest |

Reviewer evidence for `high_throughput_review`:

- Review reasons remain projected by `project_review_reasons` / persisted
  `requires_review` flags — not by the label.
- Formal export authority remains `ReportRenderService._validate_export_permission`.
- Trusted operator seam remains `_require_persisted_mark_reviewed`.

TASK-011 goldens under `backend/tests/evaluation/data/expected/` and
`backend/tests/evaluation/data/task011-pilot-*.v1.json` are **not** rewritten by P3.

## 4. Public API sequence (frozen)

Seed five-stage data **only** through:

```text
cold_storage.bootstrap.v05_local_sample.seed_v05_local_sample
POST /api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution
```

Never `planning-run`. Never recalculate formulas. Never guess missing engineering values.

Report lifecycle (existing reports service/API):

```text
POST /api/v1/reports
POST /api/v1/reports/{id}/generate
POST /api/v1/reports/{id}/submit-review
POST /api/v1/reports/{id}/mark-reviewed
POST /api/v1/reports/{id}/approve
POST /api/v1/reports/{id}/revisions/{n}/render  (mode=formal, locale=zh-CN|en-US, format=docx|pdf)
```

Trusted actor for `mark_reviewed` in P3 tests: `v06-p3-trusted-reviewer`.
Default API actor `system` is intentionally **not** trusted.

## 5. Canonical calculator identities

After five-stage seed, canonical calculator names must be exactly:

```text
cold_room_zone_plan
cooling_load
equipment
installed_power
investment_estimate
```

`power_configuration` must **not** satisfy electrical/report power authority.

## 6. SQLite / PostgreSQL parity

Parametrize like P1 assembly tests:

- skip sqlite when `DATABASE_BACKEND=postgresql`
- skip postgresql otherwise

Both backends must prove the same acceptance criteria with identical API shapes.

## 7. Acceptance criteria mapped to tests

Authoritative test surface:

```text
backend/tests/evaluation/test_v06_p3_review_formal_evaluation.py
backend/tests/evaluation/v06_p3_lifecycle_helpers.py
backend/tests/fixtures/v06/**
```

| ID | Criterion | Test |
| --- | --- | --- |
| P3-AC-01 | Canonical five calculator names; `power_configuration` not canonical power | `test_p3_canonical_calculator_names_after_five_stage_seed` |
| P3-AC-02 | Report generate binds persisted calculation ids into report JSON (`source_result_id`) | `test_p3_report_generate_binds_persisted_source_result_ids` |
| P3-AC-03 | `input_conditions` / `assumptions` from persisted snapshots | `test_p3_input_conditions_and_assumptions_from_persisted_snapshots` |
| P3-AC-04 | Happy path formal zh-CN/en-US DOCX+PDF with provenance metadata | `test_p3_happy_path_formal_exports_bind_provenance` |
| P3-AC-05 | Formal render without trusted `mark_reviewed` fails closed (409) | `test_p3_formal_render_without_mark_reviewed_fails_closed` |
| P3-AC-06 | Missing canonical source fails closed for formal export | `test_p3_missing_canonical_source_fails_closed_for_formal_export` |
| P3-AC-07 | Restart/reopen preserves calculation ids/hashes and revision hash | `test_p3_restart_reopen_preserves_calculation_and_revision_hashes` |
| P3-AC-08 | `high_throughput_review` is label-only; review authority unchanged | `test_p3_high_throughput_review_label_does_not_mutate_review_authority` |

## 8. P3 allowlist (exclusive)

```text
backend/tests/evaluation/**
backend/tests/fixtures/v06/**
docs/tasks/V0_6-P3-evaluation-contract.md
```

Forbidden in P3 (unchanged from dispatch):

```text
backend/src/**
frontend/**
backend/alembic/**
reports production modules
cold_storage.evaluation production modules
samples/**
Makefile
```

## 9. Closure state

```text
V06_P3_CONTRACT_FROZEN=YES
V06_P3_EVALUATION_EXECUTED=YES_AFTER_TESTS_PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 10. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-25 | Initial P3 evaluation contract and public-API lifecycle evidence |
