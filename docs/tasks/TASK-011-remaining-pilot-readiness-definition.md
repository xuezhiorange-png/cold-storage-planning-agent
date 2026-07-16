# TASK-011 Remaining Pilot Readiness — Definition Proposal

> **Status:** `REVIEW_CORRECTIONS_APPLIED_PENDING_RE_REVIEW`
>
> **Authority:** Issue #20 comment `4993536755`.
>
> **Round-1 review:** PR #66 review `4715270274`.
>
> **Round type:** docs-only definition. This document does not authorize implementation, fixtures, expected outputs, manifest changes, production behavior changes, CI workflow changes, Ready, Merge, Issue #20 closure, Task 12, or any work named TASK-011D.

## 1. Repository identity

```text
ISSUE_NUMBER=20
AUTHORITY_COMMENT_ID=4993536755
SOURCE_MAIN_SHA=a16075fed9ef7cabafc41cf0398c54fd6088f578
BRANCH=codex/task-011-remaining-pilot-readiness-definition
DOCUMENT_PATH=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
ROUND1_REVIEW_ID=4715270274
DOCUMENT_STATUS=REVIEW_CORRECTIONS_APPLIED_PENDING_RE_REVIEW
CONTRACT_FROZEN=NO
```

This proposal follows the TASK-011 work merged through PRs #60, #64, and #65. It does not reopen or modify the frozen TASK-011C V1 scenario set (`baseline_feasible` and `invalid_blocked`).

## 2. Current completed state

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

The remaining work is pilot readiness. It is not a formula, coefficient, threshold, scoring, or production-review-rule change.

## 3. Evidence base

The existing repository provides:

- locales `zh-CN` and `en-US`;
- formats `docx` and `pdf`;
- modes `draft` and `formal`;
- report/revision creation through the report application service and `/api/v1/reports` endpoints;
- rendering through `/api/v1/reports/{report_id}/revisions/{revision_number}/render`;
- export listing/detail and verified download endpoints;
- artifact metadata including source hash, template identity, locale, translation-catalog identity, localized-template hash, file hash, and file size;
- verified-download headers including `X-Content-SHA256`, `X-Source-Content-Hash`, locale, template locale, translation-catalog identity, and localized-template hash;
- a real report data provider and production report/render services;
- a frontend export panel with report/revision, format, mode, locale, render, list, and download actions;
- an existing production E2E pattern proving that four locale/format renders originate from one canonical report revision;
- an evaluation runner that rejects stale managed outputs and writes its completion summary last.

No new report engine, localization engine, translation service, formula calculator, or frontend redesign is proposed.

## 4. Remaining deliverables

After a separate implementation authorization, the remaining TASK-011 deliverables are:

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

## 5. Binding R1–R14 decisions integrated from review 4715270274

```text
R1_PILOT_CHECK_ID=multilingual_report_same_revision
R2_FOUR_RENDER_DRAFT_MATRIX=APPROVED
R3_FORMAL_MODE_SMOKE_SCOPE=DEFERRED_OUT_OF_CURRENT_SCOPE
R4_CROSS_RENDER_INVARIANTS=AXIS_SPECIFIC_WITH_EXPLICIT_EVIDENCE_SOURCES
R5_PERMITTED_DIFFERENCE_SET=AXIS_SPECIFIC
R6_SEMANTIC_ALLOWLIST_AUTHORITY=EXACT_PRODUCTION_SYMBOLS
R7_REPEATABILITY_RUNS_PER_BACKEND=2
R8_RESULT_SCHEMA_VERSION=task11-pilot-report.v1
R9_ARTIFACT_IO_AUTHORITY=SINGLE_PUBLIC_SHARED_MODULE
R10_IMPLEMENTATION_SURFACE=CORE_VERIFIER_PLUS_TEST_SIDE_PILOT_COMPOSITION
R11_CI_BOUNDARY=EXISTING_BACKEND_SQLITE_AND_POSTGRESQL_JOBS
R12_RUNBOOK_PATH=docs/tasks/TASK-011-pilot-demo-runbook.md
R13_HIGH_THROUGHPUT_DISPOSITION=PATH_A
R14_ISSUE20_CLOSURE=SEPARATE_AUTHORIZATION_AFTER_FRESH_CHECKOUT_EVIDENCE
```

These decisions are integrated into this correction commit but are not frozen until a subsequent Charles re-review explicitly freezes the document.

## 6. Multilingual pilot check contract

### 6.1 Identity and relationship to TASK-011C

```text
PILOT_CHECK_ID=multilingual_report_same_revision
PILOT_CHECK_CLASS=REPORT_VERIFICATION
SOURCE_SCENARIO=baseline_feasible
SOURCE_DATA=SYNTHETIC_REPOSITORY_OWNED
TASK011C_V1_MANIFEST_AMENDMENT=NO
```

This pilot check is not a new TASK-011C V1 scenario and must not be inserted into the frozen V1 manifest.

### 6.2 Source execution and binding

For each backend and repetition, the pilot composition must:

1. validate the existing V1 manifest through `cold_storage.evaluation.manifest::load_and_validate_manifest`;
2. inspect the pilot output root before any database, report, or filesystem side effect;
3. execute the existing `baseline_feasible` production-bound evaluation path using the existing backend runner and a fresh database;
4. require the baseline evaluation result to be PASS;
5. obtain the persisted project/version identities from the baseline normalized result and persisted state;
6. create one report and generate exactly one report revision through the production report application services;
7. render all four mandatory artifacts from that exact report revision without executing a second calculation or scheme run.

The bound source identity is:

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
schema_version
```

### 6.3 Mandatory render matrix

Slice 1 requires exactly four draft renders:

| Locale | Format | Mode |
|---|---|---|
| `zh-CN` | `docx` | `draft` |
| `zh-CN` | `pdf` | `draft` |
| `en-US` | `docx` | `draft` |
| `en-US` | `pdf` | `draft` |

Formal-mode verification is deferred from Slice 1. A future formal-mode check requires a separate scope amendment and must use the existing report review/approval lifecycle.

### 6.4 Evidence sources

The pilot verifier must bind claims to the following existing sources:

| Claim | Required evidence source |
|---|---|
| project/report relationship | persisted `Report` and production report service result |
| revision number/content hash | persisted `ReportRevision` and revision API/service result |
| artifact report/revision binding | persisted `ReportExportArtifact` |
| requested format/locale | artifact fields plus request parameters |
| render mode | `ReportExportArtifact.render_manifest_json["render_mode"]` |
| template provenance | persisted template ID/version/content hash/schema plus render manifest |
| translation catalog provenance | artifact catalog version/hash plus catalog authority |
| localized template provenance | artifact localized-template hash |
| file integrity | artifact metadata, downloaded bytes, and verified-download headers |
| semantic section/value checks | canonical render model, localization authorities, and extracted downloaded content |

The verifier must not infer `mode` from a top-level artifact API response because the current top-level artifact response does not expose that field.

### 6.5 Axis-specific invariants

#### A. Global invariants across all four renders

The following must be exact for all four artifacts:

```text
project_id
project_version_id
report_id
report_revision_id
revision_number
report_revision_content_hash
source_content_hash
report_type=cold_storage_concept_design
schema_version
render_mode=draft
canonical_section_key_set
canonical_numeric_field_path_set
canonical_numeric_value_and_unit_set
```

`source_content_hash` must equal `report_revision_content_hash`.

#### B. Same-locale invariants across DOCX and PDF

For the same locale, the following must be exact across both formats:

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

#### C. Same locale+format invariants across repetitions and backends

For the same locale/format pair, the following must be exact across both fresh runs and both database backends:

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

Database-generated template IDs need not be equal across backends; template version and content hash are the governed identity.

#### D. Cross-locale rule

Human-language strings may differ. The canonical section keys, canonical field paths, numeric values, and canonical unit codes must remain exact. No client-side translation may manufacture the English result.

### 6.6 Self-integrity-only fields

The following may differ across renders, repetitions, or backends, but every value must pass its own type, request-binding, and integrity rule:

```text
artifact_id
file_name
file_size_bytes
file_sha256
generated_at
storage_key
mime_type
downloaded binary bytes
container metadata internal to DOCX/PDF
```

Each artifact must satisfy:

```text
artifact_status=completed
file_size_bytes>0
file_sha256=LOWERCASE_SHA256_HEX
DOWNLOAD_BYTES_SHA256=file_sha256
DOWNLOAD_HEADER_X_CONTENT_SHA256=file_sha256
DOWNLOAD_HEADER_X_SOURCE_CONTENT_HASH=source_content_hash
translation_catalog_version=NON_EMPTY
translation_catalog_content_hash=LOWERCASE_SHA256_HEX
localized_template_content_hash=LOWERCASE_SHA256_HEX
```

Complete DOCX/PDF byte equality is never required across formats, locales, repetitions, or backends.

### 6.7 Semantic authority

The exact semantic authorities are:

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

TEMPLATE_PROVENANCE_AUTHORITY=
  persisted ReportTemplate.manifest_json
  persisted ReportTemplate.template_content_hash
  production ReportRenderService template selection
```

Required section headings are derived from canonical `section_key` values and catalog keys `section.<section_key>`. Numeric verification is derived from canonical field paths, raw canonical values, and canonical unit codes. The implementation must not maintain an independent handwritten frontend heading or numeric allowlist.

Downloaded-file checks must prove:

- all required canonical sections are represented in each locale;
- localized headings match the catalog values for that locale;
- declared numeric values and units are semantically equivalent across locales and formats;
- missing sections, units, or numeric drift cannot be hidden by broad normalization;
- engineering formulas are not recomputed by the verifier.

### 6.8 Repeatability and backend coverage

```text
SQLITE_REPORT_PILOT=REQUIRED
POSTGRESQL_REPORT_PILOT=REQUIRED
REPEATABILITY_RUNS_PER_BACKEND=2
FRESH_DATABASE_PER_RUN=YES
CLEAN_OUTPUT_ROOT_PER_RUN=YES
CROSS_BACKEND_BUSINESS_INVARIANTS=EXACT
```

Generated database IDs, timestamps, storage keys, and binary file hashes are not required to be identical between SQLite and PostgreSQL.

## 7. V1 pilot result schema and managed layout

### 7.1 Schema identity

```text
PILOT_RESULT_SCHEMA_VERSION=task11-pilot-report.v1
```

Unknown, missing, or non-string schema versions fail closed.

### 7.2 Managed output layout

Each fresh run owns one absolute output root outside tracked repository files:

```text
<output-root>/
  pilot-run.json
  artifacts/
    zh-CN/
      docx/
        report.docx
        artifact-metadata.json
        semantic-checks.json
      pdf/
        report.pdf
        artifact-metadata.json
        semantic-checks.json
    en-US/
      docx/
        report.docx
        artifact-metadata.json
        semantic-checks.json
      pdf/
        report.pdf
        artifact-metadata.json
        semantic-checks.json
  pilot-summary.json
```

`pilot-summary.json` is written last and is the only completion marker. A directory without a successful `pilot-summary.json` is incomplete and can never be classified PASS.

### 7.3 `pilot-run.json`

Required fields:

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
schema_version_of_report
started_at
```

### 7.4 `artifact-metadata.json`

Required fields:

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

### 7.5 `semantic-checks.json`

Required fields:

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

### 7.6 `pilot-summary.json`

Required fields:

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

`overall_result=PASS` only when every source-binding, artifact-integrity, and semantic check is PASS.

## 8. Failure classification

The implementation must fail closed using stable machine-readable codes. At minimum:

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

Exception-message parsing is forbidden. Classification must use typed exceptions, structured domain fields, HTTP status/headers where applicable, persisted records, and explicit result records.

## 9. Atomic write, stale-output, and cleanup authority

Slice 1 is authorized to propose one public shared module:

```text
MODULE=backend/src/cold_storage/evaluation/artifact_io.py
PUBLIC_SYMBOLS=
  assert_no_managed_artifacts
  atomic_write_json
  atomic_write_bytes
  remove_managed_output_root
```

Rules:

- the existing suite runner must be refactored to call the same public JSON-write/stale-artifact functions without semantic change;
- the pilot verifier must call the same public authority;
- private `_atomic_write_json` or `_assert_no_stale_artifacts` imports are forbidden;
- a second implementation is forbidden;
- regression tests must prove existing C-2 stale-output and summary-last behavior remains unchanged;
- output-root inspection occurs before database, report, or managed-file side effects;
- managed files are written through temp sibling + flush/fsync where supported + atomic replace;
- prior runs are never overwritten in place;
- cleanup removes only the exact validated run root and rejects repository root, backend root, home directory, filesystem root, symlink escapes, and non-owned paths;
- failed-run evidence remains until explicit cleanup;
- generated reports, databases, and pilot result roots are never committed.

## 10. Implementation module and command surface

### 10.1 Core verifier

```text
CORE_MODULE=backend/src/cold_storage/evaluation/pilot_reports.py
PUBLIC_FUNCTION=verify_multilingual_report_pilot
```

The core verifier receives existing production service/query/storage ports and typed source identities. It must not construct production ORM rows, seed databases, modify report behavior, or import test modules.

### 10.2 Repository-owned pilot composition

```text
COMPOSITION_MODULE=backend/tests/pilot/run_multilingual_report_pilot.py
ENTRY_FUNCTION=main
```

The test-side composition may reuse the already authorized repository-owned synthetic evaluation seed helpers and must compose:

- existing V1 manifest loader and backend runner;
- existing production project/calculation/scheme query services;
- `RealReportDataProvider`;
- production `ReportService` and `ReportRenderService`;
- real filesystem artifact storage under the named temporary pilot root;
- the core pilot verifier.

It must not use `_RichDataProvider`, mock artifact storage, fabricated report contents, a second report assembler, or hand-built expected report text.

### 10.3 Command contract

The entry point requires explicit paths; no current-working-directory defaults are permitted.

SQLite:

```bash
cd backend
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:////absolute/path/task011-pilot.sqlite3" \
  --manifest "/absolute/path/to/the/repository-owned-v1-manifest.json" \
  --manifest-root "/absolute/path/to/its/data-root" \
  --output-root "/absolute/path/task011-pilot-sqlite-run-1" \
  --repeat-index 1 \
  --commit-sha "<40-character-sha>"
```

PostgreSQL:

```bash
cd backend
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend postgresql \
  --database-url "$TASK011_PILOT_POSTGRESQL_URL" \
  --manifest "/absolute/path/to/the/repository-owned-v1-manifest.json" \
  --manifest-root "/absolute/path/to/its/data-root" \
  --output-root "/absolute/path/task011-pilot-postgresql-run-1" \
  --repeat-index 1 \
  --commit-sha "<40-character-sha>"
```

Cleanup:

```bash
cd backend
uv run python tests/pilot/run_multilingual_report_pilot.py cleanup \
  --output-root "/absolute/path/to/one/named/pilot-run-root"
```

The implementation PR and runbook must replace the manifest placeholders with the exact repository path discovered on the implementation Head. The CLI must reject relative paths.

## 11. CI boundary

Slice 1 uses existing CI jobs only:

```text
CI_SQLITE_JOB=backend-sqlite
CI_POSTGRESQL_JOB=backend-postgresql
WORKFLOW_FILE_CHANGE=NO
NEW_CI_JOB=NO
```

Focused pilot tests must be discovered by the normal backend test command in both jobs. No `.github/workflows` change is authorized for Slice 1. Runtime impact must be reported in the implementation PR.

## 12. Repository-owned pilot/demo runbook

```text
RUNBOOK_PATH=docs/tasks/TASK-011-pilot-demo-runbook.md
```

The runbook must include:

- prerequisites and supported local environment;
- exact SQLite and PostgreSQL commands;
- required PostgreSQL environment variables;
- fresh-checkout setup;
- expected PASS summary;
- backend/API path;
- frontend report-export path;
- expected visible report/export result;
- exact integrity fields and headers;
- distinction between report revision hash and binary file hash;
- failure-code interpretation;
- stale-output rejection demonstration;
- cleanup and rerun procedure;
- known non-production limitations;
- confirmation that all data is synthetic and repository-owned.

Screenshots may supplement but cannot replace machine-readable evidence.

## 13. High-throughput governance disposition

```text
HIGH_THROUGHPUT_DISPOSITION=PATH_A
```

PATH_A is accepted: `high_throughput_review` and its production-integration prerequisite move to a separately authorized follow-up Issue. This document does not create that Issue and does not authorize its implementation.

Before Issue #20 may be proposed for closure:

1. Charles must separately authorize creation of the follow-up Issue;
2. the follow-up Issue must exist, remain open unless separately completed, and link Issue #20 and the frozen TASK-011C deferral authority;
3. Issue #20 closure evidence must record the follow-up Issue number and explicitly state that high-throughput implementation is not part of the closure.

PATH_B is rejected for this proposal.

## 14. Issue #20 closure criteria

Issue #20 may be proposed for closure only after all conditions are repository-verifiable:

1. baseline expected output remains unchanged and reproducible;
2. `invalid_blocked` expected output remains unchanged and reproducible;
3. SQLite evaluation passes;
4. PostgreSQL evaluation passes;
5. the four-render multilingual matrix passes twice per backend on fresh databases;
6. same project/version/report/revision source binding is proven across all renders;
7. downloaded file hashes match persisted metadata and response headers;
8. locale-specific sections and numeric semantic invariants pass;
9. stale-output rejection, cleanup, and rerun procedures pass;
10. the pilot/demo runbook is merged;
11. normal repository CI is green on the exact implementation Head;
12. a fresh checkout executes the documented SQLite and PostgreSQL pilot commands successfully;
13. no real or confidential data is committed;
14. the PATH_A follow-up Issue exists and is linked;
15. a final closure evidence comment binds all relevant PRs, merge commits, exact-head CI runs, commands, result-file hashes, and the follow-up Issue;
16. Charles separately authorizes Issue #20 closure.

Task 12 remains blocked until Issue #20 is actually closed with complete closure evidence.

## 15. Delivery slices

### Slice 1 — multilingual report acceptance

- shared artifact-I/O authority extraction with C-2 regression protection;
- core pilot verifier;
- test-side SQLite/PostgreSQL pilot composition;
- two fresh runs per backend;
- four-render matrix;
- source binding, download integrity, semantic checks, stale-output, cleanup, and rerun tests.

### Slice 2 — pilot/demo runbook

- repository-owned operator instructions;
- backend/API and frontend paths;
- expected visible outcomes;
- failure, cleanup, rerun, and limitations.

### Slice 3 — closure evidence

- create the PATH_A follow-up Issue only after separate authorization;
- run the final fresh-checkout pilot on both backends;
- collect merged identities and exact-head CI;
- post Issue #20 closure evidence;
- request separate closure authorization.

Each slice requires a new Draft PR, independent review, exact-head CI, separate Ready authorization, and separate Merge authorization.

## 16. Hard boundaries

```text
DOCS_ONLY_THIS_ROUND=YES
CHANGED_PATH_COUNT_THIS_ROUND=1
TASK011D_NOT_ASSIGNED
TASK011D_NOT_AUTHORIZED
IMPLEMENTATION_NOT_AUTHORIZED
PRODUCTION_BEHAVIOR_CHANGE_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
TASK011C_MANIFEST_CHANGE_NOT_AUTHORIZED
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

## 17. Correction-round completion marker

```text
FINAL_CLASSIFICATION=TASK_011_REMAINING_PILOT_READINESS_DEFINITION_REVIEW_CORRECTIONS_APPLIED
DOCUMENT_STATUS=REVIEW_CORRECTIONS_APPLIED_PENDING_RE_REVIEW
CONTRACT_FROZEN=NO
IMPLEMENTATION_AUTHORIZED=NO
STOPPED_AWAITING_CHARLES_DEFINITION_RE_REVIEW
```
