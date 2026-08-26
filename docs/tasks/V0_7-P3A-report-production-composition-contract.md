# V0.7 P3A Report Production Composition Contract

**Status:** Definition freeze R1 — operator `create_app` report DI composition
**Authority:** Parent contract `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Previous release:** `v0.6.0`
**Target branch:** `cursor/v07-p3a-report-production-composition-6c68`

P3A closes V07-GAP-001 only: inject `project_service` into
`RealReportDataProvider` on the unmodified operator `create_app` path so
`project_summary` can be assembled after report generate. It does not add
scheme routes, weaken fail-closed, change assembler `REQUIRED_SECTIONS`, or
recalculate formulas.

## 0. Contract identity and governance

```text
TASK=V07_P3A_REPORT_PRODUCTION_COMPOSITION_R1
PARENT_ISSUE=PENDING
P3A_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
BASE_TREE=23af6e60e4247394b2b12c50440d5fc03a819074
PREVIOUS_RELEASE=v0.6.0
TARGET_BRANCH=cursor/v07-p3a-report-production-composition-6c68
TARGET_FILE=docs/tasks/V0_7-P3A-report-production-composition-contract.md
TARGET_PR_STATE=DRAFT
```

```text
V07_P3A_IMPLEMENTATION_AUTHORIZED=YES
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective and non-goals

### 1.1 Objective

On the unmodified operator `create_app` path, after seeding the existing
v06 five-stage sample and calling report create + generate:

1. Generated report JSON **includes** `project_summary`.
2. `project_summary.project_name` equals the seeded project name from the
   sample manifest (`samples/v06-formal-delivery/manifest.json`).
3. SQLite and PostgreSQL integration tests both pass with isolated env and
   `dependencies._singletons`.

### 1.2 Non-goals (hard boundaries)

```text
ASSEMBLER_REQUIRED_SECTIONS_CHANGE=NO
FAIL_CLOSED_WEAKENING=NO
SCHEME_ROUTE_ADDITION=NO
FORMULA_CHANGE=NO
SUBMIT_REVIEW_HAPPY_PATH_REQUIRED=NO
FORMAL_EXPORT_HAPPY_PATH_REQUIRED=NO
```

Until P3B lands, `scheme_comparison` may still be absent on the operator
sample. `submit-review` and formal zh-CN/en-US DOCX/PDF may remain 409
fail-closed. P3A tests must **not** assert full submit-review or formal
export success.

## 2. Production change boundary

**Single allowed production edit:**

`backend/src/cold_storage/bootstrap/app.py` — function `_get_report_service`
only.

Wire the canonical `get_project_service()` singleton into
`RealReportDataProvider(project_service=...)`, matching the evaluation DI
pattern already used in integration fixtures and unit tests.

Forbidden production paths for P3A:

```text
backend/src/cold_storage/modules/reports/application/assembler.py
backend/src/cold_storage/modules/schemes/**
backend/src/cold_storage/modules/calculations/**
frontend/**
```

## 3. Inherited contracts

P3A inherits frozen report source mapping, fail-closed lifecycle rules, and
demo-coefficient governance from V0.7 P0 and V0.6 P0. Reports must not
recalculate formulas.

## 4. Exclusive allowlist

```text
V07_P3A_FILE_ALLOWLIST
docs/tasks/V0_7-P3A-report-production-composition-contract.md
backend/src/cold_storage/bootstrap/app.py
backend/tests/integration/test_v07_p3a_report_project_summary_sqlite.py
backend/tests/integration/test_v07_p3a_report_project_summary_postgresql.py
```

## 5. Test matrix

| Test file | Backend | Assertions |
| --- | --- | --- |
| `test_v07_p3a_report_project_summary_sqlite.py` | SQLite | generate → export JSON contains `project_summary`; name matches seed |
| `test_v07_p3a_report_project_summary_postgresql.py` | PostgreSQL | same; env vars set before `create_app`; `_singletons` isolated |

Test setup must follow V0.6 P5 PostgreSQL conventions:

- Set `COLD_STORAGE_DATABASE_BACKEND` and `COLD_STORAGE_DATABASE_URL` before
  `create_app`.
- Isolate `cold_storage.bootstrap.dependencies._singletons` across tests.
- Use `trusted_sample_client` / v06 sample seed through public APIs only.

## 6. Acceptance criteria

```text
P3A_CONTRACT_EXISTS=PASS
PROJECT_SERVICE_INJECTED_IN_GET_REPORT_SERVICE=PASS
PROJECT_SUMMARY_PRESENT_AFTER_GENERATE_SQLITE=PASS
PROJECT_SUMMARY_PRESENT_AFTER_GENERATE_POSTGRESQL=PASS
PROJECT_NAME_MATCHES_SEED=PASS
ALLOWLIST_RESPECTED=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 7. Contract closure state

```text
TASK=V07_P3A_REPORT_PRODUCTION_COMPOSITION_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P3A-report-production-composition-contract.md
V07_P3A_CONTRACT_FROZEN=YES
V07_P3A_IMPLEMENTATION_AUTHORIZED=YES
V07_P3A_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 8. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P3A report production composition contract |
