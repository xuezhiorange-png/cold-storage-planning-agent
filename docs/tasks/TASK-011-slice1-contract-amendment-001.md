# TASK-011 Slice 1 Contract Amendment 001

> **Status:** `AUTHORED_PENDING_REVIEW` (corrective-2 applied 2026-07-19)
>
> **Authority sequence:**
>
> ```text
> DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
> CONTRACT_AMENDMENT_FROZEN=NO
> SOURCE_CONTRACT_PR=66
> SOURCE_CONTRACT_MERGE_SHA=e6922ce406e093ec06fbbf23ca89a0d65a5956f0
> SOURCE_CONTRACT_DOCUMENT=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
> PRIOR_AMENDMENT_PR=68
> PRIOR_AMENDMENT_STATE=MERGED
> PRIOR_AMENDMENT_MERGE_COMMIT=4603648045a031667f992500c59ee1deb026cd53
> PRIOR_AMENDMENT_EFFECTIVE_AUTHORITY=SOURCE_CONTRACT_SECTION_20
> PRIOR_AMENDMENT_FIVE_PATH_STATUS=ACTIVE_AND_CONTINUING
> PRIOR_AMENDMENT_AMENDMENT_ACTIVATION=ON_PR68_MERGE
> PRIOR_AMENDMENT_SCOPE_OF_EFFECT=PR67_IMPLEMENTATION
> PR67_FIVE_PATH_ALLOWLIST_P0_CURRENT_STATUS=RESOLVED_BY_MERGED_PR68
> PR67_FIVE_PATH_AUTHORITY_SOURCE=MERGED_PR68_SECTION_20
> PR69_RETROACTIVE_INVALIDATION_OF_PRIOR_AMENDMENT=NO
> PR69_REAUTHORIZES_FIVE_PATHS=NO
> PR69_REACTIVATES_FIVE_PATHS=NO
> PR69_GATES_PR68_FIVE_PATH_AUTHORITY=NO
> PR69_RELATIONSHIP_TO_PRIOR_AMENDMENT=ADDITIVE_CLARIFYING_AMENDMENT
> PR69_ADDS_CLARIFICATIONS_AND_ACCEPTANCE_OBLIGATIONS_ONLY=YES
> PR69_ONLY_GOVERNS_FIVE_NEW_ACCEPTANCE_OBLIGATIONS=YES
> BLOCKED_IMPLEMENTATION_PR=67
> BLOCKED_IMPLEMENTATION_PR_CURRENT_HEAD=4ab6ebfa3d16c707f5aa849ff5b4bc831aa36669
> BINDING_REVIEW_ID=4727663461
> BINDING_REVIEW_VERDICT=CHANGES_REQUESTED  (on historical head f315f6a57cf5b1fbbca97856069bf10975ec0415)
> STATUS_CONFIRMATION_COMMENT_ID=5009963180
> PR67_REMAINS_IN_CHANGES_REQUESTED_STATE=YES  (snapshot per 2026-07-19)
> PR67_READY_AUTHORIZED=NO
> PR67_MERGE_AUTHORIZED=NO
> AMENDMENT_ROUND_TYPE=DOCS_ONLY_CORRECTIVE_ROUND_2
> AUTHORIZATION=AUTHORIZE_PR69_CONTRACT_AMENDMENT_CORRECTIVE_2
> ```
>
> **Round type:** one-file docs-only contract amendment (corrective-2).
> This document amends the frozen contract merged through PR #66 and
> operates additively to merged PR #68 §20. It does NOT freeze
> implementation, does NOT authorize Readiness, Merge, Issue #20
> closure, Task 12, or any PR #67 mutation. PR #67 remains untouched.
> After this round, Charles freeze-authorization in a SEPARATE round is
> the sole path to converting this draft amendment into a binding
> contract delta.

## 0. Relationship to merged PR #68 and source-contract §20
|
|This amendment is explicitly **additive-clarifying** relative to the
|merged PR #68 amendment. It does **NOT** revoke, supersede, or
|retroactively invalidate PR #68's authority. Required because the
|engineering-review verdict on this draft identified an unqualified
|"supersedes" claim that had to be reconciled with the fact that
|PR #68 is already merged into `main`.
|
|```text
|PR68_STATE=MERGED
|PR68_MERGE_COMMIT=4603648045a031667f992500c59ee1deb026cd53
|PR68_MERGE_TIMESTAMP=2026-07-18T05:50:37Z
|PR68_EFFECTIVE_AUTHORITY=SOURCE_CONTRACT_SECTION_20
|PR68_FIVE_PATH_AUTHORITY=ACTIVE_AND_CONTINUING
|PR69_RETROACTIVE_INVALIDATION_OF_PR68=NO
|PR69_REAUTHORIZES_FIVE_PATHS=NO
|PR69_SUPERSEDES_PR68=NO          # This string MUST NOT appear unconditioned in any future restatement.
|PR69_RELATIONSHIP_TO_PR68=ADDITIVE_CLARIFYING_AMENDMENT
|PR69_ADDS_CLARIFICATIONS_AND_ACCEPTANCE_OBLIGATIONS_ONLY=YES
|PR69_MERGES_AUTHORITY_PRECEDENCE=PR_68_AUTHORITY_CONTINUES_FOR_FIVE_PATHS,
|                                 THIS_AMENDMENT_CONTROLS_NEW_OBLIGATIONS
|```
|
|Normative rules for how the two amendments coexist on `main` after
|PR #69 merges:
|
|1. PR #68 has merged into `main` and has written the five-path
|   narrower authorization into source-contract §20. That authority
|   continues in force exactly as written.
|2. PR #69 does not reauthorize, withdraw, or retroactively alter
|   those five paths. The paths are already effective via §20.
|3. PR #69 is permitted to **clarify**, **restate for audit**, and
|   **add new acceptance obligations** that were not present in §20.
|4. Before PR #69 merges, it produces no new authority. The five
|   paths are governed by §20 from PR #68's merge onward regardless
|   of whether PR #69 ever merges.
|5. After PR #69 merges, if any clause in this document appears to
|   conflict with §20:
|   - §20 continues to control the five-path authorization scope.
|   - PR #69 controls the additional acceptance obligations and
|     any prerequisite / runner surface clarification explicitly
|     listed in §3a, §5, §6 below.
|   - PR #69 never widens the five-path scope beyond §20.
|6. Whether a historical PR #67 mutation was authorized at the time
|   it was made remains a historical fact; PR #69 merge does not
|   rewrite that history.
|
|When referring to PR #68 in this document or in the PR #69 body,
|this amendment uses phrases equivalent to "clarifies and extends
|the merged PR #68 amendment", never the unqualified verb
|"supersedes".
|
|## 1. Repository identity

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
source contract. The five-path authority activated by merged PR #68 §20
at `4603648045a031667f992500c59ee1deb026cd53` is **preserved
unchanged**. This amendment proposes **five additional Slice 1
acceptance obligations** and clarifies their execution and audit
requirements. The `evaluate.py` shared artifact-I/O reminder remains a
separate retained source-contract obligation and is not counted among
the five new ones.

## 3. Terminology

- **Source contract** — `docs/tasks/TASK-011-remaining-pilot-readiness-definition.md`
  frozen by PR #66, merged at `e6922ce406e093ec06fbbf23ca89a0d65a5956f0`.
- **Prior amendment (PR #68)** — the contract-amendment PR that merged
  into `main` at `4603648045a031667f992500c59ee1deb026cd53`, which
  added source-contract §20. Its five-path authorization is **active
  and continuing** regardless of whether PR #69 ever merges.
- **Blocked implementation PR** — PR #67
  (`codex/task-011-multilingual-report-pilot`), which has accumulated
  semantics required by the binding engineering review but is not
  authorized to Ready or Merge under any current amendment of this round.
- **Binding engineering review** — PR #67 review id `4727663461`,
  status `CHANGES_REQUESTED`, with status confirmation in PR #67
  conversation comment `5009963180` (a comment on the PR #67 issue
  thread, NOT on Issue #20). The verdict was anchored to PR #67
  historical head `f315f6a57cf5b1fbbca97856069bf10975ec0415`;
  PR #67 current head is `4ab6ebfa3d16c707f5aa849ff5b4bc831aa36669`
  (2026-07-19 snapshot). The current head carries no new engineering
  verdict; the canonical binding references are `PR_NUMBER=67` +
  `BINDING_REVIEW_ID=4727663461`, not the easily-stale head SHA.
- **Five-path authority (inherited from §20)** — the five tracked paths
  enumerated in §4 of this amendment. Authority was granted by PR #68
  §20 at `4603648045...` merge. This amendment restates them for audit
  only; it does NOT reauthorize them and does NOT alter their scope.
- **Translation catalog key (canonical)** — the dot-separated namespaced
  key as it appears in the locale `_MESSAGES` dict, e.g.
  `field.condenser_heat_rejection` and `unit.kw_th`. The
  **rendered unit label** for `unit.kw_th` is `"kW(th)"`; the
  **canonical unit code** is the rendered unit label string itself
  (verbatim).
- **Five additional acceptance obligations** — the five contract clauses
  enumerated in §5 of this amendment (5.1 manifest & golden binding,
  5.2 stable verifier exit-code classification, 5.3 field-bound artifact
  semantic verification, 5.4 four-render repeatability across SQLite +
  PostgreSQL × repeat 1/2, 5.5 production runner prerequisite and
  invocation contract). The `evaluate.py` refactor reminder in §6
  below is a **retained source-contract obligation** and is NOT
  counted among these five new obligations.

## 3a. Production runner prerequisite and invocation contract

The pilot composition must invoke the production runner through a
precise public surface with full prerequisite provisioning. The
contract below replaces the earlier unqualified "import
`run_scenario`" wording, which implicitly relied on the runner's
own documentation to supply missing required parameters.

```text
RUNNER_PUBLIC_SURFACE=cold_storage.evaluation.execute::run_scenario
RUNNER_REQUIRED_KEYWORD_ONLY_ARGUMENTS=4
# in canonical order:
RUNNER_REQUIRED_ARG_1=source_binding_id
RUNNER_REQUIRED_ARG_2=weight_set_revision_id
RUNNER_REQUIRED_ARG_3=correlation_id
RUNNER_REQUIRED_ARG_4=database_backend

PILOT_REQUIRES_PREEXISTING_SOURCE_BINDING_ID=YES
PILOT_REQUIRES_PREEXISTING_APPROVED_WEIGHT_SET_REVISION_ID=YES
PILOT_MUST_PROVISION_OR_RESOLVE_REQUIRED_PRODUCTION_IDENTITIES_BEFORE_RUN=YES

RUNNER_CANONICAL_SIGNATURE_SOURCE=backend/src/cold_storage/evaluation/execute.py
RUNNER_CANONICAL_SIGNATURE_AUTHORITY=CODE_AS_OF_ORIGIN_MAIN_4603648045
RUNNER_SIGNATURE_LAG_CLAIM=NO  # NOT lag — the four required identity parameters were always required.

PILOT_IMPORT_RUN_SCENARIO_VIA_MARKERS=FORBIDDEN
PILOT_DIRECT_ADAPTER_IMPORT=FORBIDDEN
PILOT_MUTATE_EXECUTE_PY=FORBIDDEN
```

Normative calling pattern the pilot composition MUST satisfy:

```python
from cold_storage.evaluation.execute import run_scenario

# IDs MUST reference real persisted rows already provisioned by
# §11.3 production-context composition in PR #67 — they are NOT
# allowed to be random or placeholder strings.
outcome = run_scenario(
    session_factory,
    source_binding_id=<backend-local persisted SourceBindingRecord.id>,
    weight_set_revision_id=<backend-local approved ApprovedWeightSetRevision.id>,
    correlation_id=<frozen golden-bound pilot baseline correlation id>,
    database_backend='sqlite' | 'postgresql',
)
```

The pilot composition passes the **same frozen pilot baseline
correlation ID** on every repeat. Two databases may have their
own prerequisite rows (`source_binding_id` /
`weight_set_revision_id`), but **the correlation ID is the same
golden-bound value across all four runs**.

Required conditions PR #67 must satisfy without modifying
`backend/src/cold_storage/evaluation/execute.py`:

1. Slice 1 pilot harness MUST establish or resolve real persisted
   prerequisites **before** invoking the runner (already implemented
   in `backend/tests/pilot/run_multilingual_report_pilot.py` via
   `seed_a1_all_prereqs` + `SOURCE_BINDING_ID` + `WEIGHT_REVISION_ID`).
2. `source_binding_id` MUST reference a real `SourceBindingRecord`
   row in the active database; cross-backend invocations MUST each
   use the row created in their own database.
3. `weight_set_revision_id` MUST reference a real `ApprovedWeightSetRevision`
   row with `status='approved'`, not a synthesised constant.
4. Neither ID MAY be forged as a random string. The IDs MAY be
   reused across repeated runs on the same backend provided they
   resolve to the same persisted rows. The production
   `correlation_id` is golden-bound at the pilot baseline value
   and MUST stay identical across every repeat (SQLite repeat
   1/2, PostgreSQL repeat 1/2); repeat uniqueness MUST be
   expressed through `repeat_index`, `run_root`, execution
   metadata, timestamps and storage keys, not through
   `correlation_id` variation.
5. SQLite and PostgreSQL runs MUST each provision their prerequisite
   rows in their own database; the pilot MUST NOT depend on a shared
   cross-backend fixture.
6. The pilot MUST NOT bypass the runner's FK validation, MUST NOT
   mock the production runner, and MUST NOT call
   `cold_storage.evaluation.adapter::execute_scenario` directly.
7. Prerequisite setup belongs to the §11.3 production-context
   composition surface — it is not a separate allowlist entry.
8. The existing `execute.py` signature is the contract authority
   for the four required identity parameters. The earlier proposal
   "signature lags the call site" was incorrect — the runner's
   signature is canonical; the prior amendment's wording simply
   failed to enumerate all four required inputs.

```text
PR67_ALLOWLIST_CAN_ACCOMMODATE_PREREQUISITE_BOOTSTRAP=YES
PR67_ALLOWLIST_REQUIRES_NEW_PATH_ENTRY=NO
PR67_CAN_COMPLY_WITHOUT_EXECUTE_PY_MUTATION=YES
PR67_IMPLEMENTATION_BLOCKED_PENDING_SEPARATE_ALLOWLIST_DECISION=NO
```

Pre-existing inconsistency surface (record only; OUT OF SCOPE):

```text
PREEXISTING_EXECUTE_MODULE_SURFACE_INCONSISTENCY=
  run_scenario_via_markers is described as internal but exported in __all__
PREEXISTING_SURFACE_INCONSISTENCY_RESOLUTION=
  OUTSIDE_THIS_AMENDMENT_AND_OUTSIDE_PR67
RUN_SCENARIO_VIA_MARKERS_CLASSIFICATION=
  INTERNAL_RUN_DIRECTORY_COMPATIBILITY_WRAPPER
```

The pre-existing inconsistency in the `execute` module's `__all__`
list (the literal entry `run_scenario_via_markers` coexists with the
intent that this name is an internal wrapper) is recorded here as a
separate observation and is OUT OF SCOPE for this amendment AND OUT
OF SCOPE for the PR #67 corrective round. PR #67 MUST NOT touch
`execute.py` even to "fix" this inconsistency. The
`run_scenario_via_markers` path MAY continue to exist in
`__all__` without this amendment declaring it part of the public
authority — the wrapping discipline forbids it from import by the
pilot regardless of its `__all__` membership.

## 4. Inherited five-path authority (audit restatement of merged PR #68 §20)

The source contract §11 "Exact Slice 1 implementation allowlist"
remains authoritative. After PR #68 merged into `main` at
`4603648045...`, source-contract §20 added the five tracked paths
below as **already effective** narrower authorizations. PR #69 does
**not** introduce these authorizations; it lists them here only for
audit restatement.

```text
NORMATIVE_AUTHORITY=SOURCE_CONTRACT_SECTION_20_AS_MERGED_BY_PR68
THIS_SECTION_ROLE=NON_EXPANSIVE_AUDIT_RESTATEMENT
FIVE_PATH_DUPLICATION_FOR_AUDIT=YES
FIVE_PATH_REAUTHORIZATION=NO
FIVE_PATH_SCOPE_EXPANSION_BEYOND_PR68=NO
FIVE_PATH_SCOPE_NARROWING_RELATIVE_TO_PR68=POSSIBLE
PR69_ADDITIONAL_RESTRICTION_LABELED_PER_PATH=YES
```

For each path below, the **effective authority** comes from source
contract §20, not from this document. Where PR #69 lists any
additional forbidden-scope clause beyond §20's, that clause is an
**additional restriction** (`PR69_ADDITIONAL_RESTRICTION`), not a §20
override — it narrows the path further but never widens it.
Because PR #67 has not yet been authorized to Ready/Merge,
PR69_ADDITIONAL_RESTRICTION clauses here are still proposed
additions; they become binding only after this amendment merges.

```text
CURRENT_PR67_CONTENT_TECHNICALLY_PRESENT=YES
FIVE_PATH_AUTHORITY_CURRENTLY_ACTIVE=YES
FIVE_PATH_AUTHORITY_SOURCE=PR68_SECTION_20
HISTORICAL_MUTATION_TIMING_RECORDED_SEPARATELY=YES
HISTORICAL_PRE_PR68_MUTATION_AUTHORIZATION_STATUS=HISTORICAL_FACT_NOT_REWRITTEN
CURRENT_PR67_FIVE_PATH_AUTHORITY=ACTIVE_VIA_MERGED_PR68_SECTION_20
PR67_FIVE_PATH_P0_RESOLVED_BY_PR68=YES
```

The historical authorization status of PR #67's branch-time mutations
is recorded under `HISTORICAL_PRE_PR68_MUTATION_AUTHORIZATION_STATUS`
and is **not** rewritten by this amendment. The current PR #67 P0
frozen-allowlist finding is **already resolved** by PR #68 §20; this
amendment does **not** gate, reactivate, or re-freeze that
resolution.

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

```text
CATALOG_KEY=field.condenser_heat_rejection
RENDERED_LABEL_EN_US="Condenser Heat Rejection"  # verbatim, no paraphrase
CATALOG_KEY=unit.kw_th
RENDERED_UNIT_LABEL_EN_US="kW(th)"               # verbatim
CANONICAL_UNIT_CODE="kW(th)"                     # = rendered unit label string
```

The two **catalog keys** (`field.condenser_heat_rejection`,
`unit.kw_th`) are dot-separated namespaced identifiers in the
`_MESSAGES` dict (matching the existing `field.<x>` and `unit.<x>`
convention in `en_us.py`). The **rendered unit label** for
`unit.kw_th` is the literal string `kW(th)` — this is also the
**canonical unit code** for downstream metric binding.

**Forbidden scope (`PR69_ADDITIONAL_RESTRICTION`)**:
`NO_UNRELATED_TRANSLATION_REWRITE`,
`NO_TEMPLATE_CHANGE`,
`NO_LOCALE_FALLBACK_REDESIGN`,
`NO_NEW_LANGUAGE_ADDITION`,
`NO_REPORT_WORDING_CLEANUP_OUTSIDE_EXACT_REQUIRED_KEYS`,
`NO_EXISTING_KEY_MODIFICATION`,
`NO_MESSAGES_DICT_ORDERING_CHANGE_FOR_NON_NEW_KEYS`,
`NO_CATALOG_VERSION_BUMP`.

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

```text
CATALOG_KEY=field.condenser_heat_rejection
RENDERED_LABEL_ZH_CN="冷凝器排热量"  # verbatim, no paraphrase
CATALOG_KEY=unit.kw_th
RENDERED_UNIT_LABEL_ZH_CN="kW(th)"  # verbatim (raw string retained)
CANONICAL_UNIT_CODE="kW(th)"
```

**Forbidden scope (`PR69_ADDITIONAL_RESTRICTION`)** is identical to
§4.2.

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

## 5. Five additional acceptance obligations (binding only after Charles freeze)

The five-path authority inherited from §20 (PR #68) is **necessary
but not sufficient** for Slice 1 acceptance. This amendment proposes
five additional acceptance obligations that become binding only after
this amendment is itself reviewed, freeze-authorized, Ready, merged,
and the post-merge main identity is verified; none is enforceable in
this authoring round. The `evaluate.py` refactor reminder in §6 below
is a **retained source-contract obligation** and is not counted among
these five.

```text
TOTAL_ADDITIONAL_ACCEPTANCE_OBLIGATIONS=5
OBLIGATION_5_1=Exact manifest and golden acceptance binding
OBLIGATION_5_2=Stable verifier exit-code classification
OBLIGATION_5_3=Field-bound artifact semantic verification
OBLIGATION_5_4=True SQLite+PostgreSQL × repeat 1/2 four-render E2E evidence
OBLIGATION_5_5=Production runner prerequisite and invocation contract
EVALUATE_PY_REFACTOR_REMINDER=RETAINED_FROM_SOURCE_CONTRACT_NOT_COUNTED_HERE
```

After the post-freeze state takes effect, each obligation below
becomes binding. PR #67 readiness review will check that the merged
PR #67 satisfies all five.

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
# correlation ID is golden-bound and MUST be identical across
# every SQLite/PostgreSQL repeat per §5.5:
CORRELATION_ID
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

### 5.5 Production runner prerequisite and invocation contract

After the post-freeze state takes effect, future Slice 1 implementation MUST satisfy the runner surface and prerequisite-provisioning contract specified in §3a. Concretely:

- The pilot composition MUST call
  `cold_storage.evaluation.execute::run_scenario` with all four
  keyword-only arguments `source_binding_id`, `weight_set_revision_id`,
  `correlation_id`, `database_backend`.
- `source_binding_id` and `weight_set_revision_id` MUST reference
  real persisted rows (`SourceBindingRecord` /
  `ApprovedWeightSetRevision` with `status='approved'`) provisioned
  by the §11.3 composition.
- Random, placeholder, or cross-backend-shared IDs are forbidden.
- The pilot MUST NOT import
  `cold_storage.evaluation.adapter::execute_scenario` directly, MUST
  NOT import `cold_storage.evaluation.execute.run_scenario_via_markers`,
  and MUST NOT modify
  `backend/src/cold_storage/evaluation/execute.py`.
- Repeated runs (SQLite repeat 1/2, PostgreSQL repeat 1/2) MAY reuse
  the same prerequisite IDs in their respective database.
- Repeat uniqueness MUST be expressed through non-correlation-ID
  channels: `database_backend`, `repeat_index`, `run_root` /
  output-root identity, execution record, artifact identity,
  timestamp, storage key — **never through varying the production
  correlation ID**. The production correlation ID is part of the
  golden-bound business projection and stays frozen at the pilot
  baseline value across every repeat.

```text
PRODUCTION_CORRELATION_ID_SOURCE=FROZEN_GOLDEN_CONTRACT
PRODUCTION_CORRELATION_ID_REPEAT_VARIATION=NO
REPEAT_EXECUTION_IDENTITY_SOURCE=
  database_backend
  repeat_index
  run_root
  execution_metadata
REPEAT_EXECUTION_IDENTITY_UNIQUE=YES
PILOT_BASELINE_CORRELATION_ID_REQUIRED=YES
REPEAT_1_PRODUCTION_CORRELATION_ID_EQUALS_REPEAT_2=YES
REPEAT_UNIQUENESS_DOES_NOT_REQUIRE_CORRELATION_VARIATION=YES
CROSS_REPEAT_GOLDEN_INVARIANT_INCLUDES_CORRELATION_ID=YES
```
- Freeze of this amendment becomes binding immediately on main merge,
  but enforcement for PR #67 waits for Charles's separate PR #67
  corrective authorization.

```text
OBLIGATION_5_5_BINDING_AFTER_MERGE=YES
OBLIGATION_5_5_ENFORCEMENT_FOR_PR67=REQUIRES_SEPARATE_PR67_CORRECTIVE_ROUND
RUNNER_PREREQUISITES_EXPLICIT=YES
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

## 7. PR #67 governance state and the effect of PR #69's new obligations

This amendment tracks PR #67 identity using **stable identifiers**,
not easily-stale head SHAs. Where a head SHA appears below it is
explicitly labeled as a **historical snapshot** or a **non-normative
current snapshot**, never as a contract authority.

```text
PR_NUMBER=67
PR67_BINDING_REVIEW_ID=4727663461
PR67_BINDING_REVIEW_VERDICT=CHANGES_REQUESTED
PR67_BODY_CONVERSATION_COMMENT_ID=5009963180

PR67_HEAD_HISTORICAL_AT_INITIAL_AMENDMENT_AUTHORING=f315f6a57cf5b1fbbca97856069bf10975ec0415
PR67_HEAD_CURRENT_SNAPSHOT_2026_07_19=4ab6ebfa3d16c707f5aa849ff5b4bc831aa36669
PR67_HEAD_SNAPSHOT_NON_NORMATIVE=YES
PR67_NEW_ENGINEERING_VERDICT_AFTER_CORRECTIVE_ROUNDS=NO  # No new review verdict anchored to the current head; the canonical binding remains review 4727663461.
PR67_REMAINS_OPEN_AND_DRAFT=YES

# Three concepts that MUST remain distinct:
A_HISTORICAL_PRE_PR68_MUTATION_AUTHORIZATION_STATUS=HISTORICAL_FACT_NOT_REWRITTEN
B_CURRENT_PR67_FIVE_PATH_AUTHORITY=ACTIVE_VIA_MERGED_PR68_SECTION_20
C_PR69_ADDITIONAL_ACCEPTANCE_OBLIGATIONS=NOT_BINDING_UNTIL_PR69_MERGE
```

### 7.1 Five-path P0 status (already resolved)

The PR #67 P0 frozen-allowlist finding from binding review
`4727663461` is **resolved by merged PR #68 §20**. PR #69 does not
gate, reactivate, or re-freeze that resolution; PR #69 merge is
**not** required for the five paths to be authorized for PR #67.
This separation is binding: PR #69 merge MUST NOT be cited as
proof of five-path authorization.

### 7.2 Why PR #67 still cannot Ready/Merge

PR #67 still cannot Ready or Merge under any current authorization,
not because of the five-path authority (which §20 already
provides) but because the following unrelated conditions are open:

1. **Open engineering-findings on PR #67** — the binding review
   `4727663461` verdict `CHANGES_REQUESTED` remains the controlling
   verdict until separate, individually authorized corrective
   rounds lift or replace it.
2. **Five new acceptance obligations proposed by PR #69 are not
   yet binding** — they are authored in this draft and require
   Charles's freeze authorization, then Ready, then Merge, then
   post-merge main identity verification, in four separate
   rounds.
3. **No PR #67 corrective/Ready/Merge authorization issued** —
   Charles has not yet issued any of these authorizations for
   PR #67 directly.

### 7.3 Effect of a future PR #69 merge

If and when PR #69 merges:

- Its five new acceptance obligations become binding contract
  delta on `main`.
- Its merge does **not** retroactively rewrite whether PR #67's
  branch-time mutations were authorized at the moment they were
  made. That historical fact is preserved under §0 concept A
  (above).
- Its merge does **not** alter the five-path authorization already
  in force via PR #68 §20.

### 7.4 Canonical binding references

The canonical binding references for PR #67 — **independent of
easily-stale head SHAs** — are:

```text
PR_NUMBER=67
PR67_BINDING_REVIEW_ID=4727663461
PR67_BODY_CONVERSATION_COMMENT_ID=5009963180
```

The historical head `f315f6a57cf5b1fbbca97856069bf10975ec0415`
records the head the binding review was anchored to. The
current head `4ab6ebfa3d16c707f5aa849ff5b4bc831aa36669` is a
non-normative snapshot.

## 8. State surface at end of this round

```text
DOCUMENT_STATUS=AUTHORED_PENDING_REVIEW
CONTRACT_AMENDMENT_FROZEN=NO
PR68_STATE=MERGED
PR68_MERGE_COMMIT=4603648045a031667f992500c59ee1deb026cd53
PR68_FIVE_PATH_AUTHORITY=ACTIVE_AND_CONTINUING
PR69_FIVE_PATH_AUTHORITY=INHERITED_FROM_PR68_REVIEW_RESTATEMENT_ONLY
PR69_FIVE_PATH_REAUTHORIZATION=NO
MANIFEST_GOLDEN_BINDING_OBLIGATION_AUTHORED=YES
EXIT_CODE_4_OBLIGATION_AUTHORED=YES
FIELD_BOUND_SEMANTIC_OBLIGATION_AUTHORED=YES
FOUR_RUN_E2E_OBLIGATION_AUTHORED=YES
RUNNER_PREREQUISITE_OBLIGATION_AUTHORED=YES
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
FINAL_CLASSIFICATION=
  TASK011_SLICE1_CONTRACT_AMENDMENT_001_CORRECTED_2_PENDING_INDEPENDENT_REVIEW

PR68_FIVE_PATH_AUTHORITY=ACTIVE
PR67_FIVE_PATH_P0=RESOLVED
PR69_FIVE_NEW_OBLIGATIONS=AUTHORED_PENDING_REVIEW
PR69_CONTRACT_AMENDMENT_FROZEN=***

PR67_CORRECTION_AUTHORIZED=***
PR67_READY_AUTHORIZED=***
PR67_MERGE_AUTHORIZED=***
ISSUE20_CLOSURE_AUTHORIZED=***
TASK12_AUTHORIZED=***
```

This document is corrected (single-file docs-only patch on top
of the prior committed corrective-1 round), and is pending
independent contract review. It contains zero implementation
authority, zero PR #67 mutation authority, and zero GitHub
workflow change authority as a result of this round's
correction. The contract corrections this document records
(surface resolution, status language, repeat-identity
clarification, allowlist authority separation, obligation
count unification, final classification rewrite) are recorded
in proposed-for-freeze form: they would become binding only
after Charles's explicit freeze authorization in a separate
round followed by Ready, Merge, and post-merge main-identity
verification. Absent that freeze-authorization round, this
document remains in `CORRECTED_2_PENDING_INDEPENDENT_REVIEW`
indefinitely and PR #69 remains in its current Draft state.

*End of Amendment 001 (corrective-2).*
