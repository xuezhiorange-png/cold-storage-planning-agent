# Technical Debt

## 当前治理状态（2026-09-12）

```ini
CURRENT_RELEASE=v2.1.2
V2_1_2_RELEASED=true
RELEASE_TARGET_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
DEPLOYMENT_EXECUTED=false
ACTIVE_GOVERNANCE_LANE=V2.2_P0
V22_P0_STATUS=CONTRACT_FROZEN_DRAFT_REVIEW
P1_AUTHORIZED=false
P2_AUTHORIZED=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

v2.1.2 已正式发布。下文 V2.1.2 closure 的 Draft、TAG_AUTHORIZED=NO、
RELEASE_AUTHORIZED=NO 及其他早期授权块均是历史 snapshot，不再代表当前发布状态。
当前工作为 V2.2 P0 场地约束平面规划合同冻结，参见
`docs/tasks/V2_2-version-plan.md` 和 ADR-044。
P0 仅文档/schema/architecture evidence；布局引擎、第七 MCP 工具和投影均未实现。
现有六工具、五 KEY 与工程计算保持 v2.1.2 基线。
网格容量几何需保留；缺少的定尺/access profile 及人车避让尺寸须另行工程决策。
本任务未关闭无关技术债；TD-008、TD-019、TD-021、TD-024 保持原有状态。

> **V0.9 P0 freeze (2026-08-27, `main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`,
> release `v0.8.0`; previous releases `v0.7.0`, `v0.6.0`):** TD-007 and TD-015
> are **delivered** by V0.5. V0.6 P1–P5 delivered report assembly/rendering/evaluation
> on the evaluation surface.
> V0.7 closed the operator trust-loop seam at `v0.7.0`. V0.8 closed the
> five-KEY operator path at `v0.8.0`. Demo coefficient conflicts (TD-003 note)
> remain open. Prior contracts: `docs/tasks/V0_7-P0-trust-loop-contract.md`,
> `docs/tasks/V0_8-P0-operator-minimal-input-contract.md`,
> `docs/tasks/V0_9-P0-version-contract.md`. V1.1 inbound connector is complete
> at `v1.1.0` (`docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`).
> V1.2 five-stage inbound preview is complete at `v1.2.0`. V1.3 conversation
> preview lineage is complete at `v1.3.0`. V1.4 workbench debt is complete
> at `v1.4.0`. V1.5 envelope wall/roof geometry bind is complete at
> `v1.5.0`. V1.6 power-fan demo catalog is complete at `v1.6.0`.
> V1.7 per-zone cooling component surface is complete at `v1.7.0`.
> V1.8 per-zone temperature and height surface:
> `docs/tasks/V1_8-version-plan.md` (`V18_IMPLEMENTATION_AUTHORIZED=YES`).
> **V1.9 implementation and release closure are complete:** the P0 contract is
> frozen, P1 is merged through PR #254 at `main@675fa8adfc58e2362101079d83393e90706505b2`,
> the report projection regression is closed, the V0.7 golden controlled
> evolution is complete, and `v1.9.0` is released. **V2.0 implementation is
> complete** on `main@a7049ca93d238013c0cf62069fe1e0a89ff834d7`: P0, P1, and P2
> are merged and `v2.0.0` tag/GitHub Release are complete. V2.1 P0, P1, and P2 for
> `v2.1.0` are merged, and the current governance lane is the separately
> authorized V2.1 release closure/readiness audit. Release execution, deployment,
> and later feature lanes remain unauthorized until separately dispatched.

Current V2.0 release-closure state:

```text
V20_IMPLEMENTATION_COMPLETE=YES
V20_P3_DEFINED=NO
V20_P3_EXECUTED=NO
TARGET_RELEASE=v2.0.0
V2_0_0_RELEASE_CANDIDATE=YES
V2_0_0_RELEASE_READY=YES
TAG_CREATION_AUTHORIZED=NO
GITHUB_RELEASE_CREATION_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

V2.0 release execution is complete at `v2.0.0`; the block above preserves the
historical V2.0 readiness authorization snapshot. Historical V2.1 P0 governance
state (dispatch snapshot; current P1 state follows):

```text
ACTIVE_GOVERNANCE_LANE=V2.1_P0
TARGET_VERSION=v2.1.0
BASE_RELEASE=v2.0.0
BASE_MAIN_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1
CONTRACT_FREEZE=YES
RUNTIME_IMPLEMENTATION=NO
MCP_IMPLEMENTATION=NO
SKILL_IMPLEMENTATION=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

V2.1 P0 froze canonical zone-plan upstream authority and the append-only Doubao
MCP contract and is merged. The separately authorized P1 adapter and P2
MCP/Doubao integration are also merged; their historical records are recorded
below. This does not close unrelated technical-debt rows.

Current V2.1 P1 implementation state:

```text
TASK_ID=V21_P1_FACTORY_POWER_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0
ACTIVE_GOVERNANCE_LANE=V2.1_P1
P0_STATUS=MERGED
P1_STATUS=IMPLEMENTATION_ACTIVE
P1_EXECUTED=YES
P2_STATUS=UNAUTHORIZED
P2_EXECUTED=NO
BACKEND_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION=YES
FACTORY_AREA_BINDING_IMPLEMENTATION=YES
COLD_STORAGE_AREA_BINDING_IMPLEMENTATION=YES
V20_FACTORY_POWER_CALCULATOR_INVOCATION=YES
V20_CALCULATOR_CHANGED=NO
V20_PRESENTATION_CHANGED=NO
DOUBAO_MCP_IMPLEMENTATION=NO
MCP_IMPLEMENTED=NO
SKILL_IMPLEMENTED=NO
FRONTEND_CHANGED=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1 的面积 authority、canonical zone-plan 校验和 V2.0 calculator 接入由
`docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md`
记录；上述 block 保留 P1 dispatch 时的历史授权快照。

Current V2.1 P2 MCP / Doubao Skill integration state:

```text
TASK_ID=V21_P2_FACTORY_POWER_MCP_DOUBAO_SKILL_INTEGRATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37
ACTIVE_GOVERNANCE_LANE=V2.1_P2
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=IMPLEMENTATION_ACTIVE
P2_EXECUTED=YES
MCP_TOOL_COUNT=6
NEW_MCP_TOOL=preview_factory_power
NEW_MCP_TOOL_POSITION=6
EXISTING_FIVE_TOOL_ORDER_CHANGED=NO
MCP_INPUT_REMAINS_FIVE_KEY=YES
FACTORY_POWER_FORMULA_CHANGE=NO
P1_AUTHORITY_ADAPTER_CHANGED=NO
V20_CALCULATOR_CHANGED=NO
V20_SHARED_PRESENTATION_CHANGED=NO
CONCEPT_PREVIEW_STAGE_COUNT=5
V18_SKILL_CHANGED=NO
V18_RUNBOOK_CHANGED=NO
FRONTEND_CHANGED=NO
DATABASE_MIGRATION=NO
OUTBOUND_LIVE_AILY_SESSION=NO
RELEASE_CLOSURE=UNAUTHORIZED
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2 实施记录：
`docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md`。
此阶段只增加 MCP/Skill/runbook 集成，不关闭无关 TD 行，也不授权发布或
下一 feature lane。

Current V2.1 release-closure / v2.1.0 readiness state:

```text
TASK_ID=V21_RELEASE_CLOSURE_READINESS_R1
TARGET_RELEASE=v2.1.0
BASE_MAIN_SHA=b314f08c74296e23e2a1729dd4f84dc8387c7a4e
BASE_MAIN_CI_RUN_ID=34349430563
BASE_MAIN_CI_RESULT=SUCCESS
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=MERGED
V21_IMPLEMENTATION_COMPLETE=YES
V21_P3_DEFINED=NO
V21_P3_EXECUTED=NO
V21_RELEASE_CANDIDATE=YES
V2_1_0_RELEASE_READY=YES
ACTIVE_GOVERNANCE_LANE=V2.1_RELEASE_CLOSURE
RELEASE_CLOSURE_AUTHORIZED=YES
RELEASE_CLOSURE_EXECUTED=YES
TAG_CREATION_AUTHORIZED=NO
TAG_MOVEMENT_AUTHORIZED=NO
GITHUB_RELEASE_CREATION_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

这是 readiness determination，不是 Ready、Merge、tag、GitHub Release、部署或
下一 feature lane 的执行授权；TD-008、TD-019、TD-021、TD-024 等无关技术债
保持各自真实状态。

| ID | Status | Priority | Module | Cause | Current Impact | Temporary Approach | Permanent Resolution | Target Task / Version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TD-001 | **Resolved** | High | bootstrap/settings | ~~Local runtime still defaults to SQLite while repo target architecture documents PostgreSQL/pgvector + Redis~~ | ~~Runtime behavior diverges from README and roadmap~~ | ~~Keep SQLite for local baseline and document the mismatch~~ | Runtime configuration aligned: dual SQLite/PostgreSQL modes with explicit env-driven selection | Task 1 |
| TD-002 | **Resolved** | High | bootstrap/app | ~~Route module contains planning orchestration, power formulas, request flattening, and response assembly~~ | ~~API layer violates intended architecture and is hard to test in isolation~~ | ~~Keep current endpoints stable and document boundaries~~ | Orchestration extracted to `modules/planning/application/service.py` | Task 1 |
| TD-003 | **Superseded** | High | calculations/zone_planning | Demo coefficients were embedded in Python and not registered in persistent storage | Coefficient registry now exists; **demo coefficient conflicts in `docs/audit/coefficient-inventory.md` remain unresolved** | Do not silently promote conflicting demo values | Explicit review/promotion only | V0.5+ |
| TD-004 | Open | Medium | planning_agent | Only `ModelGateway` exists; embedding gateway/session workflow is missing | Agent feature scope is narrower than target architecture | Keep fake extraction behavior and explicit limitations | Add `EmbeddingGateway`, session state, and tool confirmation flow | Task 8 |
| TD-005 | **Superseded** | High | knowledge | Knowledge service was in-memory substring search only | Durable ingestion/chunking/retrieval delivered; production retrieval hardening continues | Consumer-only workflow provenance remains separate authority | Continue ops/quality hardening | Task 7 follow-up |
| TD-006 | **Superseded** | High | reports | Report generation wrote files directly without persisted report versions | Persisted revisions and API delivery exist; assembler reads persisted results only | Reports must not recalculate formulas | Align report consumers with five-stage canonical mapping | V0.5 P3 |
| TD-007 | **Resolved** | Medium | frontend | ~~`App.vue` was a monolith~~ | ~~UI maintenance cost is high~~ | Delivered at `v0.5.0` | Five-stage workbench wiring complete | V0.5 |
| TD-008 | Open | Medium | frontend/backend demo | Demo defaults and power/equipment reference data are duplicated between backend and frontend | V1.4 closed **operator five KEY + storage-day defaults** onto `samples/v09-process-input/manifest.json`; V1.6 closed **evaporator/condenser fan 10/8 kW(e)** onto `samples/v05-local-workbench/manifest.json`; leftover V0.4 `demo_overview` and nine-zone equipment catalogs may still diverge; V1.5 overwrites wall/roof catalog `200`/`100` from zone geometry on the five-stage bind; V1.7 surfaces per-zone cooling components; V1.8 stamps refrigerated-zone height **4.0 m** (V18-H1) and zone-plan band **cold end** 8 / 1 / −18 °C (V18-T1) on the operator-minimal path; product mass stays v05 **20 t/day** per zone | Operator KEY/days from v09 sample; fan kW(e) from v05 sample via `demo_power_fan_catalog`; envelope wall/roof from shared bind (demo square plan); T/H from `demo_zone_thermal_catalog` (V18-T1 / V18-H1) | Unify remaining equipment catalog copies; product-mass catalog recut stays unauthorized | V1.8 |
| TD-009 | Resolved | Medium | quality | Backend formatting check failed on two files | CI truthfully shows formatting drift | Do not suppress the check | Reformatted `demo_overview.py` and `investment.py` via `ruff format` in Task 0 completion | Task 0 |
|| TD-010 | **Resolved** | Medium | dependencies/bootstrap | ~~Global singleton services are created at import time~~ | ~~Startup side effects complicate testing and environment changes~~ | ~~Keep current dependency wiring for baseline stability~~ | Import-time singletons removed; lifecycle managed via FastAPI lifespan | Task 1 |
|| TD-011 | **Resolved** | High | projects/versioning | ~~ProjectVersion lacked state machine, immutability, and snapshot isolation~~ | ~~Approved versions could be modified, no audit trail for state changes~~ | ~~Keep basic approval check~~ | Implemented full version state machine with immutability rules, snapshots, and audit events | Task 2 |
|| TD-012 | **Resolved** | High | coefficients | ~~Engineering coefficients hardcoded across modules without governance~~ | ~~No audit trail, inconsistent values, no versioning~~ | ~~Keep hardcoded values with demo markers~~ | Implemented coefficient registry with Definition/Revision split, state machine, scope resolution, and snapshot integration | Task 3 |
|| TD-013 | **Resolved** | High | calculations | ~~Core calculations scattered across modules with inconsistent input handling~~ | ~~No traceability, no Decimal precision, no coefficient integration~~ | ~~Keep existing calculation logic~~ | Implemented deterministic calculation kernel with Decimal, CoefficientSet integration, and step-by-step traceability | Task 4 |
| TD-014 | **Resolved** | High | calculations/cooling | ~~Cooling load and equipment capability used float arithmetic with hardcoded factors~~ | ~~No step traceability, kW(r)/kW(e) mixed, no temperature-level grouping~~ | ~~Keep legacy run_cooling_load and run_equipment_requirement~~ | Deterministic cooling load (envelope/product/infiltration/internal/defrost), equipment capability (evaporator/compressor/condenser), and installed power calculators with Decimal, CoefficientSet, and step traceability | Task 5 |
| TD-015 | **Resolved** | High | workbench/orchestration | ~~V0.4 local workbench persisted only three helper calculators; canonical five-stage chain not wired~~ | ~~Workflow/scheme/report identity drift~~ | Delivered at `v0.5.0` | Five-stage persistence and consumer alignment complete | V0.5 |
| TD-016 | **Resolved** | High | reports/assembly | Five-stage persisted results were not fully mapped to reviewable report JSON at V0.6 P0 freeze | Delivered at `v0.7.0` on unmodified `create_app` | Keep V0.6 P5 fail-closed evidence | Operator trust loop closed | V0.7 P3A/P3B/P5 |
| TD-017 | **Resolved** | High | reports/bootstrap | `_get_report_service` does not inject `project_service` | Delivered at `v0.7.0` | Evaluation tests wired `project_service` only | Production composition fix | V0.7 P3A |
| TD-018 | **Resolved** | High | schemes/api | Public `scheme-runs` persist legacy `source_mode`; no production route | Delivered at `v0.7.0` | Loader avoided legacy scheme-runs | Public `production-scheme-runs` API | V0.7 P3B |
| TD-019 | Open | Medium | coefficients/inputs | Metadata, bundle optional leaves, and embedded defaults can diverge | Traceability and display can disagree with effective inputs | Keep demo/unverified markers; do not silent-merge | Integrity matrix + expert decisions E1–E8 | V0.7 P1 / V0.8 |
| TD-020 | **Resolved** | High | workbench/inputs | Operator 工程输入 required full `EngineeringInputBundleV1` KEY form | Delivered at `v0.8.0` | Keep V0.7 full-bundle path as compatibility | `OperatorProcessInputV1` five KEY leaves + assembler | V0.8 |
| TD-021 | Open | High | zone_planning / workbench | V0.8 KEY and planner/UI/export do not match the V0.9 lock | Unused KEY, no shipping_channel, review mixed with export, layout | P0 contract only; do not implement off-plan | V0.9 P1–P7 after dispatch | V0.9 |
| TD-022 | **Resolved** | Medium | reports/localization | ~~Investment calculator persists Chinese ``item_name``; render uses ``investment.{item_name}`` as catalog keys~~ | Draft export projects stable English ``item_key`` catalog keys | Leftover Chinese catalog keys remain for persisted report JSON | Calculator emits ``item_key``; reports-owned legacy map; snapshot admits optional ``item_key``; unknown names fail closed | post-v0.9 |
| TD-023 | **Resolved** | Medium | workflow | ~~Guided workflow still names the first step PROJECT_INPUT and V0.4 `save_inputs` snapshot~~ | Delivered at V1.4: first step is `OPERATOR_PROCESS_INPUT` / 工程输入; V0.4 `save_inputs` alone does not complete it | Keep Path A `save_inputs` as compatibility | Recut delivered | V1.4 |
| TD-024 | Open | Medium | aily | V0.7 P6 froze Aily paper only; outbound Feishu skill/session is still unwired | Chat in 豆包工作伙伴 cannot open a live session from this app | V1.1 inbound REST + MCP Streamable HTTP; V1.2 five-stage inbound preview at `v1.2.0`; V1.3 in-memory workbench lineage at `v1.3.0` (still no outbound) | Outbound live session after Charles supplies tenant skill wiring | later |

## POST-V2.1.1 current rule note

The post-`v2.1.1` engineering-rule adjustment lane does not close or reclassify
unrelated technical debt. It records current deterministic values (primary
precooling 7 batches/day, sorting/packing final-area factor 1.1, and defrost
simultaneous use 0.20) while preserving the existing demo-coefficient and
consumer-boundary debt register. In particular, TD-008, TD-019, TD-021, and
TD-024 remain in their existing states.

## V2.1.2 patch release closure note

The v2.1.2 closure records the already-merged PR #266 effective-working-hours
and factory-power rule adjustment. It does not resolve, downgrade, or otherwise
reclassify unrelated technical debt. TD-008, TD-019, TD-021, and TD-024 remain
in their existing states. The current factory-power identity is
`factory_power_estimation@2.0.0-p2`; historical p1 evidence remains immutable.

```text
TASK_ID=V2_1_2_PATCH_RELEASE_CLOSURE_R1
TARGET_RELEASE=v2.1.2
PATCH_TARGET_SHA=bdbedf885b8b42a3ca18aec9df2746a9505fee33
V2_1_2_RELEASE_READY=YES
PRODUCTION_CODE_CHANGED=NO
DATABASE_MIGRATION_CHANGED=NO
DEPLOYMENT_CHANGED=NO
NO_UNRELATED_TECHNICAL_DEBT_RECLASSIFIED=YES
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
