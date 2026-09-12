# Development Plan

## 当前治理状态（2026-09-12）

```ini
CURRENT_RELEASE=v2.1.2
V2_1_2_RELEASED=true
RELEASE_TARGET_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
DEPLOYMENT_EXECUTED=false
ACTIVE_GOVERNANCE_LANE=V2.2_P1
V22_P0_STATUS=MERGED
P1A_AUTHORIZED=true
P1A_STATUS=FOUNDATION_DRAFT_REVIEW_PARTIAL_ENGINEERING_AUTHORITY
P2_AUTHORIZED=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

v2.1.2 已正式发布。下文 V2.1.2 closure 的 Draft、TAG_AUTHORIZED=NO、
RELEASE_AUTHORIZED=NO 及其他早期授权块均是历史 snapshot，不再代表当前发布状态。
当前工作为独立授权的 V2.2 P1A 定尺/邻接基础，参见
`docs/tasks/V2_2-version-plan.md` 和 ADR-044。
P0 历史快照仍是文档/schema/architecture evidence；P1A 增加纯 backend foundation，
4 区可复用上游网格定尺，8 区因缺少 profile 明确 BLOCKED。
authority matrix 见 `docs/tasks/V2_2-P1A-zone-dimensioning-adjacency-foundation.md`。
场地 placement、第七 MCP 工具和投影均未实现，P2 未授权。
现有六工具、五 KEY 与工程计算保持 v2.1.2 基线。
网格容量几何需保留；缺少的定尺/access profile 及人车避让尺寸须另行工程决策。
本任务未关闭无关技术债；TD-008、TD-019、TD-021、TD-024 保持原有状态。

> **V0.9 P0 freeze (2026-08-27, `main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`,
> release `v0.8.0`):** Tasks 0–12 below remain the original roadmap register.
> V0.5 five-stage workbench is **complete** at tag `v0.5.0`. V0.6 report
> assembly is **complete** at tag `v0.6.0`. V0.7 trust loop is **complete**
> at tag `v0.7.0` (`docs/tasks/V0_7-P0-trust-loop-contract.md`). V0.8
> operator-minimal process input is **complete** at tag `v0.8.0`
> (`docs/tasks/V0_8-P0-operator-minimal-input-contract.md`). **Historical
> umbrella at this freeze:** V0.9 P0 contract (`docs/tasks/V0_9-P0-version-contract.md`)
> plus overall plan (`docs/tasks/V0_9-version-plan.md`). V0.9 operator
> workbench is **complete** at `v1.0.0`. **V1.1 豆包工作伙伴 inbound connector
> is complete at `v1.1.0`.** V1.2 five-stage conversation preview is
> **complete at `v1.2.0`**. V1.3 inbound preview lineage is **complete at
> `v1.3.0`**. V1.4 operator workbench debt is **complete at `v1.4.0`**.
> V1.5 cooling envelope wall/roof geometry bind is **complete at `v1.5.0`**.
> V1.6 power-fan demo catalog is **complete at `v1.6.0`**. V1.7 per-zone
> cooling component surface is **complete at `v1.7.0`**. V1.8 per-zone
> temperature and height remains complete at its authorized implementation
> lane. **V1.9 implementation is complete on `main@675fa8adfc58e2362101079d83393e90706505b2`**:
> the P0 contract is frozen, P1 is merged through PR #254, the report
> projection regression is closed, and the V0.7 golden controlled evolution is
> complete. V1.9 release closure is complete at `v1.9.0`. V2.0 P0, P1, and P2
> are complete and merged, and `v2.0.0` is released at
> `main@a7049ca93d238013c0cf62069fe1e0a89ff834d7`. V2.1 P0 upstream authority +
> Doubao MCP contract freeze, P1 backend upstream authority adapter, and P2
> factory-power MCP/Doubao Skill integration are merged; **active governance
> stage:** V2.1 release closure/readiness for `v2.1.0`.
> Later feature umbrellas (outbound live Aily session, remaining TD-008 equipment
> catalogs, and zone thermal catalog recut) stay unauthorized until Charles dispatches.

## V1.9 P0 Contract Freeze (complete)

V1.9 P0 freezes the nine-zone minimum-estimation reference matrix and reuses
the existing `zone_plan.result.zones[]` lineage. Pre-cooling uses final
`position_count`; area-type zones use canonical `required_area_m2` with the
semantic `PLANNED_ZONE_AREA`. The output semantic is
`minimum_estimated_cooling_load_kw_r` and must be expressed as not less than
the reference basis. The P0 contract is frozen. Its historical authorization
flags remain preserved in the P0 contract document; the separately authorized
P1 implementation is now merged and complete. No cooling-load formula recut is
authorized.

**P0 documents:** `docs/tasks/V1_9-version-plan.md`,
`docs/tasks/V1_9-P0-per-zone-cooling-estimation-basis-contract.md`, and
`docs/architecture/ADR-041-per-zone-cooling-estimation-basis.md`.

## V1.9 Implementation Closure

```text
V19_STATUS=IMPLEMENTATION_COMPLETE
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_MERGED=YES
PR254_MERGED=YES
PR254_MERGE_SHA=675fa8adfc58e2362101079d83393e90706505b2
REPORT_PROJECTION_REGRESSION=CLOSED
V07_GOLDEN_EVOLUTION=COMPLETE
RUNTIME_RULE_COUNT=9
V1_9_0_RELEASE_READY=YES
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## V2.1.2 Patch Release Closure（当前；Draft）

当前治理 lane 是 v2.1.2 patch release closure/readiness。PR #266 已合并，
exact-main CI 已在 `bdbedf885b8b42a3ca18aec9df2746a9505fee33` 成功；本 lane 只
记录 readiness evidence，不改变生产代码、MCP/Skill、数据库或部署边界。V2.1.2
继续使用当前 14 h 工时与 factory-power p2 identity，并保留 v2.1.0/v2.1.1
历史 release evidence。

```text
TASK_ID=V2_1_2_PATCH_RELEASE_CLOSURE_R1
TARGET_RELEASE=v2.1.2
BASE_RELEASE=v2.1.1
BASE_RELEASE_SHA=c9ce6e7399ec2a163ab4c7c7339b828a86abbf08
PATCH_TARGET_SHA=bdbedf885b8b42a3ca18aec9df2746a9505fee33
V2_1_2_PATCH_SCOPE_CLOSED=YES
V2_1_2_RELEASE_CANDIDATE=YES
V2_1_2_RELEASE_READY=YES
ACTIVE_GOVERNANCE_LANE=V2.1.2_RELEASE_CLOSURE
PRODUCTION_CODE_CHANGED=NO
FRONTEND_PRODUCTION_CODE_CHANGED=NO
DATABASE_SCHEMA_CHANGED=NO
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The V1.9 release-closure PR was documentation/governance only and has completed;
`v1.9.0` is already released. V2.0 release closure subsequently completed and
`v2.0.0` is released. The active governance work is the separate V2.1
release-closure/readiness lane; it remains Draft until separately reviewed.

## V2.0 Implementation Closure

V2.0 consists of exactly three formal implementation stages: P0 contract freeze,
P1 backend deterministic canonical calculation, and P2 workbench + Aily/Doubao
read-only presentation alignment. All three are merged on `main`; there is no
defined V2.0 P3. The `v2.0.0` release closure and release execution are complete;
the active lane is the separate V2.1 release-closure/readiness evaluation.

```text
V20_IMPLEMENTATION_COMPLETE=YES
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=MERGED
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

The historical closure/readiness record is maintained in
`docs/tasks/V2_0-release-closure-readiness.md`; its later release execution is
recorded at `v2.0.0`. V2.1 P0, P1, and P2 are merged; the active V2.1
release-closure/readiness lane is governed by `docs/tasks/V2_1-version-plan.md`
and does not imply release execution, deployment, or a next feature lane.

## V2.1 P0 Contract Freeze（已合并；历史 dispatch）

V2.1 P0 was the governance lane after the `v2.0.0` release and is now merged. It freezes
the upstream authority from `cold_room_zone_plan@1.0.0` to the existing
`factory_power_estimation@2.0.0-p1` calculator, resolves factory/cold-storage
area semantics through canonical zone rows and the refrigerated registry, and
appends the future `preview_factory_power` contract at MCP position 6. It does
not implement the adapter, MCP tool, Skill, database migration, or runtime code;
the authorization block below is retained as the historical P0 snapshot.

```text
V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1
TARGET_VERSION=v2.1.0
BASE_RELEASE=v2.0.0
BASE_MAIN_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
ACTIVE_GOVERNANCE_LANE=V2.1_P0
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
P1_EXECUTED=NO
P2_EXECUTED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The formal contract is
`docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md`;
the decision record is
`docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md`.

## V2.1 P1 Factory-Power Upstream Authority Adapter（已合并；历史 dispatch）

P1 was separately authorized on `main@1d0a8e23f550b3c9ced413932fde0995acb227c0`.
It implements only the backend adapter that validates the canonical
`cold_room_zone_plan@1.0.0`, binds factory/cold-storage areas from the 12/9 zone
authority, and invokes the unchanged `factory_power_estimation@2.0.0-p1`.
The historical branch was Draft; the P2 authorization state is recorded in the
separate current section below.

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

P1 历史实施记录：
`docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md`。

## V2.1 P2 Factory-Power MCP / Doubao Skill Integration（已合并；历史 dispatch）

P0 and P1 are merged on `main`, and P2 subsequently merged. P2 connects the existing five-key operator path
and canonical zone-plan replay to the already-authoritative P1 adapter, the
unchanged V2.0 calculator, and the existing shared presentation projector. It
appends `preview_factory_power` as MCP tool 6, creates the V2.1 Doubao Skill
contract and runbook, and leaves the original five tools, five-stage
concept-preview flow, calculator formulas, frontend, database, and V1.8 Skill
unchanged. The block below is the historical P2 dispatch snapshot; release closure
is now the active, separately gated lane.

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

## Task 0: Local Baseline, Repository Audit, And Governance

- Goal: preserve the current local project safely and establish audit/governance artifacts.
- Scope: baseline push, sensitive review, audit docs, roadmap, AGENTS rules, CI baseline, PR template.
- Non-scope: business logic refactors, calculator rewrites, database redesign.
- Inputs: current local repository snapshot and GitHub target repository.
- Deliverables: baseline commit/tag, governance branch, audit docs, governance files.
- Database changes: none.
- Tests: repository/tooling checks and current runnable validation commands.
- Acceptance: baseline exists on `main`, governance branch exists, draft PR is open.
- Risks: existing history contamination, wrong remote, sensitive file leakage.
- Rollback: reset remote branch to baseline tag or close governance PR; local preservation branch remains.
- Recommended branch name: `codex/task-0-repository-audit`
- Recommended PR title: `Task 0: Audit and standardize existing cold-storage project`

## Task 1: Existing System Runnability And Quality Baseline

- Goal: align current runtime behavior, bootstrap boundaries, and quality gates with the actual repository state.
- Scope: runtime config cleanup, formatting fixes, startup wiring cleanup, CI truthfulness.
- Non-scope: new business calculations and feature expansion.
- Inputs: Task 0 audit findings and validation baseline.
- Deliverables: clean quality gates, documented environment selection, thinner bootstrap seams.
- Database changes: possible config/migration wiring only, no schema redesign.
- Tests: pytest, ruff, mypy, frontend quality, migration smoke checks.
- Acceptance: validation baseline passes without known formatting drift; runtime docs match implementation.
- Risks: environment-specific regressions when untangling global singletons.
- Rollback: revert the Task 1 PR and keep baseline tag untouched.
- Recommended branch name: `codex/task-1-quality-baseline`
- Recommended PR title: `Task 1: Stabilize current runtime and quality baseline`

## Task 2: Projects And Immutable Versions

- Goal: harden project/version lifecycle and approval lock behavior.
- Scope: application services, persistence cleanup, response schema shaping, version immutability rules.
- Non-scope: coefficient governance and new engineering formulas.
- Inputs: existing project/version ORM and API endpoints.
- Deliverables: robust version workflow with explicit approved-lock behavior.
- Database changes: additive schema changes if needed for version metadata.
- Tests: unit, integration, approval-lock regression tests.
- Acceptance: approved versions cannot be modified and version APIs are consistently typed.
- Risks: accidental change to existing project/version behavior.
- Rollback: revert PR and restore previous API behavior from baseline tag.
- Recommended branch name: `codex/task-2-project-versions`
- Recommended PR title: `Task 2: Harden project and immutable version workflow`

## Task 3: Engineering Coefficient Registry

- Goal: move demo coefficients into a structured, reviewable registry.
- Scope: persistence model, service APIs, migrations, review metadata, source/version tracking.
- Non-scope: new cooling-load or equipment formulas.
- Inputs: embedded coefficients in calculation modules.
- Deliverables: coefficient registry, retrieval API/service, audit trail.
- Database changes: new coefficient tables and migrations.
- Tests: registry CRUD, source metadata, review-flag propagation.
- Acceptance: calculators can reference registered coefficients with source and review metadata.
- Risks: coefficient drift during extraction from embedded constants.
- Rollback: revert PR and keep embedded coefficient map.
- Recommended branch name: `codex/task-3-coefficient-registry`
- Recommended PR title: `Task 3: Add coefficient registry and review metadata`

## Task 4: Throughput, Inventory, Storage, Precooling, And Area Calculations

- Goal: formalize deterministic engineering calculators and move orchestration out of routes.
- Scope: calculator contracts, input validation, service wiring, result metadata, persistence hooks.
- Non-scope: cooling load and equipment sizing.
- Inputs: current `CalculationService` and zone planning inputs.
- Deliverables: stable deterministic calculator interfaces and API/application integration.
- Database changes: none or additive result metadata only.
- Tests: calculator unit tests and endpoint/application regression tests.
- Acceptance: calculations are deterministic, typed, and route handlers stay thin.
- Risks: behavior drift if formulas are accidentally changed during extraction.
- Rollback: restore previous calculator service and keep formula outputs from baseline.
- Recommended branch name: `codex/task-4-core-calculations`
- Recommended PR title: `Task 4: Extract and stabilize core deterministic calculations`

## Task 5: Cooling Load And Equipment Capability

- Goal: isolate cooling-load and equipment capability calculations with deterministic services.
- Scope: cooling-load contracts, equipment requirement logic, metadata, persistence.
- Non-scope: scheme comparison, knowledge retrieval, UI refactor.
- Inputs: current calculator service and demo equipment assumptions.
- Deliverables: dedicated deterministic load/equipment calculation path.
- Database changes: none or additive result storage fields.
- Tests: load/equipment unit tests and result persistence coverage.
- Acceptance: cooling-load and equipment capability run outside API-route formula code.
- Risks: hidden assumptions in current helper logic.
- Rollback: revert PR and fall back to baseline helper path.
- Recommended branch name: `codex/task-5-cooling-and-equipment`
- Recommended PR title: `Task 5: Isolate cooling-load and equipment calculations`

## Task 6: Cold-Room Scheme Generation And Comparison

- Goal: formalize scheme generation and comparison as module-owned behavior.
- Scope: deterministic scheme generation, scoring, assumptions, comparison outputs.
- Non-scope: knowledge indexing and chat workflows.
- Inputs: current `SchemeService` and zone-planning outputs.
- Deliverables: explicit scheme-generation API/application path and scoring metadata.
- Database changes: optional additive persistence for scheme runs and weight sets.
- Tests: scheme generation, comparison scoring, API regression tests.
- Acceptance: scheme output is deterministic and versionable.
- Risks: implicit scoring assumptions in current sample logic.
- Rollback: revert PR and preserve sample scheme generation.
- Recommended branch name: `codex/task-6-schemes`
- Recommended PR title: `Task 6: Formalize cold-room scheme generation and comparison`

## Task 7: Professional Knowledge Base

- Goal: implement durable knowledge ingestion and retrieval.
- Scope: upload metadata, parsing, chunking, retrieval, fake embeddings, OCR boundaries.
- Non-scope: unrestricted external OCR or production search infra hardening.
- Inputs: in-memory `KnowledgeService` baseline.
- Deliverables: persisted knowledge documents and hybrid retrieval service.
- Database changes: document/chunk metadata tables and possibly vector support.
- Tests: parser, indexing, retrieval, and `requires_ocr` behavior.
- Acceptance: knowledge results are durable, searchable, and explicitly reviewed.
- Risks: document parsing variability and storage growth.
- Rollback: revert PR and keep in-memory sample search.
- Recommended branch name: `codex/task-7-knowledge-base`
- Recommended PR title: `Task 7: Build durable knowledge ingestion and retrieval`

## Task 8: Cold Storage Planning Agent

- Goal: add sessioned planning-agent workflows that orchestrate tools without doing engineering math.
- Scope: session model, message flow, tool selection, confirmation/authorization boundaries, gateway interfaces.
- Non-scope: direct DB access from agent code and direct formula execution in prompts.
- Inputs: current fake gateway and agent service baseline.
- Deliverables: session-aware agent workflow with fake/default gateways and test coverage.
- Database changes: additive agent session/message tables if needed.
- Tests: structured-output, tool selection, missing-parameter, and authorization tests.
- Acceptance: agent proposes changes and delegates calculations without fabricating engineering values.
- Risks: hidden prompt coupling and cross-layer leakage.
- Rollback: revert PR and retain fake extraction endpoint only.
- Recommended branch name: `codex/task-8-planning-agent`
- Recommended PR title: `Task 8: Add sessioned planning-agent orchestration`

## Task 9: Word And Excel Reports

- Goal: make report generation durable and auditable.
- Scope: persisted report versions, templates, download endpoints, consistency checks.
- Non-scope: recalculating formulas inside report templates.
- Inputs: current `ReportService` sample generation path.
- Deliverables: versioned report artifacts and API delivery.
- Database changes: additive report metadata tables.
- Tests: report generation, API consistency, artifact existence, and versioning tests.
- Acceptance: reports are produced from persisted results and tracked by version.
- Risks: file-system versus object-store ownership decisions.
- Rollback: revert PR and keep sample docx/xlsx generation only.
- Recommended branch name: `codex/task-9-reports`
- Recommended PR title: `Task 9: Add durable report generation and delivery`

## Task 10: Frontend Planning Workbench

- Goal: modularize the workbench and align it with backend-owned data flows.
- Scope: feature modules, typed API clients, workflow views, compact tables, agent entry, responsive layout.
- Non-scope: speculative future screens or unrelated visual redesigns.
- Inputs: current monolithic `App.vue` baseline and backend APIs.
- Deliverables: maintainable frontend feature structure and workflow-driven UI.
- Database changes: none directly.
- Tests: frontend unit/integration view tests, build, lint, typecheck.
- Acceptance: no engineering formulas are duplicated in UI components and workflow views are modular.
- Risks: regressions in current compact workbench flows.
- Rollback: revert PR and return to baseline single-component UI.
- Recommended branch name: `codex/task-10-frontend-workbench`
- Recommended PR title: `Task 10: Modularize the frontend planning workbench`

## Task 11: Evaluation And Pilot Readiness

- Goal: assemble pilot-grade sample projects, documents, and evaluation checks.
- Scope: fixtures, demo scripts, acceptance verification, result consistency checks.
- Non-scope: production deployment hardening.
- Inputs: previous task outputs and sample documents.
- Deliverables: evaluation artifacts and repeatable pilot verification.
- Database changes: optional seed data only.
- Tests: acceptance scripts and consistency checks.
- Acceptance: a defined demo/pilot scenario can be reproduced from repository artifacts.
- Risks: sample data drift from current planning logic.
- Rollback: remove new evaluation fixtures and scripts.
- Recommended branch name: `codex/task-11-evaluation`
- Recommended PR title: `Task 11: Add evaluation baseline and pilot fixtures`

## Task 12: Productionization And Security

- Goal: harden deployment, secrets, observability, and environment separation.
- Scope: environment management, deployment docs, Docker/runtime verification, CI expansion, security controls.
- Non-scope: unrelated feature changes.
- Inputs: stabilized runtime/configuration from earlier tasks.
- Deliverables: production-readiness controls and documented operating model.
- Database changes: environment/configuration related only unless explicitly needed.
- Tests: deployment smoke tests, compose checks, migration validation, security/config checks.
- Acceptance: documented production path with clear rollback and secret-handling rules.
- Risks: infra drift between local and deployment environments.
- Rollback: revert hardening changes and fall back to baseline local-only operating model.
- Recommended branch name: `codex/task-12-productionization`
- Recommended PR title: `Task 12: Harden deployment, security, and operations`

## V2.1 Release Closure / v2.1.0 Readiness（当前；本分支 Draft）

V2.1 P0、P1、P2 已在 `main` 合并；V2.1 没有定义 P3。当前 active governance
lane 是 v2.1.0 release closure/readiness，记录于
`docs/tasks/V2_1-release-closure-readiness.md`。本节只固化当前治理事实，不改变
无关 roadmap task 或 technical-debt 状态。

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

Readiness determination 不等于 Ready、Merge、tag、GitHub Release、部署或下一
feature lane 的执行授权。

## POST-V2.1.1 Engineering Rule Adjustments（当前；Draft）

当前 follow-up lane 只记录三项已授权的工程规则调整：一级预冷 7 批次/日，
分选包装矩形排布最终面积乘 1.1，以及化霜同时使用系数 0.20。历史 V0.7/V0.9
回放保持显式旧参数；V2.0/V2.1 的 calculator identity、MCP 六工具合同和发布
证据不被重写。详见
`docs/tasks/POST-V2_1_1-engineering-rule-adjustments.md`。

```text
ACTIVE_GOVERNANCE_LANE=POST_V2_1_1_ENGINEERING_RULE_ADJUSTMENTS
FORMULA_AUTHORITY=POST-V2.1.1-charles-engineering-rule-adjustments
MCP_TOOL_COUNT=6
DATABASE_MIGRATION_CHANGED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
