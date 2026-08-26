# V0.7 P6 Feishu Aily Integration Boundary Contract

**Status:** Definition freeze R1 — Aily boundary contract only (no live implementation)
**Authority:** `docs/tasks/V0_7-P0-trust-loop-contract.md` §7
**Parent contract:** `docs/tasks/V0_7-P0-trust-loop-contract.md`
**Contract definition source SHA:** `f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba`
**Contract definition source tree:** `23af6e60e4247394b2b12c50440d5fc03a819074`
**Previous release:** `v0.6.0`
**Target branch:** `cursor/v07-p6-aily-boundary-contract-6c68`

This document freezes the Feishu Aily integration **boundary** for V0.7.
It does not implement live MCP connectors, Aily skills, outbound OpenAPI
clients, formula recut, tag publication, or Release.

## 0. Contract identity and governance

```text
TASK=V07_P6_AILY_INTEGRATION_BOUNDARY_CONTRACT_R1
PARENT_ISSUE=PENDING
P6_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
BASE_TREE=23af6e60e4247394b2b12c50440d5fc03a819074
PREVIOUS_RELEASE=v0.6.0
TARGET_BRANCH=cursor/v07-p6-aily-boundary-contract-6c68
TARGET_FILE=docs/tasks/V0_7-P6-aily-integration-boundary-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
V07_P6_IMPLEMENTATION_AUTHORIZED=YES
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P6 freezes ownership split, call-direction separation, the four model-visible
tools, the non-model confirmation callback, forbidden model surfaces, and static
contract artifacts under `docs/contracts/aily/v0.7/**`. P6 does **not** change
application behavior.

## 1. Objective and non-goals

### 1.1 Objective

Close `V07-GAP-008` by freezing how Feishu Aily may assist cold-storage
planning without becoming an engineering, persistence, confirmation, or audit
authority.

Aily is an external conversation and orchestration surface. This system
remains the only authority for:

- project and project-version lifecycle;
- `EngineeringInputBundleV1` validation;
- deterministic five-stage execution;
- calculation persistence, hashes, and source provenance;
- confirmation issuance and consumption;
- review/formal-export state machine;
- audit records and report assembly from persisted results.

### 1.2 Non-goals (hard boundaries)

```text
AILY_LIVE_IMPLEMENTATION=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
PRODUCTION_RBAC_CLAIM=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

P6 must not:

- implement MCP servers, Aily connectors, outbound Aily HTTP clients, or skill
  registration;
- add or extend `/api/v1/agent/**` routes;
- expose `mark_reviewed`, `approve`, or confirmation tokens to the model;
- let the model self-report actor identity;
- edit `backend/src/**`, `backend/alembic/**`, `frontend/**`, `samples/**`, or
  `Makefile`;
- reopen V0.6 report source mapping or V0.5 five-stage persistence as unfinished
  umbrellas.

## 2. Ownership split (frozen)

| Surface | Aily may | This system must |
| --- | --- | --- |
| Conversation | Collect intent, ask clarifying questions, phrase warnings | Persist session/turn audit only through authorized write paths |
| Engineering inputs | Relay user-provided values | Validate `EngineeringInputBundleV1`; fail closed on KEY gaps |
| Calculation | Call allowlisted tools | Run deterministic five-stage execution; persist IDs and hashes |
| Display | Show `{name, value, unit}` from tool outputs | Expose `source_result_id`, `source_tool`, `source_tool_version`, `calculator_version`, `requires_review` |
| Write actions | Propose writes through model tools | Issue confirmation records; execute only after trusted human confirmation |
| Review / formal export | Guide a human through review steps | Enforce `FORMAL_EXPORT_STATUSES`, trusted `mark_reviewed`, and quality blockers |
| Actor identity | Display operator identity to the human | Derive actor from trusted transport, never from model JSON |

Hard rules inherited from P0 §7:

- Aily MUST NOT compute engineering values.
- Aily MUST NOT access ORM models, database sessions, or internal service ports.
- Write tools follow: **proposal → trusted human confirmation →
  re-authorization → execution**.
- Reports MUST NOT recalculate formulas; templates MUST NOT embed formulas.

## 3. Call directions (must not be confused)

Two integration directions exist. They use different transports, credentials,
and failure semantics. P6 freezes them as separate contract families.

### 3.1 Aily → this system (inbound)

```text
Transport family: custom MCP or Feishu connector
Contract root: docs/contracts/aily/v0.7/aily-to-system-connector.v1.json
Purpose: expose the four model-visible tools to Aily as MCP/connector operations
Authority: this system's public planning APIs and future dedicated connector
  adapters — not /api/v1/agent/**
```

Inbound calls MUST:

- map one connector operation to exactly one frozen model-visible tool;
- reject unlisted operations fail-closed;
- bind actor identity from connector transport metadata, not tool arguments;
- never pass confirmation tokens into model context or tool argument schemas.

Inbound calls MUST NOT:

- expose `mark_reviewed`, `approve`, archive actions, or direct calculation
  execution without confirmation;
- expose raw ORM rows or internal module ports.

### 3.2 This system → Aily (outbound)

```text
Transport family: Aily skill / session / run OpenAPI
Contract root: docs/contracts/aily/v0.7/system-to-aily-openapi.v1.yaml
Purpose: let this system create or resume Aily sessions for operator assistance
Authority: external Feishu Aily platform — not this repository's public API
```

Outbound calls MUST:

- treat Aily responses as untrusted natural-language and orchestration hints;
- never treat Aily session metadata as engineering or approval authority;
- redact confirmation tokens and internal audit secrets from outbound payloads.

Outbound calls MUST NOT:

- send confirmation tokens to Aily for model consumption;
- send trusted-operator proofs or `mark_reviewed` payloads for model replay;
- request Aily to compute engineering values.

## 4. Model-visible tool surface (exactly four)

The Aily model context MUST expose **only** these four tools. No aliases, no
compound tools, no hidden fifth tool.

| # | Tool name | Authorization | Confirmation | Maps to system responsibility |
| --- | --- | --- | --- | --- |
| 1 | `planning_context.get` | READ | No | Project/version/workflow read model |
| 2 | `engineering_inputs.validate` | READ | No | `EngineeringInputBundleV1` validation |
| 3 | `five_stage_execution.propose` | WRITE | Yes | Five-stage execution proposal only |
| 4 | `report_delivery.propose` | WRITE | Yes | Report lifecycle proposal only |

Authoritative static schemas:

- `docs/contracts/aily/v0.7/model-visible-tools.v1.json`
- `docs/contracts/aily/v0.7/README.md`

### 4.1 `planning_context.get`

Read-only context assembly for dialogue. Returns persisted identifiers,
version status, workflow projection, and already-persisted summary fields.

MUST NOT return executable write capability, confirmation tokens, or
engineering numbers computed inside the model.

### 4.2 `engineering_inputs.validate`

Validates a candidate `EngineeringInputBundleV1` without persisting or
executing calculations.

MUST return per-leaf `state`, `source_type`, `validity_status`,
`requires_review`, and explicit KEY-gap errors.

MUST NOT silently guess missing KEY leaves.

### 4.3 `five_stage_execution.propose`

Creates a persisted tool-call proposal for five-stage execution.

MUST require confirmation before any calculation run is dispatched.

MUST NOT execute calculators directly or return final engineering totals as if
already persisted without execution evidence.

Proposal output MUST expose proposal identifiers only; execution outcomes are
returned only after confirmation and execution on the non-model callback path.

### 4.4 `report_delivery.propose`

Creates a persisted tool-call proposal for report create/generate/submit-review
steps that read persisted calculation results.

MUST require confirmation before any write/report mutation.

MUST NOT expose `mark_reviewed`, `approve`, formal render, or archive actions.

MUST NOT recalculate report sections from formulas.

## 5. Confirmation callback (not a model tool)

Confirmation is a **trusted human callback channel**, not a model-visible tool.

```text
Contract artifact: docs/contracts/aily/v0.7/confirmation-callback.v1.json
Surface intent: connector/UI callback after human approval or rejection
Model visibility: FORBIDDEN
```

Rules:

1. Confirmation callbacks consume server-issued confirmation records bound to
   one tool-call proposal.
2. `confirmation_token` MUST NOT appear in model prompts, model tool schemas,
   model tool results, or Aily skill inputs intended for model replay.
3. Actor on confirmation MUST come from trusted transport identity
   (Feishu user / operator principal), never from model-generated JSON fields
   such as `actor`, `actor_principal`, or `confirmed_by`.
4. Rejected confirmations MUST leave proposals unexecuted and auditable.
5. Confirmation callbacks MAY execute only the previously proposed tool call
   after re-authorization checks pass.

Historical V0.6 internal compatibility routes at `/api/v1/agent/tool-calls/{id}/confirm`
and `/api/v1/agent/tool-calls/{id}/reject` are **not** the Aily production
boundary. They remain V0.6 internal compatibility only and MUST NOT be
extended for Aily.

## 6. Forbidden model surfaces

Authoritative deny list:

- `docs/contracts/aily/v0.7/forbidden-model-surfaces.v1.json`

Frozen prohibitions:

| Category | Forbidden in model context |
| --- | --- |
| Review authority tools | `mark_reviewed`, `approve`, `archive`, `report.mark_reviewed`, `report.approve` |
| Direct legacy tools | `planning.calculate_throughput_inventory_area`, `planning.calculate_cooling_load_and_equipment`, `scheme.generate_and_compare`, `knowledge.search`, `project.get`, `project_version.get`, `report.create`, `report.generate`, `report.render` |
| Secrets / authority tokens | `confirmation_token`, trusted-operator proofs, service-account actor overrides |
| Actor self-attestation | model-supplied `actor`, `actor_principal`, `confirmed_by`, `operator_id` |
| Internal compatibility API | new `/api/v1/agent/**` endpoints or extensions |

Current `/api/v1/agent/**` status at `BASE_MAIN_SHA`:

- frozen disabled-route matrix for strict runtime modes;
- V0.6 internal compatibility surface only;
- **not** the Aily production inbound boundary;
- **no further extension** in V0.7 without a new authorized contract amendment.

## 7. Relationship to existing internal agent module

The repository already contains a planning-agent module with a broader legacy
tool registry (`knowledge.search`, `project.get`, `planning.calculate_*`,
`scheme.generate_and_compare`, legacy `report.*` tools).

P6 freezes the **Aily-facing** surface as the four-tool contract above.
Legacy registry entries remain internal/historical until a later authorized
implementation package explicitly migrates or retires them.

P6 does not authorize:

- registering the four frozen tools in `backend/src`;
- wiring Aily MCP to `/api/v1/agent/**`;
- exposing legacy tools to Aily model context.

## 8. P6 exclusive allowlist

```text
V07_P6_FILE_ALLOWLIST
docs/tasks/V0_7-P6-aily-integration-boundary-contract.md
docs/architecture/ADR-027-aily-integration-boundary.md
docs/contracts/aily/v0.7/**
backend/tests/architecture/test_v07_p6_aily_contract.py
```

P6 is pairwise disjoint from Wave 1 packages P1, P2, P3A, and P3B per P0 §5.10.

### 8.1 P6 forbidden without separate authorization

```text
backend/src/**
frontend/**
backend/alembic/**
samples/**
Makefile
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
.github/workflows/v0-3-p5-*
```

## 9. Gap closure mapping

| Gap ID | P6 action |
| --- | --- |
| V07-GAP-008 | **Freeze** Aily boundary contract, ADR, and static schemas |
| V07-GAP-008 live enablement | Remains open; requires `AILY_LIVE_IMPLEMENTATION=YES` in a later authorized package |

P6 MUST NOT claim live Aily enablement or operator-path closure of #11 / #13 /
#17 / #176.

## 10. P6 acceptance criteria

```text
P6_CONTRACT_EXISTS=PASS
ADR_027_EXISTS=PASS
AILY_CONTRACTS_V07_EXIST=PASS
FOUR_MODEL_TOOLS_FROZEN=PASS
CONFIRMATION_NOT_MODEL_TOOL=PASS
FORBIDDEN_SURFACES_DOCUMENTED=PASS
CALL_DIRECTIONS_SEPARATED=PASS
AGENT_API_NO_EXTENSION_DOCUMENTED=PASS
AILY_LIVE_IMPLEMENTATION=NO
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v07_p6_aily_contract.py
```

## 11. Contract closure state

```text
TASK=V07_P6_AILY_INTEGRATION_BOUNDARY_CONTRACT_R1
PARENT_ISSUE=PENDING
P6_TRACKING_ISSUE=PENDING
CONTRACT_DEFINITION_SOURCE_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P6-aily-integration-boundary-contract.md

V07_P6_CONTRACT_FROZEN=YES
V07_P6_IMPLEMENTATION_AUTHORIZED=YES
V07_P6_CONTRACT_EXECUTED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 12. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P6 Aily boundary freeze at `v0.6.0` / `f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba` |
