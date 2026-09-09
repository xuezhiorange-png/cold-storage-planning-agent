# Current State Audit

This audit records the repository exactly as found on the preserved baseline.

> **V0.9 P0 freeze (2026-08-27, `main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`,
> release `v0.8.0`):** Sections 1–30 below remain the Task 0 preserved snapshot.
> They are **not** current truth for delivered capabilities. See §31 for the
> post–V0.5 delta, §32 for the V0.7 trust-loop (delivered at `v0.7.0`),
> §33 for the V0.8 operator-minimal input recut (delivered at `v0.8.0`,
> `docs/tasks/V0_8-P0-operator-minimal-input-contract.md`), §34 for V0.9,
> and §35 for V1.1 豆包/Aily inbound zone-plan (complete at `v1.1.0`);
> §36 for V1.2 five-stage conversation preview (complete at `v1.2.0`);
> §37 for V1.3 conversation preview lineage (complete at `v1.3.0`);
> §38 for V1.4 operator workbench debt (complete at `v1.4.0`);
> §39 for V1.5 envelope wall/roof geometry bind (complete at `v1.5.0`);
> §40 for V1.6 power-fan demo catalog (complete at `v1.6.0`);
> §41 for V1.7 per-zone cooling component surface (complete at
> `v1.7.0`); §42 for V1.8 per-zone temperature and height
> (`docs/tasks/V1_8-version-plan.md`, implementation authorized).
> Prior contract: `docs/tasks/V0_7-P0-trust-loop-contract.md`.
> V0.9 contract: `docs/tasks/V0_9-P0-version-contract.md`.
> Released contract: `docs/tasks/V1_2-P0-aily-five-stage-preview-contract.md`.

## 1. Current Directory Tree

Core tracked tree:

```text
.
├── AGENTS.md
├── Makefile
├── README.md
├── docker-compose.yml
├── backend/
│   ├── alembic.ini
│   ├── alembic/
│   ├── pyproject.toml
│   ├── src/cold_storage/
│   └── tests/
├── docs/
│   ├── DEVELOPMENT.md
│   ├── TECH_DEBT.md
│   ├── architecture/
│   └── engineering/
└── frontend/
    ├── package.json
    ├── src/
    └── tests/
```

Impact:
- The repository already contains backend, frontend, migrations, tests, and
  governance docs.

Suggested handling:
- Keep the current structure for Task 0 and refactor incrementally.

## 2. Backend Entry

- File: `backend/src/cold_storage/bootstrap/app.py`
- Location: `create_app()` plus inline route handlers and helper functions
- Current impact:
  the backend boots from one large module that owns FastAPI app creation, route
  request/response models, orchestration helpers, demo planning logic, and power
  estimation helpers.
- Suggested handling:
  split API routes and orchestration helpers into module-owned application
  services in Task 1 and later calculator tasks.

## 3. Frontend Entry

- Files: `frontend/src/main.ts`, `frontend/src/App.vue`
- Location: `App.vue` owns the entire workbench view state and demo data
- Current impact:
  the workbench is usable, but nearly all UI behavior is concentrated in one
  component.
- Suggested handling:
  split by feature and workflow step in Task 10.

## 4. Current Technical Stack

- Backend files: `backend/pyproject.toml`, `backend/src/cold_storage/bootstrap/app.py`
- Frontend files: `frontend/package.json`
- Current impact:
  actual runtime stack is FastAPI + SQLAlchemy + Alembic + SQLite baseline on
  the backend, Vue 3 + Vite on the frontend.
- Suggested handling:
  keep README and roadmap explicit about current versus target stack.

## 5. Python And Node Dependency Management

- Python: `backend/pyproject.toml`, `backend/uv.lock`, `uv`
- Node: `frontend/package.json`, `frontend/package-lock.json`, `npm`
- Current impact:
  dependency management is explicit and reproducible enough for local baseline
  work.
- Suggested handling:
  keep `uv` and `npm ci` in CI; no toolchain replacement in Task 0.

## 6. Database Type

- Files: `backend/src/cold_storage/bootstrap/settings.py`, `backend/alembic.ini`
- Location: `Settings.database_url`, Alembic `sqlalchemy.url`
- Current impact:
  default runtime database is SQLite (`cold_storage_dev.db`), not PostgreSQL.
- Suggested handling:
  align current runtime configuration with target architecture in Task 1.

## 7. Database Connection Method

- Files: `backend/src/cold_storage/bootstrap/dependencies.py`,
  `backend/src/cold_storage/modules/projects/infrastructure/database.py`
- Location: import-time `create_database_project_service(get_settings().database_url)`
- Current impact:
  the project service is created globally at import time, which hard-codes
  startup behavior and environment coupling.
- Suggested handling:
  move to app-factory driven service construction in Task 1.

## 8. Migration Status

- Files: `backend/alembic/env.py`, `backend/alembic/versions/*.py`
- Location: Alembic metadata points to `ProjectRecord` ORM metadata
- Current impact:
  migrations work locally for SQLite, but current validation did not prove the
  PostgreSQL path.
- Suggested handling:
  add PostgreSQL migration validation in Task 1 or Task 12.

## 9. Docker And Deployment

- File: `docker-compose.yml`
- Location: Postgres + Redis services only
- Current impact:
  Compose expresses a target infra layer, but the local backend does not consume
  it by default.
- Suggested handling:
  treat Compose as target infra, not current truth, until runtime wiring is
  aligned.

## 10. Implemented APIs

- File: `backend/src/cold_storage/bootstrap/app.py`
- Endpoints:
  `/health/live`, `/health/ready`, `/api/v1/demo/overview`,
  `/api/v1/demo/planning-run`, `/api/v1/projects`,
  `/api/v1/projects/{project_id}`, `/versions`, `/approve`, `/inputs`,
  `/validate`, `/calculate`, `/calculations`, `/zone-plan`,
  `/investment-estimate`, `/planning-run`, `/audit-events`,
  `/api/v1/agent/sessions/{session_id}/messages`
- Current impact:
  most V1 surfaces have an HTTP endpoint, but many are still baseline/sample
  implementations.
- Suggested handling:
  keep endpoint paths stable and move logic behind them incrementally.

## 11. Implemented Pages

- File: `frontend/src/App.vue`
- Workflow pages:
  基本信息, 计算结果, 方案比选, 投资估算, 用电估算, 报告输出
- Additional hidden/demo views still exist in the component:
  参数完整度, 冷间区域规划, 冷间方案, 知识依据, 版本历史, 审计记录
- Current impact:
  the top workflow is usable, but the component still contains multiple demo
  views and sample-only sections.
- Suggested handling:
  split route/view modules and keep only active workflow wiring in Task 10.

## 12. Implemented Engineering Calculations

- Files:
  `backend/src/cold_storage/modules/calculations/domain/service.py`,
  `backend/src/cold_storage/modules/calculations/domain/zone_planning.py`,
  `backend/src/cold_storage/modules/calculations/domain/investment.py`
- Implemented today:
  throughput, inventory, storage capacity, precooling, room area, cooling load,
  equipment requirement, zone planning, investment estimate, power estimate
  helpers
- Current impact:
  deterministic calculation coverage is broader than a toy demo, but some logic
  still lives in API/bootstrap helpers instead of dedicated modules.
- Suggested handling:
  keep formulas intact and move orchestration boundaries in Tasks 4 and 5.

## 13. Agent Or Model Calls

- Files:
  `backend/src/cold_storage/modules/planning_agent/application/agent_service.py`,
  `.../domain/gateways.py`,
  `.../infrastructure/fake_gateways.py`
- Current impact:
  agent behavior is limited to fake extraction and field whitelisting.
- Suggested handling:
  add session state, tool confirmation, and embedding abstraction in Task 8.

## 14. Knowledge Base Implementation

- File: `backend/src/cold_storage/modules/knowledge/application/service.py`
- Location: in-memory `documents` dict and substring `search()`
- Current impact:
  there is no document persistence, chunking, vector retrieval, or hybrid search.
- Suggested handling:
  rebuild this module around stored documents and retrieval pipelines in Task 7.

## 15. Report Implementation

- File: `backend/src/cold_storage/modules/reports/application/service.py`
- Location: `ReportService.generate()`
- Current impact:
  Word and Excel draft files can be produced, but there is no persisted report
  metadata, no version entity, and no API delivery path.
- Suggested handling:
  implement report persistence and versioning in Task 9.

## 16. Test Status

- Files: `backend/tests/*`, `frontend/tests/workbench.test.ts`
- Current impact:
  backend has architecture, integration, and unit tests; frontend has one
  consolidated workbench test file.
- Suggested handling:
  preserve the current baseline tests and expand per task rather than rewriting
  them wholesale.

## 17. Currently Runnable Features

- Backend API bootstraps and migrations run locally with SQLite.
- Backend tests pass locally.
- Frontend lint, typecheck, tests, and build pass locally.
- Demo planning endpoint and workbench can render/sample results.

Suggested handling:
- Treat this as the operational baseline for Task 1.

## 18. Currently Not Runnable Or Not Proven

- Docker Compose validation on this workstation, because `docker` is missing
- PostgreSQL/Redis runtime path
- Knowledge uploads with durable indexing
- Agent sessions with durable storage and confirmation flow
- Report download/version workflow

Suggested handling:
- Address environment parity in Task 1 and infra hardening in Task 12.

## 19. TODO / FIXME / Unfinished Modules

- Search result: no tracked `TODO` or `FIXME` markers were found
- Current impact:
  unfinished work exists, but it is implicit rather than explicitly documented
  in code comments.
- Suggested handling:
  continue using `docs/TECH_DEBT.md` and `docs/audit/gap-analysis.md` instead of
  hidden inline placeholders.

## 20. Duplicate Implementations

- Files:
  `backend/src/cold_storage/bootstrap/app.py`
  `backend/src/cold_storage/bootstrap/demo_overview.py`
  `frontend/src/App.vue`
- Locations:
  `_build_power_configuration`, `_reference_power_rows`, demo overview sample
  module data, frontend static zone/power/investment rows
- Current impact:
  demo defaults and power configuration can drift between backend and frontend.
- Suggested handling:
  centralize demo fixtures and backend-owned sample data in Task 10.

## 21. Large Files, Functions, And Classes

- `backend/src/cold_storage/bootstrap/app.py` - 788 lines
- `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` - 696 lines
- `backend/src/cold_storage/modules/calculations/domain/service.py` - 375 lines
- `frontend/src/App.vue` - 980 lines
- `frontend/src/style.css` - 940 lines
- `frontend/tests/workbench.test.ts` - 380 lines
- Current impact:
  reviewability and targeted change safety are weak.
- Suggested handling:
  split by ownership boundary, not by cosmetic formatting, over Tasks 1, 4, and
  10.

## 22. Cross-Layer Dependencies

- File: `backend/src/cold_storage/bootstrap/app.py`
- Locations:
  imports from domain calculators and direct helper orchestration
- Current impact:
  API layer bypasses application boundaries and owns business assembly.
- Suggested handling:
  move orchestration into application services while preserving endpoint
  contracts.

## 23. Circular Dependency Risk

- Files:
  `bootstrap/app.py`, `bootstrap/dependencies.py`, project infrastructure and
  planning modules
- Current impact:
  no active import cycle was observed, but the large bootstrap module and global
  service wiring make future cycles likely.
- Suggested handling:
  reduce bootstrap responsibilities and keep module dependency tests expanding.

## 24. Magic Numbers

- Files:
  `backend/src/cold_storage/modules/calculations/domain/zone_planning.py`,
  `backend/src/cold_storage/bootstrap/app.py`,
  `backend/src/cold_storage/bootstrap/demo_overview.py`,
  `frontend/src/App.vue`
- Examples:
  `25_000`, `0.30`, `0.90`, `220`, `400`, `600`, `5.6`, `1.5`, many equipment
  power constants
- Current impact:
  constants are scattered and only partly documented through demo coefficient
  references.
- Suggested handling:
  move reviewable values into a coefficient registry and reference catalog.

## 25. Unregistered Engineering Coefficients

- File: `backend/src/cold_storage/modules/calculations/domain/zone_planning.py`
- Location: `ColdRoomZonePlanner.__init__()` embedded coefficient map
- Current impact:
  coefficients are reviewable in code but not queryable or persistable as a
  registry.
- Suggested handling:
  create Task 3 coefficient registry and migration-backed storage.

## 26. Business Logic In API Routes

- File: `backend/src/cold_storage/bootstrap/app.py`
- Locations:
  `demo_planning_run`, `calculate`, `estimate_investment`,
  `run_project_planning`, `_build_zone_plan_from_inputs`,
  `_build_investment_from_zone_result`, `_build_power_configuration`
- Current impact:
  route code is doing far more than HTTP translation.
- Suggested handling:
  extract application services and keep routes thin in Task 1.

## 27. Engineering Calculation In Frontend

- File: `frontend/src/App.vue`
- Locations:
  static zone/power/investment datasets and input-to-request conversion inside
  `runPlanning()`
- Current impact:
  the frontend does not re-derive full engineering formulas, but it does own
  duplicated demo result values and request defaults.
- Suggested handling:
  source defaults from typed backend fixtures and keep calculation authority on
  the backend.

## 28. Does The Agent Directly Access The Database?

- Files:
  `backend/src/cold_storage/modules/planning_agent/*`,
  `backend/src/cold_storage/bootstrap/dependencies.py`
- Current impact:
  no direct ORM or session dependency was found in the agent module.
- Suggested handling:
  keep this invariant and add future architecture tests for gateways and session
  stores.

## 29. Are Database Models And API Schemas Mixed?

- Files:
  `backend/src/cold_storage/modules/projects/infrastructure/orm.py`,
  `backend/src/cold_storage/bootstrap/app.py`
- Current impact:
  ORM models and Pydantic request models are separate, but the API layer still
  returns raw dict snapshots assembled from ORM-backed records.
- Suggested handling:
  introduce explicit response/application schemas over time without changing
  endpoint semantics in Task 1 and Task 2.

## 30. Primary Maintenance Risks

1. Bootstrap/API module overload:
   `backend/src/cold_storage/bootstrap/app.py`
   Impact: one file owns too many responsibilities.
   Suggested handling: split orchestration and route translation.
2. Runtime architecture mismatch:
   `backend/src/cold_storage/bootstrap/settings.py`, `docker-compose.yml`,
   `README.md`
   Impact: docs and runtime diverge.
   Suggested handling: align current-state docs and runtime wiring.
3. Frontend monolith and duplicated demo data:
   `frontend/src/App.vue`
   Impact: change cost and drift risk are high.
   Suggested handling: modularize in Task 10.

## 31. V0.6 governance truth-up (`main@06a446501b83f75ba42b3920d912d980c51d7fe5`, release `v0.5.0`)

The following capabilities are **delivered** and must not be described as
baseline-only in new governance work:

| Area | Delivered state (not baseline-only) | Evidence |
| --- | --- | --- |
| Knowledge | Durable document/revision persistence, chunking, embedding, and retrieval service | `backend/src/cold_storage/modules/knowledge/` |
| Reports | Persisted report/revision lifecycle, assembler reads persisted results (no recalculation) | `backend/src/cold_storage/modules/reports/` |
| Frontend | Feature-modular workbench (`frontend/src/features/*`), not a single `App.vue` monolith | `frontend/src/features/` |
| Coefficients | Governed registry with Definition/Revision, review metadata, and persistence | `backend/src/cold_storage/modules/coefficients/` |
| Calculations | Deterministic five-stage orchestration registry and Transaction B execution path | `backend/src/cold_storage/modules/orchestration/domain/dag.py`, `transaction_b.py` |
| V0.4 local workbench | Persisted sqlite sample + controlled acceptance for zone, investment, supplemental power | `docs/tasks/V0_4-P5-controlled-acceptance-contract.md` |
| V0.5 five-stage workbench | Canonical five-stage persistence, consumer identity alignment, sqlite/PostgreSQL controlled acceptance | `docs/tasks/V0_5-P0-five-stage-workbench-contract.md`, tag `v0.5.0` |

**V0.5 delivered (do not reopen as active gap):** five-stage workbench
persistence and consumer canonical mapping are complete at `v0.5.0`. Gaps
V05-P0-001/002/003 from the V0.5 P0 contract are closed.

**Remaining V0.6 gap (report delivery):** five-stage persisted results are not
yet fully mapped into reviewable report JSON and formal DOCX/PDF closure.
Known gaps at `BASE_MAIN_SHA`:

- `persisted_calculation_reads.py` skips investment; `OrchestratedCalculationResult`
  has no `investment_result`.
- `real_data_provider._REPORT_SECTIONS` has only four calculation sections.
- `assembler` does not populate `input_conditions` / `assumptions` from immutable
  version snapshot.

See `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md` (issue #176).

**Issue #20** (Task 11 evaluation baseline) is **CLOSED** (2026-07-22). Do not
describe it as open in new governance work.

**Demo coefficient conflicts** documented in `docs/audit/coefficient-inventory.md`
(for example `storage_position_capacity_kg`, `frozen_fruit_ratio`,
`frozen_storage_days`) remain **unresolved** and must not be silently marked
resolved.

**Not in V0.6 scope:** Task 12 productionization and live Agent production
enablement remain outside the V0.6 umbrella unless separately authorized.

## 32. V0.7 governance truth-up (`main@f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba`, release `v0.6.0`)

The following V0.6 capabilities are **delivered** at tag `v0.6.0` and must not
be reopened as unfinished mapping gaps:

| Area | Delivered state at `v0.6.0` | Evidence |
| --- | --- | --- |
| Report five-stage mapping | `investment_result` and five calculation sections bind persisted runs | V0.6 P1 |
| `input_conditions` / `assumptions` | Assembler reads persisted version/calculation authority | V0.6 P1 |
| Formal rendering | zh-CN/en-US DOCX/PDF rendering path exists | V0.6 P2 |
| Evaluation review/formal bridge | P3 Surface B happy path under evaluation DI | V0.6 P3 |
| Guided report UI | Reports page binds `projectVersionId` and public report APIs | V0.6 P4A |
| Operator sample / runbook | Public-API sample; operator formal path honestly fail-closed | V0.6 P4B/P5 |

**Active umbrella:** V0.7 data and logic trust loop
(`docs/tasks/V0_7-P0-trust-loop-contract.md`).

**Remaining V0.7 gaps:** operator `create_app` composition for
`project_summary`; public production-scheme persistence for
`scheme_comparison`; input/coefficient traceability matrix; cross-consumer
hash/numeric consistency; Aily boundary freeze only.

**Demo coefficient conflicts** in `docs/audit/coefficient-inventory.md` remain
**unresolved** and must not be silently marked resolved.

**Not in V0.7 scope:** formula recut, live Aily implementation, production
RBAC, Task 12 productionization, CAD/construction drawings, field equipment
control.

## 33. V0.8 governance truth-up (`main@0330d9be36db94a62190d5775612b361fff6da8d`, release `v0.7.0`)

The V0.7 trust loop is **delivered** at tag `v0.7.0` and must not be reopened
as an unfinished umbrella. V0.8 operator-minimal process input is **delivered**
at tag `v0.8.0` (`docs/tasks/V0_8-P0-operator-minimal-input-contract.md`,
`docs/architecture/ADR-028-operator-minimal-process-input.md`).

**V0.8 delivered:** operator types only the five `zone_planning_inputs` KEY
leaves; application assembler writes catalog/lineage leaves into the full
bundle; Vue does not compute engineering values.

**Not in V0.8 scope (honest leftovers):** formula recut, coefficient
promotion, E1–E8 conflict resolution, live Aily, production RBAC, production
deployment.

## 34. V0.9 governance truth-up (`main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`, release `v0.8.0`)

V0.8 is **complete** at `v0.8.0`. V0.9 P0 freezes the next umbrella:
operator KEY recut, zone-planning formula recut (one package), workbench
layout, draft-versus-formal export, banner recut, and persisted zone result
display.

**Active umbrella:** V0.9 (`docs/tasks/V0_9-P0-version-contract.md`,
`docs/tasks/V0_9-version-plan.md`,
`docs/architecture/ADR-029-v09-operator-key-and-workbench-recut.md`).

P0 does **not** change application behavior. Wave 1 (`P1 ∥ P4 ∥ P5`) and
formula recut (P2) stay `IMPLEMENTATION_AUTHORIZED=NO` until separately
dispatched.

**Not in V0.9 scope:** cooling/equipment/power/investment formula recut,
live Aily, production RBAC, Feishu review, coefficient promotion, tag
without separate `授权`.

## 35. V1.1 shipped at `v1.1.0`

V0.9 + post-v0.9 operator workbench is **complete** at `v1.0.0`. V1.1 豆包工作伙伴
(Feishu Aily) inbound conversation connector is **complete** at `v1.1.0`
(`7fd0a28659baca56570813f3380b8223a0114f57`): five KEY in, existing
`cold_room_zone_plan@1.0.0` kernel, table out, MCP Streamable HTTP tool
`preview_zone_plan`. It does not recut cooling formulas, does not bump zone
`VERSION`, and does not open a live outbound Feishu session
(`AILY_OUTBOUND_LIVE_SESSION=NO`).

**Released umbrella:** V1.1 (`docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`,
`docs/tasks/V1_1-version-plan.md`,
`docs/architecture/ADR-031-aily-conversation-zone-plan.md`,
GitHub Release `v1.1.0`).
Prior V0.9 contract remains: `docs/tasks/V0_9-P0-version-contract.md`.
Do not move tags `v0.9.0`, `v1.0.0`, or `v1.1.0`.

## 36. V1.2 shipped at `v1.2.0`

V1.1 inbound zone-plan connector is **complete** at `v1.1.0`. V1.2
five-stage conversation preview is **complete** at `v1.2.0`
(`cb8a00bf7f95d5b29367a66f8fd06a1066ab4309`): same five KEY, existing
adapters in memory (`persisted: false`), REST `concept-preview`, MCP tools
`preview_cooling_load` / `preview_equipment` / `preview_installed_power` /
`preview_investment` plus frozen `preview_zone_plan` (first). Cooling uses
demo envelope catalog — **not** zone area auto-feed (`envelope_from_zone_area:
false`). Not Transaction B; not outbound live session
(`AILY_OUTBOUND_LIVE_SESSION=NO`).

**Released umbrella:** V1.2 (`docs/tasks/V1_2-P0-aily-five-stage-preview-contract.md`,
`docs/tasks/V1_2-version-plan.md`,
`docs/architecture/ADR-034-aily-five-stage-conversation-preview.md`,
GitHub Release `v1.2.0`).
Do not move tags `v0.9.0`, `v1.0.0`, `v1.1.0`, or `v1.2.0`.

## 37. V1.3 shipped at `v1.3.0`

V1.3 conversation preview lineage is **complete** at `v1.3.0`
(`0496010934f97dcad780acd0115866d1efc5276c`): workbench lineage binds
**in memory** on the V1.2 conversation preview path (zone `required_area_m2`
→ cooling `floor_area` / `zone_area`; equipment electrical kW(e) → installed
power; zone totals + power → investment). Wall / roof / U-values stay demo
catalog. `FORMULA_RECUT_AUTHORIZED=NO`. `AILY_OUTBOUND_LIVE_SESSION=NO`.

**Released umbrella:** V1.3 (`docs/tasks/V1_3-P0-aily-preview-lineage-contract.md`,
`docs/tasks/V1_3-version-plan.md`,
`docs/architecture/ADR-035-aily-preview-workbench-lineage.md`,
GitHub Release `v1.3.0`).
**Skill / runbook:** `docs/contracts/aily/v1.3/**`,
`docs/runbooks/v13-doubao-aily-connector.md`.
Do not move tags `v0.9.0`, `v1.0.0`, `v1.1.0`, `v1.2.0`, or `v1.3.0`.

## 38. V1.4 shipped at `v1.4.0`

V1.4 operator workbench debt is **complete** at `v1.4.0`
(`c58f0aee40af8362dbb034f6ebad94306b9d5f08`): first guided step is
`OPERATOR_PROCESS_INPUT` / 工程输入 (TD-023); operator demo five KEY +
storage-day defaults use `samples/v09-process-input/manifest.json`
(`20000 / 7 / 10 / 4 / 12`) (TD-008 slice). Path A `save_inputs` remains.
`FORMULA_RECUT_AUTHORIZED=NO` in that release.
`AILY_OUTBOUND_LIVE_SESSION=NO`. Feishu still used the V1.3 skill.

**Released umbrella:** V1.4 (`docs/tasks/V1_4-version-plan.md`,
`docs/tasks/V1_4-P0-workbench-debt-contract.md`,
`docs/architecture/ADR-036-workbench-operator-input-and-demo-defaults.md`,
GitHub Release `v1.4.0`).
Do not move tags `v0.9.0`, `v1.0.0`, `v1.1.0`, `v1.2.0`, `v1.3.0`, or
`v1.4.0`.

## 39. V1.5 shipped at `v1.5.0`

V1.5 cooling envelope wall/roof geometry bind is **complete** at `v1.5.0`
(`536603de1825b5ee7375b0d877f03cd28ba1343f`): after zone `required_area_m2`
binds to `floor_area` / `zone_area` (V1.3), the shared binder also sets
`roof_area = floor_area` and `wall_area = room_height × 4 × √floor_area`
(square plan). `room_height` stays the v05 demo catalog `5.0` m. U-values
and design temperatures stay demo/coefficient catalog. Derivation lives in
`preview_lineage_bind.py`, **not** in `cooling_load.py`, so
`cooling_load@1.0.0` is not bumped (`KEEP_COOLING_LOAD_VERSION=YES`).
Workbench persist and 豆包 in-memory preview use the same bind.
`AILY_OUTBOUND_LIVE_SESSION=NO`.

**Released umbrella:** V1.5 (`docs/tasks/V1_5-version-plan.md`,
`docs/tasks/V1_5-P0-envelope-geometry-contract.md`,
`docs/architecture/ADR-037-envelope-wall-roof-from-zone-geometry.md`,
GitHub Release `v1.5.0`).
**Skill / runbook:** `docs/contracts/aily/v1.5/**`,
`docs/runbooks/v15-doubao-aily-connector.md`.
Do not move tags `v0.9.0`, `v1.0.0`, `v1.1.0`, `v1.2.0`, `v1.3.0`,
`v1.4.0`, or `v1.5.0`.

## 40. V1.6 shipped at `v1.6.0`

V1.6 power-fan demo catalog is **complete** at `v1.6.0`
(`cd702b0abde2189c1626527bcef1086fa330238c`): evaporator/condenser fan
electrical kW(e) read `10.0` / `8.0` from
`samples/v05-local-workbench/manifest.json` via a shared loader used by the
operator-minimal assembler and Aily preview. Kernel
`InstalledPowerCalcInput` fan defaults stay `0` / `0`. Compressor electrical
still binds from equipment (`power_from_demo_catalog: false`). Do not invent
fan kW(e) from equipment. Do not treat v05 compressor `120.0` as operator
authority. `installed_power@1.0.0` is not bumped.
`AILY_OUTBOUND_LIVE_SESSION=NO`.

**Released umbrella:** V1.6 (`docs/tasks/V1_6-version-plan.md`,
`docs/tasks/V1_6-P0-power-fan-catalog-contract.md`,
`docs/architecture/ADR-038-v05-power-fan-demo-catalog.md`,
GitHub Release `v1.6.0`).
**Skill / runbook:** `docs/contracts/aily/v1.6/**`,
`docs/runbooks/v16-doubao-aily-connector.md`.
Do not move tags `v0.9.0` … `v1.6.0`.

## 41. V1.7 per-zone cooling component surface (complete at `v1.7.0`)

V1.7 **surfaced existing kernel zone components** for operator audit:
persist and display transmission / product / infiltration / internal /
defrost plus subtotal per refrigerated zone. Did not recut
`Q = U × A × ΔT`. Did not bump `cooling_load@1.0.0`. Did not retune the
shared v05 zone thermal catalog. Workbench persist and 豆包 preview use the
same adapter payload. `AILY_OUTBOUND_LIVE_SESSION=NO`.

**Released umbrella:** V1.7 (`docs/tasks/V1_7-version-plan.md`,
`docs/tasks/V1_7-P0-zone-cooling-surface-contract.md`,
`docs/architecture/ADR-039-per-zone-cooling-component-surface.md`,
GitHub Release `v1.7.0`).
**Skill / runbook:** `docs/contracts/aily/v1.7/**`,
`docs/runbooks/v17-doubao-aily-connector.md`.
V1.6 skill `docs/contracts/aily/v1.6/**` stays frozen.
Do not move tags `v0.9.0` … `v1.7.0`.

## 42. V1.8 per-zone temperature and height (implementation authorized)

V1.8 **surfaces bound cooling `room_design_temperature` and
`room_height` per refrigerated zone** so operators can audit °C and m.
Temperature catalog recut is **YES**: existing zone-plan bands, **cold
end** (8.0 / 1.0 / −18.0 °C); `product_target_temperature` follows.
Height catalog recut is **YES**: **4.0 m** for every refrigerated zone.
Do not recut `Q = U × A × ΔT`. Do not bump `cooling_load@1.0.0`.
`V18_IMPLEMENTATION_AUTHORIZED=YES` after Charles replied 可以.
`AILY_OUTBOUND_LIVE_SESSION=NO`. Tag `v1.8.0` waits for **main HEAD CI
green**. Do not tell the operator to `git pull` until that tag exists.

**Plan:** `docs/tasks/V1_8-version-plan.md`,
`docs/tasks/V1_8-P0-zone-temperature-height-contract.md`,
`docs/architecture/ADR-040-per-zone-temperature-height-surface.md`.
**Skill / runbook:** `docs/contracts/aily/v1.8/**`,
`docs/runbooks/v18-doubao-aily-connector.md`.
V1.7 skill `docs/contracts/aily/v1.7/**` stays frozen.
Do not move tags `v0.9.0` … `v1.7.0`.

## 43. V1.9 P0 per-zone cooling estimation basis (contract frozen for review)

The active V1.9 P0 lane freezes a minimum-estimation reference basis for nine
refrigerated zones; it does not change the current runtime or claim that a
formal thermal load has been calculated. It reuses the existing
`zone_plan.result.zones[]` output: pre-cooling uses final `position_count`, and
area-type zones use canonical `required_area_m2` with semantic
`PLANNED_ZONE_AREA`. The unified output semantic is
`minimum_estimated_cooling_load_kw_r`, expressed as not less than the frozen
reference.

**Contract:** `docs/tasks/V1_9-P0-per-zone-cooling-estimation-basis-contract.md`.
**Plan:** `docs/tasks/V1_9-version-plan.md`.
**ADR:** `docs/architecture/ADR-041-per-zone-cooling-estimation-basis.md`.
**Scope:** docs and `backend/tests/architecture/**` only.
`RUNTIME_IMPLEMENTATION_AUTHORIZED=NO`; `V19_P1_AUTHORIZED=NO`.
PR #252 remains unchanged and not closed; its audit direction is superseded
only in the new V1.9 contract.

## 44. V1.9 P1 per-zone minimum cooling estimation implementation

The P0 contract remains frozen and historical. Charles separately authorized
the minimal P1 runtime implementation on a fresh `main@a04aac1ac2309cfbce500ead13cfc2fc4ab176ac`
baseline. The implementation enriches the existing zone-plan rows after the
planner completes them; it does not recalculate `position_count` or
`required_area_m2`, add a sixth stage, or change the existing five-stage
calculation graph.

```text
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_EXECUTED=YES
RUNTIME_RULE_COUNT=9
PRECOOL_SOURCE_FIELD=position_count
AREA_SOURCE_FIELD=required_area_m2
MINIMUM_OUTPUT_FIELD=minimum_estimated_cooling_load_kw_r
PROVENANCE_SURFACE_IMPLEMENTED=YES
REQUIRES_REVIEW_ALL_RULES=YES
AMBIENT_ZONES_ENRICHED=NO
ZONE_PLAN_EXISTING_VALUES_CHANGED=NO
ZONE_PLANNING_ADAPTER_PRESERVES_V19_FIELDS=YES
SOURCE_SNAPSHOT_SCHEMA_PRESERVES_V19_FIELDS=YES
CALCULATION_TYPE_CHANGED=NO
ZONE_PLAN_VERSION_CHANGED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_INPUT_CHANGED=NO
POWER_INPUT_CHANGED=NO
INVESTMENT_INPUT_CHANGED=NO
FRONTEND_CHANGED=NO
MIGRATION_CREATED=NO
PR252_STATE_CHANGED=NO
```

At the time of the pre-merge implementation handoff, the next required stage
was `CHARLES_V19_P1_IMPLEMENTATION_REVIEW`; the current merged state is
recorded in §45. That historical handoff did not authorize the next
equipment/display lane.

## 45. V1.9 release-closure truth-up (`main@675fa8adfc58e2362101079d83393e90706505b2`)

Fresh repository verification confirms that `origin/main` is exactly
`675fa8adfc58e2362101079d83393e90706505b2` with tree
`71e726710d7df97fb6c2ea1b8e8cfbe080c232f9`. PR #254 is merged, with merge SHA
equal to that main commit. Its exact-head CI run `34113336197` concluded
SUCCESS; SQLite and PostgreSQL backend jobs, architecture tests, lint,
typecheck, frontend, Compose, recovery, and release-evidence checks are green.

The V1.9 current governance state is:

```text
V19_STATUS=IMPLEMENTATION_COMPLETE
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_MERGED=YES
PR254_MERGED=YES
PR254_NUMBER=254
PR254_MERGE_SHA=675fa8adfc58e2362101079d83393e90706505b2
PR254_EXACT_HEAD_CI_RUN=34113336197
PR254_EXACT_HEAD_CI=SUCCESS
RUNTIME_RULE_COUNT=9
REPORT_PROJECTION_REGRESSION=CLOSED
V07_GOLDEN_EVOLUTION=COMPLETE
V1_9_0_RELEASE_READY=YES
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The merged PR preserved the nine P1 runtime rules and closed the report
projection regression by keeping V1.9 provenance in the persisted/source zone
snapshot while excluding it from the legacy report projection. The V0.7 raw
zone-snapshot golden was evolved under the merged P1 contract; the remaining
golden hashes and numeric projection assertions stayed unchanged.

The V1.9 release-closure change was documentation/governance only and completed;
`v1.9.0` was subsequently created and released at the verified V1.9 main
commit. No next feature lane was authorized by that closure.

## 46. V2.0 released at `v2.0.0` (`main@a7049ca93d238013c0cf62069fe1e0a89ff834d7`)

Fresh verification confirms that `origin/main` is exactly
`a7049ca93d238013c0cf62069fe1e0a89ff834d7` with tree
`1e5d59b95beceacdcfa4a96ec2654a77fa52a9d0`. The V2.0 release-closure PR #259
is merged at that commit; annotated tag `v2.0.0` and its GitHub Release point to
the same commit.

V2.0 has exactly three formal implementation stages: P0 contract freeze, P1
backend deterministic canonical calculation, and P2 workbench + Aily/Doubao
read-only presentation alignment. There is no defined V2.0 P3. V2.0 release
execution is complete; V2.1 P0, P1, and P2 are merged and the active governance
lane is V2.1 release closure/readiness for target `v2.1.0`.

The following V2.0 state block preserves the historical readiness authorization
snapshot; the subsequent release execution fact is recorded immediately below.

```text
V20_IMPLEMENTATION_COMPLETE=YES
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=MERGED
P0_CONTRACT_FROZEN=YES
P1_CANONICAL_CALCULATOR_MERGED=YES
P2_READ_ONLY_PRESENTATION_MERGED=YES
P1_CANONICAL_IDENTITY=factory_power_estimation@2.0.0-p1
V20_P2_IMPLEMENTATION_STATUS=MERGED
V20_P2_PR_NUMBER=258
V20_P2_REVIEW_RESULT=PASS
V20_P2_BLOCKER_COUNT=0
V20_P2_FINAL_HEAD_SHA=2759538bcd32f7468de50c740ca17d7fbe18f49b
V20_P2_MERGE_COMMIT_SHA=5d5a9cad010a629bf52f6534fba37d047c330e00
WORKBENCH_READ_ONLY_PRESENTATION=YES
AILY_READ_ONLY_PRESENTATION=YES
WORKBENCH_AND_AILY_READ_SAME_RESULT=YES
FRONTEND_RECALCULATION=NO
AILY_RECALCULATION=NO
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_USED_AS_V2_AUTHORITY=NO
FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO
DATABASE_MIGRATION_CREATED_FOR_V20=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
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

The V2.0 factory-power result remains a concept-design estimate in `kW`, not
`kWh`, a metered value, a monthly electricity bill, transformer sizing, formal
distribution design, short-circuit calculation, cable selection, or protection
setting. V2.0 tag and GitHub Release execution is complete; deployment and a
next feature lane remain separately gated.

```text
V2_0_0_RELEASED=YES
V2_0_0_TAG_TARGET=a7049ca93d238013c0cf62069fe1e0a89ff834d7
V2_0_0_RELEASE_COMMIT=a7049ca93d238013c0cf62069fe1e0a89ff834d7
GITHUB_RELEASE_CREATED=YES
ACTIVE_GOVERNANCE_LANE=V2.1_P0
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 47. V2.1 P0：factory power upstream authority 与 Doubao MCP contract（已合并；历史 dispatch）

V2.1 P0 以 `v2.0.0` 为唯一基线，冻结了 contract、version plan、ADR 和
architecture lock，并已合并到当前 main。下面的 P0 authorization block 是
dispatch 时的历史快照，保留其 `P1_EXECUTED=NO` 等历史 gate；已合并的 P1 与
P2 的历史 implementation records 见 §48–49；当前 release closure 状态见 §50。

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
USER_REENTERS_FACTORY_AREA=NO
USER_REENTERS_COLD_STORAGE_AREA=NO
AREA_COMES_FROM_ZONE_PLAN=YES
EXPECTED_FACTORY_ZONE_COUNT=12
EXPECTED_REFRIGERATED_ZONE_COUNT=9
NEW_MCP_TOOL=preview_factory_power
NEW_MCP_TOOL_POSITION=6
EXISTING_FIVE_TOOL_ORDER_CHANGED=NO
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
P1_EXECUTED=NO
P2_EXECUTED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

正式契约、机器可读矩阵和 hostile cases 见
`docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md`；
版本计划见 `docs/tasks/V2_1-version-plan.md`，ADR 见
`docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md`。

## 48. V2.1 P1：factory power upstream authority adapter（已合并；历史 implementation record）

P1 在已合并的 P0 合同边界内实现 backend adapter 并已合并：它只接受成功且身份精确为
`cold_room_zone_plan@1.0.0` 的 canonical snapshot，从实际 12 个 zone rows 和
运行时 9-zone `REFRIGERATED_ZONE_REGISTRY` 绑定两个面积，再调用未修改的
`factory_power_estimation@2.0.0-p1`。P1 不实现 Doubao MCP、Skill、前端、数据库
或下一阶段；以下 P1 block 保留 dispatch/implementation 时的历史 gate。P2 的
历史状态见 §49，当前 release closure 状态见 §50。

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
FACTORY_AREA_FROM_12_ZONE_ROWS=YES
FACTORY_AREA_TOTAL_CROSS_CHECK=YES
COLD_STORAGE_AREA_FROM_REFRIGERATED_REGISTRY=YES
REFRIGERATED_ZONE_COUNT=9
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
V20_CALCULATOR_INVOKED=YES
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

## 49. V2.1 P2：factory-power MCP 与 Doubao Skill（已合并；历史 dispatch）

P1 upstream authority adapter 已合并，P2 随后也已合并。P2 把原五个 operator KEY
通过既有 zone-plan execution、P1 adapter、V2.0 calculator 和 shared projector
接到第 6 个 `preview_factory_power` MCP 工具，并新增 V2.1 Skill/runbook。
下面的 P2 block 保留 dispatch 时的历史 authorization snapshot；当前 release
closure/readiness 状态见 §50。

```text
TASK_ID=V21_P2_FACTORY_POWER_MCP_DOUBAO_SKILL_INTEGRATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37
BASE_MAIN_CI_RUN_ID=34321050750
BASE_MAIN_CI_RESULT=SUCCESS
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
MCP_RUNTIME_REJECTS_AREA_INPUT=YES
MCP_RUNTIME_REJECTS_UNKNOWN_INPUT=YES
FACTORY_POWER_FROM_P1_ADAPTER=YES
FACTORY_POWER_FROM_SHARED_PROJECTOR=YES
MCP_ENGINEERING_RECALCULATION=NO
V20_CALCULATOR_CHANGED=NO
P1_ADAPTER_CHANGED=NO
V20_PRESENTATION_CHANGED=NO
CONCEPT_PREVIEW_STAGE_COUNT=5
CALCULATION_TYPE_CHANGED=NO
V18_SKILL_CHANGED=NO
V18_RUNBOOK_CHANGED=NO
V21_SKILL_CREATED=YES
V21_RUNBOOK_CREATED=YES
SERVER_SIDE_CHAT_NLP=NO
OUTBOUND_LIVE_AILY_SESSION=NO
DATABASE_MIGRATION=NO
FRONTEND_CHANGED=NO
NEW_REST_ENDPOINT=NO
RELEASE_CLOSURE=UNAUTHORIZED
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2 记录见 `docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md`。
V1.8 Skill/runbook、五阶段 `concept-preview`、`preview_installed_power` 和所有
V2.0/P1 工程 authority 均保持冻结；不因 P2 实施而隐含 release、部署或下一 lane。

## 50. V2.1 Release Closure / v2.1.0 readiness（当前）

V2.1 P0、P1、P2 均已合并到 `main`；V2.1 没有定义 P3。当前治理 lane 是独立的
release closure/readiness，记录于 `docs/tasks/V2_1-release-closure-readiness.md`。
本节的当前状态 block 不改写 §47–49 中保留的历史 authorization snapshots。

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

Readiness determination 不执行 Ready、Merge、tag、GitHub Release、部署或下一
feature lane；release execution 仍是独立授权门禁。
