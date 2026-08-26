# V0.7 P3B Production Scheme Public API Contract

**Status:** Implementation R1 — public production-scheme write path only
**Authority:** `docs/tasks/V0_7-P0-trust-loop-contract.md` §5.5
**Parent contract:** `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Base (P3B branch from):** `origin/cursor/v07-p0-trust-loop-contract-6c68`
**Target branch:** `cursor/v07-p3b-production-scheme-public-api-6c68`

P3B adds the **only** authorized public HTTP write path that persists
`source_mode=production` scheme runs bound to the five-stage
`SourceBinding` for a project version. Legacy `POST .../scheme-runs`
remains legacy/demo authority and is not repurposed.

## 0. Contract identity

```text
TASK=V07_P3B_PRODUCTION_SCHEME_PUBLIC_API_R1
PARENT_CONTRACT=docs/tasks/V0_7-P0-trust-loop-contract.md
GOVERNANCE_OWNER=V0.7
TARGET_BRANCH=cursor/v07-p3b-production-scheme-public-api-6c68
TARGET_PR_STATE=DRAFT
V07_P3B_IMPLEMENTATION_AUTHORIZED=YES
MERGE_AUTHORIZED=NO
READY_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
```

## 1. Objective

Close **V07-GAP-002** by exposing a distinct production scheme API that:

1. Resolves the project version from the URL.
2. Binds the newest persisted five-stage `SourceBinding` for that version.
3. Delegates generation to `ProductionSchemeService.generate_production_scheme_run`
   via `get_production_scheme_service()`.
4. Persists `source_mode=production` with full production provenance.
5. Enables report assembly to project `scheme_comparison.review_authority`
   through strict production readback (`read_verified_production_scheme_run`).

## 2. Frozen route

```text
POST /api/v1/projects/{project_id}/versions/{version}/production-scheme-runs
```

Registration site: `register_scheme_routes` in
`backend/src/cold_storage/modules/schemes/api/routes.py`.

**Forbidden:**

- Editing `bootstrap/app.py` (P3A-only).
- Weakening `read_verified_production_scheme_run`.
- Binding `GET /api/v1/demo/scheme-comparison` to the operator/sample version.
- Changing calculator formulas or promoting coefficients.
- Repurposing legacy `POST .../scheme-runs` as production authority.

## 3. Request contract

JSON body:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `profile_codes` | `list[str]` | yes | Passed to `GenerateProductionSchemeCommand.profile_codes` |
| `weight_set_revision_id` | `str` | yes | Approved revision identity for production scoring |
| `profile_parameters` | `dict[str, dict]` | no | Defaults to `{}` |

Server-derived fields (not client-supplied):

- `source_binding_id` — newest `orchestration_source_bindings` row for the
  resolved `project_id` + `project_version_id`.
- `correlation_id` — minted per request (`uuid4`).
- `database_backend` — `get_settings().database_backend`.
- `actor` — empty string unless a future contract adds trusted transport.

## 4. Response contract

HTTP 200 returns a production run summary including at minimum:

- `run_id`, `project_id`, `project_version_id`
- `source_mode` = `"production"`
- `source_binding_id`, `weight_set_revision_id`
- `status`, `generator_version`, `recommended_scheme_code`
- `requires_review`, `review_reasons` (canonical five-field JSON)
- `combined_source_hash`, `content_hash`

## 5. Status code mapping

| Condition | HTTP |
| --- | --- |
| Project / version not found | 404 |
| No five-stage `SourceBinding` on version | 409 |
| Source binding / orchestration verification failure | 409 |
| Weight revision governance / domain validation failure | 422 |
| Unexpected persistence failure | 409 |

## 6. Report readback acceptance (P3B scope)

Integration tests prove:

1. Public API `POST .../production-scheme-runs` persists a production run
   (SQLite **and** PostgreSQL).
2. Focused report read (test-local `RealReportDataProvider` wiring — **not**
   `bootstrap/app.py`) assembles `scheme_comparison.review_authority`
   with `source_binding_id` and `combined_source_hash`.

Full operator `create_app` report composition (`project_summary`) remains
P3A. Operator sample closure remains P5.

## 7. Exclusive allowlist

```text
V07_P3B_FILE_ALLOWLIST
docs/tasks/V0_7-P3B-production-scheme-public-api-contract.md
backend/src/cold_storage/modules/schemes/api/routes.py
backend/tests/integration/test_v07_p3b_production_scheme_public_api_sqlite.py
backend/tests/integration/test_v07_p3b_production_scheme_public_api_postgresql.py
backend/tests/unit/test_v07_p3b_production_scheme_routes.py
```

## 8. Acceptance criteria

```text
P3B_CONTRACT_EXISTS=PASS
FROZEN_ROUTE_REGISTERED=PASS
USES_GET_PRODUCTION_SCHEME_SERVICE=PASS
BINDS_FIVE_STAGE_SOURCE_BINDING=PASS
SOURCE_MODE_PRODUCTION_PERSISTED=PASS
READ_VERIFIED_PRODUCTION_SCHEME_RUN_UNCHANGED=PASS
DEMO_SCHEME_COMPARISON_UNCHANGED=PASS
BOOTSTRAP_APP_UNCHANGED=PASS
REPORT_SCHEME_COMPARISON_REVIEW_AUTHORITY_SQLITE=PASS
REPORT_SCHEME_COMPARISON_REVIEW_AUTHORITY_POSTGRESQL=PASS
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 9. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P3B public production-scheme API contract |
