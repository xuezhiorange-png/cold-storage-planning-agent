# V0.4 P5 Controlled Acceptance Contract

**Status:** Definition freeze R1 — contract + sqlite integration matrix
**Authority:** Issue #150 (umbrella), tracked by Issue #155 / #159
**Contract definition source SHA:** `05b0fd07b829e72c2f6f1c560d9e8020c0b590bf`
**Target branch:** `cursor/v04-p5-controlled-acceptance-da05`

This document freezes V0.4 P5 controlled acceptance for the **local persisted
workbench path**. It does not authorize annotated tag, GitHub Release, production
deployment, live MiMo, or V0.4 P4 live Agent acceptance.

## 1. Authority and baseline

- Umbrella issue: #150, "[V0.4] Local persisted workbench delivery".
- Tracking issue: #155, "[V0.4][P5] Controlled acceptance".
- Implementation dispatch: #159, "[V0.4][P5][R1] Controlled acceptance of
  persisted local workbench".
- Repository: `xuezhiorange-png/cold-storage-planning-agent`.
- Audited branch: `main`.
- Audited source SHA: `05b0fd07b829e72c2f6f1c560d9e8020c0b590bf`.
- Previous release tag: `v0.3.0` (separate authority; not modified here).

Upstream packages consumed at this base:

| Package | Merge | P5 role |
| --- | --- | --- |
| P1 | #158 | Persisted project-version workbench; planning-run persists zone, investment, and power rows |
| P2 | #156 | Workflow aggregate exposes V0.3 knowledge provenance display fields (consumer-only) |
| P3 | #157 | Local sqlite runbook and v04 sample loader via public APIs |

P5 does not redefine P1/P2/P3 contracts. It proves the combined local path works
under controlled sqlite integration conditions.

## 2. What V0.4 acceptance proves

V0.4 P5 R1 controlled acceptance proves that on a **fresh sqlite database**
(without Alembic inside the seed loader):

1. **Sample seed + planning-run** through current public APIs persists exactly
   the workbench planning-helper calculators:
   - `cold_room_zone_plan`
   - `investment_estimate`
   - `power_configuration`
2. **Fail-closed read path:** before a persisted planning run exists,
   `GET .../calculations` returns an empty list and the workflow aggregate does
   not inject demo or transient planning-run numbers.
3. **Knowledge provenance visibility (P2):** `GET .../workflow` returns
   `knowledge_provenance` with V0.3 display-field projection wired through the
   existing `assess_knowledge_provenance` + `enrich_knowledge_provenance_projection`
   path. Assessment semantics remain owned by `assess_knowledge_provenance`; P5
   must not change them.
4. **Restart persistence:** reopening the same sqlite file still returns the
   persisted calculation rows for the seeded project version.

Passing this matrix proves the V0.4 local workbench success criterion. It does
**not** prove production readiness, formula correctness recut, or formal-report
closure.

## 3. Hard boundaries

```text
CONTROLLED_ACCEPTANCE_PASS_IMPLIES_PRODUCTION_DEPLOYMENT=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
PRODUCTION_ENABLEMENT_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
V04_P4_LIVE_AGENT_ACCEPTANCE_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
V0_4_TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
P5_CREATES_TAG_NOW=NO
P5_CREATES_GITHUB_RELEASE_NOW=NO
P5_CLONES_V03_P5_STAGE_ENGINE=NO
P5_CLONES_V03_SCENARIOS_A_B_C=NO
SECOND_CALCULATOR_INVENTED=NO
SEED_CALLS_ALEMBIC=NO
MERGE_AUTHORIZED=NO
```

Additional frozen boundaries:

1. **No V0.3 P5 clone.** P5 must not add STAGE_1–10 evidence assembly,
   Scenario A/B/C formal-report runners, multilingual formal-artifact proof, or
   PostgreSQL parity gates from `docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md`.
2. **No live Agent / live MiMo.** Core local path must remain completable without
   model API keys. Agent unavailability is expected and non-blocking.
3. **No formula or coefficient change.** Acceptance runs against existing
   deterministic calculators only.
4. **No production compose.** `docker-compose.production.yml` remains out of scope.
5. **Draft PR only.** Merge, tag, and Release each require separate later
   authorization.

## 4. Integration matrix (sqlite)

Authoritative test surface:

```text
backend/tests/integration/test_v04_p5_controlled_acceptance.py
```

| # | Assertion | Evidence |
| --- | --- | --- |
| 1 | `seed_v04_local_sample` + planning-run persists three calculator names | `GET .../calculations` |
| 2 | Missing persisted runs do not inject demo/transient numbers | empty calculations + workflow `calculations.runs` |
| 3 | Workflow exposes P2 knowledge provenance projection | `GET .../workflow` `knowledge_provenance` |
| 4 | `assess_knowledge_provenance` semantics unchanged | direct assess vs workflow status/blockers parity |
| 5 | Sqlite reopen preserves rows | second `TestClient` on same database file |

Database setup in the matrix uses `Base.metadata.create_all` only. The v04
sample loader must not invoke Alembic.

## 5. Runbook truth-up

`docs/runbooks/v04-local-run.md` must list `power_configuration` among persisted
calculator rows. P1 already persists power; P3 runbook text was stale at the
contract base.

## 6. Explicitly out of scope

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
```

## 7. Implementation allowlist

```text
docs/tasks/V0_4-P5-controlled-acceptance-contract.md
docs/runbooks/v04-local-run.md
backend/tests/integration/test_v04_p5_controlled_acceptance.py
backend/src/cold_storage/bootstrap/v04_local_sample.py  # EXPECTED_PERSISTED_CALCULATORS truth-up only
```

Forbidden without separate authorization:

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/workflow/application/knowledge_provenance.py  # assess semantics
.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
docker-compose.production.yml
```

## 8. Acceptance criteria

V0.4 P5 R1 is complete when:

```text
P5_CONTRACT_EXISTS=PASS
SQLITE_INTEGRATION_MATRIX=PASS
POWER_CONFIGURATION_PERSISTED=PASS
FAIL_CLOSED_WITHOUT_PERSISTED_RUNS=PASS
KNOWLEDGE_PROVENANCE_DISPLAY_VISIBLE=PASS
ASSESS_KNOWLEDGE_PROVENANCE_UNCHANGED=PASS
SQLITE_REOPEN_PERSISTENCE=PASS
RUNBOOK_TRUTHED=PASS
CI_GREEN=PASS
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

## 9. Contract closure state

```text
TASK=V04_P5_CONTROLLED_ACCEPTANCE_R1
PARENT_ISSUE=150
P5_TRACKING_ISSUE=155
IMPLEMENTATION_DISPATCH_ISSUE=159
CONTRACT_DEFINITION_SOURCE_SHA=05b0fd07b829e72c2f6f1c560d9e8020c0b590bf
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_4-P5-controlled-acceptance-contract.md

V04_P5_CONTRACT_FROZEN=YES
V04_P5_IMPLEMENTATION_AUTHORIZED=YES
V04_P5_CONTROLLED_ACCEPTANCE_EXECUTED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 10. Revision history

| Revision | Date | Scope | State |
| --- | --- | --- | --- |
| R1 | 2026-08-24 | V0.4 P5 controlled acceptance contract; sqlite integration matrix; runbook truth-up; no tag/Release | Draft for review |
