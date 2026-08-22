# V0.3 P4 Guided End-to-End Workbench Contract

## 0. Contract identity and governance

```text
TASK=V03_P4_GUIDED_END_TO_END_WORKBENCH_CONTRACT_DEFINITION_R1
PARENT_VERSION=V0.3
PARENT_ISSUE=108
TRACKING_ISSUE=112
GOVERNANCE_OWNER=V0.3 总控对话
GOVERNANCE_LANE=C

AUTHORIZATION_RECORD_ID=5358011052
CODEX_EXECUTION_DIRECTIVE_RECORD_ID=5358017393

BASE_MAIN_SHA=e40de849eb3cc82d54dfbdab1b3acc459c6f1bbc
BASE_MAIN_TREE=e4876c2760d80974897a126f23e1251da6946c2a
TARGET_BRANCH=codex/v03-p4-guided-workbench-contract-r1
TARGET_FILE=docs/tasks/V0_3-P4-guided-end-to-end-workbench-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
P4_IMPLEMENTATION_AUTHORIZED=NO
P4_IMPLEMENTATION_EXECUTED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This document freezes the P4 contract definition boundary only. It does not
implement a workflow module, API route, frontend state, calculation, OCR
producer, Agent provider, approval authority, or formal-report policy.

The contract is intentionally a consumer/aggregation contract over existing
persisted authorities. It may describe a future read-only endpoint and a
conceptual schema. It does not freeze a final implementation changed-file,
test, migration, dependency, or CI allowlist.

## 1. Objective and non-goals

P4 connects the existing cold-storage planning capabilities into a guided
workflow that can answer:

1. Which project and version is active?
2. Which workflow step is current?
3. Which inputs or persisted results are missing?
4. Why is the workflow blocked?
5. Which result is authoritative, and which result only requires review?
6. Is the current calculation, scheme, knowledge citation, or report revision
   stale?
7. What is the next required user action?
8. Is a draft report allowed?
9. Is a formal report/export allowed under the existing report authority?

P4 is not authorized to:

- create a new engineering domain or formula;
- make the frontend an engineering calculation authority;
- change deterministic calculator semantics;
- create a new approval authority;
- create a new Agent authority;
- create or redefine the P3 OCR producer;
- make OCR output source authority;
- create a new formal-export policy;
- replace the existing P1 report lifecycle or backend revalidation;
- rewrite the current frontend architecture speculatively;
- silently promote demo defaults, fake data, warnings, or route existence to
  authority.

## 2. Existing-system audit at the authorized base

### 2.1 Backend module map

The current backend is a modular monolith with the following relevant modules:

| Module | Existing capability | Existing authority | P4 treatment |
| --- | --- | --- | --- |
| `projects` | project/version CRUD, input snapshots, version transitions, audit events | persisted `Project` and `ProjectVersion` | canonical project/version context |
| `calculations` | deterministic throughput, inventory, precooling, area, cooling load, equipment, power, investment and core orchestration | deterministic calculator result and persisted calculation run | project and expose provenance; never recalculate |
| `coefficients` | coefficient definitions/revisions and validity metadata | governed coefficient registry | expose source/status; do not redefine |
| `schemes` | persisted scheme runs, candidate comparison, feasibility, scoring, review authority | persisted `SchemeRun` and `SchemeReviewAuthority` | project and expose source lineage |
| `reports` | report/revision lifecycle, review actions, approval binding, draft/formal render | existing P1 report lifecycle and render revalidation | project readiness only; existing report authority remains final |
| `knowledge` | document/revision, ingest, chunk, search, review status, citation fields | original artifact identity and approved knowledge revision/citation | consume frozen P3 provenance boundary only |
| `planning_agent` | session, turn, message, tool call, confirmation, actor isolation, idempotency | gateway/session/tool lifecycle plus runtime capability projection | optional assistance consumer only |
| `orchestration` | execution and coefficient context metadata | persisted execution/provenance records | expose lineage; do not create new execution semantics |
| `audit` | append-only audit events | persisted audit records | expose relevant evidence only |

There is currently no dedicated `workflow` aggregation module and no single
backend response that combines these authorities.

### 2.2 Existing backend interfaces

The current backend exposes, among others:

- `/api/v1/projects` and `/api/v1/projects/{project_id}/versions`;
- version input save and validation endpoints;
- project-version calculation endpoints and calculation history;
- `/api/v1/projects/{project_id}/versions/{version}/scheme-runs`;
- scheme run comparison and persisted review authority queries;
- knowledge document, revision, ingest, chunk, review-status, and search APIs;
- report create, generate, review, approve, archive, render, export, and
  download APIs;
- Agent session, message, turn, tool-call, confirmation, and cancellation APIs.

These interfaces are individually available but are not currently coordinated
by a workflow aggregate.

### 2.3 Existing frontend architecture

The frontend is feature-based Vue 3/TypeScript/Vite with Element Plus, Vue
Router and Pinia:

- `App.vue` mounts `AppShell`;
- `AppShell` mounts the Agent panel and the workbench router;
- `WorkbenchLayout` provides the existing workflow navigation;
- existing pages are project input, calculations, schemes, investment, power,
  and reports;
- the planning store currently holds a transient planning request/response;
- the current calculations API calls the demo planning endpoint;
- the current schemes API calls the demo comparison endpoint;
- the current report panel can list revisions and render/download artifacts but
  does not expose the full review/approval/eligibility flow;
- the current Agent composable reports `unavailable` and does not consume the
  backend capability projection.

P4 must extend this architecture rather than replace it.

### 2.4 Current user flow and integration gaps

The current frontend flow is a collection of demo-oriented islands:

1. The user enters inputs in the local project form.
2. The form performs local validation and currently maps demo values,
   including `utilization_factor=0.85` and `reserve_factor=1.05`.
3. The frontend calls `/api/v1/demo/planning-run`.
4. The response is held in transient Pinia state.
5. Calculations, investment, and power pages display that transient response.
6. The schemes page independently calls `/api/v1/demo/scheme-comparison` and
   is not bound to the just-entered project version.
7. The reports page asks for a manually typed project ID and does not create,
   generate, review, approve, or explain a current report revision.
8. The Agent drawer says the Agent is unavailable even though backend Agent
   routes and runtime capability projection exist.
9. There is no project-level knowledge provenance consumer.

The principal integration gaps are:

- no canonical project/version/revision context in the frontend;
- demo endpoints and transient state are not connected to persisted workflow
  authorities;
- no unified `current_step`, `workflow_status`, `step_applicability`,
  `missing_inputs`, `blockers`, or `next_required_actions`;
- no uniform calculation run, result hash, coefficient, formula, or source
  lineage projection;
- no unified calculation/scheme/review/approval projection;
- no stale contract across input, calculation, scheme, knowledge, Agent, and
  report revisions;
- some legacy calculation endpoints do not use the canonical injected project
  service and therefore cannot be treated as a complete workflow authority
  until revalidated in a future implementation scope;
- the scheme contract requires persisted source calculations that the demo
  planning route does not guarantee;
- report formal eligibility is enforced by the reports backend but is not
  surfaced as a separate frontend readiness state;
- current frontend engineering defaults are hidden input migration gaps, not
  P4-authoritative values;
- P3 OCR page-evidence production is merged on main; P4 remains consumer-only.

## 3. Authority and dependency matrix

### 3.1 Authority separation

| Concern | Authority | P4 role |
| --- | --- | --- |
| persisted project/version inputs | project application service and persistence | read/project/explain |
| engineering numbers | deterministic calculator/application service and persisted run | read/project/provenance |
| formulas/coefficient identity | calculation result and coefficient registry | display/provenance |
| scheme feasibility/comparison | persisted `SchemeRun` and `SchemeReviewAuthority` | read/project/explain |
| human review actions | persisted review lifecycle/action records | display/guide |
| knowledge source identity | original artifact and immutable revision/content hash | consume citations |
| OCR evidence | P3 frozen producer/consumer boundary merged on main | consumer only |
| Agent capability | runtime capability/readiness projection | read/guide |
| Agent engineering result | never Agent authority | display caveat only |
| report formal eligibility | existing reports module and frozen P1 lifecycle | project/explain only |
| final formal render/download | existing report backend revalidation | never override |

### 3.2 Interface maturity vocabulary

Every dependency statement in this contract uses three distinct concepts:

- `AVAILABLE_INTERFACE`: an interface or runtime path that can currently be
  consumed, including a guarded or conditional path;
- `FROZEN_INTERFACE`: the semantic boundary that P4 may consume without
  inventing producer semantics;
- `PENDING_INTERFACE`: an implementation, runtime acceptance, or governance
  state that P4 must not assume is available.

An available route is not automatically an available authority. A frozen
consumer boundary is not proof that its producer implementation is complete.

### 3.3 P1 dependency

```text
P1_AVAILABLE_INTERFACE=YES
P1_FROZEN_INTERFACE=YES
P1_P4_USE=report lifecycle, persisted review action, scheme review lineage,
           approval binding, formal-render revalidation
P1_P4_MAY_REDEFINE_AUTHORITY=NO
```

### 3.4 P2 dependency — corrected current state

The P2 state must not be described as “real provider implementation pending”.
The authorized current dependency facts are:

```text
P2_CONTRACT_FROZEN=YES
P2_A_IMPLEMENTED=YES
P2_B_IMPLEMENTED=YES
P2_C_IMPLEMENTED=YES
REAL_PROVIDER_IMPLEMENTED=YES
ACTIVE_PROVIDER=mimo
ACTIVE_MODEL=mimo-v2.5
STRICT_AGENT_COMPOSITION_AVAILABLE=YES
CAPABILITY_READINESS_PROJECTION_AVAILABLE=YES
LIVE_PROVIDER_ACCEPTANCE_COMPLETE=NO
PRODUCTION_ENABLEMENT_AUTHORIZED=NO
ISSUE_110_CLOSURE_COMPLETE=NO
AGENT_ROUTE_EXISTS_DOES_NOT_IMPLY_AGENT_AVAILABLE=YES
P4_AGENT_AVAILABILITY_AUTHORITY=runtime capability/readiness projection
```

Therefore:

- P4 consumes the capability/readiness projection;
- P4 does not infer availability from route registration;
- local/test/fake behavior may be surfaced as environment capability, never as
  silent production fallback;
- `LIVE_PROVIDER_ACCEPTANCE_COMPLETE=NO` and
  `PRODUCTION_ENABLEMENT_AUTHORIZED=NO` remain visible dependency facts;
- Agent assistance remains optional for the core planning workflow.

### 3.5 P3 dependency — consumer-only boundary

```text
P3_CONTRACT_FROZEN_AND_MERGED=YES
P3_IMPLEMENTATION_MERGED_ON_MAIN=YES
P3_IMPLEMENTATION_MERGE_MAIN_SHA=3dc728d897ece0d3163d9aff7a5219a1dcb35332
P3_IMPLEMENTATION_MERGE_MAIN_TREE=b9388021139439e2f94a63a9fb8b0ce3b524899e
P3_IMPLEMENTATION_PR=139
P3_IMPLEMENTATION_CURRENTLY_AUTHORIZED_ON_SEPARATE_B_LANE=NO
P3_OCR_PAGE_EVIDENCE_IMPLEMENTATION_COMPLETE=YES
CURRENT_ALEMBIC_HEAD_INCLUDES=0040_add_knowledge_page_evidence
P4_MAY_CONSUME_FROZEN_P3_CONSUMER_BOUNDARY=YES
P4_MAY_DEFINE_NEW_OCR_PRODUCER_SEMANTICS=NO
P4_MAY_TREAT_OCR_DETECTION_AS_OCR_EVIDENCE=NO
P4_MAY_TREAT_PARTIAL_OCR_AS_COMPLETE_PROVENANCE=NO
```

P3 OCR and knowledge provenance implementation is merged on `main` at
`3dc728d897ece0d3163d9aff7a5219a1dcb35332` (PR #139). At that main tree the
Alembic head includes `0040_add_knowledge_page_evidence` (revision
`0040_add_knowledge_page_evidence`, down revision
`0039_widen_report_export_artifact_mime_type`).

P4 may consume the frozen relationship:

```text
original artifact -> page evidence -> chunk -> retrieval -> Agent/report citation
```

P4 may expose pending or unavailable provenance when required page evidence is
incomplete, failed, unreviewed, or otherwise not a complete governed lineage.
P4 may not add OCR fields, confidence rules, persistence rules,
page-selection rules, or producer status meanings.

## 4. Contract-level workflow model

### 4.1 Mainline and side capabilities

The canonical mainline is:

```text
PROJECT_INPUT
  -> INPUT_COMPLETENESS
  -> DETERMINISTIC_CALCULATION
  -> SCHEME_COMPARISON
  -> REVIEW_BLOCKER
  -> HUMAN_REVIEW
  -> APPROVAL
  -> REPORT_ELIGIBILITY
  -> FORMAL_REPORT
```

The following are side capabilities attached to the project/version context:

```text
AGENT_ASSISTANCE
KNOWLEDGE_PROVENANCE
```

Agent assistance is not a required mainline gate by default. Knowledge
provenance becomes a gate only when the governed current output actually
depends on a knowledge source.

### 4.2 WORKFLOW_STEP

```text
WORKFLOW_STEP=
PROJECT_INPUT
INPUT_COMPLETENESS
DETERMINISTIC_CALCULATION
SCHEME_COMPARISON
REVIEW_BLOCKER
HUMAN_REVIEW
APPROVAL
AGENT_ASSISTANCE
KNOWLEDGE_PROVENANCE
REPORT_ELIGIBILITY
FORMAL_REPORT
```

`current_step` is a backend projection. The frontend must not select the
current step by inspecting which endpoint happened to return data.

### 4.3 WORKFLOW_STATUS

```text
WORKFLOW_STATUS=
NOT_STARTED
IN_PROGRESS
READY
RUNNING
COMPLETED
BLOCKED
REVIEW_REQUIRED
UNDER_REVIEW
APPROVED
STALE
UNAVAILABLE
FAILED
NOT_APPLICABLE
```

The aggregate must distinguish an optional unavailable side capability from a
required mainline blocker.

### 4.4 STEP_APPLICABILITY

```text
STEP_APPLICABILITY=REQUIRED|OPTIONAL|CONDITIONAL|NOT_APPLICABLE
```

Semantics:

| Applicability | Meaning | Blocking behavior |
| --- | --- | --- |
| `REQUIRED` | required for the selected governed workflow goal/output | incomplete or failed state may block |
| `OPTIONAL` | useful assistance that the user may choose to use | unavailable state must not block core workflow |
| `CONDITIONAL` | required only when a declared dependency is used | blocks only when the condition is true |
| `NOT_APPLICABLE` | not relevant to the selected output or current context | must not block |

The aggregate must return, for every step:

- `applicability`;
- `applicability_reason`;
- `status`;
- `blocking`;
- `blockers`;
- `next_actions`.

Default applicability:

```text
PROJECT_INPUT=REQUIRED
INPUT_COMPLETENESS=REQUIRED
DETERMINISTIC_CALCULATION=REQUIRED
SCHEME_COMPARISON=CONDITIONAL
REVIEW_BLOCKER=CONDITIONAL
HUMAN_REVIEW=CONDITIONAL
APPROVAL=CONDITIONAL
AGENT_ASSISTANCE=OPTIONAL
KNOWLEDGE_PROVENANCE=CONDITIONAL
REPORT_ELIGIBILITY=CONDITIONAL
FORMAL_REPORT=CONDITIONAL
```

For a formal-report goal, scheme comparison, review, human review, approval,
report eligibility, and formal report become required according to the existing
P1/report lifecycle authority. For a planning-only preview, formal report may
be `NOT_APPLICABLE`.

The following rules are mandatory:

```text
AGENT_ASSISTANCE_DEFAULT_APPLICABILITY=OPTIONAL
KNOWLEDGE_PROVENANCE_DEFAULT_APPLICABILITY=CONDITIONAL
AGENT_UNAVAILABLE_BLOCKS_CORE_WORKFLOW=NO
KNOWLEDGE_PROVENANCE_BLOCKS_CORE_WORKFLOW=YES_ONLY_IF_CURRENT_GOVERNED_OUTPUT_ACTUALLY_DEPENDS_ON_KNOWLEDGE_SOURCE
OPTIONAL_OR_NOT_APPLICABLE_STEP_MAY_NOT_BECOME_CORE_BLOCKER=YES
```

## 5. Canonical project/version context

Every aggregate must be scoped to an explicit persisted context:

```text
project_id
project_code
project_name
project_version_id
project_version_number
project_version_status
revision_id
revision_number
revision_fingerprint
revision_stale
revision_stale_reasons
```

`revision_id` is the persisted project-version identity. A human-readable
version number is not sufficient for lineage. A revision is fresh only when
the referenced input, calculation, scheme, report, Agent, and knowledge source
identities can be proven to belong to the same governed context.

If freshness cannot be proven, the aggregate must expose that condition as
stale or unproven and must not declare formal eligibility.

## 6. Input, blocker, and action contracts

### 6.1 MISSING_INPUTS

`MISSING_INPUTS` is a structured projection, not a frontend validation string.
Each item contains:

```text
field
label
unit
required
status=missing|invalid|tentative|complete
source
reason
remediation
```

The backend must not silently guess missing engineering parameters. A frontend
default is not authoritative merely because it was placed in the request.

### 6.2 BLOCKER_CODE

The aggregation layer may use the following closed conceptual codes:

```text
INPUT_MISSING
INPUT_INVALID
INPUT_REQUIRES_REVIEW
CALCULATION_MISSING
CALCULATION_FAILED
CALCULATION_STALE
CALCULATION_REQUIRES_REVIEW
COEFFICIENT_UNVERIFIED
SCHEME_MISSING
SCHEME_INFEASIBLE
SCHEME_STALE
SCHEME_REVIEW_REQUIRED
REVIEW_REASONS_UNRESOLVED
HUMAN_REVIEW_PENDING
APPROVAL_PENDING
APPROVAL_STALE
KNOWLEDGE_PROVENANCE_PENDING
KNOWLEDGE_PROVENANCE_UNAVAILABLE
REPORT_MISSING
REPORT_REVISION_STALE
REPORT_QUALITY_BLOCKER
FORMAL_REPORT_NOT_APPROVED
AGENT_UNAVAILABLE
DEPENDENCY_UNAVAILABLE
VERSION_LOCKED
```

`BLOCKER_REASON` contains:

```text
code
message
stage
source_type
source_id
severity
evidence
remediation
```

The aggregation layer may wrap an existing producer reason with projection
metadata. It must not mutate the producer reason itself.

### 6.3 NEXT_REQUIRED_ACTION

`NEXT_REQUIRED_ACTION` is a backend-owned action projection:

```text
action_id
type
target_step
label
reason
required
enabled
blocked_by
preconditions
requires_confirmation
target_route
target_resource
```

The backend returns an ordered list and identifies one `primary_action_id`.
The frontend renders and invokes the returned action; it does not derive a new
priority order from raw endpoint responses.

Recommended priority:

1. complete missing or invalid required inputs;
2. confirm or resolve tentative engineering inputs;
3. run missing deterministic calculations;
4. resolve calculation review/stale blockers;
5. create or refresh the applicable scheme run;
6. resolve scheme review reasons or infeasibility;
7. start human review;
8. complete approval;
9. resolve conditional knowledge provenance;
10. create/regenerate the report revision;
11. complete report review and approval;
12. render/download the formal artifact when the existing report gate allows.

Agent assistance may be returned as an optional action and must not displace a
required blocking action.

## 7. Calculation, scheme, review, approval, and provenance projections

### 7.1 CALCULATION_STATUS

```text
CALCULATION_STATUS=
NOT_RUN
RUNNING
SUCCEEDED
SUCCEEDED_WITH_REVIEW
FAILED
STALE
BLOCKED
UNAVAILABLE
```

### 7.2 CALCULATION_PROVENANCE

Every projected calculation result must identify, when available:

```text
calculation_run_id
project_version_id
calculator_name
calculator_version
orchestration_version
input_snapshot_hash
result_hash
formula_references
coefficient_references
assumptions
warnings
errors
source_references
requires_review
engineering_numeric_authority
created_at
```

The authority rules are:

```text
FRONTEND_ENGINEERING_CALCULATION_AUTHORITY=NO
FRONTEND_HIDDEN_ENGINEERING_DEFAULT_AUTHORITY=NO
BACKEND_DETERMINISTIC_CALCULATOR_AUTHORITY=YES
AGENT_ENGINEERING_CALCULATION_AUTHORITY=NO
```

`engineering_numeric_authority=YES` means the number came from the governed
deterministic calculation path. It does not mean that the number is approved
for a formal report. `requires_review=true`, unverified coefficients, or stale
lineage must remain visible.

### 7.3 SCHEME_STATUS

```text
SCHEME_STATUS=
NOT_RUN
RUNNING
COMPLETED
REVIEW_REQUIRED
BLOCKED
STALE
FAILED
```

The scheme projection contains:

```text
scheme_run_id
project_version_id
source_calculation_run_ids
source_snapshot_hash
content_hash
recommended_scheme_code
feasible
candidate_count
review_reasons
requires_review
```

P4 must consume the persisted scheme comparison and review authority. It must
not score schemes again in the frontend or infer a recommendation from cards.

### 7.4 REVIEW_STATUS and REVIEW_REASONS

Review must be projected by source type:

```text
calculation_review_status
scheme_review_status
project_review_status
report_review_status
aggregate_review_status
```

Allowed aggregate values:

```text
NOT_REQUIRED
REQUIRED
UNDER_REVIEW
REVIEWED
CHANGES_REQUESTED
APPROVAL_PENDING
APPROVED
STALE
BLOCKED
```

The canonical P1 `ReviewReason` remains exactly:

```text
code
message
stage
source_type=calculation_run
source_id
```

The producer's `requires_review` boolean remains the review authority. P4 must
not infer review from arbitrary warning text.

### 7.5 APPROVAL_STATUS

Approval is represented as separate authorities, not one frontend boolean:

```text
project_version_approval_status
report_approval_status
effective_approval_status
approved_revision_id
approved_content_hash
approved_by
approved_at
```

Allowed values:

```text
NOT_REQUESTED
PENDING
APPROVED
CHANGES_REQUESTED
STALE
BLOCKED
```

P4 projects existing approval state. It does not add autonomous approval or
replace persisted human/operator actions.

## 8. Revision and staleness semantics

### 8.1 REVISION_ID and REVISION_STALE

The aggregate must expose:

```text
revision_id
revision_number
revision_fingerprint
revision_stale
revision_freshness=fresh|stale|unproven
revision_stale_reasons
```

`revision_stale=true` or `revision_freshness=unproven` is required when any of
the following is true:

- the current input snapshot differs from the calculation input snapshot;
- a calculation run is from a different project version;
- calculation input/result hashes do not match the persisted lineage;
- scheme source snapshot hash does not match the current calculation set;
- a report revision is not the current report revision;
- report approval fields reference another revision or content hash;
- a cited knowledge revision was superseded, withdrawn, or cannot be proven;
- an Agent session/turn/tool call is bound to an older project version;
- the source binding is missing and freshness cannot be established.

A new input revision invalidates downstream readiness until affected
calculations, schemes, reports, and approvals are regenerated or re-reviewed.

### 8.2 Knowledge provenance availability

The aggregate exposes:

```text
KNOWLEDGE_PROVENANCE_AVAILABLE=true|false
knowledge_provenance_status=NOT_REQUIRED|AVAILABLE|PENDING|INVALID
knowledge_provenance_blockers
knowledge_source_references
```

`AVAILABLE` requires a source-bound document revision, original content hash,
chunk/page/source locator, and the applicable P3 review/provenance conditions.

P3-specific rules:

- original artifacts remain source authority;
- OCR is derived evidence, not source authority;
- OCR-derived content requires human review;
- OCR detection is not OCR evidence;
- partial OCR is not complete provenance;
- P4 does not add or alter the OCR producer contract.

### 8.3 Frontend hidden engineering defaults

The current demo mapping of `0.85` utilization and `1.05` reserve is a
migration gap. It is not a frozen P4 default and must not be presented as
authoritative.

```text
FRONTEND_MAY_SILENTLY_INJECT_UTILIZATION_FACTOR=NO
FRONTEND_MAY_SILENTLY_INJECT_RESERVE_FACTOR=NO
```

Future authoritative engineering input values must originate from exactly one
of:

```text
PERSISTED_PROJECT_INPUT
GOVERNED_BACKEND_DEFAULT
GOVERNED_COEFFICIENT_REFERENCE
EXPLICIT_USER_CONFIRMED_TENTATIVE_INPUT
```

The contract does not authorize the implementation fix for this migration gap;
the future implementation scope must revalidate the input API and frontend
ownership before changing it.

## 9. Agent assistance contract

### 9.1 AGENT_ASSISTANCE_AVAILABLE

The aggregate may return:

```text
AGENT_ASSISTANCE_AVAILABLE=true|false
agent_assistance_status=AVAILABLE|NOT_READY|UNAVAILABLE|NOT_APPLICABLE
agent_capability_state
active_provider=mimo
active_model=mimo-v2.5
strict_composition_available
live_provider_acceptance_complete
production_enablement_authorized
agent_unavailability_reason
```

The authoritative availability source is the runtime capability/readiness
projection. Route existence alone is insufficient.

### 9.2 Optionality and authority

```text
AGENT_ASSISTANCE_DEFAULT_APPLICABILITY=OPTIONAL
AGENT_UNAVAILABLE_BLOCKS_CORE_WORKFLOW=NO
AGENT_ENGINEERING_CALCULATION_AUTHORITY=NO
AGENT_APPROVAL_AUTHORITY=NO
AGENT_FORMAL_REPORT_AUTHORITY=NO
```

Agent sessions, turns, tool calls, confirmations, and citations may be
projected into provenance when used. They do not replace deterministic
calculation runs, human review, or report approval.

If the user chooses Agent assistance and a governed output depends on its
knowledge-backed content, the applicable knowledge provenance condition is
evaluated separately. Agent optionality does not make invalid provenance valid.

## 10. Read-only backend aggregation contract

### 10.1 Conceptual endpoint

P4 may describe the following future endpoint:

```text
GET /api/v1/projects/{project_id}/versions/{version}/workflow
```

The endpoint is read-only. It does not run calculations, mutate inputs, create
scheme runs, change review status, approve reports, or render artifacts.

### 10.2 WorkflowAggregateV1 conceptual schema

The conceptual response is:

```text
WorkflowAggregateV1
  contract_version
  generated_at
  project_context
  current_step
  workflow_status
  workflow_goal
  steps[]
  missing_inputs[]
  blockers[]
  primary_action_id
  next_required_actions[]
  calculations
  schemes
  review
  approval
  revision
  knowledge_provenance
  agent_assistance
  workflow_readiness
  formal_export_eligibility
  authorities[]
```

`steps[]` contains:

```text
step
applicability
applicability_reason
status
blocking
blockers[]
next_actions[]
```

`workflow_readiness` is a P4 projection:

```text
workflow_readiness.status=READY|NOT_READY|BLOCKED|STALE|UNAVAILABLE
workflow_readiness.blockers[]
workflow_readiness.reasons[]
workflow_readiness.next_required_actions[]
```

`formal_export_eligibility` is explicitly not a new P4 authority:

```text
formal_export_eligibility.status=ELIGIBLE|INELIGIBLE|STALE|UNKNOWN
formal_export_eligibility.eligible
formal_export_eligibility.blockers[]
formal_export_eligibility.authority_owner=reports_module_p1_lifecycle
formal_export_eligibility.revalidation_required=YES
```

P4 may project and explain this result. The existing reports backend must
revalidate the authoritative conditions again at render/download time.

### 10.3 Aggregation rules

The aggregation service:

- reads existing application/query services and persisted records;
- projects source IDs, hashes, statuses, review reasons, and timestamps;
- does not duplicate engineering formulas;
- does not create a second report lifecycle;
- does not promote Agent output to engineering authority;
- does not define OCR producer semantics;
- does not convert an unavailable optional step into a core blocker;
- fails closed for unknown or unproven formal lineage.

## 11. Frontend consumer contract

### 11.1 Consumer responsibilities

The frontend may:

- select and display the current project/version context;
- render `WorkflowAggregateV1` statuses and blockers;
- display the backend-selected next action;
- format deterministic results and provenance;
- navigate to existing mutation surfaces;
- show review/approval controls backed by existing APIs;
- show Agent capability and optionality;
- show conditional knowledge provenance requirements;
- disable or explain actions returned as disabled by the backend;
- adapt layout for narrow screens and keyboard/screen-reader use.

The frontend may not:

- calculate authoritative engineering numbers;
- silently inject engineering defaults;
- infer freshness from local timestamps;
- infer review from warning text;
- infer formal eligibility from a project status alone;
- treat an Agent route as available without capability projection;
- treat a draft artifact as a formal report;
- create a second copy of backend state-machine rules.

### 11.2 Existing-page integration direction

P4 should extend the existing pages:

| Existing page | P4 consumer responsibility |
| --- | --- |
| project | persisted project/version context, input completeness, next action |
| calculations | authoritative calculation result and provenance |
| schemes | current-version scheme run, feasibility, review reasons |
| investment/power | deterministic result display and review/stale indicators |
| reports | report revision, review actions, readiness, formal eligibility projection |
| Agent panel | runtime capability, session binding, optional assistance |

No speculative navigation rewrite is part of this contract.

### 11.3 Accessibility and responsiveness

The future consumer must preserve the existing workbench and provide:

- keyboard-operable navigation and action controls;
- visible focus states;
- semantic headings and landmarks;
- status and blocker announcements through accessible live regions where
  appropriate;
- text explanations in addition to color or icon status;
- responsive layouts for narrow desktop/tablet widths without hiding blockers;
- non-truncated source/reason text with accessible expansion;
- loading, stale, unavailable, and failed states that are distinguishable;
- disabled actions with an explanation of the blocking condition;
- tables or equivalent accessible structures for provenance and review reasons.

## 12. Workflow readiness versus formal-export authority

These two concepts must remain separate.

### 12.1 P4 workflow readiness

P4 may calculate a user-facing readiness projection from the existing
authorities. It answers whether the user can continue the guided workflow and
what action is next.

It may report:

```text
READY
NOT_READY
BLOCKED
STALE
UNAVAILABLE
```

### 12.2 Formal-export authority

```text
P4_MAY_CREATE_NEW_FORMAL_EXPORT_POLICY=NO
P4_WORKFLOW_READINESS_PROJECTION_ALLOWED=YES
AUTHORITATIVE_FORMAL_EXPORT_ELIGIBILITY_OWNER=existing reports module / frozen P1 lifecycle
P4_FORMAL_ELIGIBILITY_PROJECTION_MUST_PROJECT_EXISTING_REPORT_AUTHORITY=YES
REPORT_BACKEND_REVALIDATION_REQUIRED=YES
P4_MAY_NOT_OVERRIDE_EXISTING_REPORT_GATE_WITH_NEW_POLICY=YES
```

The existing report authority remains responsible for checking, at render or
download time, the approved status, approval fields, exact revision ID,
content hash, latest revision, quality blockers, and persisted scheme review
lineage. P4 cannot make a formal export eligible when that backend gate fails.

### 12.3 Draft versus formal report

The aggregate must distinguish:

```text
DRAFT_REPORT_ALLOWED
FORMAL_REPORT_ELIGIBLE
FORMAL_REPORT_BLOCKERS
```

A draft may be allowed while human approval or formal lineage remains pending.
That draft must not be labelled or presented as an approved formal report.

## 13. Future implementation split and ownership principles

The future work may be split into two separately authorized stages:

### 13.1 P4_BACKEND_WORKFLOW_AGGREGATION

Potential responsibilities:

- workflow aggregation application boundary;
- read-only `WorkflowAggregateV1` projection;
- query adapters over existing authorities;
- applicability, blocker, reason, stale, and next-action projection;
- workflow readiness versus formal eligibility projection;
- backend unit/integration coverage.

This stage must not change deterministic formulas, P1 report authority, P2
gateway authority, or P3 OCR producer semantics.

### 13.2 P4_FRONTEND_GUIDED_WORKBENCH

Potential responsibilities:

- typed aggregate consumer;
- workflow store/context;
- existing page integration;
- blocker/reason/next-action/provenance display;
- Agent capability display;
- report review and eligibility consumer;
- responsive/accessibility coverage;
- frontend integration/e2e coverage.

This stage must not add authoritative engineering calculations or duplicate
backend state-machine rules.

### 13.3 Candidate ownership is not a final allowlist

Candidate future paths may include a backend `workflow` module, a frontend
workflow contract/API/store, and extensions to existing workbench/report/Agent
consumers. These are planning candidates only.

```text
FUTURE_IMPLEMENTATION_FILE_ALLOWLIST_MUST_NOT_BE_FROZEN_AS_FINAL_BY_THIS_CONTRACT_DEFINITION=YES
FUTURE_IMPLEMENTATION_SCOPE_REVALIDATION_REQUIRED=YES
```

Before any future P4 implementation authorization, the implementing agent must
revalidate against then-current `main`:

1. exact base SHA/tree;
2. current P3 implementation and merge state;
3. current P2 capability/provider state;
4. current P1 report authority and API shape;
5. current frontend/backend ownership and existing uncommitted changes;
6. exact changed-file, test, migration, dependency, and CI scope;
7. whether a new ADR or technical-debt record is required.

No implementation file list in this document grants future mutation authority.

## 14. Future validation boundaries

Future implementation validation must be scoped to the authorized stage.

### Backend aggregation validation

Must demonstrate at least:

- project/version binding;
- deterministic status and provenance projection;
- calculation/scheme source lineage;
- structured review reason continuity;
- applicability behavior for optional and conditional steps;
- stale detection;
- next-action ordering;
- formal eligibility projection does not override report authority;
- no formula duplication;
- no P3 producer mutation;
- read-only endpoint behavior.

### Frontend consumer validation

Must demonstrate at least:

- current project/version context remains visible;
- missing inputs and blockers are actionable;
- optional Agent unavailability does not block core workflow;
- conditional knowledge provenance blocks only when applicable;
- hidden engineering defaults are not treated as authority;
- stale/review/approval states remain distinguishable;
- formal export is disabled/explained from backend eligibility projection;
- frontend performs no authoritative engineering calculation;
- responsive and keyboard-accessible operation.

### CI and readiness boundary

Automatic CI may run on the Draft PR. No manual CI rerun is authorized by this
contract. CI status is evidence for the changed docs-only commit only; it does
not authorize Ready, Merge, implementation, P3 closure, or Issue #112 closure.

## 15. Post-P3-merge governance hold

P3 implementation lane B is closed on `main`. P4 contract definition remains on
lane C as a Draft PR.

```text
P3_IMPLEMENTATION_LANE=B
P3_IMPLEMENTATION_MERGED_ON_MAIN=YES
P4_CONTRACT_DEFINITION_LANE=C
P4_CONTRACT_DRAFT_PR_MAY_BE_CREATED_IN_PARALLEL=YES
P4_CONTRACT_POST_P3_ALIGNMENT_AMENDMENT=R1
P4_CONTRACT_READY_AUTHORIZED=NO
P4_CONTRACT_MERGE_AUTHORIZED=NO
P4_CONTRACT_FINAL_MERGE_MUST_WAIT_FOR_POST_P3_ALIGNMENT_INDEPENDENT_REVIEW_PASS=YES
```

The P4 branch must not be marked Ready or merged before:

1. post-P3 alignment independent review authorization is obtained;
2. the P4 contract P3-merge alignment amendment R1 is accepted in review;
3. any remaining consumer-boundary gaps against then-current `main` are closed
   or explicitly deferred in review.

The P3 merge and this contract amendment do not automatically authorize P4 Ready
or Merge.

## 16. Contract closure state

```text
CONTRACT_DEFINITION_SCOPE=AUTHORIZED
CONTRACT_DOCUMENT_SCOPE=ONE_FILE
BACKEND_MUTATION_AUTHORIZED=NO
FRONTEND_MUTATION_AUTHORIZED=NO
TEST_MUTATION_AUTHORIZED=NO
MIGRATION_MUTATION_AUTHORIZED=NO
DEPENDENCY_MUTATION_AUTHORIZED=NO
WORKFLOW_MUTATION_AUTHORIZED=NO
P2_MUTATION_AUTHORIZED=NO
P3_MUTATION_AUTHORIZED=NO
P4_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
ISSUE_112_CLOSURE_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
PRODUCTION_OPERATION_AUTHORIZED=NO

NEXT_REQUIRED_STAGE=V03_P4_POST_P3_ALIGNMENT_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 17. Revision history

| Revision | Date | Scope | State |
| --- | --- | --- | --- |
| R1 | 2026-08-20 | P4 guided end-to-end workbench consumer/aggregation contract; corrected P2 facts, applicability, frontend default authority, report authority separation, P3 consumer boundary, and future scope revalidation | Draft for independent review |
| P3-merge alignment R1 | 2026-08-22 | Record P3 implementation merge on main@3dc728d (PR #139), Alembic head `0040_add_knowledge_page_evidence`, closed lane-B authorization, and post-P3 alignment review gate | Draft for post-P3 alignment independent review |
