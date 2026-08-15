# V0.3 P1 Review and Formal-Report Closure Contract

Status: CONTRACT-FROZEN FOR INDEPENDENT REVIEW

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

## 2. Scope decision

P1 is a closure package for two related lanes:

1. propagate real production review reasons from deterministic calculation
   output through the production scheme result and its consumers;
2. prove the existing report lifecycle and formal render path with a real,
   approved, multilingual acceptance matrix.

`high_throughput_review` is a scenario label for Lane A. It is not a new
throughput threshold, formula, coefficient, score, or review rule. The
implementation cannot start until the exact source evidence gate in section 6
is satisfied.

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
frontend consumer gap; it is not silently treated as complete.

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

### Review invariants

These are acceptance invariants, not new review rules:

```text
review_required=false  => review_reasons=[]
review_required=true   => review_reasons contains >= 1 valid source-bound item
```

The persisted value, fresh readback, API projection, and formal-report
consumer must agree. Any mismatch blocks approval/formal export and reports a
deterministic validation error.

## 6. Exact high-throughput source and evidence gate

`HIGH_THROUGHPUT_EXACT_SOURCE_EVIDENCE` is a required pre-implementation gate.
It is not satisfied by a historical candidate value, a fixture name, or the
string `high_throughput_review`.

The source package must bind all of the following:

- canonical project and project-revision identity;
- exact canonical input payload and SHA-256 hash;
- deterministic calculation input snapshot and version;
- exact five-stage `requires_review` vector;
- ordered warning code/message/reason evidence for every true stage;
- exact `CalculationRun` identities and result hashes;
- exact `SourceBinding` identity and combined source hash;
- exact persisted `SchemeRun` review boolean and reason list;
- successful/completed status and no partial transaction;
- two independent SQLite runs on fresh database/run roots;
- two independent PostgreSQL runs on fresh database/run roots;
- repeatability and cross-backend parity;
- fresh-session/restart readback of reasons, state, and identity;
- no tracked-file mutation from evidence generation.

Until this package exists and is independently verified:

```text
HIGH_THROUGHPUT_REAL_PRODUCTION_SIGNAL_CONFIRMED=YES
HIGH_THROUGHPUT_EXACT_SOURCE_DEFINED=NO
HIGH_THROUGHPUT_SOURCE_EVIDENCE_GATE_REQUIRED=YES
IMPLEMENTATION_READY=NO
```

The evidence package must be attached to Issue #72 before Lane A
implementation is considered ready.

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

## 11. API and frontend boundary

The backend API already exposes report CRUD, revision, review action, render,
export-list, artifact-detail, and download routes. P1 implementation may make
the review reason and approval snapshot explicit in responses, but it may not
add an autonomous approval endpoint or let the client manufacture approval
identity.

The frontend currently provides report list, revision selection, draft/formal
mode selection, locale/format selection, render, export listing, and download.
It does not provide review action controls or a human approval workflow. The
P1 frontend acceptance must either add the minimum explicit human workflow or
document that the backend operator surface is the only authorized reviewer; it
must not present formal export as available merely because the user chose
`formal` in a dropdown.

## 12. Exact future implementation allowlist

This is the maximum path allowlist for a future P1 implementation. The
contract-freeze PR itself changes only this document.

### PRODUCTION_CODE_ALLOWLIST

```text
backend/src/cold_storage/modules/schemes/application/production_ports.py
backend/src/cold_storage/modules/schemes/application/source_binding_verifier.py
backend/src/cold_storage/modules/schemes/application/production_service.py
backend/src/cold_storage/evaluation/adapter.py
backend/src/cold_storage/modules/reports/api/routes.py
backend/src/cold_storage/evaluation/pilot_reports.py
backend/src/cold_storage/evaluation/followup_acceptance.py
```

The permitted roles are reason projection, persisted-source verification,
review API identity, and controlled pilot orchestration only. No calculator
formula or report renderer redesign is implied.

### TEST_ALLOWLIST

```text
backend/tests/unit/test_source_binding_verifier_strict.py
backend/tests/integration/test_production_scheme_sqlite.py
backend/tests/integration/test_production_scheme_postgresql.py
backend/tests/evaluation/test_path_a_adapter.py
backend/tests/architecture/test_phase1_identity_foundation_boundary.py
backend/tests/test_reports/test_real_approve_to_formal.py
backend/tests/test_reports/test_real_storage_e2e.py
backend/tests/test_reports/test_scheme_provenance_golden_e2e.py
backend/tests/test_reports/test_p0_approval_snapshot_and_uow.py
backend/tests/test_reports/test_waiter_concurrent.py
backend/tests/test_reports/test_idempotency_failure_states.py
backend/tests/test_reports/test_storage_recovery_and_atomic.py
backend/tests/pilot/test_task011_followup_acceptance.py
backend/tests/pilot/run_task011_followup_acceptance.py
```

### FRONTEND_ALLOWLIST

```text
frontend/src/api/contracts/reports.ts
frontend/src/features/reports/api/reportsApi.ts
frontend/src/features/reports/composables/useReportExport.ts
frontend/src/features/reports/components/ReportsPage.vue
frontend/src/features/reports/components/ReportExportPanel.vue
frontend/src/features/reports/components/ReportExportPanel.test.ts
frontend/src/features/reports/composables/useReportExport.test.ts
```

Only the report review/status/export consumer is in scope. No unrelated
frontend feature is allowlisted.

### DOC_ALLOWLIST

```text
docs/tasks/V0_3-P1-review-formal-report-closure-contract.md
docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
docs/tasks/TASK-011-pilot-demo-runbook.md
docs/runbooks/TASK-012-slice6-end-to-end-operational-acceptance.md
```

### WORKFLOW_ALLOWLIST

```text
.github/workflows/task011-followup-controlled-acceptance.yml
```

The workflow is not modified in this freeze round. Any future controlled
acceptance must remain workflow-dispatch-only, exact-source-bound, and
production-operation-free.

### MIGRATION_ALLOWLIST

```text
MIGRATION_ALLOWLIST=[]
```

The P1 reason projection uses existing JSON persistence and existing report
identity fields. A schema migration would require a new contract round.

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
4. Reason code/message/stage/source ID order and exact deduplication are stable.
5. Reasons and state survive fresh-session/restart readback.
6. SQLite and PostgreSQL produce identical canonical reason payloads.
7. Two independent runs per backend prove repeatability.
8. No autonomous approval path exists.

### High-throughput source

1. Exact input and SHA binding.
2. Exact project/revision and calculation-run binding.
3. Exact five-stage review vector and warning evidence.
4. Transaction completion and source-binding hash verification.
5. Two fresh SQLite runs and two fresh PostgreSQL runs.
6. Cross-backend parity and restart readback.
7. Missing, mismatched, or synthetic-only source evidence fails closed.

### Formal report

1. Formal export fails before approval.
2. Formal export succeeds after valid approval.
3. Stale revision, approval identity mismatch, content-hash mismatch, and
   blocker state all fail closed.
4. Approved `zh-CN` DOCX/PDF and `en-US` DOCX/PDF are produced.
5. All four artifacts share canonical source/revision/approval identity and
   have independently verified file hashes.
6. Duplicate and concurrent formal requests converge idempotently.
7. Failed render and retry preserve storage atomicity and do not create a
   false formal artifact.
8. Existing report lifecycle, approval snapshot, waiter, storage-recovery,
   and provenance regressions remain green.

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
- frontend report tests if the frontend allowlist is used;
- TASK-011 draft regressions.

The controlled acceptance surface, if added or reused, must be dispatch-only,
main-only, exact-source-bound, and independently verify its evidence. It must
record:

- source SHA and tree SHA;
- exact high-throughput input identity and hash;
- stage review vector and reason objects;
- SourceBinding and SchemeRun identity;
- every lifecycle transition and human actor;
- approval revision/content hash/actor/time;
- four formal artifact IDs, formats, locales, and file hashes;
- fresh restart/reload proof;
- SQLite/PostgreSQL result and repeatability summary;
- safe failure diagnostics without secrets.

No ordinary PR job may be presented as controlled acceptance. No controlled
run may mutate production, registry, release, signing, or deployment state.

## 16. Stop conditions and failure handling

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

## 17. Acceptance criteria

P1 is complete only when all are true:

```text
HIGH_THROUGHPUT_EXACT_SOURCE_EVIDENCE=PASS
REVIEW_REASON_PROPAGATION=PASS
REVIEW_REQUIRED_REASON_INVARIANT=PASS
SQLITE_PERSISTENCE_AND_RESTART=PASS
POSTGRESQL_PERSISTENCE_AND_RESTART=PASS
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

## 18. Next-stage boundary

This document freezes the P1 contract only. It does not authorize production
code, test, workflow, frontend, migration, controlled acceptance, Ready, or
Merge changes in this round.

```text
V03_P1_IMPLEMENTATION_AUTHORIZED=NO
V03_P1_IMPLEMENTATION_STARTED=NO
NEXT_REQUIRED_STAGE=V03_P1_CONTRACT_INDEPENDENT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
