# Gap Analysis

## P0

No active P0 issue was found in the tracked baseline after sensitive-file
review. The earlier wrong-remote configuration was corrected before baseline
push and is not a remaining repository state issue.

## P1

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1-001 | P1 | Runtime persistence defaults to SQLite while repository docs and Compose target PostgreSQL/pgvector + Redis | `backend/src/cold_storage/bootstrap/settings.py`, `backend/alembic.ini`, `docker-compose.yml` | Environment behavior diverges from architecture claims; integration confidence is weak | Make runtime DB selection explicit and verify PostgreSQL path | Task 1 | Yes |
| P1-002 | P1 | API layer directly assembles planning, power, and investment logic instead of delegating to application services | `backend/src/cold_storage/bootstrap/app.py` `demo_planning_run`, `estimate_investment`, `run_project_planning`, `_build_power_configuration` | Core planning behavior is hard to isolate, reuse, and govern | Extract orchestration into application services and dedicated modules | Task 1 / Task 4 / Task 5 | Yes |
| P1-003 | P1 | Knowledge base is only in-memory substring search, without persistence or vector retrieval | `backend/src/cold_storage/modules/knowledge/application/service.py` | Claimed knowledge capabilities are not actually delivered | Build durable document storage, chunking, embeddings, and retrieval | Task 7 | Yes |
| P1-004 | P1 | Reports are generated as ad hoc files without persisted metadata, versioning, or download API | `backend/src/cold_storage/modules/reports/application/service.py` | Report outputs are not auditable and do not match target behavior | Add persisted report versions and API-driven delivery | Task 9 | No |

## P2

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P2-001 | P2 | Frontend workbench is concentrated in one 980-line `App.vue` file with static samples, API calls, and rendering mixed together | `frontend/src/App.vue` | UI maintenance cost is high; regression risk grows with every feature | Split into feature modules and typed view components | Task 10 | No |
| P2-002 | P2 | Demo planning and power configuration logic is duplicated across backend and frontend | `backend/src/cold_storage/bootstrap/demo_overview.py`, `backend/src/cold_storage/bootstrap/app.py`, `frontend/src/App.vue` | Drift between sample UI and API outputs is likely | Move demo fixtures to shared backend-owned sources | Task 10 | No |
| P2-003 | P2 | Agent abstraction only defines `ModelGateway`; `EmbeddingGateway` and session-oriented workflow are missing | `backend/src/cold_storage/modules/planning_agent/domain/gateways.py`, `.../application/agent_service.py` | Agent architecture is incomplete relative to the roadmap | Add explicit gateway interfaces and session orchestration | Task 8 | No |
| P2-004 | P2 | Import-time singleton services hide startup behavior and environment coupling | `backend/src/cold_storage/bootstrap/dependencies.py` | Harder to test, override, and configure runtime services | Use explicit factories or lifespan wiring | Task 1 | No |
| P2-005 | P2 | Demo coefficients are embedded in code instead of living in a governed registry | `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` | Coefficients cannot be reviewed or versioned centrally | Build coefficient registry with persistence and review status | Task 3 | Yes |

## P3

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P3-001 | P3 | README previously described target stack as current stack without clarifying SQLite reality | `README.md` | New contributors may use the wrong runtime assumptions | Keep current-state and target-state docs separate | Task 0 | No |
| P3-002 | P3 | Backend formatting drift remains in two files | `backend/src/cold_storage/bootstrap/demo_overview.py`, `backend/src/cold_storage/modules/calculations/domain/investment.py` | CI truthfully fails formatting gate | Reformat in dedicated quality task | Task 1 | No |
| P3-003 | P3 | Frontend production bundle is large and emits chunk-size warning | `frontend/package.json` toolchain output | DevEx and initial load can degrade as features grow | Introduce route/feature splitting and chunk strategy | Task 10 | No |
