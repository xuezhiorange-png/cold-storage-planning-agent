# Gap Analysis

> **V0.9 P0 freeze (2026-08-27, `main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`,
> release `v0.8.0`):** The tables below retain the Task 0–5 preserved gap
> register. Rows marked **SUPERSEDED** are no longer accurate. V0.5 P0 gaps
> V05-P0-001/002/003 are **delivered** at `v0.5.0`. V0.6 report source mapping
> gaps V06-P0-001/002/003/004/005 are **delivered** at `v0.6.0`. V0.7 trust-loop
> delivery is **complete** at `v0.7.0`. See `docs/tasks/V0_7-P0-trust-loop-contract.md`
> for the delivered V0.7 register. V0.8 operator-minimal process input is
> **complete** at `v0.8.0` (`docs/tasks/V0_8-P0-operator-minimal-input-contract.md`).
> **Active umbrella:** V0.9 (`docs/tasks/V0_9-P0-version-contract.md`).

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

## V0.5 (delivered at `v0.5.0`)

| ID | Priority | Problem Description | Status at `v0.5.0` | Evidence |
| --- | --- | --- | --- | --- |
| V05-P0-001 | P0 | Local workbench persisted only three helper calculators, not the canonical five-stage chain | **DELIVERED** | V0.5 P1–P5 controlled acceptance at `06a446501b83f75ba42b3920d912d980c51d7fe5` |
| V05-P0-002 | P0 | `power_configuration` supplemental vs canonical `installed_power` identity separation | **DELIVERED** | `consumer_bindings.SUPPLEMENTAL_ONLY_CALCULATOR_NAMES` |
| V05-P0-003 | P0 | Workflow/scheme/report consumers used inconsistent calculator identities | **DELIVERED** | Canonical mapping aligned in V0.5 P1–P3 |
| V05-P0-004 | P0 | Demo coefficient conflicts remain documented but unresolved | **OPEN** | `docs/audit/coefficient-inventory.md` — must not be silently resolved |

## V0.6 (report-delivery gap register — delivered at `v0.6.0` except coefficient conflicts)

| ID | Priority | Problem Description | Status at `v0.6.0` | Evidence |
| --- | --- | --- | --- | --- |
| V06-P0-001 | P0 | Report assembly skips investment stage; `OrchestratedCalculationResult` lacks `investment_result` | **DELIVERED** | V0.6 P1 report assembly + P5 controlled acceptance |
| V06-P0-002 | P0 | `real_data_provider._REPORT_SECTIONS` omits `investment_estimate` | **DELIVERED** | V0.6 P1 `_REPORT_SECTIONS` mapping |
| V06-P0-003 | P0 | Assembler does not populate `input_conditions` / `assumptions` from immutable version snapshot | **DELIVERED** | V0.6 P1 assembler + P3 evaluation |
| V06-P0-004 | P0 | Report rendering hardening for Issue #17 items not yet under V0.6 evaluation matrix | **DELIVERED as V0.6 scope** | V0.6 P2 rendering + P3 goldens; leftover display items remain on #17 |
| V06-P0-005 | P0 | Review/formal-export evaluation bridge not yet proven end-to-end for V0.6 | **DELIVERED (evaluation surface)** | V0.6 P3 + P5 Surface B; operator Surface A remain fail-closed by design |
| V06-P0-006 | P0 | Demo coefficient conflicts remain documented but unresolved | **OPEN** | `docs/audit/coefficient-inventory.md` — must not be silently resolved |

## V0.8 (active operator-minimal process-input gap register)

See `docs/tasks/V0_8-P0-operator-minimal-input-contract.md`. Do not reopen V0.7
trust-loop delivery as unfinished work.

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V08-GAP-001 | P0 | Operator 工程输入 form requires the full bundle KEY surface | `EngineeringInputBundleForm.vue` | Operator substitutes for calculators | `OperatorProcessInputV1` five KEY leaves only | V0.8 P2 | Yes |
| V08-GAP-002 | P0 | Bundle KEY validation runs before lineage bind | `engineering_input_bundle.py`, `five_stage_execution.py` | Downstream KEY must be typed at submit | Assemble then validate; bind typed upstream results | V0.8 P1 | Yes |
| V08-GAP-003 | P0 | Cooling envelope/thermal KEY have no operator-minimal source | `ZoneCoolingLoadInput`; V0.5 geometry auto-feed forbidden | Cannot run cooling from five process leaves alone | Explicit demo catalog leaves, not silent defaults | V0.8 P1 | Yes |
| V08-GAP-004 | P0 | Installed-power KEY are operator-typed despite equipment electrical output | equipment result vs `installed_power_inputs` | Duplicate operator entry | Lineage bind compressor electrical input | V0.8 P1 | Yes |
| V08-GAP-005 | P1 | 基本信息 page still looks like the primary operator form | `ProjectPage.vue` | Wrong path looks authoritative | Keep V0.4 leftover label; V0.8 authority is 工程输入 | V0.8 P2 | No |

## V0.7 (delivered data and logic trust-loop gap register)

See `docs/tasks/V0_7-P0-trust-loop-contract.md`. Delivered at `v0.7.0`. Do not reopen V0.6 mapping gaps as unfinished umbrellas.

| ID | Priority | Problem Description | File Location | Impact | Suggested Fix | Suggested Task | Blocks Later Work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V07-GAP-001 | P0 | Operator `create_app` report DI omits `project_service`, so `project_summary` is absent | `backend/src/cold_storage/bootstrap/app.py` `_get_report_service` | Operator generate stays `draft`; `submit-review` HTTP 409 | Inject `project_service` into `RealReportDataProvider` | V0.7 P3A | Yes |
| V07-GAP-002 | P0 | No public API persists `source_mode=production` scheme runs on the five-stage version | `backend/src/cold_storage/modules/schemes/api/routes.py` | Operator `scheme_comparison` missing | Add `POST .../production-scheme-runs` | V0.7 P3B | Yes |
| V07-GAP-003 | P0 | Evaluation happy path ≠ operator path | V0.6 P3 helpers vs `v06_sample_loader` | Dual-surface evidence; #11/#13 remain OPEN | Align operator public API after P3A+P3B | V0.7 P5 | Yes |
| V07-GAP-004 | P0 | Coefficient metadata / optional bundle leaves can diverge from effective calculator inputs | `zone_planning.py`, `engineering_input_bundle.py` | Traceability failure without formula bug | Integrity matrix; expert decisions E1–E8 | V0.7 P1 | No |
| V07-GAP-005 | P0 | Workflow/scheme hash helpers may not equal persisted `result_hash` | `workflow/application/service.py`, `canonical_source_reads.py` | Cross-consumer identity drift | Consistency matrix; optional later P2b | V0.7 P2 | No |
| V07-GAP-006 | P0 | Complete `EngineeringInputBundleV1` is not default version snapshot on operator sample | `five_stage_execution.py`, `persisted_calculation_query.py` | Report input authority fallback | Snapshot-authority proof | V0.7 P1 | No |
| V07-GAP-007 | P1 | Registry seed and embedded calculator coefficients remain dual-track | `modules/coefficients/` vs embedded maps | Dual authority | Seed-authority tests; no silent merge | V0.7 P1 | No |
| V07-GAP-008 | P1 | No Feishu Aily integration boundary | docs | Future integration would bypass trust rules | P6 docs + schema contract | V0.7 P6 | No |
| V07-GAP-010 | P0 | Demo coefficient conflicts remain unresolved | `docs/audit/coefficient-inventory.md` | Silent promotion forbidden | Keep `requires_review=true` | V0.7+ expert | No |
| V09-GAP-001 | P0 | Zone planner does not match the V0.9 formula lock (including 出货通道) | `calculations/domain/zone_planning.py` | Operator KEY unused; aisle factors fixed; no shipping_channel | P2 formula recut after dispatch | V0.9 P2 | Yes |
| V09-GAP-002 | P0 | Operator KEY still the V0.8 five (includes precooling ratio and working time) | `OperatorProcessInputV1` | KEY do not match locked planner inputs | P1 assembler + form | V0.9 P1 | Yes |
| V09-GAP-004 | P0 | Stacked workbench blockers and review/export confusion | `WorkflowGuidancePanel.vue`, `ReportExportPanel.vue` | Draft work looks blocked | P4 + P5 | V0.9 P4/P5 | No |
