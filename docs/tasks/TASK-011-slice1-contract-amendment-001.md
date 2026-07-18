# TASK-011 Slice 1 Contract Amendment 001

> **Status:** `AUTHORED_PENDING_REVIEW`
>
> **Authority sequence:**
>
> ```text
> DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
> CONTRACT_AMENDMENT_FROZEN=NO
> SOURCE_CONTRACT_PR=66
> SOURCE_CONTRACT_MERGE_SHA=e6922ce406e093ec06fbbf23ca89a0d65a5956f0
> SOURCE_CONTRACT_DOCUMENT=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
> BLOCKED_IMPLEMENTATION_PR=67
> BINDING_REVIEW_ID=4727663461
> STATUS_CONFIRMATION_COMMENT_ID=5009963180
> AMENDMENT_ROUND_TYPE=DOCS_ONLY_CONTRACT_AMENDMENT_NO_IMPLEMENTATION
> AUTHORIZATION=AUTHORIZE_TASK011_SLICE1_AMENDMENT_COLLISION_RESOLUTION_AND_DOC_CORRECTION
> ```
>
> **Round type:** one-file docs-only contract amendment. This document is
> an amendment of the frozen contract merged through PR #66; it does NOT
> freeze implementation, does NOT authorize Readiness, Merge, Issue #20
> closure, Task 12, or any PR #67 mutation. PR #67 remains untouched.
> After this round, Charles freeze-authorization in a SEPARATE round is
> the sole path to converting this draft amendment into a binding
> contract delta.

## 1. Repository identity

```text
ISSUE_NUMBER=20
AUTHORITY_PARENT_AMENDMENT=Issue #20 comment 4993536755 + Issue #20 comment 4998309475
SOURCE_CONTRACT_AUTHORITY=PR #66 review 4715270274
SOURCE_CONTRACT_MERGE=e6922ce406e093ec06fbbf23ca89a0d65a5956f0
BINDING_REVIEW=4727663461
STATUS_CONFIRMATION=5009963180
REPOSITORY=xuezhiorange-png/cold-storage-planning-agent
```

This amendment is authored on top of the same `main` that PR #66 merged
into. It does not fold into PR #66, PR #21, PR #23, PR #60, PR #64, or
PR #65. No PR comment is added from this round — the GitHub audit trail
is the future Draft PR's body and the PR #67 conversation comment
`5009963180` (a comment on the PR #67 issue thread, NOT on Issue #20).

## 2. Purpose and binding scope

The amendment explicitly governs **Slice 1 only** (multilingual report
pilot acceptance). It does NOT reopen or modify:

- TASK-011C V1 frozen scenario semantics, schema, goldens, formulas,
  coefficients, thresholds, scoring, review rules, or canonicalization;
- the deferral of `high_throughput_review` to a separately authorized
  PATH_A follow-up Issue;
- the freeze on formal-mode pilot acceptance;
- any external OCR, model, translation, or document service introduction;
- any production deployment hardening, or Task 12.

The amendment binds ONLY the Slice 1 scope already defined by the
source contract; it extends the path-precise allowlist and codifies four
corrective obligations that the binding engineering review
`4727663461` accepted as needed-for-acceptance.

## 3. Terminology

- **Source contract** — `docs/tasks/TASK-011-remaining-pilot-readiness-definition.md`
  frozen by PR #66, merged at `e6922ce406e093ec06fbbf23ca89a0d65a5956f0`.
- **Blocked implementation PR** — PR #67
  (`codex/task-011-multilingual-report-pilot`), which has accumulated
  semantics required by the binding engineering review but is not
  authorized to Ready or Merge under any current amendment of this round.
- **Binding engineering review** — PR #67 review id `4727663461`,
  status `CHANGES_REQUESTED`, with status confirmation in PR #67
  conversation comment `5009963180` (a comment on the PR #67 issue
  thread, NOT on Issue #20).
- **Five-path scope expansion** — the five tracked paths enumerated in
  §4 of this amendment. They are technically present on PR #67 as of
  this amendment's authoring moment but remain **retroactively
  unauthorized** unless this amendment itself is reviewed, freeze-
  authorized, Ready, merged, and post-merge main identity verified.
- **Five corrective obligations** — the four contract clauses
  enumerated in §5 plus the existing `evaluate.py` obligation carried
  over from §6.

## 3a. Public surface resolution for the production runner

```text
ADAPTER_PUBLIC_SURFACE=
  cold_storage.evaluation.adapter::execute_scenario
EVALUATION_RUNNER_PUBLIC_SURFACE=
  cold_storage.evaluation.execute::run_scenario
PILOT_COMPOSITION_REQUIRED_SURFACE=
  cold_storage.evaluation.execute::run_scenario
RUN_SCENARIO_VIA_MARKERS_CLASSIFICATION=
  INTERNAL_RUN_DIRECTORY_COMPATIBILITY_WRAPPER
PILOT_IMPORT_RUN_SCENARIO_VIA_MARKERS=FORBIDDEN
PILOT_DIRECT_ADAPTER_IMPORT=FORBIDDEN
```

Future PR #67 corrective implementation MUST, where applicable:

- import the pilot composition from the frozen runner entry point
  `cold_storage.evaluation.execute::run_scenario`, NOT from
  `run_scenario_via_markers`, and NOT directly from
  `cold_storage.evaluation.adapter::execute_scenario`;
- pass the canonical kwargs `correlation_id=` and `database_backend=`
  to that entry point;
- NOT modify `backend/src/cold_storage/evaluation/execute.py` as part
  of the PR #67 corrective round, even if the existing entry point's
  signature lags the call site;
- NOT widen the §11 allowlist beyond the five proposed paths in §4
  of this amendment, even if the runner surface resolution appears
  to require it;
- NOT rely on the wrapper being listed in `__all__` of its module as
  evidence that it is part of the public authority.

```text
PREEXISTING_EXECUTE_MODULE_SURFACE_INCONSISTENCY=
  run_scenario_via_markers is described as internal but exported in __all__
PREEXISTING_SURFACE_INCONSISTENCY_RESOLUTION=
  OUTSIDE_THIS_AMENDMENT_AND_OUTSIDE_PR67
PR67_REQUIRED_ACTION=
  STOP_IMPORTING_THE_INTERNAL_WRAPPER_ONLY
```

The pre-existing inconsistency in the `execute` module's `__all__`
list (the literal entry `run_scenario_via_markers` coexists with the
intent that this name is an internal wrapper) is recorded here as a
separate observation and is OUT OF SCOPE for this amendment AND OUT
OF SCOPE for the PR #67 corrective round. PR #67 may not touch
`execute.py` even to "fix" this inconsistency. Future correction
rounds must address `__all__` separately under their own scope.

## 4. Proposed path expansion pending freeze authorization (extends §11 of source contract)

The source contract §11 "Exact Slice 1 implementation allowlist"
remains authoritative. After independent review, explicit Charles
freeze authorization, Ready, Merge, and post-merge main identity
verification, this amendment would authorize the following five
**additional** tracked paths, with the proposed purpose and proposed
forbidden scope below. Until Charles freeze authorization of this
amendment is granted in a separate round, NONE of the proposed
authorizations below is binding, and PR #67 remains frozen at
`CHANGES_REQUESTED` per the binding review `4727663461`. The current
text is recorded as the proposed-post-freeze contract delta only.

```text
FIVE_PATH_SCOPE_AMENDMENT_AUTHORED=YES
FIVE_PATH_SCOPE_AMENDMENT_FROZEN=NO
CURRENT_PR67_CONTENT_TECHNICALLY_PRESENT=YES
CURRENT_PR67_CONTENT_RETROACTIVELY_AUTHORIZED=NO
```

### 4.1 `backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py`

**Authorized ONLY for**:

- Strict persisted-result v0 → report-schema v1 projection that maps
  the persisted `result_snapshot` shape onto the v1
  `cold_storage_concept_design@1.0.0` measured-value fields.
- Required source field fail-closed semantics (a required v1 field with
  no v0 source raises a typed `ReportProjectionError` carrying
  section_key / result_id / field_path / reason_code).
- Primary-vs-alias conflict fail-closed semantics (when both a v0
  primary name and one of its declared aliases are populated, the
  projection must raise, never silently pick).
- Unsupported source type fail-closed semantics (bool, NaN / +Inf / -Inf,
  empty string, non-numeric string, non-dict structure all raise with
  typed reason codes; int, finite Decimal, finite float, finite decimal
  string coerce to JSON `number`).
- Preservation of raw canonical numeric values, canonical unit codes,
  result identity, and lineage metadata as persisted on the
  `CalculationRunRecord` row.

**Forbidden scope (no exceptions)**:

```text
NO_RECALCULATION
NO_FABRICATED_VALUES
NO_GOLDEN_BACKFILL
NO_LATEST_ROW_FALLBACK
NO_IMPLICIT_COERCION_OUTSIDE_THE_FOUR_REASON_CODES_ABOVE
NO_ENGINEERING_FORMULA_CHANGE
NO_REPORT_SCHEMA_REDESIGN
NO_UNRELATED_DATA_PROVIDER_EXPANSION
```

### 4.2 `backend/src/cold_storage/modules/reports/localization/en_us.py`

**Authorized ONLY for the addition of the multilingual pilot's exact
catalog keys** that the schema-required condenser heat-rejection
measured-value and its unit require. Specifically:

- `field.condenser_heat_rejection` → en-US label "Condenser Heat
  Rejection" (verbatim, no paraphrase).
- `unit.kw_th` → en-US unit label "kW(th)" (verbatim, raw string
  retained).

**Forbidden scope**:

```text
NO_UNRELATED_TRANSLATION_REWRITE
NO_TEMPLATE_CHANGE
NO_LOCALE_FALLBACK_REDESIGN
NO_NEW_LANGUAGE_ADDITION
NO_REPORT_WORDING_CLEANUP_OUTSIDE_EXACT_REQUIRED_KEYS
NO_EXISTING_KEY_MODIFICATION
NO_MESSAGES_DICT_ORDERING_CHANGE_FOR_NON_NEW_KEYS
NO_CATALOG_VERSION_BUMP
```

The existing en-US keys MUST remain byte-identical except for the
two inserted keys above; the `MESSAGES` dict insertion order MUST keep
the new keys in their alphabetical / category-preserving positions
relative to the existing layout so that the catalog content hash is
deterministic and the catalog identity change is exclusively the
addition.

### 4.3 `backend/src/cold_storage/modules/reports/localization/zh_cn.py`

**Authorized ONLY for the addition of the multilingual pilot's exact
catalog keys** that the schema-required condenser heat-rejection
measured-value and its unit require. Specifically:

- `field.condenser_heat_rejection` → zh-CN label "冷凝器排热量"
  (verbatim, no paraphrase).
- `unit.kw_th` → zh-CN unit label "kW(th)" (verbatim, raw string
  retained).

**Forbidden scope** is identical to §4.2.

### 4.4 `backend/tests/test_reports/test_localization.py`

**Authorized ONLY for the seven-case
`TestCondenserHeatRejectionLocalization` test class** (or any
mechanically equivalent set of seven cases) that proves:

1. The zh-CN label of `field.condenser_heat_rejection` equals
   "冷凝器排热量" exactly.
2. The en-US label of `field.condenser_heat_rejection` equals
   "Condenser Heat Rejection" exactly.
3. The zh-CN label of `unit.kw_th` equals "kW(th)" exactly.
4. The en-US label of `unit.kw_th` equals "kW(th)" exactly.
5. A canonical metric carrying the condenser heat-rejection
   measured-value localizes end-to-end in both locales.
6. The localized metric preserves raw value, `display_unit == "kW(th)"`,
   and the correct locale-specific label.
7. Unknown keys still raise `MissingTranslationError` (no fallback
   added).

**Forbidden scope**:

```text
NO_STUB_ONLY_TEST_DESCRIBED_AS_REAL_DATABASE_E2E_EVIDENCE
NO_NEW_TEST_FILE_AUTHORED
NO_EXISTING_TEST_REMOVAL_OR_WEAKENING
NO_KEY_OUTSIDE_FIELD_CONDENSER_HEAT_REJECTION_OR_UNIT_KW_TH
NO_FALLBACK_INTRODUCTION
NO_CATALOG_MUTATION_INSIDE_TEST_FIXTURE
```

### 4.5 `backend/tests/unit/test_real_report_data_provider.py`

**Authorized ONLY for focused unit tests that exercise the
`RealReportDataProvider` strict projection logic in isolation,
without opening a database, without touching a real session, and
without depending on the A1 seed fixtures**. The minimum cases are:

1. throughput v0 → v1 zone rename and extras drop.
2. cooling-load measured-value shape.
3. equipment measured-values (kW(r) + kW(th)).
4. electrical measured-value (kW(e)).
5. Decimal / string precise coercion (parametrised).
6. Provenance sourced from the persisted row (not synthesised).
7. Non-numeric / empty strings fail closed with typed reason codes.
8. Bool fails with `BOOL_NOT_NUMERIC`.
9. NaN / +Inf / -Inf fail with `NON_FINITE_NUMBER` (parametrised over
   float and Decimal).
10. Required v1 source field missing raises
    `REQUIRED_SOURCE_FIELD_MISSING`.
11. Conflicting v0 aliases raise `ALIAS_CONFLICT`.
12. Unconsumed v0 extras are dropped silently (per source contract
    §6 fail-closed contract; not an error on benign extras).
13. Calculator is not re-executed (no second call to
    `calculation_service.get_orchestrated_result`).
14. No database writes (structural assertion on the read path).
15. Source snapshot is not mutated (post-call dict equality).

**Forbidden scope**:

```text
NO_NEW_TEST_FILE_AUTHORED
NO_STUB_DESCRIBED_AS_REAL_DB_E2E_EVIDENCE
NO_TEST_FIXTURE_AUTHORING_/_SEED_HELPERS_MUTATION
NO_PRODUCTION_SOURCE_HELPER_DUPLICATION_BEYOND_THE_FROKEN_PROJECTION_LOGIC
NO_ENGINEERING_FORMULA_TEST_ADDITION
NO_SCHEMA_CHANGE_TEST
```

## 5. Proposed corrective obligation clauses (binding only after Charles freeze)

The five-path expansion is NECESSARY but NOT SUFFICIENT for Slice 1
acceptance. Four corrective obligations are proposed by this
amendment for future freeze authorization. Each obligation would
become binding only after this amendment is itself reviewed, freeze-
authorized, Ready, merged, and the post-merge main identity is
verified; none is enforceable in this authoring round.

### 5.1 Exact manifest and golden acceptance binding

After the post-freeze state takes effect, future Slice 1 implementation MUST validate, at runtime, the frozen
manifest identity and execute the frozen exact-equality comparison
against the existing evaluation authority. Specifically:

- exact backend-specific `suite_id`
- exactly one scenario
- `scenario_id == "baseline_feasible"`
- `expected_outcome == "SUCCEEDED"`
- exact `expected_output.path`
- exact `expected_output.commit_sha`
- `excluded_paths == []`
- `fixtures` omitted
- `comparison_policy` omitted
- `high_throughput_review` absent
- `invalid_blocked` absent

The pilot MUST thread the captured normalized output through the
existing evaluation comparison authority against
`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`
and require a PASS.

The following are explicitly NOT sufficient as acceptance:

```text
PRODUCTION_EXECUTION_RETURNED_SUCCEEDED          # NOT SUFFICIENT
REPORT_RENDERED_SUCCESSFULLY                    # NOT SUFFICIENT
MANIFEST_SCHEMA_VALID                           # NOT SUFFICIENT
OUTPUT_FILE_EXISTS                              # NOT SUFFICIENT
```

Frozen guard-rails:

```text
BASELINE_GOLDEN_CONTENT_CHANGE=NO
BASELINE_GOLDEN_REGENERATION=NO
SECOND_COMPARATOR=NO
SECOND_CANONICALIZER=NO
```

### 5.2 Stable verifier exit classification

The future CLI composition MUST use a deterministic, stable exit-code
mapping. Frozen values:

```text
EXIT_SUCCESS=0
EXIT_USAGE_OR_MANIFEST_ERROR=<existing frozen value>
EXIT_INFRASTRUCTURE_ERROR=<existing frozen value>
EXIT_VERIFIER_ERROR=4
```

Future implementation MUST:

- catch `PilotVerificationError` at the CLI composition boundary;
- emit structured, single-line, machine-readable stderr output;
- return `EXIT_VERIFIER_ERROR`;
- avoid Python traceback as the only public classification signal;
- preserve unexpected programming defects as non-success without
  collapsing them into a typed verifier code.

Message-text parsing, substring-based classification, generic
`except Exception -> PASS` fallbacks, and "unknown failure → success"
shortcuts are forbidden.

### 5.3 Field-bound numeric semantic verification

The current verifier's global-substring existence check
(`if metric.display_value not in extracted_text`) is forbidden as the
sole numeric semantic PASS authority.

Future verifier MUST bind every canonical numeric requirement to an
auditable observation in the downloaded artifact. The minimum
per-requirement evidence row MUST include:

- canonical section key
- canonical field path
- expected raw canonical value
- expected canonical unit
- observed localized section / table context
- observed displayed value
- observed displayed unit
- locale
- format
- match result

Frozen invariants:

```text
OBSERVED_NUMERIC_FIELDS_MUST_BE_FROM_PARSED_DOWNLOADED_ARTIFACT
LOCALIZED_EXPECTED_MODEL_IS_EXPECTATION_AUTHORITY_NOT_OBSERVATION_AUTHORITY
VALUE_FOUND_IN_UNRELATED_SECTION_DOES_NOT_SATISFY_FIELD
UNIT_FOUND_ELSEWHERE_DOES_NOT_SATISFY_FIELD
DUPLICATE_AMBIGUOUS_MATCHES_FAIL_CLOSED
MISSING_VALUE_OR_UNIT_FAILS_CLOSED
NUMERIC_DRIFT_FAILS_CLOSED
```

Implementation MAY use format-specific parsers (DOCX: paragraph /
table cell + spanning header alignment; PDF: page-region text +
section anchors), but MUST NOT introduce OCR, external AI / model
service, formula recomputation, or hand-built report-body authority.

### 5.4 True end-to-end and repeatability acceptance

Future implementation tests MUST cover the real production-bound
pilot for all four executions:

```text
SQLITE_REPEAT_1=REQUIRED
SQLITE_REPEAT_2=REQUIRED
POSTGRESQL_REPEAT_1=REQUIRED
POSTGRESQL_REPEAT_2=REQUIRED
```

Each run MUST independently prove:

- one production evaluation execution through the **frozen** public
  runner entry point `cold_storage.evaluation.execute::run_scenario`
  (imported as `from cold_storage.evaluation.execute import run_scenario`)
  with canonical kwargs `correlation_id=` and `database_backend=`;
  use of the internal compatibility wrapper or direct import of the
  adapter-layer entry point is forbidden by this amendment (see §3a
  Public surface resolution);
- one `Report` created;
- one `ReportRevision` generated and bound to the report;
- four renders produced (zh-CN/docx, zh-CN/pdf, en-US/docx, en-US/pdf,
  mode=draft);
- four persisted completed artifacts;
- four verified downloads with hash + header binding matches;
- four artifact metadata records;
- four semantic-check records;
- `pilot-summary.json` written last as the sole completion marker;
- `overall_result == "PASS"`.

Future implementation MUST execute a cross-repetition and
cross-backend invariant comparison. The frozen invariant set MUST
include at minimum:

```text
REPORT_TYPE
REPORT_SCHEMA_VERSION
CANONICAL_SECTION_KEY_SET
CANONICAL_NUMERIC_FIELD_PATH_VALUE_AND_UNIT_SET
TEMPLATE_VERSION
TEMPLATE_CONTENT_IDENTITY
TRANSLATION_CATALOG_VERSION
TRANSLATION_CATALOG_CONTENT_IDENTITY
LOCALIZED_TEMPLATE_IDENTITY
PASS_FAIL_CLASSIFICATION
```

The following are explicitly NOT required to be identical across
backends or repetitions:

```text
DATABASE_IDS
TIMESTAMPS
STORAGE_KEYS
ARTIFACT_IDS
BINARY_HASHES
DOCX_OR_PDF_BYTES
```

Negative paths that MUST be covered by future tests:

```text
GOLDEN_COMPARISON_FAILURE
MANIFEST_IDENTITY_MISMATCH
VERIFIER_TYPED_FAILURE_EXIT_4
REQUIRED_SECTION_MISSING
VALUE_IN_WRONG_SECTION
UNIT_IN_WRONG_FIELD
NUMERIC_DRIFT
DOWNLOAD_HASH_MISMATCH
STALE_OUTPUT_REJECTION
UNSAFE_CLEANUP_REJECTION
```

## 6. Source-contract obligations retained

This amendment does NOT modify the following source-contract clauses,
which remain in force regardless of this amendment's freeze status:

- `evaluate.py` MUST use the shared public artifact-I/O authority
  (`cold_storage.evaluation.artifact_io`). The execution agent has
  recorded that `evaluate.py` currently does not satisfy this
  requirement (private `_atomic_write_json` and
  `_assert_no_stale_artifacts` still present); that obligation is
  preserved as a future PR #67 corrective duty and is binding under
  the source contract.
- Private duplicated artifact writers remain forbidden.
- `pilot-summary.json` remains the sole completion marker.
- `pilot-summary.json` is written last.
- One report revision binds all four renders.
- Formal render mode remains deferred to a separately authored scope
  amendment.
- `high_throughput_review` remains outside Slice 1 and remains the
  PATH_A follow-up Issue (not yet created).
- TASK-011C schema and goldens remain frozen.
- Issue #20 remains open.
- Task 12 remains blocked until Issue #20 is actually closed.

## 7. PR #67 governance state under this amendment

The amendment explicitly distinguishes the technical presence of the
five paths on PR #67 from their retroactive authorization:

```text
CURRENT_PR67_CONTENT_TECHNICALLY_PRESENT=YES
CURRENT_PR67_CONTENT_RETROACTIVELY_AUTHORIZED=NO
```

The five paths become retroactively authorized only after the
following sequence has been completed in separate, individually
authorized rounds:

1. This amendment is reviewed in an independent contract review.
2. Charles issues an explicit freeze authorization for this amendment.
3. A separate Ready authorization round transitions the amendment's
   Draft PR to Ready.
4. A separate Merge authorization round merges the amendment.
5. A post-merge main identity verification round confirms the merged
   amendment is at the expected post-merge SHA.
6. Only after step 5 may a SEPARATE PR #67 corrective authorization
   round authorize retention or amendment of the five paths as part of
   PR #67 itself.

Until step 5 is complete, this amendment's authoring, the Draft PR
creation, and any CI pass on the Draft PR MUST NOT be cited or framed as
authorization that lifts the path blocker for the PR #67 P0 finding.
The current binding review `4727663461` verdict `CHANGES_REQUESTED`
for PR #67 head `f315f6a5` remains the controlling PR #67 status until
PR #67's own remediation is reviewed and approved in separate,
individually authorized rounds.

## 8. State surface at end of this round

```text
DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
CONTRACT_AMENDMENT_FROZEN=NO
FIVE_PATH_SCOPE_AMENDMENT_AUTHORED=YES
FIVE_PATH_SCOPE_AMENDMENT_FROZEN=NO
MANIFEST_GOLDEN_BINDING_CONTRACT_AUTHORED=YES
EXIT_CODE_4_CONTRACT_AUTHORED=YES
FIELD_BOUND_SEMANTIC_CONTRACT_AUTHORED=YES
FOUR_RUN_E2E_CONTRACT_AUTHORED=YES
PR67_CORRECTION_AUTHORIZED=NO
PR67_READY_AUTHORIZED=NO
PR67_MERGE_AUTHORIZED=NO
ISSUE20_CLOSURE_AUTHORIZED=NO
TASK12_AUTHORIZED=NO
```

Charles freeze authorization in a separate round is required before
any of the `AUTHORED_*` items above may transition to `FROZEN` or
`BINDING`. The round terminates at this document authored; the Draft
PR is open and CI may run, but no Readiness, Merge, Issue #20
closure, Task 12 start, or PR #67 mutation is authorized by this
round.

## 9. Charles freeze-authorization language gates

Until Charles's freeze-authorization round, this document MUST NOT
be cited or relied upon using any pre-freeze-claim that conveys
binding effect. Specifically the following composite claims are
prohibited before Charles freeze authorization is issued and they
remain exclusively reserved for the post-freeze rounds:

```text
PROHIBITED_PRE_FREEZE_CLAIMS=
  CONTRACT_AMENDMENT_FROZEN=YES
  AUTHORIZED_FOR_IMPLEMENTATION=YES
  P0_CLOSED=YES
  PR67_CORRECTION_AUTHORIZED=YES
```

The four composite claims above are the pre-freeze-prohibited
claims for this amendment. The set is intentionally narrow: it does
NOT prohibit the bare token strings `FROZEN` or `APPROVED` from
appearing inside carefully scoped citations of other documents,
inside status-survey text describing the current PR #67 review
state, or inside quoted material from the binding review
`4727663461`. What IS prohibited is the assertion that those tokens
apply to THIS amendment prior to Charles's freeze-authorization
round.

It remains reserved exclusively for Charles's freeze-authorization
round and any subsequent PR #67 corrective-authorization round to
issue any of the four composite claims above. Their appearance as
claims about THIS amendment today would be fabricated and is
therefore forbidden.

## 10. Final classification

```text
FINAL_CLASSIFICATION=TASK011_SLICE1_CONTRACT_AMENDMENT_001_CORRECTED_PENDING_INDEPENDENT_REVIEW

PR67_CORRECTION_AUTHORIZED=NO
PR67_READY_AUTHORIZED=NO
PR67_MERGE_AUTHORIZED=NO
ISSUE20_CLOSURE_AUTHORIZED=NO
TASK12_AUTHORIZED=NO
```

This document is corrected (single-file docs-only patch on top
of the prior authored commit), and is pending independent contract
review. It contains zero implementation authority, zero PR #67
mutation authority, and zero GitHub workflow change authority as a
result of this round's correction. The contract corrections this
document records (surface resolution, status language, comment
location, catalog key preservation, four-P1 retention) are recorded
in proposed-for-freeze form: they would become binding only after
Charles's explicit freeze authorization in a separate round
followed by Ready, Merge, and post-merge main-identity verification.
Absent that freeze-authorization round, this document remains in
`CORRECTED_PENDING_REVIEW` indefinitely and PR #67 remains in its
current `CHANGES_REQUESTED` Draft state.
