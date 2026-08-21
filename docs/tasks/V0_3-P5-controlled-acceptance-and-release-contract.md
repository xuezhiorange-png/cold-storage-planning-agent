# V0.3 P5 Controlled Acceptance and Release Contract

**Status:** Definition freeze R1 — contract only
**Authority:** Issue #108, tracked by Issue #113
**Contract definition source SHA:** `02f4b0e04f4178a2e9c3275a360d5047f0e5b7e2`
**Contract definition source tree SHA:** `0d2112e61c63d1dd4d2ffa1ce7bcaeebb8579cf3`
**Target branch:** `cursor/v03-p5-controlled-acceptance-contract-r1-fdcf`

This document freezes the V0.3 P5 controlled acceptance and release authority.
It does not implement a runner, workflow, GitHub Actions job, tag, GitHub
Release, deployment, or production operation.

## 1. Authority and baseline

- Umbrella issue: #108, "[V0.3] Operational Planning Workflow Baseline".
- Tracking issue: #113, "[V0.3][P5] Controlled Acceptance and Release".
- Repository: `xuezhiorange-png/cold-storage-planning-agent`.
- Audited branch: `main`.
- Audited source SHA: `02f4b0e04f4178a2e9c3275a360d5047f0e5b7e2`.
- Audited tree SHA: `0d2112e61c63d1dd4d2ffa1ce7bcaeebb8579cf3`.

The source SHA and tree SHA above are the authority for this contract round.
A later implementation or controlled-acceptance run must revalidate its own
exact base and must not silently reuse this identity after `main` changes.

### 1.1 Upstream contract authorities

P5 consumes frozen boundaries from upstream packages. It does not redefine them.

| Package | Contract path | P5 role |
| --- | --- | --- |
| P1 | `docs/tasks/V0_3-P1-review-formal-report-closure-contract.md` | review reason, lifecycle, formal export, multilingual formal artifacts |
| P1 runbook | `docs/runbooks/V0_3-P1-review-formal-report-acceptance.md` | existing P1 controlled-acceptance surface; read-only authority |
| P2 | `docs/tasks/V0_3-P2-production-agent-gateway-contract.md` Section 27 | current provider/gateway state; live acceptance is separate |
| P3 | `docs/tasks/V0_3-P3-ocr-knowledge-provenance-contract.md` | page-level OCR/knowledge provenance consumer boundary |
| P4 | `docs/tasks/V0_3-P4-guided-end-to-end-workbench-contract.md` (PR #137) | workflow aggregation and frontend consumer boundary only |

P5 must not modify any upstream contract file, the P1 acceptance runbook, the
P1 acceptance workflow, or any file owned by open PR #137 or PR #139.

### 1.2 Explicitly excluded from V0.3 mainline

The following remain outside V0.3 P5 scope and must not be folded into this
contract as mainline requirements:

```text
TASK019_MAINLINE=NO
ISSUE17_MAINLINE=NO
EXPIRED_ISSUE11_MAINLINE=NO
EXPIRED_ISSUE13_MAINLINE=NO
HISTORICAL_TASK011_TASK012_AUTHORITY_READ_ONLY=YES
```

## 2. Scope decision

P5 is the umbrella controlled-acceptance and release-evidence package for V0.3.
It proves, under separately authorized controlled conditions, that the complete
planning workflow can be completed with auditable evidence and without treating
test success as production-deployment authority.

P5 freezes:

1. three end-to-end acceptance scenarios;
2. cross-cutting persistence, parity, lineage, multilingual, and evidence
   requirements;
3. failure diagnostics and post-run cleanup rules;
4. release-evidence assembly criteria;
5. exact conditions for a later annotated `v0.3.0` tag and GitHub Release.

This contract round adds one documentation file only. It does not authorize
implementation, controlled acceptance execution, tag creation, release
publication, deployment, or production operation.

## 3. Hard boundaries

The following boundaries are frozen and must appear in every later P5
authorization record:

```text
CONTROLLED_ACCEPTANCE_PASS_IMPLIES_PRODUCTION_DEPLOYMENT=NO
MODEL_IS_ENGINEERING_CALCULATION_AUTHORITY=NO
FORMULA_CHANGE_AUTHORIZED=NO
COEFFICIENT_CHANGE_AUTHORIZED=NO
SCHEME_SCORING_CHANGE_AUTHORIZED=NO
P5_EXECUTES_CONTROLLED_ACCEPTANCE_NOW=NO
P5_CREATES_TAG_NOW=NO
P5_CREATES_GITHUB_RELEASE_NOW=NO
P5_IMPLEMENTATION_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_AUTHORIZED=NO
V0_3_TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
REAL_PRODUCTION_OPERATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Additional frozen boundaries:

1. **Controlled acceptance pass ≠ production deployment.** Passing P5 evidence
   proves workflow closure under controlled conditions. It does not authorize
   promotion, registry push, signing, attestation, database migration in a
   production environment, rollback, backup/restore, or real model-backed
   production launch.

2. **The model is never an engineering calculation authority.** Agent output may
   orchestrate, clarify, retrieve, and explain. Deterministic calculators,
   coefficient registries, scheme scoring, review flags, and report lifecycle
   remain authoritative.

3. **No formula, coefficient, or scheme-scoring change.** P5 acceptance must
   run against existing deterministic authorities. A controlled run may not
   change engineering semantics to obtain green evidence.

4. **P5 does not authorize execution in this round.** This document freezes the
   contract only. Runner, workflow, evidence bundle, tag, and release work
   require separate later authorizations.

5. **P4 implementation must exist before P5 may claim executability.** While PR
   #137 remains unmerged and P4 implementation is absent from `main`, P5 must
   be described as a planning contract only. P5 may not claim that V0.3
   controlled acceptance is currently runnable.

6. **Scenario C depends on P3 page-level provenance.** Knowledge-backed portions
   of Scenario C require the frozen P3 page-evidence producer boundary to be
   implemented and merged. OCR detection-only or partial-publication states are
   not sufficient provenance evidence.

7. **P2 live real-provider acceptance is not a P4/P5 mainline gate.** P2
   Section 27 records `CONTROLLED_REAL_PROVIDER_ACCEPTANCE_EXECUTED=NO`. P5
   Scenario C may use the existing fake/mocked Agent gateway path in controlled
   acceptance. Live MiMo acceptance remains a separately authorized P2 surface
   and must not block P5 mainline closure when Agent assistance is optional.

8. **P1 controlled acceptance remains a separate historical surface.** P5 may
   consume P1 evidence concepts but must not modify
   `.github/workflows/v0-3-p1-review-formal-report-acceptance.yml` or the P1
   pilot runner in this round.

## 4. Dependency matrix

### 4.1 Package maturity vocabulary

Every dependency statement uses three distinct concepts:

- `AVAILABLE_INTERFACE`: a path or API that exists and may be consumed;
- `FROZEN_INTERFACE`: the semantic boundary P5 may rely on without inventing
  producer semantics;
- `PENDING_INTERFACE`: implementation, merge, or acceptance state that P5 must
  not assume complete.

An available route is not automatically an available authority.

### 4.2 Upstream readiness at contract definition base

```text
P1_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_ON_MAIN=PARTIAL_TO_BE_REVALIDATED_AT_EXECUTION
P1_CONTROLLED_ACCEPTANCE_SURFACE_EXISTS=YES
P1_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED_BY_P5=NO

P2_CONTRACT_FROZEN=YES
P2_IMPLEMENTATION_COMPLETE=YES
P2_LIVE_PROVIDER_ACCEPTANCE_COMPLETE=NO
P2_LIVE_PROVIDER_ACCEPTANCE_REQUIRED_FOR_P5_MAINLINE=NO

P3_CONTRACT_FROZEN=YES
P3_PAGE_EVIDENCE_IMPLEMENTATION_COMPLETE=NO
P3_PAGE_EVIDENCE_REQUIRED_FOR_SCENARIO_C=YES

P4_CONTRACT_FROZEN_IN_DRAFT_PR137=YES
P4_IMPLEMENTATION_ON_MAIN=NO
P4_REQUIRED_BEFORE_P5_EXECUTABLE=YES

P5_EXECUTABLE_WHILE_P4_UNMERGED=NO
P5_EXECUTABLE_WHILE_P3_SCENARIO_C_PRODUCER_PENDING=NO_FOR_SCENARIO_C
```

### 4.3 Dependency order for future execution

Issue #108 dependency order remains authoritative:

```text
V03-P1 -> V03-P4 -> V03-P5
V03-P2 -> V03-P4
V03-P3 -> V03-P4
```

Future P5 controlled acceptance therefore requires, at minimum:

1. merged P1 review/formal-report closure needed for Scenarios A and B;
2. merged P4 guided workbench aggregation/consumer implementation needed for
   umbrella executability claims;
3. merged P3 page-evidence implementation needed for Scenario C knowledge
   portions;
4. separately authorized P5 runner/workflow implementation;
5. separately authorized controlled acceptance execution;
6. separately authorized release/tag publication.

No step above authorizes the next.

## 5. Frozen E2E scenarios

P5 freezes exactly three controlled acceptance scenarios. Each scenario defines
an entry condition, required mainline path, evidence minimum, acceptance entry
surface, and explicit non-goals.

### 5.1 Scenario A — Normal mainline to formal report

#### Entry condition

A governed project/version input produces a completed deterministic calculation
and scheme path with `review_required=false` for the selected formal-report
goal. No review blocker is present on the authoritative scheme/report lineage.

#### Required mainline path

```text
PROJECT_INPUT
  -> INPUT_COMPLETENESS
  -> DETERMINISTIC_CALCULATION
  -> SCHEME_COMPARISON
  -> APPROVAL
  -> FORMAL_REPORT
```

#### Acceptance entry surface

Future controlled acceptance for Scenario A must enter through a separately
authorized P5 runner/workflow that:

1. binds exact execution source SHA and tree SHA;
2. provisions fresh isolated SQLite and PostgreSQL databases;
3. executes the governed project/version path through persisted production
   services, not demo endpoints;
4. performs trusted-operator approval through the existing report lifecycle;
5. produces four formal artifacts for one approved revision:
   `zh-CN DOCX`, `zh-CN PDF`, `en-US DOCX`, `en-US PDF`;
6. records artifact IDs, locales, formats, template/catalog lineage, and
   independent file SHA-256 values;
7. proves fresh-session/restart readback of project, calculation, scheme,
   source, revision, coefficient, approval, and artifact lineage.

#### Scenario A non-goals

Scenario A does not require:

- Agent assistance or live provider calls;
- OCR or knowledge page-evidence production;
- P4 frontend page navigation or UI automation;
- production deployment;
- GitHub Release or annotated tag creation;
- modification of P1 formulas, coefficients, or scheme scoring rules.

### 5.2 Scenario B — Review-required path with formal export blocked

#### Entry condition

The governed deterministic path produces `review_required=true` with at least
one valid structured P1 `ReviewReason` object bound to an exact
`CalculationRun` source ID. Formal export must be blocked until the required
human review and approval path completes.

#### Required mainline path

```text
PROJECT_INPUT
  -> DETERMINISTIC_CALCULATION
  -> SCHEME_COMPARISON
  -> REVIEW_BLOCKER
  -> visible structured review reason
  -> formal export blocked
  -> trusted-operator mark_reviewed
  -> trusted-operator approve
  -> FORMAL_REPORT
```

#### Acceptance entry surface

Future controlled acceptance for Scenario B must prove all of the following:

1. structured review reasons are visible and source-bound at the scheme/report
   boundary;
2. formal DOCX/PDF export fails closed before valid review/approval;
3. no draft artifact is labelled or presented as formal;
4. a persisted trusted-operator `mark_reviewed` action is required when review
   is required;
5. approval and formal render succeed only after the exact scheme-review
   snapshot and approval identity match;
6. the four multilingual formal artifacts are produced after valid approval;
7. SQLite and PostgreSQL each complete the scenario on fresh isolated
   databases with normalized business parity;
8. restart readback preserves review reason set, review action history,
   approval identity, and artifact lineage.

Scenario B may reuse P1 review/formal-report authority and may incorporate P1
controlled-acceptance concepts, but it must not mutate the existing P1
workflow or claim that P1 Stage26 alone closes V0.3 P5.

#### Scenario B non-goals

Scenario B does not require:

- Agent assistance;
- OCR/knowledge provenance beyond any review reason already produced by
  deterministic calculators;
- live provider acceptance;
- a new review rule, threshold, formula, or coefficient;
- autonomous AI approval;
- production deployment or release publication in the acceptance run itself.

### 5.3 Scenario C — Agent + knowledge assisted explanation without authority transfer

#### Entry condition

A governed project/version uses knowledge-assisted content whose current output
actually depends on an approved or explicitly governed knowledge source, and an
Agent session is used for clarification and tool orchestration. The scenario
must bind to P3 page-level provenance when citing knowledge.

#### Required path

```text
PROJECT_INPUT
  -> AGENT_ASSISTANCE (optional side capability; not a core-workflow blocker when unavailable)
  -> ASK_CLARIFICATION for missing/ambiguous input
  -> knowledge.search with page-level citation/provenance
  -> structured tool invocation (registered tools only)
  -> deterministic calculation via application tools/services
  -> explanation that does not override deterministic results
```

#### Acceptance entry surface

Future controlled acceptance for Scenario C must prove:

1. the Agent asks for clarification rather than inventing missing engineering
   inputs;
2. `knowledge.search` returns structured citations including, when applicable,
   `document_id`, `revision_id`, `content_sha256`, `page_start`, `page_end`,
   `source_locator`, `source_page_evidence_id`, `requires_review`, and review
   status according to the frozen P3 consumer boundary;
3. proposed tools are registered, schema-validated, and confirmation-bound when
   required;
4. deterministic calculation output remains authoritative and is persisted with
   calculator version, inputs, warnings, and review flags;
5. Agent prose does not override numerical results, scheme scoring, review flags,
   or formal eligibility;
6. if Agent assistance is unavailable, the scenario documents
   `AGENT_ASSISTANCE_AVAILABLE=false` and proves the core workflow remains
   completable without Agent authority transfer;
7. SQLite and PostgreSQL parity and restart readback apply to persisted Agent
   session/turn/tool-call records and knowledge lineage used by the scenario;
8. no credential, token, raw provider payload, or sensitive model I/O appears
   in evidence.

#### Scenario C dependency gate

```text
SCENARIO_C_KNOWLEDGE_PROVENANCE_AUTHORITY=P3_PAGE_LEVEL_EVIDENCE_PRODUCER
SCENARIO_C_KNOWLEDGE_PROVENANCE_COMPLETE_WHILE_P3_PAGE_EVIDENCE_PENDING=NO
SCENARIO_C_AGENT_TRANSPORT_FOR_CONTROLLED_ACCEPTANCE=fake_or_mocked_gateway_allowed
SCENARIO_C_LIVE_MIMO_PROVIDER_CALL_REQUIRED=NO
SCENARIO_C_LIVE_PROVIDER_ACCEPTANCE_REQUIRED=NO
```

Scenario C must not pass while P3 page-evidence production remains pending unless
the contract is amended to narrow Scenario C to native-text-only knowledge with
an explicit non-OCR fixture. The default frozen requirement is full page-level
provenance readback for cited knowledge.

#### Scenario C non-goals

Scenario C does not require:

- live MiMo provider acceptance or production Agent enablement;
- cloud OCR or external knowledge upload;
- frontend workbench UI proof;
- P4 workflow aggregate endpoint existence;
- report formal export unless the selected scenario fixture also includes a
  formal-report goal; Scenario C default scope is orchestration plus deterministic
  calculation plus explanation, not a substitute for Scenario A or B formal-artifact proof;
- rewriting OCR producer semantics or creating new Agent authority.

## 6. Cross-cutting acceptance requirements

Every future P5 controlled acceptance run must satisfy the following regardless
of scenario.

### 6.1 Exact source identity

Each evidence bundle must record:

```text
CONTROLLED_EXECUTION_SOURCE_SHA
CONTROLLED_EXECUTION_SOURCE_TREE_SHA
EXECUTION_REF=refs/heads/main
WORKFLOW_DISPATCH_ONLY=YES
PR_OR_FEATURE_BRANCH_EXECUTION=FORBIDDEN
```

Missing execution SHA or tree identity fails closed.

### 6.2 SQLite and PostgreSQL parity

Where persistence applies, the run must include:

1. at least one fresh isolated SQLite database per required run index;
2. at least one fresh isolated PostgreSQL database per required run index;
3. backend identity recorded in evidence;
4. raw per-run ID integrity checked within each run;
5. normalized business projection parity across backends;
6. no requirement for cross-run UUID equality.

```text
RAW_IDENTITY_PARITY_REQUIRED=NO
RAW_IDENTITY_INTEGRITY_REQUIRED=YES
NORMALIZED_CROSS_BACKEND_PARITY_REQUIRED=YES
```

### 6.3 Restart persistence and lineage

After process/session restart, evidence must show unchanged authority for:

- project ID and project-version ID/revision;
- calculation run IDs and result hashes;
- coefficient/source references used by the governed path;
- `SourceBinding` and `SchemeRun` identity;
- structured review reasons when applicable;
- report revision, approval snapshot, and review-action history when applicable;
- knowledge revision/content hash and page-evidence identity when applicable;
- Agent session/turn/tool-call persistence when Scenario C is executed;
- artifact IDs and file hashes when formal artifacts are in scope.

### 6.4 Multilingual formal report acceptance

When a scenario includes formal report proof, the acceptance target remains
exactly four artifacts for one approved revision:

| Locale | DOCX | PDF |
| --- | --- | --- |
| `zh-CN` | required | required |
| `en-US` | required | required |

All four artifacts must share the same canonical report/revision/content/source/
approval identity while retaining independent locale/format/template/catalog
hashes and file hashes.

### 6.5 Artifact and checksum evidence

Evidence must record, at minimum:

- artifact ID;
- report ID and revision ID/number;
- locale and format;
- storage key or equivalent artifact locator;
- file SHA-256;
- template ID/version/content hash;
- translation catalog version/content hash when applicable;
- render manifest or equivalent persisted render lineage;
- independent read-back hash verification from storage.

Duplicate artifact creation for the same approved revision/key must fail closed
or converge idempotently according to existing report authority.

### 6.6 Failure diagnostics

Failure evidence must be machine-readable and safe. At minimum:

```text
CONTROLLED_ACCEPTANCE_FAILED
scenario
backend
run_index
exception_type
first_fail_closed_code
```

When a controlled lifecycle action raises `InvalidStatusTransitionError`, the
evidence must also include:

```text
lifecycle_action
report_status_after_generate_revision
quality_blockers_after_generate_revision
invalid_from_status
invalid_to_status
```

Provider, database, OCR, and Agent failures must preserve frozen error codes or
deterministic validation codes already owned by the relevant package. Failures
must not be downgraded to warnings to obtain green evidence.

Secrets, credentials, tokens, signed URLs, raw provider payloads, and sensitive
model I/O must never appear in evidence.

### 6.7 Post-run cleanup

Controlled acceptance must leave no production side effects:

```text
NO_PRODUCTION_DATABASE_MUTATION=YES
NO_REGISTRY_MUTATION=YES
NO_DEPLOYMENT=YES
NO_GIT_PUSH=YES
NO_TAG_CREATION=YES
NO_RELEASE_PUBLICATION=YES
NO_ISSUE_STATE_MUTATION_BY_RUNNER=YES
EPHEMERAL_DATABASES_ONLY=YES
EVIDENCE_UPLOAD_RETENTION=SHORT_LIVED
CREDENTIALS_IN_EVIDENCE=FORBIDDEN
```

The runner/workflow may upload an evidence bundle artifact. Upload retention is
evidence retention only, not release publication.

## 7. Release evidence assembly

Passing controlled acceptance is necessary but not sufficient for release
publication. A later release-evidence stage must assemble and independently
verify at least:

1. exact merged `main` SHA/tree used for acceptance;
2. scenario A/B/C result summary with backend parity matrix;
3. restart/readback proof for each required lineage anchor;
4. multilingual formal-artifact checksum table when in scope;
5. explicit statement that no formula/coefficient/scheme-scoring change occurred;
6. explicit statement that controlled acceptance pass does not authorize
   production deployment;
7. dependency closure record for P1/P2/P3/P4 merge and post-merge verification;
8. P5 runner/workflow revision identity and allowlist used;
9. operator/authorization record IDs for the controlled run;
10. unresolved blockers list, which must be empty for release-evidence PASS.

Release evidence does not create a tag or GitHub Release by itself.

## 8. Annotated `v0.3.0` tag and GitHub Release authorization

Publication of `v0.3.0` requires separate explicit authorization after P5
controlled acceptance and release evidence both PASS. The following conditions
are frozen.

### 8.1 Preconditions

```text
P1_REQUIRED_INTERFACES_MERGED_AND_VERIFIED=YES
P2_REQUIRED_INTERFACES_MERGED_AND_VERIFIED=YES
P3_REQUIRED_INTERFACES_FOR_SCENARIO_C_MERGED_AND_VERIFIED=YES
P4_REQUIRED_INTERFACES_MERGED_AND_VERIFIED=YES
P5_CONTROLLED_ACCEPTANCE_IMPLEMENTATION_MERGED=YES
P5_CONTROLLED_ACCEPTANCE_EXECUTION_PASS=YES
P5_RELEASE_EVIDENCE_PASS=YES
P5_CONTRACT_INDEPENDENT_REVIEW_PASS=YES
P5_IMPLEMENTATION_INDEPENDENT_REVIEW_PASS=YES
MAIN_EXACT_SHA_TREE_REVERIFIED_AT_RELEASE_GATE=YES
```

### 8.2 Tag rules

```text
TAG_NAME=v0.3.0
TAG_ANNOTATION_REQUIRED=YES
TAG_TARGET=exact merged main commit SHA
TAG_MESSAGE_MUST_INCLUDE=source SHA, tree SHA, acceptance evidence reference, non-deployment disclaimer
TAG_CREATION_BY_CONTROLLED_ACCEPTANCE_RUN=FORBIDDEN
TAG_CREATION_BY_THIS_CONTRACT=FORBIDDEN
```

### 8.3 GitHub Release rules

```text
GITHUB_RELEASE_TAG=v0.3.0
GITHUB_RELEASE_MUST_REFERENCE=exact source SHA/tree and P5 evidence bundle
GITHUB_RELEASE_MAY_CLAIM_PRODUCTION_DEPLOYMENT=NO
GITHUB_RELEASE_MAY_CLAIM_CONSTRUCTION_DRAWINGS=NO
GITHUB_RELEASE_MAYOMIT_NON_DEPLOYMENT_DISCLAIMER=NO
GITHUB_RELEASE_PUBLICATION_BY_ACCEPTANCE_RUN=FORBIDDEN
```

### 8.4 Still forbidden after tag/release authorization record

Even with tag/release authorization, the following remain forbidden unless a
future version-specific authorization explicitly grants them:

```text
PRODUCTION_DEPLOYMENT=NO
REAL_PRODUCTION_DATABASE_MIGRATION=NO
REAL_MODEL_PRODUCTION_ENABLEMENT=NO
REGISTRY_PUSH=NO
SIGNING_ATTESTATION=NO
AUTONOMOUS_AI_APPROVAL=NO
```

## 9. Relationship to existing P1 controlled acceptance

P1 already defines a package-local controlled acceptance surface:

- contract: `docs/tasks/V0_3-P1-review-formal-report-closure-contract.md`
- runbook: `docs/runbooks/V0_3-P1-review-formal-report-acceptance.md`
- workflow: `.github/workflows/v0-3-p1-review-formal-report-acceptance.yml`

P5 respects that surface as historical/package-local authority:

```text
P1_CONTROLLED_ACCEPTANCE_REMAINS_PACKAGE_LOCAL=YES
P5_MAY_NOT_REWRITE_P1_WORKFLOW=YES
P5_MAY_CONSUME_P1_EVIDENCE_CONCEPTS=YES
P1_STAGE26_ALONE_CLOSES_V03_P5=NO
```

Future P5 implementation must introduce a new V0.3 P5 acceptance surface rather
than repurposing the P1 workflow.

## 10. Future implementation allowlist

The following allowlist is frozen for a later separately authorized P5
implementation round. It is not permission to mutate these paths now.

### 10.1 Production code allowlist

```text
backend/src/cold_storage/evaluation/v03_controlled_acceptance.py
```

If a future audit proves a different exact path is required, implementation
must stop and request a contract amendment rather than silently widening scope.

### 10.2 Test and pilot allowlist

```text
backend/tests/pilot/run_v03_controlled_acceptance.py
backend/tests/pilot/test_v03_controlled_acceptance.py
backend/tests/pilot/data/v03-scenario-a-normal-formal-report.v1.json
backend/tests/pilot/data/v03-scenario-b-review-required-formal-report.v1.json
backend/tests/pilot/data/v03-scenario-c-agent-knowledge-deterministic.v1.json
```

Scenario fixture JSON files may be created only after separately authorized
source-definition evidence binds their exact content and SHA-256.

### 10.3 Runbook allowlist

```text
docs/runbooks/V0_3-P5-controlled-acceptance-and-release.md
```

### 10.4 Workflow allowlist

```text
.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
```

The future workflow must be `workflow_dispatch` only, `main` only, exact-source-
bound, trusted-operator-bound, and production-operation-free. It must not modify
the P1 workflow.

### 10.5 Contract authority path

```text
docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md
```

```text
CONTRACT_AUTHORITY_PATH_IS_IMPLEMENTATION_ALLOWLIST=NO
CONTRACT_DOC_POST_MERGE_READ_ONLY=YES
CONTRACT_DOC_ORDINARY_IMPLEMENTATION_WRITE_AUTHORITY=NO
CONTRACT_DOC_CHANGE_REQUIRES_SEPARATE_AMENDMENT_AUTHORIZATION=YES
```

### 10.6 Explicitly forbidden implementation targets in P5

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/coefficients/**
backend/src/cold_storage/modules/schemes/**
backend/src/cold_storage/modules/reports/**
backend/src/cold_storage/modules/knowledge/**
backend/src/cold_storage/modules/planning_agent/**
frontend/**
.github/workflows/v0-3-p1-review-formal-report-acceptance.yml
docs/tasks/V0_3-P1-review-formal-report-closure-contract.md
docs/tasks/V0_3-P2-production-agent-gateway-contract.md
docs/tasks/V0_3-P3-ocr-knowledge-provenance-contract.md
docs/tasks/V0_3-P4-guided-end-to-end-workbench-contract.md
backend/alembic/**
TASK-019 contract files
PR137_FILES=FORBIDDEN
PR139_FILES=FORBIDDEN
```

## 11. Required future test and acceptance matrix

A later P5 implementation must prove at least the following before controlled
acceptance execution may be authorized:

| # | Required evidence |
| --- | --- |
| 1 | Scenario A passes on fresh SQLite and PostgreSQL |
| 2 | Scenario B proves visible structured review reason and formal export fail-closed until valid review/approval |
| 3 | Scenario C proves clarification, cited knowledge provenance, structured tools, deterministic calculation, and non-overriding explanation |
| 4 | Scenario C fails closed or remains blocked while P3 page-evidence producer is pending |
| 5 | Restart readback preserves source/revision/coefficient lineage |
| 6 | Restart readback preserves Agent session/tool-call records when Scenario C runs |
| 7 | Multilingual formal artifacts match shared canonical identity with independent file hashes |
| 8 | Normalized cross-backend parity passes |
| 9 | Failure diagnostics emit deterministic codes without secrets |
| 10 | Post-run cleanup leaves no production side effects |
| 11 | Ordinary PR CI is not presented as controlled acceptance |
| 12 | No formula, coefficient, or scheme-scoring change |

## 12. P5 stage order and authorization boundary

```text
P5_STAGE_0=CONTRACT_FREEZE
P5_STAGE_1=CONTRACT_INDEPENDENT_REVIEW
P5_STAGE_2=UPSTREAM_P1_P2_P3_P4_MERGE_AND_POST_MERGE_VERIFICATION
P5_STAGE_3=P5_IMPLEMENTATION
P5_STAGE_4=P5_IMPLEMENTATION_INDEPENDENT_REVIEW
P5_STAGE_5=P5_IMPLEMENTATION_READY_AUTHORIZATION
P5_STAGE_6=P5_IMPLEMENTATION_MERGE_AUTHORIZATION
P5_STAGE_7=P5_IMPLEMENTATION_POST_MERGE_VERIFICATION
P5_STAGE_8=CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZATION
P5_STAGE_9=CONTROLLED_ACCEPTANCE_EXECUTION
P5_STAGE_10=RELEASE_EVIDENCE_ASSEMBLY
P5_STAGE_11=RELEASE_EVIDENCE_INDEPENDENT_REVIEW
P5_STAGE_12=V0_3_0_TAG_AUTHORIZATION
P5_STAGE_13=ANNOTATED_TAG_CREATION
P5_STAGE_14=GITHUB_RELEASE_AUTHORIZATION
P5_STAGE_15=GITHUB_RELEASE_PUBLICATION
P5_STAGE_16=P5_CLOSURE
```

No stage authorizes the next stage.

## 13. Stop conditions and failure handling

Implementation or acceptance execution must stop and return `CONTRACT_BLOCKER`
if it requires any of:

1. a new engineering formula, coefficient, or scheme-scoring rule;
2. autonomous AI approval;
3. live provider acceptance where only fake/mocked Agent transport is authorized;
4. OCR or knowledge producer semantic changes outside frozen P3;
5. P4 workflow producer changes outside frozen P4;
6. modification of the P1 acceptance workflow;
7. mutation of PR #137 or PR #139 files;
8. production deployment, registry push, signing, or release publication inside
   the acceptance run;
9. treating TASK-019, Issue #17, or expired Issue #11/#13 as V0.3 mainline scope;
10. claiming executability while P4 implementation remains unmerged.

Every required source, review, approval, persistence, provenance, or artifact
identity must fail closed on missing, stale, mismatched, or ambiguous evidence.

## 14. Acceptance criteria

V0.3 P5 is complete only when all are true:

```text
P5_CONTRACT_INDEPENDENT_REVIEW=PASS
UPSTREAM_P1_P2_P3_P4_VERIFIED=PASS
P5_IMPLEMENTATION=PASS
P5_IMPLEMENTATION_INDEPENDENT_REVIEW=PASS
SCENARIO_A=PASS
SCENARIO_B=PASS
SCENARIO_C=PASS
SQLITE_PERSISTENCE_AND_RESTART=PASS
POSTGRESQL_PERSISTENCE_AND_RESTART=PASS
NORMALIZED_CROSS_BACKEND_PARITY=PASS
SOURCE_REVISION_COEFFICIENT_LINEAGE=PASS
ZH_CN_DOCX=PASS
ZH_CN_PDF=PASS
EN_US_DOCX=PASS
EN_US_PDF=PASS
ARTIFACT_CHECKSUM_EVIDENCE=PASS
FAILURE_DIAGNOSTICS=PASS
POST_RUN_CLEANUP=PASS
RELEASE_EVIDENCE=PASS
V0_3_0_TAG=PASS
GITHUB_RELEASE=PASS
NO_FORMULA_OR_COEFFICIENT_CHANGE=PASS
NO_PRODUCTION_DEPLOYMENT_CLAIM=PASS
```

Until then, every `PASS` item above is planning vocabulary only.

## 15. Contract closure state

```text
TASK=V03_P5_CONTROLLED_ACCEPTANCE_AND_RELEASE_CONTRACT_DEFINITION_R1
PARENT_ISSUE=108
TRACKING_ISSUE=113
CONTRACT_DEFINITION_SOURCE_SHA=02f4b0e04f4178a2e9c3275a360d5047f0e5b7e2
CONTRACT_DEFINITION_SOURCE_TREE=0d2112e61c63d1dd4d2ffa1ce7bcaeebb8579cf3
CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
CONTRACT_CHANGED_FILE_COUNT=1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md

V03_P5_CONTRACT_FROZEN=YES
V03_P5_IMPLEMENTATION_AUTHORIZED=NO
V03_P5_IMPLEMENTATION_EXECUTED=NO
CONTROLLED_ACCEPTANCE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTED=NO
V0_3_TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
P5_EXECUTABLE_WHILE_P4_UNMERGED=NO
P5_SCENARIO_C_EXECUTABLE_WHILE_P3_PAGE_EVIDENCE_PENDING=NO
P2_LIVE_PROVIDER_ACCEPTANCE_REQUIRED_FOR_P5_MAINLINE=NO

READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
IMPLEMENTATION=NO

NEXT_REQUIRED_STAGE=V03_P5_CONTRACT_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 16. Revision history

| Revision | Date | Scope | State |
| --- | --- | --- | --- |
| R1 | 2026-08-21 | P5 controlled acceptance and release contract; scenarios A/B/C; SQLite/PostgreSQL; restart lineage; multilingual formal artifacts; SHA/tree and checksum evidence; failure diagnostics; cleanup; separate tag/release authorization; hard non-deployment boundary | Draft for independent review |
