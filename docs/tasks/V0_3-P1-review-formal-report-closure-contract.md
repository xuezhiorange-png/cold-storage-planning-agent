# V0.3 P1 Review and Formal-Report Closure Contract

Status: CORRECTIVE AMENDMENT R4 FOR FINAL CONTRACT INDEPENDENT REVIEW

This document defines the V03-P1 contract. It does not implement the deferred
review or formal-report work.

## 1. Authority and baseline

- Umbrella issue: #108, "[V0.3] Operational Planning Workflow Baseline".
- Tracking issue: #109, "[V0.3][P1] Review and Formal Report Closure".
- Upstream deferred scope: #72, "TASK-011 Follow-up".
- Repository: `xuezhiorange-png/cold-storage-planning-agent`.
- Audited branch: `main`.
- Audited source SHA: `b7704b2dba53a294e827cddf8d99ddf225ee5d04`.
- Audited tree SHA: `8c0bf37368306c46f5937439a03df1ccbb735b16`.
- Source drift during audit: `false`.
- Worktree at audit start: clean.

The source SHA and tree SHA above are the authority for this contract round.
An implementation PR must revalidate its own exact base and must not silently
reuse this identity after `main` changes.

This contract authority has an explicit, append-only review lineage:

```text
INITIAL_CONTRACT_HEAD=a1ebd4cb25e104f5bcde7c8b004b58bb8e79ddbd
INITIAL_INDEPENDENT_REVIEW_ID=4942369620
INITIAL_REVIEW_COMMENT_ID=4942414051
INITIAL_ISSUE109_RESULT_COMMENT_ID=5299888272

R1_CORRECTED_HEAD=6ed78d4f77320ed94159c57e04a1d1daa751fc79
R1_CORRECTED_INDEPENDENT_REVIEW_ID=4943239922
R1_ISSUE109_RESULT_COMMENT_ID=5301160868

R2_CORRECTED_HEAD=bdb44f923bfc207904c7a7f9e0ae22bda9973ff5
R2_INDEPENDENT_REVIEW_ID=4943334847
R2_ISSUE109_RESULT_COMMENT_ID=5301325775

R3_AMENDMENT_PARENT_HEAD=bdb44f923bfc207904c7a7f9e0ae22bda9973ff5
R3_CORRECTED_HEAD=f98291939730ac0f54f62ec7661ab24cd21357da
FINAL_CONTRACT_INDEPENDENT_REVIEW_ID=4943731867
FINAL_REVIEW_FOLLOWUP_COMMENT_ID=5302009558
FINAL_ISSUE109_RESULT_COMMENT_ID=5301999778

R4_AMENDMENT_PARENT_HEAD=f98291939730ac0f54f62ec7661ab24cd21357da
```

The R4 commit SHA is intentionally not written into its own content. It is
recorded by the PR, the R4 Issue #109 completion record, and the later R4
independent review. The preceding R3 head and final-review records above are
retained as append-only provenance. This contract PR may change this document
only; all future allowlists below are not permissions for this round.

### Corrective finding closure map

1. **Structured reason type:** P1 uses a closed structured JSON object,
   lossless typed/readback paths, existing JSON persistence, and no migration;
   legacy string-only values are non-canonical.
2. **Cross-backend parity:** raw IDs are retained and checked within each run;
   normalized business projection is the cross-backend/repeatability contract.
3. **Source-gate cycle:** Step A proves upstream source evidence while
   recording the current missing SchemeRun propagation; Step B implements it;
   Step C verifies non-empty reason continuity.
4. **Report bridge:** a minimal public-query/provider/report-application bridge
   is required and formal export must consume it; no ORM shortcut or
   acceptance-only ambiguity remains.
5. **Actor authority:** controlled acceptance uses a trusted injected operator
   seam; P1 does not claim full production authentication/RBAC.
6. **Fixture path:** the canonical fixture path is allowlisted only after Step
   A evidence and its hash are accepted; this round does not create it.
7. **Historical governance:** TASK-011/TASK-012 authority documents and
   workflows are read-only; future P1 acceptance has a new V0.3 path.

```text
R1_FINDINGS_01_07=CLOSED
R2_FINDINGS_01_04=CLOSED
R3_FINDING_01_AUTHORITY_PRECEDENCE_CLOSED=YES
R3_FINDING_02_LANE_ALLOWLIST_SEPARATION_CLOSED=YES
R3_FINDING_03_CONTRACT_PROVENANCE_CLOSED=YES
R1_REGRESSION=NO
R2_REGRESSION=NO
```

## 1.1 Authority reconciliation with Issue #72

Issue #72 Definition / Freeze Record v1 (`5294899790`) remains the upstream
historical deferred-scope authority. V0.3 P1 does not rely on an implicit
"newer document wins" rule and does not blanket-supersede Issue #72.

```text
ISSUE72_ROLE=UPSTREAM_HISTORICAL_DEFERRED_SCOPE_AUTHORITY
V03_P1_ROLE=NARROW_EXPLICIT_AMENDMENT_FOR_V0_3_P1_ONLY
ISSUE72_BLANKET_SUPERSEDE=NO
ISSUE72_UNAMENDED_RULES_REMAIN_AUTHORITY=YES
V03_P1_MERGED_CONTRACT_CONTROLS_ENUMERATED_AMENDMENTS=YES
IMPLEMENTATION_AUTHORIZED_BY_AUTHORITY_RECONCILIATION=NO
```

The merged V0.3 P1 contract makes only these narrow, enumerated amendments:

### Amendment A: Lane A reason continuity

The Issue #72 Lane-A continuity contract is extended only to make the
existing production signal auditable and lossless: structured `ReviewReason`
objects, exact source-bound reason identity, typed JSON persistence/readback,
the required repository/read-port closure, and normalized cross-backend
parity. The following Issue #72 rules remain binding and are not amended:

- producer `requires_review` remains the review boolean authority;
- source-definition evidence must pass before Lane-A implementation;
- `high_throughput_review` is a scenario label, not a new rule;
- no new threshold, formula, coefficient, scoring rule, or review rule;
- historical TASK-011 goldens/manifests remain immutable.

### Amendment B: Lane B report enforcement

Issue #72 defines Lane B as an acceptance-composition extension. The current
main audit proves that an acceptance-only description would leave a real
production bypass: the report composition does not consume Scheme review
authority. V0.3 P1 therefore narrows that extension into
`MINIMAL_APPLICATION_ENFORCEMENT`, limited to the public
`SchemeReviewAuthority` query, provider/assembler lineage, ReportService
approval gate, ReportRenderService formal gate, persisted review-action
readback, and composition wiring. It does not authorize report status-machine
or renderer-mechanics redesign, autonomous approval, frontend approval
authority, or production authentication/RBAC expansion.

### Unamended Issue #72 rules

The following remain fully binding: Lane A/Lane B separation, the mandatory
source-definition evidence gate, no historical TASK-011 mutation, no formula,
threshold, coefficient, scoring, or autonomous approval change, separate
governance authorization for every stage, and
`NO_STEP_IMPLIES_THE_NEXT=TRUE`.

The amendment is not effective on `main` while PR #114 is unmerged:

```text
V03_P1_AMENDMENT_EFFECTIVE_ON_MAIN=NO
```

It becomes effective only after final independent review PASS, separate Ready
authorization, separate Merge authorization, and post-merge exact SHA/tree
verification. Until then the Issue #72 authority and this draft contract are
planning records only.

```text
V03_P1_AMENDMENT_EFFECTIVE_ON_MAIN=YES_AFTER_POST_MERGE_VERIFICATION
```

After final contract independent review PASS, a separate Issue #72 authority
reconciliation record is required before the contract Ready gate. It must
name this contract path, reviewed PR head, final review ID, the enumerated
amendments above, the unamended Issue #72 rules, and the continuing
implementation/Ready/Merge prohibitions. R3 does not create that record, and
it does not authorize Ready. The post-merge verification must recheck that the
merged exact SHA/tree still matches the reconciled contract before source
evidence can be authorized.

```text
ISSUE72_RECONCILIATION_RECORD_REQUIRED_BEFORE_READY=YES
ISSUE72_RECONCILIATION_RECORD_CREATED_BY_R3=NO
ISSUE72_RECONCILIATION_AUTO_AUTHORIZES_READY=NO
```

## 2. Scope decision

P1 is a closure package for two related lanes:

1. propagate real production review reasons from deterministic calculation
   output through the production scheme result and its consumers;
2. prove the existing report lifecycle and formal render path with a real,
   approved, multilingual acceptance matrix.

`high_throughput_review` is a scenario label for Lane A. It is not a new
throughput threshold, formula, coefficient, score, or review rule. The
implementation cannot start until the staged source-definition evidence gate
in section 6 is satisfied. The report bridge is a minimal application-boundary
enforcement change, not a redesign of the report status machine or renderer.

The P1 contract reuses existing calculation, source-binding, scheme, report,
approval, renderer, and artifact-storage authorities. It does not redesign
those domains.

## 3. Current production review-signal chain

The audited chain is:

```text
deterministic calculator
  -> calculation adapter
  -> Transaction B / CalculationRun warnings and requires_review
  -> SourceBinding and verified source mapping
  -> ProductionSchemeService
  -> SchemeRunRecord persistence
  -> evaluation adapter / API and report consumers
  -> frontend report/export consumer
```

### 3.1 Signals currently produced

The following production calculators can set `requires_review=true` or emit
review-relevant warnings. These are existing rules, not new P1 rules:

| Source | Existing signal |
| --- | --- |
| `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` / `ColdRoomZonePlanner.plan` | `DEMO_ASSUMPTIONS_REQUIRE_REVIEW`, with `requires_review=true` |
| `backend/src/cold_storage/modules/calculations/domain/investment.py` / `InvestmentEstimator.estimate` | `DEMO_INVESTMENT_REQUIRES_REVIEW`, with `requires_review=true` |
| `backend/src/cold_storage/modules/calculations/domain/inventory.py` | `NO_SAFETY_STOCK` or `PEAK_FACTOR_DEFAULT` can set the review boolean |
| `backend/src/cold_storage/modules/calculations/domain/throughput.py` | `DEMO_COEFFICIENT` can set the review boolean |
| `backend/src/cold_storage/modules/calculations/domain/pallets.py` | `HIGH_STACKING` or `NO_RESERVE` can set the review boolean |
| `backend/src/cold_storage/modules/calculations/domain/cooling_load.py` | demo/sensible-only/coefficient conditions can set the review boolean |
| `backend/src/cold_storage/modules/calculations/domain/areas.py` | any warning sets the review boolean |
| `backend/src/cold_storage/modules/calculations/domain/power.py` | warnings may exist while the current boolean is explicitly false; this producer-specific behavior is not changed by P1 |

`backend/src/cold_storage/modules/orchestration/application/production_calculation/adapters.py:_build_warning_dicts`
preserves warning code, message, and details without rewriting. The adapter
also preserves the calculator `requires_review` boolean.

### 3.2 Confirmed loss point

The boolean survives the current source-binding path:

- `ProductionSourceBindingUseCase` returns `requires_review`.
- `VerifiedSourceMapping` carries `requires_review`.
- `ProductionSchemeService.generate_production_scheme_run` includes the
  boolean in the content hash and `SchemeRun`.
- `SchemeRunRecord` persists the boolean and a JSON `warning_messages`
  field.
- `backend/src/cold_storage/evaluation/adapter.py` reads the persisted
  boolean and warning list into `AdapterResult.review_required` and
  `AdapterResult.review_reasons`.

The confirmed loss is in
`backend/src/cold_storage/modules/schemes/application/production_service.py`:
the content-hash input and the domain/persisted `SchemeRun` are currently
constructed with `warning_messages=[]` even when the authoritative source has
review warnings. This permits a real persisted result with
`review_required=true` and no persisted review reason. The current
`VerifiedSourceMapping` and `ProductionSourceBindingOutcome` also expose the
boolean but not a reason projection.

This is a missing integration, not evidence for a new calculator rule. P1
must repair propagation and make the invariant fail closed. It must not parse
warning text to infer the boolean, change an existing rule, or invent a
high-throughput threshold.

### 3.3 Current consumers

The backend review endpoints exist in
`backend/src/cold_storage/modules/reports/api/routes.py`:
`submit-review`, `request-changes`, `mark-reviewed`, `approve`, and
`archive`. The current dependency returns the literal actor `system`, so it
is an API stub rather than a complete human-identity/authorization boundary.
P1 acceptance must use an explicit human/operator actor and must prove there
is no autonomous approval path.

The current frontend report feature consumes report lists, revisions, render,
exports, and downloads. `frontend/src/features/reports/components/
ReportExportPanel.vue` has no review or approval controls. This is a confirmed
frontend consumer gap. P1 does not authorize frontend production changes: the
backend operator surface is the only accepted reviewer boundary for this
package, and a frontend formal-mode selection must never be treated as
approval.

## 4. Current report and approval lifecycle

The current report domain defines exactly these statuses in
`backend/src/cold_storage/modules/reports/domain/enums.py`:

```text
draft -> generated -> under_review -> reviewed -> approved -> archived
                              \-> draft (request_changes)
```

The corresponding service actions are `submit_review`, `request_changes`,
`mark_reviewed`, `approve`, and `archive`. The status machine in
`backend/src/cold_storage/modules/reports/domain/status_machine.py` rejects
other transitions. P1 does not add a status.

Current behavior confirmed from `ReportService`:

- report and revision creation are idempotent when an idempotency key is used;
- review actions are append-only audit records with actor, comment, source
  status, and target status;
- optimistic version checking protects report updates;
- approval stores `approved_revision_id`, `approved_content_hash`,
  `approved_by`, and `approved_at`;
- a new revision clears the approval binding;
- quality blockers prevent submit/approve transitions;
- owner isolation is applied through the service actor argument;
- the API actor provider is currently a `system` stub and is not a
  substitute for a real human authorization integration.

### Frozen lifecycle rules for P1

1. Only the existing service transitions are valid.
2. `request_changes` returns the report to `draft` and invalidates any
   prior approval binding.
3. A revision change makes the previous approval stale; the new revision must
   pass the complete review path again.
4. A stale calculation or stale source reference cannot be approved for a
   different project revision.
5. A review-required result must have at least one real, source-bound reason.
6. Approval is an explicit human/operator action. An AI, calculator, renderer,
   or background retry may not call `approve`.
7. Restart must reload the same status, reason set, revision identity, and
   approval identity.
8. Concurrent transitions must fail with the existing conflict semantics; they
   must not choose a winner by timestamp or retry an approval silently.
9. For a review-required SchemeRun, a valid trusted-operator `mark_reviewed`
   action for the exact scheme review snapshot is required before approval;
   the existing report statuses are reused and no new status is added.
10. Formal render must revalidate the approved revision's scheme-review
    snapshot through the report application boundary. An approved report
    whose required scheme review is absent, stale, or source-mismatched is not
    eligible for formal output.

## 5. ReviewReason contract

P1 freezes a machine-readable reason projection without adding a new
calculation rule. The canonical reason item is the following closed object:

```json
{
  "code": "DEMO_ASSUMPTIONS_REQUIRE_REVIEW",
  "message": "exact producer message",
  "stage": "zone",
  "source_type": "calculation_run",
  "source_id": "exact CalculationRun id"
}
```

Field rules:

- `code` and `message` are copied verbatim from the authoritative
  calculator warning; consumers do not rewrite or classify them.
- `stage` is one of the existing ordered production stages:
  `zone`, `cooling_load`, `equipment`, `power`, `investment`.
- `source_type` is the fixed value `calculation_run` for this P1
  projection; it is not inferred from message text.
- `source_id` is the exact persisted `CalculationRun` identity referenced
  by the verified `SourceBinding`.
- No `details`, free-form severity, threshold, score, or invented field is
  added to the P1 reason contract. Existing warning details remain upstream
  evidence unless separately required by a future contract.

Current-main type reconciliation is explicit:

- `SchemeRun.warning_messages`, `PersistedSchemeRun.warning_messages`, and
  `ProductionSchemeRunRepository` currently type this value as
  `list[str]`; P1 changes that canonical projection to a typed structured
  reason object without changing the column shape.
- `AdapterResult.review_reasons` currently exposes `tuple[str, ...]`; the P1
  implementation must update the relevant typed boundary to the structured
  object and preserve JSON objects through write, read, and restart.
- `SchemeRunRecord.warning_messages` is already a JSON column. No database
  schema change or migration is needed or allowed for this projection.
- No read path may perform `str(reason)` or otherwise serialize an object into
  a lossy string. A legacy string-only value is historical compatibility data,
  not a new canonical approval authority.
- The future implementation allowlist includes the minimum domain, query,
  repository, and evaluation paths needed for this typed/readback closure;
  it does not open the entire `schemes/**` tree.

The reason item field set is closed. The warning-code set is producer-owned
and therefore open, but every code must be present in the exact upstream
warning evidence. An unknown code without matching persisted source evidence
is a fail-closed error, not a warning downgrade.

Ordering and deduplication are deterministic:

1. order stages by the existing orchestration stage order;
2. preserve warning order within each stage;
3. remove only exact duplicate
   `(code, message, stage, source_type, source_id)` entries, retaining the
   first occurrence.

Persistence and API rules:

- the canonical persisted `SchemeRun.warning_messages` JSON value is a list
  of these objects for new P1 records;
- `review_reasons` at the evaluation/API boundary exposes the same ordered
  objects, without text parsing or lossy reformatting;
- restart readback must be field equivalent after canonical JSON
  normalization;
- legacy non-empty string-only warning lists cannot be promoted as a new
  canonical approval authority without regeneration and source verification;
  they may remain visible as historical draft data;
- no new table or migration is authorized for this JSON projection.

```text
STRUCTURED_REVIEW_REASON_OBJECT_REQUIRED=YES
DB_SCHEMA_MIGRATION_REQUIRED=NO
LOSSLESS_JSON_RESTART_READBACK_REQUIRED=YES
LEGACY_STRING_REASON_CANONICAL_AUTHORITY=NO
```

### Review invariants

These are acceptance invariants, not new review rules:

```text
review_required=false  => review_reasons=[]
review_required=true   => review_reasons contains >= 1 valid source-bound item
```

The persisted value, fresh readback, API projection, and formal-report
consumer must agree. Any mismatch blocks approval/formal export and reports a
deterministic validation error.

### ReviewReason projection authority

The producer's persisted stage-level `requires_review` boolean is the sole
authority for whether a warning participates in the canonical
`ReviewReason` projection. Warning text, warning presence, and warning code
must never be used to infer or upgrade that boolean. For each authoritative
stage/`CalculationRun`:

1. when `requires_review=false`, its warnings remain ordinary advisory
   warnings and its `ReviewReason` projection is `[]`;
2. when `requires_review=true` and at least one valid source-bound warning is
   present, each such warning is projected into the closed structured reason
   object using the exact producer code/message, stage, source type, and
   `CalculationRun` source ID;
3. when `requires_review=true` but no valid source-bound warning exists, the
   projection fails closed with `REVIEW_REASON_SOURCE_MISSING`.

Only reasons from true stages are aggregated. Therefore a legal producer
warning such as the current installed-power `DEFAULT_DEMAND_FACTOR` warning
does not become an approval blocker when that stage persists
`requires_review=false`. Conversely, a true stage cannot be made acceptable by
parsing, inventing, or copying a warning from another stage/run. The existing
overall invariants remain authoritative after this stage-scoped projection.

```text
REVIEW_BOOLEAN_AUTHORITY=PRODUCER_REQUIRES_REVIEW
WARNING_TEXT_DECIDES_REVIEW=NO
WARNINGS_FROM_FALSE_STAGE_BECOME_REVIEW_REASON=NO
TRUE_STAGE_WITHOUT_VALID_REASON=FAIL_CLOSED
```

## 6. Staged high-throughput source and evidence gates

The pre-implementation source-definition gate and the post-implementation
reason-continuity gate are separate contracts. The first gate must not require
the very SchemeRun propagation that Lane A is intended to implement.

### STEP A: HIGH_THROUGHPUT_SOURCE_DEFINITION_EVIDENCE

`HIGH_THROUGHPUT_EXACT_SOURCE_EVIDENCE` is a required pre-implementation gate.
It is not satisfied by a historical candidate value, a fixture name, or the
string `high_throughput_review`. It is allowed to record the current confirmed
gap:

```text
SCHEME_RUN_REVIEW_REASON_PROPAGATION=CURRENTLY_MISSING
```

That observation is not a Step A failure. Step A proves the upstream production
authority from which Lane A must propagate reasons.

The source package must bind all of the following:

- canonical project and project-revision identity;
- exact canonical input payload and SHA-256 hash;
- deterministic calculation input snapshot and version;
- exact five-stage `requires_review` vector;
- ordered warning code/message/reason evidence for every true stage;
- exact `CalculationRun` identities and result hashes;
- exact `SourceBinding` identity and combined source hash;
- exact persisted `SchemeRun` review boolean and the observed current reason
  state, including an empty list when the current integration loses reasons;
- successful/completed status and no partial transaction;
- two independent SQLite runs on fresh database/run roots;
- two independent PostgreSQL runs on fresh database/run roots;
- repeatability and normalized cross-backend parity;
- fresh-session/restart readback of upstream evidence and identity;
- no tracked-file mutation from evidence generation.

For every run, raw evidence must retain the real `CalculationRun` IDs,
`SourceBinding` ID, `SchemeRun` ID, reason `source_id`, result hashes, combined
source hash, and backend identity. Within that run, each reason `source_id`
must resolve to the declared stage's persisted `CalculationRun` and its result
hash/source binding. This is raw identity integrity, not cross-run UUID
equality.

Repeatability and cross-backend comparison use a normalized business
projection containing canonical input hash, the five-stage `requires_review`
vector, ordered warning code/message, stage, source type, stage-result or
semantic source evidence hash, boolean result, and normalized reason ordering.
Runtime IDs are excluded from this projection.

```text
RAW_IDENTITY_PARITY_REQUIRED=NO
RAW_IDENTITY_INTEGRITY_REQUIRED=YES
NORMALIZED_BUSINESS_PARITY_REQUIRED=YES
```

Step A passes only when its upstream production evidence is complete and
normalized parity is proven. It does not require non-empty canonical
`SchemeRun.warning_messages` while that is the confirmed P1 gap.

### STEP B: REVIEW_REASON_PROPAGATION_IMPLEMENTATION

Lane A must carry the exact upstream reason objects through Transaction B,
`SourceBinding`, `SchemeRun`, JSON persistence, fresh-session/restart readback,
and the evaluation `AdapterResult` without changing producer rules. Lane A ends
at a persisted and readable Scheme review authority. It does not implement the
public `SchemeReviewAuthority` query, report-side projection, approval gate,
formal-render gate, or bootstrap composition; those are Lane-B responsibilities
under the separate Lane-B authorization.

```text
LANE_A_REVIEW_REASON_CONTINUITY_END_BOUNDARY=SCHEME_PERSISTENCE_READBACK_AND_EVALUATION
LANE_A_PUBLIC_REPORT_BRIDGE_REQUIRED=NO
LANE_B_REVIEW_BRIDGE_START_BOUNDARY=PERSISTED_SCHEME_REVIEW_AUTHORITY
LANE_B_REVIEW_BRIDGE_END_BOUNDARY=REPORT_APPROVAL_AND_FORMAL_EXPORT_ENFORCEMENT
LANE_B_CONSUMES_LANE_A_AUTHORITY=YES
LANE_B_MAY_REDEFINE_LANE_A_REASON_SEMANTICS=NO
```

A new canonical fixture may be created only after Step A evidence passes:

```text
backend/tests/pilot/data/task011-followup-high-throughput-source.v1.json
FILE_CREATION_BEFORE_SOURCE_EVIDENCE_PASS=FORBIDDEN
```

The fixture content and SHA-256 must be generated from the accepted Step A
source evidence, never from historical memory, a guessed golden, or a
handwritten candidate.

### STEP C: POST_IMPLEMENTATION_ACCEPTANCE

The post-implementation gates are lane-specific and do not make Lane A
responsible for unimplemented Lane-B paths.

#### LANE_A_POST_IMPLEMENTATION_GATE

After Lane A implementation, acceptance covers only the SchemeRun persistence
and evaluation boundary:

```text
review_required=false => review_reasons=[]
review_required=true  => review_reasons contains >= 1 valid source-bound item
```

This Lane-A gate applies to structured reasons in persisted SchemeRun, fresh
readback/restart, and the evaluation adapter. All report-bridge and formal
acceptance surfaces are evaluated only by Lane B.

```text
LANE_A_ACCEPTANCE_MAY_DEPEND_ON_UNIMPLEMENTED_LANE_B=NO
```

#### LANE_B_POST_IMPLEMENTATION_GATE

After Lane A's merged authority is available, Lane B acceptance covers the
public `SchemeReviewAuthority` query, report-source projection, approval
bridge, formal-render bridge, persisted `mark_reviewed` action readback, and
multilingual formal acceptance.

```text
LANE_B_REQUIRES_LANE_A_MERGED_AUTHORITY=YES
```

#### P1_COMPLETE_CHAIN_GATE

The separately authorized controlled acceptance validates the complete chain:
`CalculationRun -> SchemeRun -> public query -> report -> approval -> formal
artifacts`. No Lane-A implementation PR is required to prove Lane-B behavior
before Lane B exists.

```text
SOURCE_DEFINITION_GATE_FROZEN=YES
POST_IMPLEMENTATION_REASON_CONTINUITY_GATE_FROZEN=YES
```

Until this package exists and is independently verified:

```text
HIGH_THROUGHPUT_REAL_PRODUCTION_SIGNAL_CONFIRMED=YES
HIGH_THROUGHPUT_EXACT_SOURCE_DEFINED=NO
HIGH_THROUGHPUT_SOURCE_EVIDENCE_GATE_REQUIRED=YES
IMPLEMENTATION_READY=NO
```

The Step A evidence package must be attached to Issue #72 before Lane A
implementation is considered ready. This amendment round does not create the
fixture or execute Step A.

## 7. Formal export eligibility

Current formal export authority is in
`backend/src/cold_storage/modules/reports/application/render_service.py`.
The existing renderer supports `RenderMode.FORMAL`,
`ExportFormat.DOCX/PDF`, and `ReportLocale.ZH_CN/EN_US`. Formal mode
currently requires:

- report status `approved` or `archived`;
- all approval fields present;
- requested revision ID equals `approved_revision_id`;
- requested content hash equals `approved_content_hash`;
- requested revision is the current latest revision;
- no blocking quality finding;
- an approval snapshot is written into the render manifest.

P1 freezes the following fail-closed extension of that existing authority:

```text
review_required=true AND approval is absent/invalid/stale
    => formal DOCX/PDF export fails
```

There is no silent draft fallback and a draft artifact cannot be labelled
formal. An approval for a different project revision, calculation result,
source binding, report revision, or content hash is invalid. A new report
revision clears approval and requires the lifecycle again.

The formal gate must continue to use service state and persisted identity; it
must not trust a frontend flag, an LLM statement, or an artifact filename.

### Scheme-review to report-approval bridge

The current-main audit found that `SchemeQueryPort` exposes scheme results but
not `requires_review`; `RealReportDataProvider` does not carry scheme review
state/reasons into its report projection; and `ReportService`/
`ReportRenderService` currently validate report approval and quality findings
without consuming SchemeRun review authority. Therefore a report-side bridge
is required for P1. It is not safe to describe Lane B as acceptance-only while
leaving this production bypass intact.

P1 freezes the following minimum architecture:

1. `SchemeQueryPort` exposes a typed, read-only `SchemeReviewAuthority`
   snapshot containing the authoritative SchemeRun identity, project/version
   identity, `requires_review`, ordered structured reasons, combined/source
   hash, and the persisted result identity. It is a public application query
   boundary, not a Scheme ORM dependency.
2. `RealReportDataProvider` maps that snapshot into the report-side source
   projection. `ReportAssembler` preserves the review snapshot and its source
   reference in the report revision/content lineage.
3. `ReportService` validates the latest exact SchemeRun review snapshot before
   `approve`, and requires a trusted-operator `mark_reviewed` action when the
   snapshot is review-required. `ReportRenderService` revalidates that the
   approved revision still carries the same valid review snapshot before
   formal DOCX/PDF export.
4. Reports must not import Scheme ORM/models or open a Scheme session directly.
   No routes-only check and no frontend-only flag is sufficient. The existing
   report status machine, approval snapshot, quality blocker rules, and render
   mechanics remain unchanged except for this application-boundary gate.
5. A missing, stale, mismatched, or ambiguous review snapshot fails closed;
   it cannot be converted into a draft export or hidden warning.

```text
REPORT_REVIEW_BRIDGE_MODE=MINIMAL_APPLICATION_ENFORCEMENT
LANE_B_REPORT_CORE_CHANGE_REQUIRED=YES
```

This is the selected architecture for P1; an acceptance-only alternative is
not simultaneously retained as an unresolved option.

### Persisted review-action authority

The current main persists `ReportReviewActionRecord` and exposes
`save_review_action`, but the application/repository boundary has no
authoritative read path yet. P1 must add the smallest read-port method in the
existing report application repository contract and implement it in the SQL
repository. A fresh session must be able to query the persisted action; report
status fields, `approved_by`, frontend state, request memory, or a client
claim are not substitutes.

For a review-required SchemeRun, formal authority requires a persisted action
whose exact values include:

- `report_id` equal to the report being approved/rendered;
- `report_revision_id` equal to the current approved report revision;
- `action=mark_reviewed`;
- a non-empty actor supplied by the trusted operator seam;
- persisted `created_at` and a valid existing lifecycle `from_status` /
  `to_status` transition.

The action's revision identity is chained through the existing report
revision source references and canonical content hash to the exact SchemeRun,
SourceBinding, and scheme-review authority hash. This is the minimum proof of
which frozen review snapshot was acted on; no new database column is
authorized. A `mark_reviewed` action for another revision, a missing action,
an ambiguous readback, or a direct/manual `report.status=approved` mutation
fails closed. The implementation must preserve the existing report state
machine and append-only action history.

```text
REPORT_REVIEW_AUTHORITY_SOURCE=PERSISTED_REPORT_REVIEW_ACTION
REPORT_REVIEW_ACTION_READBACK_REQUIRED=YES
MARK_REVIEWED_ACTION_READBACK_REQUIRED=YES
REPORT_STATUS_ALONE_SUFFICIENT_FOR_REVIEW_PROOF=NO
REPORT_REVIEW_ACTION_MIGRATION_REQUIRED=NO
```

## 8. Multilingual formal acceptance

The acceptance target is exactly four artifacts for one approved revision:

| Locale | DOCX | PDF |
| --- | --- | --- |
| `zh-CN` | required | required |
| `en-US` | required | required |

All four artifacts must share the same canonical content hash, report ID,
project-version identity, report revision number, approval snapshot, and
source references. Locale-specific template/catalog hashes and file hashes
must be recorded independently.

Current evidence is partial, not closed:

- `backend/tests/test_reports/test_real_approve_to_formal.py` proves real
  approved `zh-CN` formal DOCX/PDF paths and approval-manifest persistence;
- `backend/tests/test_reports/test_real_storage_e2e.py` and
  `backend/tests/test_reports/test_scheme_provenance_golden_e2e.py` exercise
  four locale/format render combinations, but as draft/golden render coverage;
- the TASK-011 pilot runbook remains draft-mode and explicitly excludes formal
  mode.

The P1 controlled acceptance must therefore prove approved formal `zh-CN`
and `en-US` DOCX/PDF, download integrity, semantic parity, and fresh-session
readback. It must not claim that current draft-only pilot evidence is formal
acceptance.

## 9. Report lineage and persistence

The existing report model and render manifest provide the following lineage
anchors and must be preserved:

- project ID;
- project-version ID and revision number;
- calculation/scheme result IDs and persisted content hashes;
- `ReportSourceReference` type, source ID, source revision, result ID, and
  content hash;
- report revision ID and canonical content hash;
- approval revision ID, approval content hash, actor, and timestamp;
- artifact ID, report/revision IDs, file SHA-256, template/version, locale,
  translation catalog hashes, and render manifest.

The real data provider reads persisted project, calculation, and completed
scheme results. The assembler maps persisted values and source references; it
does not recalculate engineering values. A formal artifact must be traceable
through this chain after a fresh process/session restart. No new lineage field
is authorized unless a gap is demonstrated against these existing anchors.

The scheme-review snapshot is part of this existing source lineage for P1. It
must be carried through public query/provider/application boundaries rather
than by a cross-module ORM shortcut. Its content hash and exact SchemeRun /
SourceBinding identity must be included in the report revision's source
references or equivalent existing approval snapshot fields.

## 10. Concurrency and idempotency boundary

P1 must preserve the current report guarantees:

- duplicate create/generate/render requests with the same idempotency key and
  fingerprint converge on one result;
- a different payload under an existing key is a conflict;
- concurrent render callers wait for the completed artifact or receive a
  deterministic timeout/failure;
- claim token/version, report ID, and revision number are checked;
- stale claims and failed render cleanup remain recoverable;
- storage writes are temporary-file plus atomic-finalization operations;
- a completed artifact is revalidated against the database record and file
  hash;
- retries do not create a second formal artifact for the same approved
  revision/key;
- concurrency conflicts never bypass review or approval.

The current authorities are `ReportRenderService`,
`DatabaseIdempotencyWaiter`, `ReportArtifactStorage`, and the report
repository idempotency/CAS paths. Review closure must add regression coverage
around these guarantees rather than replace them.

## 11. API, operator, and frontend boundary

The backend API already exposes report CRUD, revision, review action, render,
export-list, artifact-detail, and download routes. P1 implementation may make
the review reason and approval snapshot explicit in responses, but it may not
add an autonomous approval endpoint or let the client manufacture approval
identity.

The P1 approval actor is frozen as a controlled trusted-operator seam:

- controlled acceptance injects a non-empty, deterministic operator actor from
  a trusted test/control dependency;
- `approved_by` may not be supplied by HTTP body, query parameter, header,
  client JavaScript, model output, calculator output, or a background retry;
- the actor is recorded in the existing report review/approval audit fields;
- the current API literal `system` is not evidence of a human identity and may
  not be used as the controlled-acceptance operator without the trusted seam.

```text
TRUSTED_OPERATOR_AUTHORITY_FROZEN=YES
PRODUCTION_AUTH_INTEGRATION_REQUIRED_BY_P1=NO
```

P1 proves the trusted operator boundary and explicitly defers full
production-authentication/RBAC integration to a later version. This is not
autonomous AI approval.

The frontend currently provides report list, revision selection, draft/formal
mode selection, locale/format selection, render, export listing, and download.
It does not provide review action controls or a human approval workflow. The
P1 uses the backend trusted-operator surface as the only authorized reviewer
and does not authorize frontend production changes. The frontend must not
present formal export as available merely because the user chose `formal` in a
dropdown.

## 12. Exact future implementation allowlist

This is the maximum path allowlist for a future P1 implementation. The
contract-freeze PR itself changes only this document.

### Lane-specific allowlist authority

`P1_MAXIMUM_UNION_ALLOWLIST` is an audit-only mathematical union. It is not a
write authority. Later implementation authorizations must bind to the
lane-specific lists below.

```text
P1_MAXIMUM_UNION_ALLOWLIST_IS_WRITE_AUTHORITY=NO
LANE_SPECIFIC_ALLOWLIST_IS_WRITE_AUTHORITY=YES
LANE_A_ALLOWLIST_FROZEN=YES
LANE_B_ALLOWLIST_FROZEN=YES
CONTROLLED_ACCEPTANCE_ALLOWLIST_FROZEN=YES
```

### LANE_A_PRODUCTION_CODE_ALLOWLIST

Lane A is limited to high-throughput review-reason continuity from verified
CalculationRun evidence through SchemeRun persistence/readback and evaluation.
It does not modify report approval or formal rendering.

```text
backend/src/cold_storage/modules/schemes/domain/models.py
backend/src/cold_storage/modules/schemes/application/production_ports.py
backend/src/cold_storage/modules/schemes/application/source_binding_verifier.py
backend/src/cold_storage/modules/schemes/application/production_service.py
backend/src/cold_storage/modules/schemes/infrastructure/production_repository.py
backend/src/cold_storage/modules/schemes/infrastructure/production_read_ports.py
backend/src/cold_storage/modules/schemes/infrastructure/repository.py
backend/src/cold_storage/evaluation/adapter.py
```

This exact set covers the current-main typed domain/read model, verified source
mapping, Transaction-B SchemeRun write path, production/restart readback,
legacy repository lossless JSON projection, and evaluation readback. It
explicitly excludes `bootstrap/app.py`, all reports paths, frontend, workflow,
and migration.

### LANE_A_TEST_ALLOWLIST

```text
backend/tests/unit/test_schemes_domain.py
backend/tests/unit/test_schemes_service.py
backend/tests/unit/test_source_binding_verifier_strict.py
backend/tests/integration/test_production_scheme_sqlite.py
backend/tests/integration/test_production_scheme_postgresql.py
backend/tests/evaluation/test_path_a_adapter.py
backend/tests/architecture/test_schemes_production_boundaries.py
```

### LANE_B_PRODUCTION_CODE_ALLOWLIST

Lane B is limited to the formal-report review bridge and multilingual formal
acceptance. It consumes Lane-A authority through public boundaries; it does
not modify calculators, producer `requires_review`, scoring, coefficients, or
Lane-A reason semantics.

```text
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/modules/schemes/application/query.py
backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py
backend/src/cold_storage/modules/reports/infrastructure/repository.py
backend/src/cold_storage/modules/reports/application/assembler.py
backend/src/cold_storage/modules/reports/application/service.py
backend/src/cold_storage/modules/reports/application/render_service.py
backend/src/cold_storage/modules/reports/domain/schema.py
```

`bootstrap/app.py` is composition-only: it may inject the public
`SchemeQueryPort`/`SchemeReviewAuthority`, report services, and trusted
operator seam. It may not contain review business logic, access Scheme ORM,
decide review/approval, or implement the report state machine.

```text
BOOTSTRAP_APP_ROLE=COMPOSITION_ONLY
REPORT_REVIEW_BUSINESS_LOGIC_IN_BOOTSTRAP=FORBIDDEN
SCHEME_ORM_ACCESS_FROM_REPORT_COMPOSITION=FORBIDDEN
```

### LANE_B_TEST_ALLOWLIST

```text
backend/tests/unit/test_real_report_data_provider.py
backend/tests/unit/test_reports_api.py
backend/tests/unit/test_reports_boundaries.py
backend/tests/unit/test_reports_service.py
backend/tests/unit/test_reports_rendering.py
backend/tests/architecture/test_architecture_boundaries.py
backend/tests/test_reports/test_approval_and_artifact.py
backend/tests/test_reports/test_real_approve_to_formal.py
backend/tests/test_reports/test_real_production_e2e.py
backend/tests/test_reports/test_real_storage_e2e.py
backend/tests/test_reports/test_scheme_provenance_golden_e2e.py
backend/tests/test_reports/test_p0_approval_snapshot_and_uow.py
backend/tests/test_reports/test_localization.py
backend/tests/test_reports/test_waiter_concurrent.py
backend/tests/test_reports/test_concurrent_activation.py
backend/tests/test_reports/test_idempotency_failure_states.py
backend/tests/test_reports/test_storage_recovery_and_atomic.py
```

```text
LANE_B_REPORTS_API_TEST_CORRECTIVE_SCOPE=TEST_ONLY
PRODUCTION_SCOPE_EXPANSION=NO
FAIL_CLOSED_SEMANTICS_WEAKENING=NO
```

### P1_CONTROLLED_ACCEPTANCE_CODE_ALLOWLIST

```text
backend/src/cold_storage/evaluation/followup_acceptance.py
```

### P1_CONTROLLED_ACCEPTANCE_TEST_ALLOWLIST

```text
backend/tests/pilot/run_task011_followup_acceptance.py
backend/tests/pilot/test_task011_followup_acceptance.py
backend/tests/pilot/data/task011-followup-high-throughput-source.v1.json
```

The source JSON may be created only after the separately authorized
source-definition evidence round binds its exact content and SHA-256. No
historical TASK-011 golden or draft-pilot manifest may be rewritten.

### P1_SHARED_PATH_ALLOWLIST

```text
P1_SHARED_PATH_ALLOWLIST=[]
```

No current path must be shared by Lane A and Lane B. If a later audit proves a
shared path unavoidable, it requires a further contract amendment and an
explicit lane reference.

```text
SHARED_PATH_DOES_NOT_AUTO_AUTHORIZE_WRITE=YES
CURRENT_LANE_MUST_EXPLICITLY_REFERENCE_SHARED_PATH=YES
```

### P1_MAXIMUM_UNION_ALLOWLIST

The existing combined list immediately below is retained only as the audit
reference for the mathematical union of the lane-specific and controlled
acceptance production paths. It is not a write authority.

```text
P1_MAXIMUM_UNION_ALLOWLIST_IS_WRITE_AUTHORITY=NO
```

### P1_MAXIMUM_UNION_PRODUCTION_PATHS

```text
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/modules/schemes/domain/models.py
backend/src/cold_storage/modules/schemes/application/production_ports.py
backend/src/cold_storage/modules/schemes/application/source_binding_verifier.py
backend/src/cold_storage/modules/schemes/application/query.py
backend/src/cold_storage/modules/schemes/application/production_service.py
backend/src/cold_storage/modules/schemes/infrastructure/production_repository.py
backend/src/cold_storage/modules/schemes/infrastructure/production_read_ports.py
backend/src/cold_storage/modules/schemes/infrastructure/repository.py
backend/src/cold_storage/evaluation/adapter.py
backend/src/cold_storage/evaluation/followup_acceptance.py
backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py
backend/src/cold_storage/modules/reports/infrastructure/repository.py
backend/src/cold_storage/modules/reports/application/assembler.py
backend/src/cold_storage/modules/reports/application/service.py
backend/src/cold_storage/modules/reports/application/render_service.py
backend/src/cold_storage/modules/reports/domain/schema.py
```

The union contains the structured reason projection, lossless JSON
persistence/readback, public Scheme query exposure, report provider/assembler
lineage, persisted review-action readback, report application
approval/formal enforcement, and controlled pilot paths listed above. The
report status machine and renderer mechanics are not redesigned. No calculator
formula or report producer rule is authorized by this union.

`backend/src/cold_storage/bootstrap/app.py` is allowlisted only as the
production composition root. Its future changes may wire the public
`SchemeQueryPort`/`SchemeReviewAuthority` dependency into
`RealReportDataProvider`, `ReportService`, and `ReportRenderService`, plus the
trusted operator seam when required. It may not contain review business logic,
read Scheme ORM objects directly, decide `requires_review`, decide approval,
or implement the report status machine.

```text
BOOTSTRAP_APP_ROLE=COMPOSITION_ONLY
REPORT_REVIEW_BUSINESS_LOGIC_IN_BOOTSTRAP=FORBIDDEN
SCHEME_ORM_ACCESS_FROM_REPORT_COMPOSITION=FORBIDDEN
```

### P1_MAXIMUM_UNION_TEST_PATHS

```text
backend/tests/unit/test_schemes_domain.py
backend/tests/unit/test_schemes_service.py
backend/tests/unit/test_source_binding_verifier_strict.py
backend/tests/integration/test_production_scheme_sqlite.py
backend/tests/integration/test_production_scheme_postgresql.py
backend/tests/evaluation/test_path_a_adapter.py
backend/tests/architecture/test_schemes_production_boundaries.py
backend/tests/unit/test_real_report_data_provider.py
backend/tests/unit/test_reports_api.py
backend/tests/unit/test_reports_boundaries.py
backend/tests/unit/test_reports_service.py
backend/tests/unit/test_reports_rendering.py
backend/tests/architecture/test_architecture_boundaries.py
backend/tests/test_reports/test_approval_and_artifact.py
backend/tests/test_reports/test_real_approve_to_formal.py
backend/tests/test_reports/test_real_production_e2e.py
backend/tests/test_reports/test_real_storage_e2e.py
backend/tests/test_reports/test_scheme_provenance_golden_e2e.py
backend/tests/test_reports/test_p0_approval_snapshot_and_uow.py
backend/tests/test_reports/test_localization.py
backend/tests/test_reports/test_waiter_concurrent.py
backend/tests/test_reports/test_concurrent_activation.py
backend/tests/test_reports/test_idempotency_failure_states.py
backend/tests/test_reports/test_storage_recovery_and_atomic.py
backend/tests/pilot/test_task011_followup_acceptance.py
backend/tests/pilot/run_task011_followup_acceptance.py
backend/tests/pilot/data/task011-followup-high-throughput-source.v1.json
```

### FRONTEND_ALLOWLIST

```text
FRONTEND_ALLOWLIST=[]
```

P1 uses the backend trusted-operator surface as the reviewer. No frontend
production implementation is required or allowlisted; existing frontend
formal-mode controls must not be treated as approval authority.

### IMPLEMENTATION_DOC_ALLOWLIST

```text
docs/runbooks/V0_3-P1-review-formal-report-acceptance.md
```

The governing contract is a separate authority path, not an ordinary
implementation-document target. This R4 amendment may edit it only because
the current round has explicit contract-amendment authorization; ordinary
Lane-A, Lane-B, or controlled-acceptance implementation authorization does not.

### CONTRACT_AUTHORITY_PATH

```text
docs/tasks/V0_3-P1-review-formal-report-closure-contract.md
```

```text
CONTRACT_AUTHORITY_PATH_IS_IMPLEMENTATION_ALLOWLIST=NO
CONTRACT_DOC_POST_MERGE_READ_ONLY=YES
CONTRACT_DOC_ORDINARY_IMPLEMENTATION_WRITE_AUTHORITY=NO
CONTRACT_DOC_CHANGE_REQUIRES_SEPARATE_AMENDMENT_AUTHORIZATION=YES
```

### WORKFLOW_ALLOWLIST

```text
.github/workflows/v0-3-p1-review-formal-report-acceptance.yml
```

The future workflow is a new V0.3 P1 surface, not a permission to mutate the
historical TASK-011 workflow. It must remain workflow-dispatch-only,
exact-source-bound, controlled-operator-bound, and production-operation-free.
No workflow is modified in this freeze round.

### MIGRATION_ALLOWLIST

```text
MIGRATION_ALLOWLIST=[]
```

The P1 reason projection uses existing JSON persistence and existing report
identity fields. A schema migration would require a new contract round.

Historical TASK-011/TASK-012 documents and workflows are frozen authorities:

```text
HISTORICAL_TASK011_TASK012_AUTHORITY_READ_ONLY=YES
```

They are not future implementation targets unless a later contract explicitly
proves an unavoidable historical factual correction.

## 13. Forbidden paths and semantic changes

The following are forbidden in P1:

```text
backend/src/**/pressure*
backend/src/**/shell_tube*
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/coefficients/**
backend/alembic/versions/**
docker-compose.production.yml
uv.lock
TASK-019 contract files
unrelated OCR/model-gateway/frontend files
V03-P2/**
V03-P3/**
V03-P4/**
```

No P1 change may add an engineering formula, throughput threshold, coefficient
value, scoring algorithm, pressure-drop/shell-and-tube calculation, new
autonomous model route, or autonomous AI approval. No existing TASK-011
golden semantics may be rewritten.

## 14. Required test matrix

### Review signal and reason propagation

1. Real calculator warning -> adapter -> Transaction B -> SourceBinding ->
   SchemeRun -> persisted reason.
2. `review_required=true` with an empty reason list is rejected.
3. No-review input produces `review_required=false` and an empty reason list.
4. Structured reason objects survive domain typing, JSON write/read, and
   fresh-session/restart readback without `str(reason)` conversion.
5. Reason code/message/stage/source ID order and exact deduplication are stable.
6. Each run proves raw `source_id` integrity against the correct
   CalculationRun/result hash/SourceBinding; runtime IDs are not compared
   across independent runs.
7. SQLite and PostgreSQL match on the normalized business projection, while
   raw identity integrity is checked separately.
8. Two independent runs per backend prove repeatability.
9. No autonomous approval path exists.
10. The real production composition test proves the app wiring injects the
    Scheme review authority into both `ReportService` and
    `ReportRenderService`; an isolated service test is insufficient.
11. A persisted `mark_reviewed` action can be read in a fresh session and is
    required for review-required approval/formal export.
12. A manually approved report without that action fails, and an action for a
    different report revision fails.
13. Warnings with `requires_review=false` produce no `ReviewReason`; a true
    stage with a valid source-bound warning produces one; a true stage without
    one fails closed.
14. A composition-boundary guard rejects report imports of Scheme ORM,
    review logic in `bootstrap/app.py`, and routes-only enforcement.

### High-throughput source

1. Exact input and SHA binding.
2. Exact project/revision and calculation-run binding.
3. Exact five-stage review vector and warning evidence.
4. Transaction completion and source-binding hash verification.
5. Two fresh SQLite runs and two fresh PostgreSQL runs.
6. Normalized cross-backend parity and upstream-evidence restart readback;
   raw identity parity is explicitly not required.
7. Missing, mismatched, or synthetic-only source evidence fails closed.

### Formal report

1. Formal export fails before approval.
2. Formal export succeeds after valid approval.
3. A review-required SchemeRun without a valid trusted-operator review action
   cannot be approved or formally rendered, even if report status is manually
   marked approved.
4. Stale revision, approval identity mismatch, content-hash mismatch, scheme
   review snapshot mismatch, and blocker state all fail closed.
5. Approved `zh-CN` DOCX/PDF and `en-US` DOCX/PDF are produced.
6. All four artifacts share canonical source/revision/approval identity and
   have independently verified file hashes.
7. Duplicate and concurrent formal requests converge idempotently.
8. Failed render and retry preserve storage atomicity and do not create a
   false formal artifact.
9. Existing report lifecycle, approval snapshot, waiter, storage-recovery,
   and provenance regressions remain green.
10. The real application composition injects and reads the Scheme review
    authority through public boundaries, and review-action readback is
    authoritative after restart.

## 15. CI and controlled-acceptance contract

An implementation PR must run, at minimum:

- targeted unit tests;
- targeted SQLite integration tests;
- collected PostgreSQL integration tests owned by the relevant shard;
- report lifecycle/formal-render regressions;
- architecture/static boundary tests;
- ruff check;
- format check;
- mypy;
- report boundary and provider tests;
- the existing TASK-011 draft regressions without changing their historical
  authority.

The future controlled acceptance surface is the new V0.3 P1 workflow and
runbook path in the allowlist. It must be dispatch-only, main-only,
exact-source-bound, trusted-operator-bound, and independently verify its
evidence. It must record:

- source SHA and tree SHA;
- exact high-throughput input identity and hash;
- stage review vector and reason objects;
- SourceBinding and SchemeRun identity;
- raw per-run IDs and backend identity plus normalized business projection;
- every lifecycle transition and human actor;
- approval revision/content hash/actor/time;
- four formal artifact IDs, formats, locales, and file hashes;
- fresh restart/reload proof;
- SQLite/PostgreSQL result and repeatability summary;
- safe failure diagnostics without secrets.

No ordinary PR job may be presented as controlled acceptance. No controlled
run may mutate production, registry, release, signing, or deployment state.

## 16. P1 stage order and authorization boundary

The corrected sequence is:

```text
P1_STAGE_0=CONTRACT_FREEZE
P1_STAGE_1=INDEPENDENT_REVIEW
P1_STAGE_2=CONTRACT_CORRECTIVE_AMENDMENT_R1
P1_STAGE_3=R1_CONTRACT_INDEPENDENT_REVIEW
P1_STAGE_4=CONTRACT_CORRECTIVE_AMENDMENT_R2
P1_STAGE_5=R2_CONTRACT_INDEPENDENT_REVIEW
P1_STAGE_6=CONTRACT_CORRECTIVE_AMENDMENT_R3
P1_STAGE_7=FINAL_CONTRACT_INDEPENDENT_REVIEW
P1_STAGE_8=CONTRACT_CORRECTIVE_AMENDMENT_R4
P1_STAGE_9=R4_CONTRACT_INDEPENDENT_REVIEW
P1_STAGE_10=ISSUE72_AUTHORITY_RECONCILIATION_RECORD
P1_STAGE_11=CONTRACT_READY_AUTHORIZATION
P1_STAGE_12=CONTRACT_MERGE_AUTHORIZATION
P1_STAGE_13=CONTRACT_POST_MERGE_VERIFICATION
P1_STAGE_14=HIGH_THROUGHPUT_SOURCE_DEFINITION_EVIDENCE
P1_STAGE_15=LANE_A_IMPLEMENTATION
P1_STAGE_16=LANE_A_INDEPENDENT_REVIEW
P1_STAGE_17=LANE_A_READY_AUTHORIZATION
P1_STAGE_18=LANE_A_MERGE_AUTHORIZATION
P1_STAGE_19=LANE_A_POST_MERGE_VERIFICATION
P1_STAGE_20=LANE_B_IMPLEMENTATION
P1_STAGE_21=LANE_B_INDEPENDENT_REVIEW
P1_STAGE_22=LANE_B_READY_AUTHORIZATION
P1_STAGE_23=LANE_B_MERGE_AUTHORIZATION
P1_STAGE_24=LANE_B_POST_MERGE_VERIFICATION
P1_STAGE_25=CONTROLLED_ACCEPTANCE_IMPLEMENTATION
P1_STAGE_26=POST_MERGE_CONTROLLED_ACCEPTANCE
P1_STAGE_27=P1_CLOSURE
```

No stage authorizes the next stage. In particular, this amendment does not
authorize Step A evidence generation, fixture creation, Lane A/B code, Ready,
Merge, or controlled acceptance. The `CONTROLLED_ACCEPTANCE_IMPLEMENTATION`
stage exists only if a later audit proves a separate workflow/runner
implementation is still required; it is not automatically combined with Lane
B. The contract must be merged into `main` and then verified against the
actual post-merge exact SHA/tree before source-definition evidence can be
authorized.

```text
CONTRACT_MUST_BE_ON_MAIN_BEFORE_SOURCE_EVIDENCE=YES
CONTRACT_READY_GATE_FROZEN=YES
CONTRACT_MERGE_GATE_FROZEN=YES
CONTRACT_POST_MERGE_VERIFICATION_GATE_FROZEN=YES
CONTRACT_REVIEW_PASS_AUTO_READY=NO
READY_AUTO_MERGE=NO
MERGE_AUTO_SOURCE_EVIDENCE=NO
ISSUE72_RECONCILIATION_RECORD_REQUIRED_BEFORE_READY=YES
ISSUE72_RECONCILIATION_AUTO_AUTHORIZES_READY=NO
R4_REVIEW_PASS_AUTO_RECONCILIATION=NO
ISSUE72_RECONCILIATION_REQUIRES_SEPARATE_AUTHORIZATION=YES
```

## 17. Stop conditions and failure handling

Implementation must stop and return `CONTRACT_BLOCKER` if it requires any of:

1. a new engineering formula or throughput threshold;
2. a coefficient value or scoring-rule change;
3. pressure-drop or shell-and-tube redesign;
4. TASK-019 change;
5. report-core redesign beyond the existing lifecycle/renderer authority;
6. autonomous AI approval;
7. synthetic-only high-throughput authority without the evidence gate;
8. a migration or production credential;
9. expansion into V03-P2/P3/P4.

Every required source, review, approval, persistence, or artifact identity must
fail closed on missing, stale, mismatched, or ambiguous evidence. It may not
be converted to a warning to obtain a green CI result.

## 18. Acceptance criteria

P1 is complete only when all are true:

```text
HIGH_THROUGHPUT_EXACT_SOURCE_EVIDENCE=PASS
SOURCE_DEFINITION_GATE=PASS
REVIEW_REASON_PROPAGATION=PASS
REVIEW_REQUIRED_REASON_INVARIANT=PASS
POST_IMPLEMENTATION_REASON_CONTINUITY_GATE=PASS
SQLITE_PERSISTENCE_AND_RESTART=PASS
POSTGRESQL_PERSISTENCE_AND_RESTART=PASS
NORMALIZED_CROSS_BACKEND_PARITY=PASS
RAW_IDENTITY_INTEGRITY=PASS
LIFECYCLE_AND_HUMAN_APPROVAL=PASS
FORMAL_EXPORT_FAIL_CLOSED=PASS
ZH_CN_DOCX=PASS
ZH_CN_PDF=PASS
EN_US_DOCX=PASS
EN_US_PDF=PASS
LINEAGE_AND_HASHES=PASS
CONCURRENCY_AND_IDEMPOTENCY=PASS
NO_AUTONOMOUS_APPROVAL=PASS
NO_FORMULA_OR_COEFFICIENT_CHANGE=PASS
```

The implementation PR must remain Draft until independent review accepts the
evidence. Merge does not authorize controlled acceptance; controlled
acceptance requires a separate exact-source authorization.

## 19. Next-stage boundary

This document freezes the P1 contract only. It does not authorize production
code, test, workflow, frontend, migration, controlled acceptance, Ready, or
Merge changes in this round.

```text
R4_FINDING_01_LANE_SCOPE_ALLOWLIST_CONFLICT_CLOSED=YES
R4_FINDING_02_CONTRACT_SELF_MUTATION_AUTHORITY_CLOSED=YES
R4_FINDING_03_STALE_NEXT_STAGE_MARKER_CLOSED=YES
CURRENT_NEXT_STAGE_MARKER_UNAMBIGUOUS=YES
V03_P1_IMPLEMENTATION_AUTHORIZED=NO
V03_P1_IMPLEMENTATION_STARTED=NO
ISSUE72_RECONCILIATION_RECORD_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NEXT_REQUIRED_STAGE=V03_P1_R4_CONTRACT_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
