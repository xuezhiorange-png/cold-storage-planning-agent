# Gap Analysis

> **V0.5 governance truth-up (2026-08-24, `main@eec12b9d`):** The tables
> below retain the Task 0–5 preserved gap register. Rows marked below as
> **SUPERSEDED** are no longer accurate. See §V0.5 for the active P0 gap.

## P0

No active P0 issue was found in the tracked baseline after sensitive-file
review. The earlier wrong-remote configuration was corrected before baseline
push and is not a remaining repository state issue.

## P1

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1-001 | P1 | ~~Runtime persistence defaults to SQLite while repository docs and Compose target PostgreSQL/pgvector + Redis~~ **RESOLVED** — dual mode with explicit config; settings restructured to support SQLite (local dev) and PostgreSQL (production) via env-driven selection | `backend/src/cold_storage/bootstrap/settings.py`, `backend/alembic.ini`, `docker-compose.yml` | ~~Environment behavior diverges from architecture claims~~ | ~~Make runtime DB selection explicit and verify PostgreSQL path~~ | Task 1 | ~~Yes~~ |
| P1-002 | P1 | ~~API layer directly assembles planning, power, and investment logic instead of delegating to application services~~ **RESOLVED** — orchestration extracted to `modules/planning/application/service.py` | `backend/src/cold_storage/bootstrap/app.py` `demo_planning_run`, `estimate_investment`, `run_project_planning`, `_build_power_configuration` | ~~Core planning behavior is hard to isolate, reuse, and govern~~ | ~~Extract orchestration into application services and dedicated modules~~ | Task 1 | ~~Yes~~ |
| P1-003 | P1 | ~~Knowledge base is only in-memory substring search, without persistence or vector retrieval~~ **SUPERSEDED** — durable knowledge ingestion, chunking, embedding, and retrieval are implemented; hybrid/production hardening remains | `backend/src/cold_storage/modules/knowledge/` | ~~Claimed knowledge capabilities are not actually delivered~~ | Continue retrieval quality and ops hardening | Task 7 follow-up | No |
| P1-004 | P1 | ~~Reports are generated as ad hoc files without persisted metadata, versioning, or download API~~ **SUPERSEDED** — persisted report revisions, lifecycle, and API delivery exist; formal-export governance continues under reports module | `backend/src/cold_storage/modules/reports/` | ~~Report outputs are not auditable~~ | Extend template/report consumer alignment with five-stage canonical mapping | Task 9 follow-up | No |

## P2

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P2-001 | P2 | ~~Frontend workbench is concentrated in one 980-line `App.vue` file~~ **SUPERSEDED** — feature modules exist under `frontend/src/features/`; remaining work is five-stage workbench wiring and identity alignment | `frontend/src/features/` | ~~UI maintenance cost is high~~ | Wire persisted five-stage results and unify calculator identities | V0.5 P1+ | No |
| P2-002 | P2 | Demo planning and power configuration logic is duplicated across backend and frontend | `backend/src/cold_storage/bootstrap/demo_overview.py`, `backend/src/cold_storage/bootstrap/app.py`, `frontend/src/App.vue` | Drift between sample UI and API outputs is likely | Move demo fixtures to shared backend-owned sources | Task 10 | No |
| P2-003 | P2 | Agent abstraction only defines `ModelGateway`; `EmbeddingGateway` and session-oriented workflow are missing | `backend/src/cold_storage/modules/planning_agent/domain/gateways.py`, `.../application/agent_service.py` | Agent architecture is incomplete relative to the roadmap | Add explicit gateway interfaces and session orchestration | Task 8 | No |
| P2-004 | P2 | ~~Import-time singleton services hide startup behavior and environment coupling~~ **RESOLVED** — lifecycle management via FastAPI lifespan; import-time singletons removed from `dependencies.py` | `backend/src/cold_storage/bootstrap/dependencies.py` | ~~Harder to test, override, and configure runtime services~~ | ~~Use explicit factories or lifespan wiring~~ | Task 1 | ~~No~~ |
| P2-005 | P2 | ~~Demo coefficients are embedded in code instead of living in a governed registry~~ **RESOLVED** — coefficient registry implemented; **demo coefficient conflicts remain open** (see `docs/audit/coefficient-inventory.md`) | `backend/src/cold_storage/modules/coefficients/` | ~~Coefficients cannot be reviewed or versioned centrally~~ | Do not promote conflicting demo values without explicit review | V0.5+ | ~~Yes~~ |
| P2-006 | P2 | PostgreSQL integration tests do not truly test PostgreSQL — all integration tests use SQLite in-memory fixtures | `backend/tests/integration/` | PostgreSQL CI validates migrations but not actual database operations | Migrate integration tests to use PostgreSQL fixtures when DATABASE_BACKEND=postgresql | Task 12 | No |
| P2-007 | P2 | Cooling load calculator currently only computes sensible infiltration load; latent load is omitted | `backend/src/cold_storage/modules/calculations/domain/cooling_load.py` | Humidity-dependent loads (defrost, product respiration latent) not captured | Add latent infiltration model with humidity state calculations | Task 5 follow-up | No |

## P3

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P3-001 | P3 | README previously described target stack as current stack without clarifying SQLite reality | `README.md` | New contributors may use the wrong runtime assumptions | Keep current-state and target-state docs separate | Task 0 | No |
| P3-002 | P3 | ~~Backend formatting drift remains in two files~~ **RESOLVED in Task 0** — `ruff format` applied to `demo_overview.py` and `investment.py` | `backend/src/cold_storage/bootstrap/demo_overview.py`, `backend/src/cold_storage/modules/calculations/domain/investment.py` | ~~CI truthfully fails formatting gate~~ | ~~Reformat in dedicated quality task~~ | Task 0 | ~~No~~ |
| P3-003 | P3 | Frontend production bundle is large and emits chunk-size warning | `frontend/package.json` toolchain output | DevEx and initial load can degrade as features grow | Introduce route/feature splitting and chunk strategy | Task 10 | No |

## V0.5 (active P0 gap register)

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V05-P0-001 | P0 | Local workbench persists only three helper calculators (`cold_room_zone_plan`, `investment_estimate`, `power_configuration`), not the canonical five-stage chain | `backend/src/cold_storage/modules/planning/`, `backend/src/cold_storage/bootstrap/v04_local_sample.py` | Workflow/scheme/report cannot treat workbench as five-stage authoritative | Execute and persist canonical chain per `docs/tasks/V0_5-P0-five-stage-workbench-contract.md` | V0.5 P1 | Yes |
| V05-P0-002 | P0 | `power_configuration` is supplemental/demo but can be mistaken for canonical `installed_power` | `backend/src/cold_storage/modules/planning/application/service.py` | Power authority drift between V0.4 read path and orchestration DAG | Keep identity separation; wire canonical `installed_power` in P1+ | V0.5 P1 | Yes |
| V05-P0-003 | P0 | Workflow/scheme/report consumers use inconsistent calculator identities and snapshot shapes vs orchestration DAG | `backend/src/cold_storage/modules/workflow/domain/steps.py`, `backend/src/cold_storage/modules/schemes/application/source_binding_verifier.py` | Stale-lineage and source-binding verification failures across modules | Unify canonical mapping on `ORCHESTRATION_STAGE_ORDER` / `CALCULATOR_BINDINGS` | V0.5 P1–P3 | Yes |
| V05-P0-004 | P0 | Demo coefficient conflicts remain documented but unresolved | `docs/audit/coefficient-inventory.md` | Silent promotion would violate review governance | Explicit review/promotion only; never auto-resolve conflicts | V0.5+ | No |
