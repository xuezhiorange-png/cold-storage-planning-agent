# Current State Audit

This audit records the repository exactly as found on the preserved baseline.

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
