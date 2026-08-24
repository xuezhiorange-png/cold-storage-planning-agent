# V0.4 P4 Agent Fail-Closed Acceptance Contract

**Status:** Definition freeze R1 — contract + sqlite integration matrix
**Authority:** Issue #150 (umbrella), tracked by Issue #154 / #161
**Contract definition source SHA:** `a0886ad25743a2e05c088209fadb1bcb5d237289`
**Target branch:** `cursor/v04-p4-r1-fail-closed-acceptance-8c6f`

This document freezes V0.4 P4 R1 acceptance for the **persisted local workbench
Agent path**. Agent assistance is explicit unavailable (fail-closed). It does not
authorize annotated tag, GitHub Release, production deployment, live MiMo, or
`AGENT_CAPABILITY_ENABLED_READY` in default/CI.

## 1. Authority and baseline

- Umbrella issue: #150, "[V0.4] Local persisted workbench delivery".
- Tracking issue: #154, "[V0.4][P4] Agent fail-closed acceptance".
- Implementation dispatch: #161, "[V0.4][P4][R1] Agent fail-closed acceptance
  on persisted workbench — dispatch authorized".
- Repository: `xuezhiorange-png/cold-storage-planning-agent`.
- Audited branch: `main`.
- Audited source SHA: `a0886ad25743a2e05c088209fadb1bcb5d237289`.
- Previous release tag: `v0.3.0` (separate authority; not modified here).

Upstream packages consumed at this base:

| Package | Merge | P4 role |
| --- | --- | --- |
| P1 | #158 | Persisted project-version workbench; planning-run persists zone, investment, and power rows |
| P2 | #156 | Workflow aggregate consumer (unchanged by P4) |
| P3 | #157 | Local sqlite runbook and v04 sample loader via public APIs |
| P5 | #160 | Controlled acceptance matrix for combined local path (P4 does not redefine P5) |

P4 does not redefine P1/P2/P3/P5 contracts. It proves the persisted local
workbench remains completable with Agent unavailable and without fabricated
engineering numbers.

## 2. What V0.4 P4 acceptance proves

V0.4 P4 R1 fail-closed acceptance proves that on a **fresh sqlite database**
(without Alembic inside the seed loader):

1. **Sample seed + planning-run** through current public APIs still persists
   exactly the workbench planning-helper calculators:
   - `cold_room_zone_plan`
   - `investment_estimate`
   - `power_configuration`
2. **Workflow read path:** `GET .../workflow` exposes
   `agent_assistance.available=false` (or status not `AVAILABLE` / not READY),
   with `capability_state` and `unavailability_reason` present. The projection
   must not claim a fake available Agent.
3. **Agent route fail-closed:** default app without live MiMo credentials
   returns an explicit capability error (HTTP 4xx/503 with documented error
   code) for `POST /api/v1/agent/sessions` and
   `POST /api/v1/agent/sessions/{session_id}/messages`. Response bodies must
   not contain fabricated cooling-load or investment numbers.
4. **Frontend binding:** backend-shaped `agent_assistance.available=false`
   renders explicit 不可用 copy, shows capability state, and does not expose a
   message composer or fake local LLM.

Passing this matrix proves the V0.4 local workbench success criterion with
optional Agent unavailable. It does **not** prove production readiness, formula
correctness recut, or live-model enablement.

## 3. Hard boundaries

```text
CONTROLLED_ACCEPTANCE_PASS_IMPLIES_PRODUCTION_DEPLOYMENT=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
PRODUCTION_ENABLEMENT_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
V04_P4_LIVE_AGENT_ACCEPTANCE_AUTHORIZED=NO
AGENT_CAPABILITY_ENABLED_READY_IN_DEFAULT_CI=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
V0_4_TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
P4_CREATES_TAG_NOW=NO
P4_CREATES_GITHUB_RELEASE_NOW=NO
P4_CLONES_V03_P5_STAGE_ENGINE=NO
P4_ENABLES_LIVE_MIMO=NO
P4_ADDS_API_KEYS=NO
P4_CALLS_PUBLIC_INTERNET=NO
SECOND_CALCULATOR_INVENTED=NO
SEED_CALLS_ALEMBIC=NO
MERGE_AUTHORIZED=NO
```

Additional frozen boundaries:

1. **No live Agent / live MiMo.** Core local path must remain completable without
   model API keys. Agent unavailability is expected and non-blocking.
2. **No silent fake chat.** Missing capability must not invent calculator
   numbers or present a working message composer.
3. **No formula or coefficient change.** Acceptance runs against existing
   deterministic calculators only.
4. **No production compose.** `docker-compose.production.yml` remains out of scope.
5. **Draft PR only.** Merge, tag, and Release each require separate later
   authorization.

## 4. Integration matrix (sqlite)

Authoritative test surface:

```text
backend/tests/integration/test_v04_p4_agent_fail_closed_acceptance.py
```

| # | Assertion | Evidence |
| --- | --- | --- |
| 1 | `seed_v04_local_sample` + planning-run persists three calculator names | `GET .../calculations` |
| 2 | Workflow exposes fail-closed agent assistance projection | `GET .../workflow` `agent_assistance` |
| 3 | Default app agent session/message create fail closed | `POST .../agent/sessions`, `POST .../messages` |
| 4 | Agent error bodies contain no fabricated engineering numbers | response body scan |

Database setup in the matrix uses `Base.metadata.create_all` only. The v04
sample loader must not invoke Alembic. Tests must mock/inject only; no live MiMo
or public internet calls.

## 5. Frontend acceptance

Authoritative test surface:

```text
frontend/src/features/agent/components/AgentPanel.test.ts
```

| # | Assertion | Evidence |
| --- | --- | --- |
| 1 | `agent_assistance.available=false` shows 不可用 copy | drawer text |
| 2 | Capability state rendered from backend projection | `能力状态：` line |
| 3 | No message composer controls | absent `textarea` / message input |

## 6. Runbook truth-up

`docs/runbooks/v04-local-run.md` Agent troubleshooting may note that disabled
Agent routes return `AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE` by design in local
mode. One-line addition only; do not rewrite the runbook.

## 7. Explicitly out of scope

```text
ANNOTATED_V0_4_0_TAG=NO
GITHUB_RELEASE_V0_4_0=NO
V03_P5_WORKFLOW_CLONE=NO
V03_SCENARIO_A_B_C_FORMAL_REPORT=NO
V04_P4_LIVE_AGENT=NO
LIVE_MIMO_ACCEPTANCE=NO
FORMULA_RECUT=NO
ZONE_AREA_TO_COOLING_LOAD_AUTO_FEED=NO
DEMO_COEFFICIENT_PROMOTION=NO
HEAT_EXCHANGER=NO
CONSTRUCTION_DRAWINGS=NO
FIELD_EQUIPMENT_CONTROL=NO
PRODUCTION_COMPOSE=NO
FAKE_LOCAL_LLM=NO
```

## 8. Implementation allowlist

```text
docs/tasks/V0_4-P4-agent-fail-closed-acceptance-contract.md
docs/runbooks/v04-local-run.md
backend/tests/integration/test_v04_p4_agent_fail_closed_acceptance.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/app.py
backend/tests/integration/test_health_endpoints.py
frontend/src/features/agent/components/AgentPanel.test.ts
```

Forbidden without separate authorization:

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/workflow/application/knowledge_provenance.py
.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
docker-compose.production.yml
```

## 9. Acceptance criteria

V0.4 P4 R1 is complete when:

```text
P4_CONTRACT_EXISTS=PASS
SQLITE_INTEGRATION_MATRIX=PASS
POWER_CONFIGURATION_PERSISTED=PASS
WORKFLOW_AGENT_FAIL_CLOSED=PASS
AGENT_ROUTES_FAIL_CLOSED=PASS
NO_FABRICATED_ENGINEERING_NUMBERS=PASS
FRONTEND_AGENT_UNAVAILABLE_UI=PASS
CI_GREEN=PASS
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

## 10. Contract closure state

```text
TASK=V04_P4_AGENT_FAIL_CLOSED_ACCEPTANCE_R1
PARENT_ISSUE=150
P4_TRACKING_ISSUE=154
IMPLEMENTATION_DISPATCH_ISSUE=161
CONTRACT_DEFINITION_SOURCE_SHA=a0886ad25743a2e05c088209fadb1bcb5d237289
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_4-P4-agent-fail-closed-acceptance-contract.md

V04_P4_CONTRACT_FROZEN=YES
V04_P4_IMPLEMENTATION_AUTHORIZED=YES
V04_P4_FAIL_CLOSED_ACCEPTANCE_EXECUTED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 11. Revision history

| Revision | Date | Scope | State |
| --- | --- | --- | --- |
| R1 | 2026-08-24 | V0.4 P4 fail-closed agent acceptance contract; sqlite integration matrix; frontend unavailable UI test; no tag/Release/live MiMo | Draft for review |
