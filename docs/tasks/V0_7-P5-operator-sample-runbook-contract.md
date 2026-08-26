# V0.7 P5 Operator Sample, Runbook, and UI Alignment Contract

**Status:** Definition freeze R1 — operator trust-loop sample + runbook + frontend alignment
**Authority:** Parent contract `docs/tasks/V0_7-P0-trust-loop-contract.md` §5.7
**Requires:** P3A (`project_summary` on unmodified `create_app`) and P3B (`POST .../production-scheme-runs`)
**Target branch:** `cursor/v07-p5-operator-sample-runbook-6c68`

P5 closes **V07-GAP-003** on the operator path: the bundled V0.7 sample
completes the trust loop on **unmodified** `create_app` through public HTTP
only (plus the frozen production-weight seed exception documented below).

## 0. Contract identity and governance

```text
TASK=V07_P5_OPERATOR_SAMPLE_RUNBOOK_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=e6ad66eef6da66117bd6f0c3bbb67d5179780ebb
TARGET_BRANCH=cursor/v07-p5-operator-sample-runbook-6c68
TARGET_FILE=docs/tasks/V0_7-P5-operator-sample-runbook-contract.md
TARGET_PR_STATE=DRAFT
```

```text
V07_P5_IMPLEMENTATION_AUTHORIZED=YES
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
PRODUCTION_RBAC_CLAIM=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

On **unmodified** `create_app`, the V0.7 operator sample must complete:

```text
POST five-stage-execution
 → POST .../production-scheme-runs (source_mode=production)
 → POST /api/v1/reports + generate
 → JSON contains project_summary and scheme_comparison.review_authority
 → submit-review HTTP 200
 → trusted TestClient actor mark-reviewed HTTP 200
 → untrusted actor mark-reviewed fail-closed
 → zh-CN/en-US DOCX/PDF formal render HTTP 200
```

### 1.1 Non-goals (hard boundaries)

```text
V06_SAMPLE_LOADER_MUTATION=NO
BOOTSTRAP_APP_MUTATION=NO
SCHEMES_API_ROUTES_MUTATION=NO
WORKFLOW_SERVICE_MUTATION=NO
CANONICAL_SOURCE_READS_MUTATION=NO
FORMULA_CHANGE=NO
COEFFICIENT_PROMOTION=NO
DEMO_SCHEME_COMPARISON_BINDING=NO
LEGACY_SCHEME_RUNS_AS_REPORT_AUTHORITY=NO
PLANNING_RUN=NO
ALEMBIC_INSIDE_LOADER=NO
V06_P5_TEST_ASSERTION_MUTATION=NO
V05_V06_TEST_ASSERTION_MUTATION=NO
V06_P3_EVALUATION_HELPERS_IN_OPERATOR_TESTS=NO
PRODUCTION_RBAC_CLAIM=NO
```

## 2. Frozen operator sample identity

| Item | Frozen value |
| --- | --- |
| Sample id | `v07-trust-loop` |
| Manifest | `samples/v07-trust-loop/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v07_sample_loader.py` |
| Trusted actor (TestClient seam) | `v07-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Production weight revision | `wsr-production-default-v1` (`PRODUCTION_WEIGHT_SET_REVISION_ID`) |
| Production scheme profile | `balanced` |
| Production scheme route | `POST /api/v1/projects/{project_id}/versions/{version}/production-scheme-runs` |

### 2.1 HTTP-only loader rule

The loader uses **only** these public API families:

- `POST/GET /api/v1/projects/**`
- `POST .../five-stage-execution`
- `POST .../production-scheme-runs`
- `POST/GET /api/v1/reports/**` (create, generate, submit-review, mark-reviewed, approve, export, render, download)

**Forbidden loader paths:**

- `GET /api/v1/demo/scheme-comparison`
- legacy `POST .../scheme-runs` as report authority
- `planning-run`
- Alembic inside the loader

### 2.2 Sole non-HTTP exception

After `create_app` lifespan starts, the loader **may** call the existing
`seed_production_weight_revision()` with frozen id `wsr-production-default-v1`.
It must not invent alternate weight content.

## 3. Report JSON acceptance (operator path)

After generate, exported JSON must include:

| Section | Minimum assertion |
| --- | --- |
| `project_summary` | present; `project_name` matches manifest |
| `scheme_comparison.review_authority` | present; `scheme_run_id`, `source_binding_id`, `combined_source_hash` bound to production run |

Reports must not recalculate formulas. Vue must display persisted values only.

## 4. Review / formal-export acceptance

| Step | Trusted client | Untrusted client |
| --- | --- | --- |
| `submit-review` | HTTP 200 | n/a in verify seed path |
| `mark-reviewed` | HTTP 200 | must **not** HTTP 200 |
| `approve` | HTTP 200 after trusted mark-reviewed | n/a |
| formal `zh-CN`/`en-US` DOCX/PDF | HTTP 200 | n/a |

Trusted operator remains a TestClient `_get_actor` override — **not** production RBAC.

## 5. Makefile targets

```text
seed-v07-sample    → python -m cold_storage.bootstrap.v07_sample_loader
verify-v07-sample  → python -m cold_storage.bootstrap.v07_sample_loader --verify
```

Existing `seed-v06-sample` / `verify-v06-sample` must remain unchanged.

## 6. Frontend alignment (read-only display)

Allowed UI changes:

- `frontend/src/features/reports/**` — show persisted `project_summary` and
  `scheme_comparison` from report JSON export; no formula computation.
- `frontend/src/features/five-stage/components/**` — trigger
  `production-scheme-runs`; display persisted run summary; no formula computation.

E9 (`scheme_comparison` formal-export blocker) is **not** changed. The sample
satisfies existing rules by persisting a production scheme run before report
generate.

## 7. Exclusive allowlist

```text
V07_P5_FILE_ALLOWLIST
docs/tasks/V0_7-P5-operator-sample-runbook-contract.md
samples/v07-trust-loop/**
backend/src/cold_storage/bootstrap/v07_sample_loader.py
docs/runbooks/v07-trust-loop-runbook.md
Makefile
backend/tests/integration/v07_p5_operator_fixtures.py
backend/tests/integration/test_v07_p5_operator_sample_sqlite.py
backend/tests/integration/test_v07_p5_operator_sample_postgresql.py
frontend/src/features/reports/**
frontend/src/features/five-stage/components/**
frontend/tests/features/reports/**
```

## 8. Test matrix

| Test file | Backend | Assertions |
| --- | --- | --- |
| `test_v07_p5_operator_sample_sqlite.py` | SQLite | unmodified `create_app`; full trust loop; restart stability |
| `test_v07_p5_operator_sample_postgresql.py` | PostgreSQL | same; env before `create_app`; `_singletons` isolated |

Operator tests must **not** import `tests/evaluation/v06_p3_lifecycle_helpers.py`.

## 9. Acceptance criteria

```text
P5_CONTRACT_EXISTS=PASS
V07_SAMPLE_MANIFEST_EXISTS=PASS
V07_LOADER_PUBLIC_API_ONLY=PASS
PRODUCTION_SCHEME_RUN_PERSISTED=PASS
REPORT_PROJECT_SUMMARY_PRESENT=PASS
REPORT_SCHEME_COMPARISON_REVIEW_AUTHORITY_PRESENT=PASS
SUBMIT_REVIEW_200_SQLITE=PASS
SUBMIT_REVIEW_200_POSTGRESQL=PASS
TRUSTED_MARK_REVIEWED_200=PASS
UNTRUSTED_MARK_REVIEWED_FAIL_CLOSED=PASS
FORMAL_ZH_CN_EN_US_DOCX_PDF_200=PASS
MAKEFILE_V07_TARGETS=PASS
V06_MAKEFILE_UNCHANGED=PASS
FRONTEND_PRODUCTION_SCHEME_RUN_UI=PASS
FRONTEND_REPORT_PERSISTED_SECTIONS=PASS
RUFF_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 10. Contract closure state

```text
TASK=V07_P5_OPERATOR_SAMPLE_RUNBOOK_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P5-operator-sample-runbook-contract.md
V07_P5_CONTRACT_FROZEN=YES
V07_P5_IMPLEMENTATION_AUTHORIZED=YES
V07_P5_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 11. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P5 operator sample, runbook, and UI alignment contract at `e6ad66e` |
