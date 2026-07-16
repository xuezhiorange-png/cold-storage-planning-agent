# TASK-011 Remaining Pilot Readiness — Definition Proposal

> **Status:** `AUTHORED_PENDING_REVIEW`
>
> **Authority:** Issue #20 comment `4993536755`.
>
> **Round type:** docs-only definition. This document does not authorize implementation, fixtures, expected outputs, manifests, runner changes, CI changes, Ready, Merge, Issue #20 closure, Task 12, or any work named TASK-011D.

## 1. Repository identity

```text
ISSUE_NUMBER=20
AUTHORITY_COMMENT_ID=4993536755
SOURCE_MAIN_SHA=a16075fed9ef7cabafc41cf0398c54fd6088f578
BRANCH=codex/task-011-remaining-pilot-readiness-definition
DOCUMENT_PATH=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
```

This proposal follows the completed TASK-011 baseline and evaluation work already merged through PRs #60, #64, and #65. It does not reopen or modify the frozen TASK-011C V1 scenario set (`baseline_feasible` and `invalid_blocked`).

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

The remaining work is pilot readiness rather than a change to engineering formulas or to the frozen TASK-011C V1 contract.

## 3. Repository evidence used by this proposal

The current report subsystem already exposes the production capabilities required for a pilot definition:

- supported locales: `zh-CN`, `en-US`;
- supported formats: `docx`, `pdf`;
- supported render modes: `draft`, `formal`;
- report creation and revision generation through `/api/v1/reports`;
- rendering through `/api/v1/reports/{report_id}/revisions/{revision_number}/render`;
- export listing and detail retrieval through `/api/v1/reports/{report_id}/exports`;
- verified download through `/api/v1/reports/{report_id}/exports/{artifact_id}/download`;
- download integrity metadata including `X-Content-SHA256`, `X-Source-Content-Hash`, locale, template locale, translation-catalog identity, and localized-template hash;
- a frontend report export panel that allows report/revision selection, format, mode, locale, rendering, export listing, and download;
- a production E2E test pattern covering four independent renders (`zh-CN` / `en-US` × DOCX / PDF) from one canonical source snapshot;
- the existing evaluation runner already rejects stale managed outputs and writes its completion summary last.

No new report engine, localization engine, formula calculator, translation service, or frontend redesign is proposed.

## 4. Proposed remaining deliverables

The definition round proposes exactly three implementation deliverables after separate authorization:

1. **Multilingual report pilot acceptance**
2. **Repository-owned pilot/demo runbook**
3. **TASK-011 closure evidence record**

The following are excluded:

- `high_throughput_review` production integration;
- new formulas, coefficients, thresholds, scoring, or review rules;
- external OCR, model, translation, or document service rollout;
- production deployment hardening or Task 12;
- real customer, farm, factory, personal, confidential, or secret data;
- replacement of the existing report or evaluation architecture.

## 5. Proposed multilingual pilot check

### 5.1 Check identity

The proposed pilot check is not a new TASK-011C V1 evaluation scenario and must not be inserted into the frozen V1 manifest without a separate contract amendment.

```text
PILOT_CHECK_ID=multilingual_report_same_revision
PILOT_CHECK_CLASS=REPORT_VERIFICATION
SOURCE_SCENARIO=baseline_feasible
SOURCE_DATA=SYNTHETIC_REPOSITORY_OWNED
```

### 5.2 Source binding

One successful synthetic baseline execution must produce or identify one persisted project and project version. Report verification must then use:

```text
ONE_PROJECT_ID
ONE_PROJECT_VERSION_ID
ONE_REPORT_ID
ONE_REPORT_REVISION_NUMBER
ONE_REPORT_REVISION_CONTENT_HASH
```

All locale and format renders in the same pilot run must bind to that exact report revision. A second calculation or scheme run must not be performed merely to produce the other locale.

### 5.3 Mandatory render matrix

The minimum mandatory matrix is four draft renders:

| Locale | Format | Mode | Required |
|---|---|---|---|
| `zh-CN` | `docx` | `draft` | yes |
| `zh-CN` | `pdf` | `draft` | yes |
| `en-US` | `docx` | `draft` | yes |
| `en-US` | `pdf` | `draft` | yes |

A future implementation may add a formal-mode smoke check only if it uses the existing report review/approval lifecycle. Formal rendering must not bypass the production status rules.

### 5.4 Cross-render invariants

The following values must be identical for all four mandatory renders:

```text
project_id
project_version_id
report_id
revision_number
report_revision_content_hash
source_content_hash
report_type=cold_storage_concept_design
```

The following values must equal the request for each artifact:

```text
locale
template_locale
format
mode
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

### 5.5 Permitted differences

The following values are expected or permitted to differ and must not be compared for cross-locale or cross-format equality:

```text
artifact_id
file_name
file_size_bytes
file_sha256
generated_at
storage_key
mime_type
locale
template_locale
translation_catalog_version
translation_catalog_content_hash
localized_template_content_hash
rendered human-language text
container metadata internal to DOCX or PDF
```

Permitted difference does not mean “unchecked.” Each value must still pass its own type, integrity, request-binding, and download verification rule.

### 5.6 Semantic verification

The downloaded files must be checked without recomputing engineering formulas.

Required checks:

- both locale files identify the same project and source report revision;
- required engineering sections are present in both locales;
- declared numeric engineering values and units remain semantically equivalent across locales;
- `zh-CN` contains the approved Chinese section headings/labels;
- `en-US` contains the approved English section headings/labels;
- no client-side translation is used to manufacture the English result;
- no equality assertion is made on complete DOCX/PDF bytes across formats or locales;
- no broad text normalization may hide missing sections, missing units, or numeric drift.

The exact heading and field allowlist must be frozen in the implementation PR before Ready. It must be derived from the repository-owned report template manifests and translation catalogs, not handwritten independently in the frontend.

### 5.7 Repetition and backend coverage

The implementation proposal must include:

```text
SQLITE_REPORT_PILOT=REQUIRED
POSTGRESQL_REPORT_PILOT=REQUIRED
REPEATABILITY_RUNS_PER_BACKEND>=2
CROSS_BACKEND_BUSINESS_INVARIANTS=EXACT
```

Cross-backend exactness applies to source business values, report/revision relationship, requested locale/format, section presence, semantic numeric values, content/integrity metadata shape, and PASS/FAIL classification.

Generated database IDs, timestamps, artifact IDs, storage keys, and binary file hashes are not required to be identical between SQLite and PostgreSQL unless a later reviewed implementation demonstrates that the production contract guarantees such identity.

## 6. Proposed pilot result record

The implementation must emit one machine-readable pilot result and one concise human-readable summary. The exact filenames and schema remain proposed pending review.

Proposed managed files:

```text
pilot-run.json
artifacts/<locale>/<format>/artifact-metadata.json
pilot-summary.json
```

The result must bind:

```text
schema_version
pilot_check_id
source_commit_sha
source_manifest_sha
project_id
project_version_id
report_id
revision_number
report_revision_content_hash
database_backend
started_at
completed_at
render_matrix
artifact_integrity_results
semantic_results
overall_result
```

`pilot-summary.json` must be written last and is the only completion marker. A directory containing partial artifacts without a successful summary must be classified as incomplete, never PASS.

The implementation must either reuse the existing evaluation atomic-write and stale-output semantics or call the existing authority directly. It must not introduce a weaker duplicate cleanup policy.

## 7. Failure classification

The future implementation must fail closed with stable machine-readable classifications. At minimum:

```text
SOURCE_BINDING_MISMATCH
REPORT_REVISION_MISMATCH
UNSUPPORTED_LOCALE
UNSUPPORTED_FORMAT
RENDER_FAILED
ARTIFACT_NOT_COMPLETED
ARTIFACT_METADATA_MISMATCH
DOWNLOAD_NOT_FOUND
DOWNLOAD_INTEGRITY_MISMATCH
SOURCE_CONTENT_HASH_MISMATCH
LOCALE_BINDING_MISMATCH
TEMPLATE_LOCALE_MISMATCH
TRANSLATION_CATALOG_IDENTITY_MISSING
LOCALIZED_TEMPLATE_HASH_MISSING
REQUIRED_SECTION_MISSING
NUMERIC_SEMANTIC_MISMATCH
STALE_PILOT_ARTIFACTS
INFRASTRUCTURE_ERROR
```

Exception message parsing is forbidden as a classification mechanism. Existing typed domain errors, HTTP status, structured fields, and explicit result records must be used.

## 8. Cleanup, rerun, and stale-output rules

The runbook and implementation must define one owned output root outside tracked repository files by default.

Required behavior:

1. inspect the output root before any report or database side effect;
2. reject any managed stale file or partial prior run;
3. never overwrite a prior successful or failed run in place;
4. provide an explicit cleanup command that deletes only the named run root;
5. require a clean output root before rerun;
6. write files atomically;
7. write the completion summary last;
8. leave failed-run evidence available until explicit cleanup;
9. never commit generated reports, databases, temporary files, or pilot result directories.

## 9. Repository-owned pilot/demo runbook

Proposed implementation path:

```text
docs/tasks/TASK-011-pilot-demo-runbook.md
```

The runbook must include:

- prerequisites and supported local environment;
- SQLite execution command;
- PostgreSQL execution command and required environment variables;
- one-command execution where practical;
- expected PASS summary;
- expected visible report/export outcome;
- backend/API path: create/select report, select revision, render, list exports, retrieve metadata, verified download;
- frontend path: open project workspace, open report export panel, choose report and revision, choose format/mode/locale, render, verify completed export, download;
- exact integrity headers and fields to inspect;
- how to distinguish source revision hash from final binary hash;
- failure-class interpretation;
- cleanup and rerun procedure;
- stale-output rejection demonstration;
- known non-production limitations;
- confirmation that all data is synthetic and repository-owned.

Screenshots may be optional evidence but cannot replace machine-readable checks.

## 10. Proposed implementation ownership

The definition review must decide the exact implementation surface before code is authorized. The preferred architecture is:

- reuse the existing report API/application services and report domain contracts;
- reuse the current evaluation manifest identity and canonicalization authorities for source binding where applicable;
- add one narrow pilot report verification module rather than extending production report code;
- add focused tests for SQLite, PostgreSQL, download integrity, locale semantics, cleanup, and stale-output rejection;
- add CI wiring only after separate review confirms runtime and dependency impact.

No production report behavior may be altered to make the pilot pass.

## 11. High-throughput governance disposition

### 11.1 Proposed decision

```text
HIGH_THROUGHPUT_DISPOSITION_PROPOSAL=PATH_A
```

**PATH_A is recommended:** create a separately authorized follow-up Issue for the production-integration prerequisite and `high_throughput_review` scenario. This allows Issue #20 to close after all other TASK-011 pilot-readiness deliverables and closure evidence are complete.

Rationale:

- the TASK-011C frozen contract already removed `high_throughput_review` from V1;
- current-main evidence classified it as a production-integration architecture gap;
- implementing that gap is materially different from documenting and validating the existing pilot flow;
- retaining it indefinitely inside Issue #20 would couple pilot closure to a separately governed production capability.

This document does not create the follow-up Issue and does not authorize implementation. The disposition becomes binding only after Charles review.

### 11.2 Rejected alternative for this proposal

```text
PATH_B=retain high_throughput_review under Issue #20
```

PATH_B remains available to the reviewer but is not recommended because it would keep Issue #20 open until a separately scoped production-integration prerequisite is designed, authorized, implemented, and verified.

## 12. Proposed Issue #20 closure criteria

Issue #20 may be proposed for closure only after all conditions below are repository-verifiable:

1. baseline expected output remains unchanged and reproducible;
2. `invalid_blocked` expected output remains unchanged and reproducible;
3. SQLite evaluation passes;
4. PostgreSQL evaluation passes;
5. multilingual four-render matrix passes on both backends;
6. same project/version/report/revision source binding is proven across locales;
7. downloaded file hashes match persisted metadata and response headers;
8. required locale-specific sections and numeric semantic invariants pass;
9. stale-output rejection, cleanup, and rerun procedures pass;
10. repository-owned pilot/demo runbook is merged;
11. normal repository CI is green on exact implementation Head;
12. no real or confidential data is committed;
13. high-throughput disposition is formally recorded;
14. a final closure evidence comment binds all relevant PRs, merge commits, CI runs, commands, and result hashes;
15. Charles separately authorizes Issue #20 closure.

Task 12 remains blocked until Issue #20 is actually closed and its closure evidence is complete.

## 13. Proposed delivery slices

After this document is reviewed and frozen, implementation should remain split:

### Slice 1 — multilingual report acceptance

- pilot check implementation;
- SQLite and PostgreSQL verification;
- four-render matrix;
- download integrity and semantic checks;
- cleanup/stale-output behavior;
- no runbook beyond command notes required for test execution.

### Slice 2 — pilot/demo runbook

- repository-owned operator instructions;
- backend/API and frontend paths;
- expected visible outcomes;
- failure, cleanup, rerun, and limitations.

### Slice 3 — closure evidence

- no new production capability;
- collect merged identities and exact-head CI;
- run final fresh-checkout pilot;
- post Issue #20 closure evidence;
- request separate closure authorization.

Each slice requires a new Draft PR, independent review, exact-head CI, separate Ready authorization, and separate Merge authorization.

## 14. Review decisions required before freeze

The reviewer must explicitly decide:

```text
R1_PILOT_CHECK_ID
R2_FOUR_RENDER_DRAFT_MATRIX
R3_FORMAL_MODE_SMOKE_SCOPE
R4_CROSS_RENDER_INVARIANTS
R5_PERMITTED_DIFFERENCE_SET
R6_SEMANTIC_HEADING_AND_FIELD_ALLOWLIST_AUTHORITY
R7_SQLITE_POSTGRESQL_REPEATABILITY_COUNT
R8_PILOT_RESULT_SCHEMA_AND_FILENAMES
R9_ATOMIC_WRITE_AND_STALE_OUTPUT_AUTHORITY
R10_IMPLEMENTATION_MODULE_AND_COMMAND_SURFACE
R11_CI_BOUNDARY
R12_RUNBOOK_PATH_AND_REQUIRED_SECTIONS
R13_HIGH_THROUGHPUT_PATH_A_OR_PATH_B
R14_ISSUE20_CLOSURE_CRITERIA
```

Until all decisions are reviewed:

```text
DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
CONTRACT_FROZEN=NO
IMPLEMENTATION_AUTHORIZED=NO
```

## 15. Hard boundaries

```text
DOCS_ONLY=YES
CHANGED_PATH_COUNT=1
TASK011D_NOT_ASSIGNED
TASK011D_NOT_AUTHORIZED
IMPLEMENTATION_NOT_AUTHORIZED
PRODUCTION_CODE_NOT_AUTHORIZED
TEST_CODE_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
MANIFEST_CHANGE_NOT_AUTHORIZED
RUNNER_CHANGE_NOT_AUTHORIZED
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

## 16. Definition-round completion marker

```text
FINAL_CLASSIFICATION=TASK_011_REMAINING_PILOT_READINESS_DEFINITION_AUTHORED_PENDING_REVIEW
STOPPED_AWAITING_CHARLES_DEFINITION_REVIEW
```
