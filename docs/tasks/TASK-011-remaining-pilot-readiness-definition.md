# TASK-011 Remaining Pilot Readiness — Freeze Candidate

> **Status:** `FINAL_FREEZE_CANDIDATE_PENDING_CI_AND_CHARLES_AUTHORIZATION`
>
> **Authority:** Issue #20 comment `4993536755`.
>
> **Round-1 review:** PR #66 review `4715270274`.
>
> **Round type:** docs-only definition. This document does not itself authorize implementation, Ready, Merge, Issue #20 closure, Task 12, or any work named TASK-011D.

## 1. Repository identity

```text
ISSUE_NUMBER=20
AUTHORITY_COMMENT_ID=4993536755
SOURCE_MAIN_SHA=a16075fed9ef7cabafc41cf0398c54fd6088f578
BRANCH=codex/task-011-remaining-pilot-readiness-definition
DOCUMENT_PATH=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
ROUND1_REVIEW_ID=4715270274
DOCUMENT_STATUS=FINAL_FREEZE_CANDIDATE_PENDING_CI_AND_CHARLES_AUTHORIZATION
CONTRACT_FROZEN=NO
```

This definition follows the TASK-011 work merged through PRs #60, #64, and #65. It does not reopen or modify the frozen TASK-011C V1 scenario semantics, schema, golden files, formulas, coefficients, thresholds, scoring, or production review rules.

## 2. Verified completed state

```text
BASELINE_FEASIBLE_EXPECTED_OUTPUT=MERGED
MANIFEST_SCHEMA_AND_LOADER=MERGED
CANONICALIZATION_AND_COMPARISON=MERGED
MULTI_SCENARIO_RUNNER=MERGED
INVALID_BLOCKED_PRODUCTION_PATH=MERGED
INVALID_BLOCKED_EXPECTED_OUTPUT=MERGED
D3_V1_EXCLUDED_JSON_PATHS=[]
HIGH_THROUGHPUT_REVIEW=DEFERRED_FROM_TASK_011C_V1
```

Repository audit of PR #63 and PR #64 confirms that those rounds delivered the manifest schema, loader, models, canonicalization, comparison, and runners, but did **not** commit an executable repository-owned V1 manifest instance.

```text
TRACKED_EXECUTABLE_V1_MANIFEST_INSTANCE=ABSENT
PILOT_MANIFEST_PATH_PLACEHOLDERS=FORBIDDEN
```

Therefore this contract defines two new backend-specific pilot manifest instances without changing the frozen schema or expected outputs.

## 3. Remaining deliverables

After separate implementation authorization, the remaining TASK-011 deliverables are:

1. multilingual report pilot acceptance;
2. repository-owned pilot/demo runbook;
3. TASK-011 closure evidence record.

Explicit exclusions:

- `high_throughput_review` production integration;
- formal-mode pilot acceptance in Slice 1;
- new formulas, coefficients, thresholds, scoring, or review rules;
- external OCR, model, translation, or document services;
- production deployment hardening or Task 12;
- real customer, farm, factory, personal, confidential, or secret data;
- replacement of the report or evaluation architecture.

## 4. Binding R1–R14 freeze candidate

```text
R1_PILOT_CHECK_ID=multilingual_report_same_revision
R2_FOUR_RENDER_DRAFT_MATRIX=zh-CN/en-US_x_docx/pdf
R3_FORMAL_MODE_SMOKE_SCOPE=DEFERRED_OUT_OF_CURRENT_SCOPE
R4_CROSS_RENDER_INVARIANTS=AXIS_SPECIFIC_WITH_EXPLICIT_EVIDENCE
R5_PERMITTED_DIFFERENCES=AXIS_SPECIFIC_SELF_INTEGRITY_ONLY
R6_SEMANTIC_AUTHORITY=EXISTING_PRODUCTION_SYMBOLS
R7_REPEATABILITY_RUNS_PER_BACKEND=2
R8_RESULT_SCHEMA_VERSION=task11-pilot-report.v1
R9_ARTIFACT_IO_AUTHORITY=SINGLE_PUBLIC_SHARED_MODULE
R10_IMPLEMENTATION_SURFACE=EXACT_PATH_ALLOWLIST
R11_CI_BOUNDARY=EXISTING_BACKEND_SQLITE_AND_POSTGRESQL_JOBS
R12_RUNBOOK_PATH=docs/tasks/TASK-011-pilot-demo-runbook.md
R13_HIGH_THROUGHPUT_DISPOSITION=PATH_A
R14_ISSUE20_CLOSURE=SEPARATE_AUTHORIZATION_AFTER_FRESH_CHECKOUT_EVIDENCE
```

## 5. Pilot source manifests

### 5.1 Exact tracked paths

```text
SQLITE_PILOT_MANIFEST=
  backend/tests/evaluation/data/task011-pilot-sqlite.v1.json

POSTGRESQL_PILOT_MANIFEST=
  backend/tests/evaluation/data/task011-pilot-postgresql.v1.json
```

Each file is a valid `schema_version="1.0"` manifest loaded only through:

```text
cold_storage.evaluation.manifest::load_and_validate_manifest
```

### 5.2 Exact semantic content

Each manifest contains exactly one scenario:

```text
scenario_id=baseline_feasible
expected_outcome=SUCCEEDED
expected_output.path=expected/baseline_feasible.v1.json
expected_output.expected_outcome=SUCCEEDED
expected_output.commit_sha=f274db66fe4bb2de206d12c2d561d1b3549ab6c0
excluded_paths=[]
fixtures=OMITTED
comparison_policy=OMITTED
```

Omitting `comparison_policy` means the existing frozen exact-equality default applies. The implementation must not introduce an alternative comparison strategy.

Backend identity differs only as follows:

```text
task011-pilot-sqlite.v1.json:
  suite_id=task011-pilot-multilingual-sqlite
  database_backend=sqlite

task011-pilot-postgresql.v1.json:
  suite_id=task011-pilot-multilingual-postgresql
  database_backend=postgresql
```

The manifests must not:

- contain `invalid_blocked` or `high_throughput_review`;
- modify the baseline expected output;
- introduce a new expected output;
- use a non-empty exclusion set;
- reference a path outside their own parent directory;
- introduce scenario-specific production behavior;
- contain real or confidential data.

The expected-output relative path is valid because both manifests live beside the existing `expected/` directory under `backend/tests/evaluation/data/`.

### 5.3 Path-precise tracking

A future separately authorized Slice 1 may amend `.gitignore` only to track these exact files and the exact new implementation files listed in §11. Directory-wide unignore and `git add -f` remain forbidden.

## 6. Multilingual pilot execution

### 6.1 Pilot identity

```text
PILOT_CHECK_ID=multilingual_report_same_revision
PILOT_CHECK_CLASS=REPORT_VERIFICATION
SOURCE_SCENARIO=baseline_feasible
SOURCE_DATA=SYNTHETIC_REPOSITORY_OWNED
TASK011C_SCHEMA_CHANGE=NO
TASK011C_GOLDEN_CHANGE=NO
```

For each backend and repetition, the pilot composition must:

1. validate the backend-specific pilot manifest;
2. reject stale managed pilot outputs before database/report/filesystem side effects;
3. execute the existing `baseline_feasible` production-bound evaluation path against a fresh database;
4. require the baseline evaluation result to be PASS;
5. obtain the persisted project/version identities from the normalized result and persisted production state;
6. create one report and generate exactly one report revision through production report application services;
7. render all four mandatory artifacts from that exact revision without executing a second calculation or scheme run;
8. download each artifact through production download verification;
9. write `pilot-summary.json` last.

### 6.2 Exact source identity

```text
source_commit_sha
source_manifest_sha
project_id
project_version_id
report_id
report_revision_id
revision_number
report_revision_content_hash
report_type=cold_storage_concept_design
report_schema_version
```

### 6.3 Mandatory render matrix

| Locale | Format | Mode |
|---|---|---|
| `zh-CN` | `docx` | `draft` |
| `zh-CN` | `pdf` | `draft` |
| `en-US` | `docx` | `draft` |
| `en-US` | `pdf` | `draft` |

Formal-mode verification is deferred. It requires a future scope amendment and the existing report review/approval lifecycle.

## 7. Evidence and invariants

### 7.1 Required production authorities

```text
CANONICAL_MODEL_AUTHORITY=
  cold_storage.modules.reports.application.canonical_render_model_builder
  ::build_canonical_render_model

LOCALIZATION_AUTHORITY=
  cold_storage.modules.reports.application.render_model_localizer
  ::localize_render_model

CATALOG_AUTHORITY=
  cold_storage.modules.reports.localization.catalog
  ::get_catalog
  ::compute_catalog_content_hash

DATA_PROVIDER_AUTHORITY=
  cold_storage.modules.reports.infrastructure.real_data_provider
  ::RealReportDataProvider

ARTIFACT_STORAGE_AUTHORITY=
  cold_storage.modules.reports.infrastructure.artifact_storage
  ::ReportArtifactStorage

TEMPLATE_PROVENANCE_AUTHORITY=
  persisted ReportTemplate.manifest_json
  persisted ReportTemplate.template_content_hash
  production ReportRenderService template selection
```

The pilot must not use `_RichDataProvider`, mock storage, fabricated report contents, handwritten translated report bodies, or a second report assembler.

### 7.2 Evidence sources

| Claim | Required source |
|---|---|
| project/report relationship | persisted `Report` plus production report service result |
| revision identity | persisted `ReportRevision` plus revision service result |
| artifact/report/revision binding | persisted `ReportExportArtifact` |
| format and locale | request values plus persisted artifact fields |
| render mode | `ReportExportArtifact.render_manifest_json["render_mode"]` |
| template provenance | persisted template plus render manifest |
| catalog provenance | artifact catalog version/hash plus catalog authority |
| localized template provenance | artifact localized-template hash |
| file integrity | persisted artifact, downloaded bytes, and verified-download headers |
| sections and numeric semantics | canonical model, localization authorities, and extracted downloaded content |

The verifier must not assume render mode exists as a top-level artifact API field.

### 7.3 Global invariants across all four renders

```text
project_id
project_version_id
report_id
report_revision_id
revision_number
report_revision_content_hash
source_content_hash
report_type
report_schema_version
render_mode=draft
canonical_section_key_set
canonical_numeric_field_path_set
canonical_numeric_value_and_unit_set
```

`source_content_hash` must equal `report_revision_content_hash`.

### 7.4 Same-locale invariants across DOCX/PDF

```text
locale
template_locale
translation_catalog_version
translation_catalog_content_hash
canonical_section_key_set
canonical_numeric_field_path_set
canonical_numeric_value_and_unit_set
```

`template_locale` must equal the requested locale.

### 7.5 Same locale+format invariants across repetitions/backends

```text
format
locale
template_locale
template_version
template_content_hash
template_schema_version
translation_catalog_version
translation_catalog_content_hash
localized_template_content_hash
required_section_result
numeric_semantic_result
PASS_FAIL_classification
```

Database-generated template IDs need not match across backends; template version and content hash are the governed identity.

### 7.6 Permitted self-integrity-only differences

```text
artifact_id
file_name
file_size_bytes
file_sha256
generated_at
storage_key
mime_type
downloaded binary bytes
DOCX/PDF container metadata
```

Each artifact must independently satisfy:

```text
artifact_status=completed
file_size_bytes>0
file_sha256=LOWERCASE_SHA256_HEX
DOWNLOAD_BYTES_SHA256=file_sha256
DOWNLOAD_HEADER_X_CONTENT_SHA256=file_sha256
DOWNLOAD_HEADER_X_SOURCE_CONTENT_HASH=source_content_hash
DOWNLOAD_HEADER_X_REPORT_LOCALE=locale
DOWNLOAD_HEADER_X_TEMPLATE_LOCALE=template_locale
translation_catalog_version=NON_EMPTY
translation_catalog_content_hash=LOWERCASE_SHA256_HEX
localized_template_content_hash=LOWERCASE_SHA256_HEX
```

Complete DOCX/PDF byte equality is never required.

### 7.7 Semantic verification

Required headings are derived from canonical `section_key` values and catalog keys `section.<section_key>`. Numeric verification is derived from canonical field paths, raw canonical values, and canonical unit codes.

The implementation must prove:

- every required canonical section is represented in each locale;
- localized headings equal the catalog values for that locale;
- numeric values and units are semantically equivalent across locales and formats;
- missing sections, units, or numeric drift fail closed;
- the verifier does not recompute engineering formulas.

## 8. Repeatability and backend coverage

```text
SQLITE_REPORT_PILOT=REQUIRED
POSTGRESQL_REPORT_PILOT=REQUIRED
REPEATABILITY_RUNS_PER_BACKEND=2
FRESH_DATABASE_PER_RUN=YES
CLEAN_OUTPUT_ROOT_PER_RUN=YES
CROSS_BACKEND_BUSINESS_INVARIANTS=EXACT
```

Generated database IDs, timestamps, storage keys, and binary hashes are not required to be identical between backends.

## 9. Result schema and managed layout

```text
PILOT_RESULT_SCHEMA_VERSION=task11-pilot-report.v1
```

Each run owns one absolute output root outside tracked repository files:

```text
<output-root>/
  pilot-run.json
  artifacts/
    zh-CN/docx/report.docx
    zh-CN/docx/artifact-metadata.json
    zh-CN/docx/semantic-checks.json
    zh-CN/pdf/report.pdf
    zh-CN/pdf/artifact-metadata.json
    zh-CN/pdf/semantic-checks.json
    en-US/docx/report.docx
    en-US/docx/artifact-metadata.json
    en-US/docx/semantic-checks.json
    en-US/pdf/report.pdf
    en-US/pdf/artifact-metadata.json
    en-US/pdf/semantic-checks.json
  pilot-summary.json
```

`pilot-summary.json` is written last and is the sole completion marker.

### 9.1 `pilot-run.json`

```text
schema_version
pilot_check_id
source_commit_sha
source_manifest_sha
database_backend
repeat_index
project_id
project_version_id
report_id
report_revision_id
revision_number
report_revision_content_hash
report_type
report_schema_version
started_at
```

### 9.2 `artifact-metadata.json`

```text
schema_version
artifact_id
report_id
report_revision_id
revision_number
format
locale
template_locale
render_mode
template_version
template_content_hash
template_schema_version
source_content_hash
translation_catalog_version
translation_catalog_content_hash
localized_template_content_hash
artifact_status
file_name
file_size_bytes
file_sha256
download_headers
integrity_result
```

### 9.3 `semantic-checks.json`

```text
schema_version
locale
format
canonical_section_keys
required_heading_keys
observed_localized_headings
canonical_numeric_fields
observed_numeric_fields
missing_sections
missing_units
numeric_mismatches
semantic_result
```

### 9.4 `pilot-summary.json`

```text
schema_version
pilot_check_id
source_commit_sha
source_manifest_sha
database_backend
repeat_index
started_at
completed_at
render_matrix
source_binding_result
artifact_integrity_result
semantic_result
overall_result
managed_file_sha256
```

`overall_result=PASS` only when every subordinate check is PASS.

## 10. Failure classification

At minimum, implementation must use stable machine-readable codes:

```text
SOURCE_BINDING_MISMATCH
REPORT_REVISION_MISMATCH
UNSUPPORTED_LOCALE
UNSUPPORTED_FORMAT
UNSUPPORTED_RENDER_MODE
RENDER_FAILED
ARTIFACT_NOT_COMPLETED
ARTIFACT_METADATA_MISMATCH
DOWNLOAD_NOT_FOUND
DOWNLOAD_INTEGRITY_MISMATCH
SOURCE_CONTENT_HASH_MISMATCH
LOCALE_BINDING_MISMATCH
TEMPLATE_LOCALE_MISMATCH
TEMPLATE_PROVENANCE_MISMATCH
TRANSLATION_CATALOG_IDENTITY_MISSING
TRANSLATION_CATALOG_IDENTITY_MISMATCH
LOCALIZED_TEMPLATE_HASH_MISSING
LOCALIZED_TEMPLATE_HASH_MISMATCH
REQUIRED_SECTION_MISSING
NUMERIC_SEMANTIC_MISMATCH
STALE_PILOT_ARTIFACTS
UNSAFE_OUTPUT_ROOT
INFRASTRUCTURE_ERROR
```

Message-text parsing is forbidden. Classification uses typed exceptions, structured fields, persisted records, and verified response headers.

## 11. Exact Slice 1 implementation allowlist

A future Slice 1 requires separate Charles implementation authorization. Its maximum tracked-file allowlist is:

```text
.gitignore
backend/src/cold_storage/evaluation/artifact_io.py
backend/src/cold_storage/evaluation/evaluate.py
backend/src/cold_storage/evaluation/pilot_reports.py
backend/tests/evaluation/data/task011-pilot-sqlite.v1.json
backend/tests/evaluation/data/task011-pilot-postgresql.v1.json
backend/tests/evaluation/test_artifact_io.py
backend/tests/evaluation/test_run_directory.py
backend/tests/pilot/run_multilingual_report_pilot.py
backend/tests/pilot/test_multilingual_report_pilot.py
backend/tests/architecture/test_phase1_identity_foundation_boundary.py
```

No other tracked path is authorized by this definition.

### 11.1 Shared artifact-I/O authority

```text
MODULE=backend/src/cold_storage/evaluation/artifact_io.py
PUBLIC_SYMBOLS=
  assert_no_managed_artifacts
  atomic_write_json
  atomic_write_bytes
  remove_managed_output_root
```

Rules:

- `evaluate.py` is refactored to use the public shared authority with no C-2 semantic change;
- the pilot verifier uses the same authority;
- importing private `_atomic_write_json` or `_assert_no_stale_artifacts` is forbidden;
- a second implementation is forbidden;
- regression tests preserve existing stale-output and summary-last behavior;
- output-root inspection precedes DB/report/managed-file side effects;
- writes use temp sibling, flush/fsync where supported, and atomic replace;
- prior runs are never overwritten;
- cleanup removes only the exact validated owned run root and rejects roots, home, repo root, backend root, symlink escapes, and non-owned paths;
- failed-run evidence remains until explicit cleanup.

### 11.2 Core verifier

```text
CORE_MODULE=backend/src/cold_storage/evaluation/pilot_reports.py
PUBLIC_FUNCTION=verify_multilingual_report_pilot
```

The core receives production service/query/storage ports and typed source identities. It does not seed databases, construct production ORM rows, modify report behavior, or import tests.

### 11.3 Repository-owned composition

```text
COMPOSITION_MODULE=backend/tests/pilot/run_multilingual_report_pilot.py
ENTRY_FUNCTION=main
```

The composition may reuse the already authorized synthetic evaluation seed helpers and must compose:

- the backend-specific pilot manifest;
- existing manifest loader and backend runner;
- existing production project/calculation/scheme query services;
- `RealReportDataProvider`;
- production `ReportService` and `ReportRenderService`;
- `ReportArtifactStorage` rooted under the named pilot output root;
- the core verifier.

It must not use `_RichDataProvider`, mock storage, fabricated report contents, or hand-built translated text.

### 11.4 `.gitignore` amendment

The future Slice 1 may add path-precise exceptions only for the new files in this allowlist. It must retain the generic `data/` and evaluation guardrails, and must not unignore a directory broadly.

## 12. Exact commands

All file paths passed to Python are absolute. Commands execute from `backend/` and derive the exact implementation Head from Git.

### 12.1 SQLite

```bash
cd backend
REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:///${PILOT_ROOT}/task011-pilot.sqlite3" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-sqlite.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

Repeat with a new `PILOT_ROOT` and `--repeat-index 2`.

### 12.2 PostgreSQL

```bash
cd backend
REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend postgresql \
  --database-url "$TASK011_PILOT_POSTGRESQL_URL" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-postgresql.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

Repeat with a fresh database/schema, a new `PILOT_ROOT`, and `--repeat-index 2`.

### 12.3 Cleanup

Cleanup uses the exact output root created in the same shell session:

```bash
cd backend
uv run python tests/pilot/run_multilingual_report_pilot.py cleanup \
  --output-root "${PILOT_ROOT}/run-1"
```

The CLI rejects relative manifest/output paths and refuses unsafe cleanup roots.

## 13. CI boundary

```text
CI_SQLITE_JOB=backend-sqlite
CI_POSTGRESQL_JOB=backend-postgresql
WORKFLOW_FILE_CHANGE=NO
NEW_CI_JOB=NO
```

Focused pilot tests are discovered by normal backend test execution in both existing jobs. No `.github/workflows` change is authorized in Slice 1.

## 14. Runbook

```text
RUNBOOK_PATH=docs/tasks/TASK-011-pilot-demo-runbook.md
```

Slice 2 is a separate docs PR and requires separate authorization. The runbook must include exact commands, PostgreSQL variables, fresh-checkout setup, expected PASS results, backend/API path, frontend report-export path, visible outcomes, integrity headers, hash distinctions, failure interpretation, stale-output demonstration, cleanup/rerun, limitations, and synthetic-data confirmation.

## 15. High-throughput disposition

```text
HIGH_THROUGHPUT_DISPOSITION=PATH_A
```

`high_throughput_review` moves to a separately authorized follow-up Issue. This definition does not create that Issue and does not authorize implementation.

Before Issue #20 closure may be proposed:

1. Charles separately authorizes creation of the follow-up Issue;
2. the Issue exists and links Issue #20 plus the frozen TASK-011C deferral authority;
3. closure evidence records its number and states that high-throughput implementation is outside Issue #20 closure.

PATH_B is rejected for this definition.

## 16. Issue #20 closure criteria

Issue #20 may be proposed for closure only after repository-verifiable evidence proves:

1. baseline and `invalid_blocked` goldens remain unchanged and reproducible;
2. SQLite and PostgreSQL evaluation pass;
3. the four-render matrix passes twice per backend on fresh databases;
4. one report revision binds all four renders;
5. downloaded hashes match persisted metadata and response headers;
6. sections and numeric semantic invariants pass;
7. stale-output rejection, cleanup, and rerun pass;
8. the runbook is merged;
9. normal CI is green on exact implementation Heads;
10. a fresh checkout executes the documented SQLite and PostgreSQL pilot commands successfully;
11. no real/confidential data is committed;
12. the PATH_A follow-up Issue exists and is linked;
13. a closure comment binds PRs, merge commits, exact-head CI, commands, result hashes, and follow-up Issue;
14. Charles separately authorizes Issue #20 closure.

Task 12 remains blocked until Issue #20 is actually closed.

## 17. Delivery slices

### Slice 1 — multilingual report acceptance

Implementation is limited to §11 after separate authorization.

### Slice 2 — pilot/demo runbook

One docs file at §14 after separate authorization.

### Slice 3 — closure evidence

- create the PATH_A follow-up Issue only after separate authorization;
- run final fresh-checkout pilots;
- post closure evidence;
- request separate closure authorization.

Each code/docs PR follows Draft → review → exact-head CI → separate Ready authorization → separate Merge authorization.

## 18. Hard boundaries

```text
DOCS_ONLY_THIS_ROUND=YES
CHANGED_PATH_COUNT_THIS_ROUND=1
TASK011D_NOT_ASSIGNED
TASK011D_NOT_AUTHORIZED
IMPLEMENTATION_NOT_AUTHORIZED
PRODUCTION_BEHAVIOR_CHANGE_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
TASK011C_SCHEMA_CHANGE_NOT_AUTHORIZED
TASK011C_GOLDEN_CHANGE_NOT_AUTHORIZED
REPORT_TEMPLATE_CHANGE_NOT_AUTHORIZED
TRANSLATION_CATALOG_CHANGE_NOT_AUTHORIZED
FRONTEND_CHANGE_NOT_AUTHORIZED
GITHUB_WORKFLOW_CHANGE_NOT_AUTHORIZED
DEPENDENCY_CHANGE_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
ISSUE20_REMAINS_OPEN
ISSUE20_CLOSURE_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
HIGH_THROUGHPUT_IMPLEMENTATION_NOT_AUTHORIZED
FOLLOW_UP_ISSUE_CREATION_NOT_AUTHORIZED
PR21_UNTOUCHED
PR23_UNTOUCHED
BRANCH_DELETION_NOT_AUTHORIZED
```

## 19. Freeze-candidate completion marker

```text
FINAL_CLASSIFICATION=TASK_011_REMAINING_PILOT_READINESS_DEFINITION_FINAL_FREEZE_CANDIDATE
DOCUMENT_STATUS=FINAL_FREEZE_CANDIDATE_PENDING_CI_AND_CHARLES_AUTHORIZATION
CONTRACT_FROZEN=NO
IMPLEMENTATION_AUTHORIZED=NO
STOPPED_AWAITING_CHARLES_DEFINITION_FREEZE_AUTHORIZATION
```

---

## 20. Amendment 001 — Slice 1 P0 frozen-allowlist reconciliation

> **Scope of this section**: this is a *separately authorized, single-purpose amendment* to the TASK-011 remaining-pilot-readiness definition document. It does **not** retro-rewrite the original contract; it adds an explicit, dated, auditable extension that lists exactly which additional tracked paths and which narrow semantic operations are now authorized for the implementation observed in PR #67. All other sections of this document (§1–§19) remain in force, except where they are explicitly narrowed below.

### 20.1 Amendment identity

```text
AMENDMENT_ID=TASK-011_SLICE_1_P0_ALLOWLIST_AMENDMENT_001
AMENDMENT_TARGET=TASK-011_SLICE_1
SOURCE_CONTRACT_PR=66
SOURCE_CONTRACT_MERGE_COMMIT=e6922ce406e093ec06fbbf23ca89a0d65a5956f0
IMPLEMENTATION_PR=67
OBSERVED_IMPLEMENTATION_HEAD=f315f6a57cf5b1fbbca97856069bf10975ec0415
AMENDMENT_REASON=P0_FROZEN_ALLOWLIST_RECONCILIATION
AMENDMENT_PATH=B
AMENDMENT_DOCS_ONLY=YES
AMENDMENT_REQUIRES_FUTURE_PR_MERGE=YES
AMENDMENT_ACTIVATION=ON_MERGE_OF_THIS_AMENDMENT_PR
AMENDMENT_SCOPE_OF_EFFECT=PR_67_IMPLEMENTATION_ONLY
AMENDMENT_REMAINS_VALID_AFTER_PR_67_MERGE=YES
AMENDMENT_EXPIRES=NEVER_UNLESS_REVOKED
```

### 20.2 New additional allowed paths (additive only)

The following five (5) tracked paths are added to the §11 maximum allowlist, **additively**. No path already in §11 is removed, and no other unlisted tracked path is added.

```text
ADDITIONAL_ALLOWED_PATH_COUNT=5

ADDITIONAL_ALLOWED_PATHS=
  backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py
  backend/src/cold_storage/modules/reports/localization/en_us.py
  backend/src/cold_storage/modules/reports/localization/zh_cn.py
  backend/tests/test_reports/test_localization.py
  backend/tests/unit/test_real_report_data_provider.py

ALL_OTHER_UNLISTED_TRACKED_PATHS_REMAIN_UNAUTHORIZED=YES
```

The combined Slice 1 allowlist is the union of the §11 list and the five paths above. The §11 clause

> "No other tracked path is authorized by this definition."

remains in force for every tracked path **not** named in §11 or in this §20.2 list.

### 20.3 Authorized semantic operations (narrow, non-general)

This amendment authorizes **only** the following narrowly-scoped semantic operations, each of which corresponds directly to the implementation observed in PR #67 at `f315f6a57cf5b1fbbca97856069bf10975ec0415`:

```text
AUTHORIZED_OPERATION_PROJECTION=YES
  Description: project a persisted evaluation result_snapshot from the existing
  v0 shape into the existing report v1 schema shape, using a strict typed
  projection that preserves the field-path and unit contract from
  §7.7 ("Semantic verification") and §9 ("Result schema and managed layout").
  No new field is added; no existing field is removed or renamed.

AUTHORIZED_OPERATION_FAIL_CLOSED_NUMERIC_AND_CONFLICT=YES
  Description: for the projection inputs above, perform fail-closed numeric
  coercion and fail-closed field-conflict detection; raise a typed error
  (ReportProjectionError) when (a) a value cannot be coerced to the target
  numeric type, (b) the same canonical field is bound to multiple distinct
  raw values, or (c) a required v0 source field is missing for a v1 field.

AUTHORIZED_OPERATION_TRANSLATION_CATALOG_EXACT_KEYS=YES
  Description: extend the translation catalog with exactly the following two
  (2) keys, only, each in both en_us and zh_cn:
    condenser_heat_rejection
    kW(th)
  No other translation key, pluralization rule, locale, or fallback is added
  or changed.

AUTHORIZED_OPERATION_CORRESPONDING_TESTS=YES
  Description: add tests that directly cover the projection logic, the
  fail-closed numeric/conflict checks, and the two new translation keys.
  The test files listed in §20.2 (test_localization.py,
  test_real_report_data_provider.py) are the only authorized test
  locations for this work.
```

### 20.4 Explicit non-authorizations (boundaries reaffirmed)

The following remain **not** authorized by this amendment. They are stated explicitly to prevent scope drift:

```text
GENERAL_REPORT_PROVIDER_REDESIGN_AUTHORIZED=NO
UNRELATED_LOCALIZATION_CHANGE_AUTHORIZED=NO
ADDITIONAL_TRANSLATION_KEY_AUTHORIZED=NO
REPORT_SCHEMA_CHANGE_AUTHORIZED=NO
REPORT_TEMPLATE_CHANGE_AUTHORIZED=NO
GOLDEN_CHANGE_AUTHORIZED=NO
FRONTEND_CHANGE_AUTHORIZED=NO
WORKFLOW_CHANGE_AUTHORIZED=NO
```

### 20.5 Narrowing of the §18 "TRANSLATION_CATALOG_CHANGE_NOT_AUTHORIZED" clause

The §18 hard-boundary clause

```text
TRANSLATION_CATALOG_CHANGE_NOT_AUTHORIZED
```

is **narrowed** by this amendment to the following, and only the following:

```text
TRANSLATION_CATALOG_CHANGE_NARROW_AUTHORIZATION=
  Scope: backend/src/cold_storage/modules/reports/localization/en_us.py
         and
         backend/src/cold_storage/modules/reports/localization/zh_cn.py
  Permitted addition set: exactly the two keys
    condenser_heat_rejection
    kW(th)
  Method constraint: keys may be added, but existing keys, fallbacks,
    pluralization, locale list, and any non-key catalog structure must
    remain unchanged.
  Audit constraint: the PR body must list these two keys verbatim and
    must not assert TRANSLATION_CATALOG_CHANGE=NO.

TRANSLATION_CATALOG_CHANGE_OTHER_THAN_THE_TWO_KEYS_NOT_AUTHORIZED=YES
```

All other §18 hard boundaries remain in force exactly as written.

### 20.6 Other clauses that are **not** changed by this amendment

For audit clarity, the following are **not** modified by this amendment and continue to bind PR #67:

```text
DOCS_ONLY_THIS_ROUND=YES
CHANGED_PATH_COUNT_THIS_ROUND=1
TASK011D_NOT_ASSIGNED
TASK011D_NOT_AUTHORIZED
IMPLEMENTATION_NOT_AUTHORIZED
PRODUCTION_BEHAVIOR_CHANGE_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
TASK011C_SCHEMA_CHANGE_NOT_AUTHORIZED
TASK011C_GOLDEN_CHANGE_NOT_AUTHORIZED
REPORT_TEMPLATE_CHANGE_NOT_AUTHORIZED
FRONTEND_CHANGE_NOT_AUTHORIZED
GITHUB_WORKFLOW_CHANGE_NOT_AUTHORIZED
DEPENDENCY_CHANGE_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
ISSUE20_REMAINS_OPEN
ISSUE20_CLOSURE_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
HIGH_THROUGHPUT_IMPLEMENTATION_NOT_AUTHORIZED
FOLLOW_UP_ISSUE_CREATION_NOT_AUTHORIZED
PR21_UNTOUCHED
PR23_UNTOUCHED
BRANCH_DELETION_NOT_AUTHORIZED
```

### 20.7 P1 remediation is **not** authorized by this amendment

This amendment **does not** authorize any P1 finding remediation. Each P1 item below requires a separate round-specific authorization from Charles:

```text
P1_1_MANIFEST_GOLDEN_REMEDIATION_AUTHORIZED=NO
P1_2_EXIT_CODE_REMEDIATION_AUTHORIZED=NO
P1_3_SEMANTIC_CHECK_REMEDIATION_AUTHORIZED=NO
P1_4_E2E_TEST_REMEDIATION_AUTHORIZED=NO
PR67_BODY_SYNC_AUTHORIZED=NO
PR67_REBASE_OR_MAIN_MERGE_AUTHORIZED=NO
```

After this amendment is merged, P1-1 through P1-4 and PR #67 body synchronization still require Charles's next round of independent authorization. This amendment only resolves the single P0 frozen-allowlist blocker.

### 20.8 PR #67 status under this amendment

```text
PR67_STATE_AT_AMENDMENT_TIME=open
PR67_DRAFT_AT_AMENDMENT_TIME=true
PR67_HEAD_AT_AMENDMENT_TIME=f315f6a57cf5b1fbbca97856069bf10975ec0415
PR67_BODY_MUTATION_BY_THIS_AMENDMENT=NO
PR67_BRANCH_HISTORY_REWRITE_BY_THIS_AMENDMENT=NO
PR67_MERGE_STATE_AFTER_AMENDMENT_MERGE=REMAINS_DRAFT
PR67_READY_TRANSITION_BY_THIS_AMENDMENT=NO
PR67_MERGE_TRANSITION_BY_THIS_AMENDMENT=NO
PR67_REMAINS_DRAFT_UNTIL_NEXT_ROUND_AUTHORIZATION=YES
```

### 20.9 Amendment validity and revocation

```text
AMENDMENT_VALIDITY=PERMANENT_UNTIL_REVOKED
AMENDMENT_REVOCATION_MECHANISM=A_FUTURE_AMENDMENT_OR_CONTRACT_REVISION_PR
AMENDMENT_DOES_NOT_AUTO_REVOKE=YES
AMENDMENT_DOES_NOT_TRIGGER_PR67_MERGE=YES
AMENDMENT_REQUIRES_CHARLES_FINAL_REVIEW=YES
```

---

*End of Amendment 001.*
