# V1.1 P2 豆包工作伙伴 Skill Pack Contract

**Status:** Definition freeze R1 — static paste-ready skill (no live outbound session)  
**Authority:** Charles 2026-08-28 — 吨=每天；豆包理解语义；五个 KEY 调内核；表格回复分区规划  
**Previous release:** `v1.0.0`  
**Base `main` SHA:** `938002546090ac0ca0932c65c48e83cd107a6702` (`feat(aily): inbound 豆包 zone-plan connector for V1.1 (#237)`)  
**Parent contract:** `docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`  
**Target branch:** `cursor/v11-p2-doubao-skill-742e`

This document freezes the **static** 豆包工作伙伴 skill pack for V1.1 P2.
Operators paste the skill into Feishu 豆包工作伙伴. This package does **not**
create live Feishu sessions, outbound HTTP clients, or skill registration from
this application.

## 0. Governance

```text
TASK=V11_P2_DOUBAO_SKILL_PACK_CONTRACT_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
BASE_MAIN_SHA=938002546090ac0ca0932c65c48e83cd107a6702
TARGET_BRANCH=cursor/v11-p2-doubao-skill-742e
TARGET_FILE=docs/tasks/V1_1-P2-doubao-skill-contract.md
TARGET_PR_STATE=DRAFT

V11_P2_IMPLEMENTATION_AUTHORIZED=YES
AILY_INBOUND_ZONE_PLAN_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2 ships a paste-ready conversation policy for 豆包工作伙伴, like V0.7 P6 paper
contracts. P2 does **not** implement live outbound Feishu control.

## 1. Objective

Give operators a **paste-ready skill** so 豆包工作伙伴 can:

1. Understand spoken plant size. **吨 always means per day** (每天).
   「要建一个多少吨的加工厂」is only an example utterance — 豆包 owns semantics.
2. Ask until all five operator KEY are present, using the Chinese labels in
   `OPERATOR_KEY_ASK` (`backend/src/cold_storage/modules/aily/application/operator_payload.py`).
3. Convert 吨/天 → `daily_inbound_mass_kg` (kg/day; multiply by 1000) **before**
   calling the connector.
4. `POST /api/v1/aily/v1/zone-plan` with KEY JSON — not the chat text.
5. On `400` with `ask_operator` / `missing_keys`, ask the user those fields;
   do not invent numbers.
6. On `200`, show `markdown_table` as-is (plus `extra_tables` if present).
   State this is 概念设计, needs review, not construction drawings.
7. Never compute area, positions, or cooling itself (`AGENT_TO_ENGINEERING_VALUE=NO`).

This system does **not** parse chat. 豆包 owns NLP.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg          kg/day
zone_planning_inputs.finished_storage_days          day
zone_planning_inputs.frozen_storage_days            day
zone_planning_inputs.main_packaging_storage_days    day
zone_planning_inputs.auxiliary_packaging_storage_days  day
```

`OperatorProcessInputV1` schema_version stays `1.1.0`.  
Calculator identity stays `cold_room_zone_plan@1.0.0` (`DO_NOT_BUMP_ZONE_PLAN_VERSION=YES`).

## 3. Static skill artifacts

| Artifact | Purpose |
| --- | --- |
| `docs/contracts/aily/v1.1/doubao-skill.v1.md` | Paste-ready Chinese skill for 豆包工作伙伴 |
| `docs/contracts/aily/v1.1/doubao-skill.v1.json` | Structured companion for tests and tooling |

OpenAPI for the inbound connector remains:
`docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml` (P0/P1 on `main`).

## 4. Non-goals (hard boundaries)

```text
AILY_OUTBOUND_LIVE_SESSION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

P2 must not:

- call Feishu/Aily APIs from this application;
- create skills or sessions from this repository;
- add outbound HTTP clients;
- expose `mark_reviewed` / `approve` as model tools for 豆包;
- extend `/api/v1/agent/**`;
- edit `backend/src/**` (P0/P1 already delivered inbound connector on `main`);
- reopen issues #11 / #13 / #17 / #176 / #20;
- move tags `v0.9.0` or `v1.0.0`.

## 5. P2 exclusive allowlist

```text
V11_P2_FILE_ALLOWLIST
docs/tasks/V1_1-P2-doubao-skill-contract.md
docs/contracts/aily/v1.1/doubao-skill.v1.md
docs/contracts/aily/v1.1/doubao-skill.v1.json
docs/contracts/aily/v1.1/README.md
docs/tasks/V1_1-version-plan.md
docs/architecture/ADR-032-doubao-skill-pack.md
backend/tests/architecture/test_v11_p2_doubao_skill_contract.py
```

P2 is pairwise disjoint from P3 (auth) and P4 (runbook/OpenAPI examples),
which are parallel sibling packages owned by other PRs.

## 6. Expert decisions

| ID | Decision |
| --- | --- |
| V11-P2-E1 | Static skill pack ≠ live outbound session (`AILY_OUTBOUND_LIVE_SESSION=NO`) |
| V11-P2-E2 | 吨 always means per day; 豆包 owns semantics; this system does not parse chat |
| V11-P2-E3 | Five KEY unchanged; 豆包 converts 吨/天 → kg/day before POST |
| V11-P2-E4 | First engineering reply is zone-plan table from `POST /api/v1/aily/v1/zone-plan` |
| V11-P2-E5 | 豆包 must not compute area / positions / cooling (`AGENT_TO_ENGINEERING_VALUE=NO`) |
| V11-P2-E6 | `mark_reviewed` is not a 豆包 tool (`MARK_REVIEWED_AS_MODEL_TOOL=NO`) |

## 7. Acceptance criteria

```text
P2_CONTRACT_EXISTS=PASS
ADR_032_EXISTS=PASS
DOUBAO_SKILL_MD_EXISTS=PASS
FIVE_KEY_FIELD_NAMES_PRESENT=PASS
TON_MEANS_PER_DAY=PASS
DOUBAO_OWNS_NLP=PASS
AILY_OUTBOUND_LIVE_SESSION=NO
COLD_ROOM_ZONE_PLAN_VERSION_1_0_0=PASS
POST_ZONE_PLAN_ENDPOINT=PASS
NO_ENGINEERING_FORMULAS_IN_SKILL=PASS
NO_MARK_REVIEWED_AS_TOOL=PASS
ARCHITECTURE_TESTS_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v11_p2_doubao_skill_contract.py
```

## 8. Closed issues

#11 / #13 / #17 / #176 / #20 stay CLOSED.

## 9. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-28 | Initial P2 static 豆包 skill pack at `938002546090ac0ca0932c65c48e83cd107a6702` |
