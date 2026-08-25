# V0.5 P5 Controlled Acceptance Contract

**Status:** Definition freeze R1 — contract + bounded sqlite/postgresql evidence matrix
**Authority:** Issue #163 (umbrella), tracked by Issue #169
**Contract definition source SHA:** `7e187d52198d708bdaa5006ca48c7da880983286`
**Contract definition source tree:** `3a2497b025a2413c3b9c2f4af9b6a6628714aea6`
**Target branch:** `cursor/v05-p5-controlled-acceptance-6c68`

This document freezes V0.5 P5 controlled acceptance for the **canonical persisted
five-stage workbench path**. It does not authorize merge, annotated `v0.5.0` tag,
GitHub Release, controlled-acceptance execution dispatch, production deployment,
live MiMo, formula recut, or coefficient promotion.

## 1. Authority and baseline

```text
TASK=V05_P5_CONTROLLED_ACCEPTANCE_R1
PARENT_ISSUE=163
P5_TRACKING_ISSUE=169
GOVERNANCE_OWNER=V0.5
BASE_MAIN_SHA=7e187d52198d708bdaa5006ca48c7da880983286
BASE_TREE=3a2497b025a2413c3b9c2f4af9b6a6628714aea6
PREVIOUS_RELEASE_TAG=v0.4.0
PROPOSED_FUTURE_RELEASE=v0.5.0
TARGET_BRANCH=cursor/v05-p5-controlled-acceptance-6c68
TARGET_PR_STATE=DRAFT
CI_GATE=main@BASE_MAIN_SHA with BASE_TREE and CI green recorded as later gates
```

Upstream packages consumed at this base:

| Package | Issue | P5 role |
| --- | --- | --- |
| P0 | #170 | Five-stage workbench contract freeze |
| P1 | #171 | `POST .../five-stage-execution` canonical API |
| P2 | #173 | `/workbench/engineering-inputs` |
| P3 | #172 | Workflow/scheme/report bind `installed_power`, not `power_configuration` |
| P4 | #174 | `samples/v05-local-workbench`, seed loader, sqlite+pg acceptance matrix |

P5 does not redefine P0–P4 contracts. It assembles bounded acceptance evidence that
the combined V0.5 local/CI path is ready for a later `v0.5.0` release gate.

## 2. What V0.5 P5 must prove

On **sqlite and postgresql** (bounded integration matrix, not production compose):

1. **Source identity gates** — contract and runbook record `BASE_MAIN_SHA`,
   `BASE_TREE`, and CI as later gates. Tests assert helper/schema presence only;
   they do not invent a SHA at runtime.
2. **Explicit-input sample** — `samples/v05-local-workbench` seeded via public
   APIs only: `POST /api/v1/projects` then
   `POST .../five-stage-execution`. Never `planning-run`. Loader must not run
   Alembic.
3. **Canonical five calculator names** exactly:
   `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`,
   `investment_estimate`.
4. **Lineage** — each canonical row exposes `calculation_id`, `result_hash`, and
   `upstream_calculation_ids` matching P0 DAG /
   `STAGE_UPSTREAM_PROVENANCE_KEYS`.
5. **Restart persistence** — reopening the same database returns identical
   calculation ids and hashes.
6. **Missing KEY leaf fail-closed** — at least `condensing_temperature_c` and
   cooling geometry `zone_area` return `MISSING_ENGINEERING_PARAMETER` with zero
   partial canonical rows and zero source binding.
7. **Consumers read persisted rows only** — workflow not blocked by
   `CALCULATION_MISSING` when the five exist; scheme binds `installed_power`, not
   `power_configuration`; reports read persisted rows only and do not recalculate
   formulas.
8. **Demo coefficients** remain `source_type=demo`,
   `validity_status` in `{unverified, conflict}`, `requires_review=true`.
9. **Agent optional/unavailable** — core five-stage chain works without model API
   keys; workflow `agent_assistance` must not claim fake available Agent.

Passing this matrix proves the V0.5 local/CI path is ready for a later controlled
acceptance execution dispatch. It does **not** prove production readiness, formula
recut, tag publication, or GitHub Release.

## 3. Hard boundaries

```text
V05_P5_IMPLEMENTATION_AUTHORIZED=YES
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
ZONE_AREA_TO_COOLING_GEOMETRY_AUTO_FEED=NO
P5_CREATES_TAG_NOW=NO
P5_CREATES_GITHUB_RELEASE_NOW=NO
P5_CLONES_V03_P5_STAGE_ENGINE=NO
P5_CLONES_V03_SCENARIOS_A_B_C=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Additional frozen boundaries:

1. **No V0.3 P5 clone.** No STAGE_1–10 engine, Scenario A/B/C runners, or
   `.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml` changes.
2. **No live Agent / live MiMo.** Reuse V0.4 fail-closed coverage only.
3. **No formula or coefficient change.**
4. **No production compose, registry, signing, or real production migration.**
5. **Draft PR only.** Merge, tag, Release, and controlled-acceptance execution each
   require separate later authorization.

## 4. Integration matrix

Authoritative test surfaces:

```text
backend/tests/architecture/test_v05_p5_controlled_acceptance_contract.py
backend/tests/integration/test_v05_p5_controlled_acceptance_sqlite.py
backend/tests/integration/test_v05_p5_controlled_acceptance_postgresql.py
backend/tests/integration/v05_p5_acceptance_evidence.py
```

P5 **reuses** P4 fixtures (`v05_p4_acceptance_fixtures`, `v05_p1_bundle_fixtures`)
and must not duplicate P4 test bodies.

| # | Assertion | Evidence |
| --- | --- | --- |
| 1 | Source identity fields in contract/runbook | architecture contract scan |
| 2 | Sample seed via five-stage-execution only | loader + seed integration |
| 3 | Canonical five persisted with ids/hashes/lineage | `GET .../calculations` |
| 4 | Restart/reopen stability | second client on same database |
| 5 | Missing KEY leaves fail closed atomically | condensing_temperature_c, zone_area |
| 6 | Workflow/scheme/report consume persisted `installed_power` | workflow + scheme + report reads |
| 7 | Demo coefficient markings preserved | manifest + calculation rows |
| 8 | Agent assistance not fake-available | workflow `agent_assistance` |

Database setup uses Alembic head in integration tests. The V0.5 sample loader must
not invoke Alembic.

## 5. Runbook

Operator path: `docs/runbooks/v05-controlled-acceptance.md`

Local verification:

```bash
make verify-v05-p5-controlled-acceptance
```

## 6. Explicitly out of scope

```text
ANNOTATED_V0_5_0_TAG=NO
GITHUB_RELEASE_V0_5_0=NO
V03_P5_WORKFLOW_CLONE=NO
V03_SCENARIO_A_B_C=NO
LIVE_MIMO_ACCEPTANCE=NO
FORMULA_RECUT=NO
PRODUCTION_COMPOSE=NO
POST_PLANNING_RUN_AS_V05_PROOF=NO
```

## 7. Implementation allowlist

```text
docs/tasks/V0_5-P5-controlled-acceptance-contract.md
docs/runbooks/v05-controlled-acceptance.md
backend/tests/architecture/test_v05_p5_controlled_acceptance_contract.py
backend/tests/integration/test_v05_p5_controlled_acceptance_sqlite.py
backend/tests/integration/test_v05_p5_controlled_acceptance_postgresql.py
backend/tests/integration/v05_p5_acceptance_evidence.py
Makefile  # verify-v05-p5-controlled-acceptance only
```

Forbidden without separate authorization:

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/orchestration/application/five_stage_execution.py  # behavior change
.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
annotated tag / GitHub Release UI / production release automation
```

## 8. Acceptance criteria

V0.5 P5 R1 is complete when:

```text
P5_CONTRACT_EXISTS=PASS
P5_RUNBOOK_EXISTS=PASS
SOURCE_IDENTITY_FIELDS_RECORDED=PASS
ARCHITECTURE_GUARDS=PASS
SQLITE_INTEGRATION_MATRIX=PASS
POSTGRESQL_INTEGRATION_MATRIX=PASS
P4_FIXTURES_REUSED=PASS
CI_GREEN=PASS
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 9. Contract closure state

```text
TASK=V05_P5_CONTROLLED_ACCEPTANCE_R1
PARENT_ISSUE=163
P5_TRACKING_ISSUE=169
CONTRACT_DEFINITION_SOURCE_SHA=7e187d52198d708bdaa5006ca48c7da880983286
CONTRACT_DEFINITION_SOURCE_TREE=3a2497b025a2413c3b9c2f4af9b6a6628714aea6
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_5-P5-controlled-acceptance-contract.md

V05_P5_CONTRACT_FROZEN=YES
V05_P5_IMPLEMENTATION_AUTHORIZED=YES
V05_P5_CONTROLLED_ACCEPTANCE_EXECUTED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 10. Revision history

| Rev | Date | Scope | State |
| --- | --- | --- | --- |
| R1 | 2026-08-25 | V0.5 P5 controlled acceptance contract; bounded sqlite+pg matrix; runbook; no tag/Release | Draft for review |
