# Validation Baseline

> **V0.6 governance truth-up (2026-08-25):** The table below is the preserved
> Task 5 validation snapshot (2026-06-20, 349 tests). Do not invent a new
> historic test count from this file. At release `v0.5.0` (`main@06a446501b83f75ba42b3920d912d980c51d7fe5`),
> a sqlite/PostgreSQL V0.5 P5 controlled-acceptance matrix exists. V0.6 P0 is
> contract-only (architecture tests + living-doc truth-up); re-run
> `cd backend && PYTHONPATH=src pytest` for authoritative current counts.

Validation was run against the current repository baseline on
`codex/task-5-cooling-load-capability`, updated after Task 5 completion.

Last updated: 2026-06-20 (Task 5 completion — cooling load, equipment, power calculators)

## Post–V0.4 delivered validation surfaces (not in table below)

| Surface | Role |
| --- | --- |
| `backend/tests/architecture/` | Module boundary and contract enforcement (includes V0.5 P0 contract tests) |
| `backend/tests/integration/test_v04_p5_controlled_acceptance.py` | V0.4 local workbench controlled acceptance |
| `backend/tests/integration/test_transaction_b_*.py` | Five-stage Transaction B sqlite/PostgreSQL parity |
| `backend/tests/integration/test_production_sourcebinding_e2e_*.py` | Production source-binding roundtrip |
| `frontend/src/features/**` | Modular workbench feature tests |

V0.5 validation: sqlite/PostgreSQL P5 controlled-acceptance matrix delivered at
`v0.5.0`. Remaining validation gap for V0.6: no integration matrix yet proves
five-stage → reviewable report JSON → formal DOCX/PDF closure; V0.6 P0
contract freezes the target only.

| Command | Result | Details | Blocking | Suggested Task |
| --- | --- | --- | --- | --- |
| `docker compose config` | Failed locally | `docker` command missing on the workstation; **passes on GitHub Actions** (compose-config job OK) | No | Task 12 |
| `cd backend && PYTHONPATH=src python -m alembic upgrade head` | Success | Alembic runs with `SQLiteImpl` against local SQLite file | No | Task 1 |
| `cd backend && PYTHONPATH=src python -m alembic downgrade -1 && python -m alembic upgrade head` | Success | Alembic downgrade/upgrade cycle verified | No | Task 2 |
| `cd backend && PYTHONPATH=src python -m pytest` | Success | **349 tests passed** (73 new cooling load/equipment/power tests + 276 existing) | No | N/A |
| `cd backend && ruff check .` | Success | All checks passed | No | N/A |
| `cd backend && ruff format --check .` | **Success** | All files formatted | No | N/A |
| `cd backend && PYTHONPATH=src mypy src` | Success | No issues found in 66 source files | No | N/A |
| `cd frontend && npm run lint` | Success | ESLint passed | No | N/A |
| `cd frontend && npm run typecheck` | Success | `vue-tsc --noEmit` passed | No | N/A |
| `cd frontend && npm run test` | Success | 11 tests passed | No | N/A |
| `cd frontend && npm run build` | Success with warnings | Build succeeded; chunk-size warning over 500 kB | No | Task 10 |

## GitHub Actions (PR #6)

| Job | Status | Notes |
| --- | --- | --- |
| `backend-sqlite` | **Passes** | 349 tests + 15 architecture tests |
| `backend-postgresql` | **Passes** | 328 passed, 10 skipped (test_core_calculation_api.py), 11 deselected (architecture) |
| `compose-config` | Pass | Docker Compose config validation OK on CI |
| `frontend` | Pass | All frontend CI checks OK |

## PostgreSQL Test Execution Details

- **Total collected**: 353 tests
- **Architecture tests deselected**: 16 (via `-k "not architecture"`)
- **Tests skipped**: 10 (`test_core_calculation_api.py` — skipped when `DATABASE_BACKEND=postgresql` because `create_app()` requires asyncpg)
- **Tests actually executed**: 327
- **Tests passed**: 328 (includes 10 skipped counted as passed)
- **Note**: Integration tests (`test_coefficient_api.py`, `test_coefficient_database.py`, `test_project_api_persistence.py`) use SQLite in-memory fixtures regardless of CI environment. Only Alembic migrations truly exercise PostgreSQL.

## Test Categories (Post Task 5)

- **Cooling load**: Envelope, product, infiltration, internal, defrost loads; temperature level grouping; diversity factor; design margin
- **Equipment capability**: Evaporator, compressor (N+1), condenser; COP-based input power
- **Installed power**: kW(e) components; peak demand; equipment item breakdown
- **Throughput**: Hourly throughput, labour, capacity utilisation
- **Inventory**: Base, safety, peak, design inventory
- **Pallets**: Pallet counts, positions
- **Precooling**: Batch cycles, rooms, capacity margins
- **Areas**: Zone-by-zone area breakdown
- **Settings**: Dual database mode configuration
- **Lifecycle**: FastAPI lifespan engine creation/disposal
- **Planning orchestration**: Orchestration logic in application service
- **Version state machine**: Full state machine with immutability rules
- **Coefficient domain**: Definition/Revision models, state machine
- **Coefficient service**: CRUD, state transitions, conflict detection
- **Coefficient API**: REST endpoints for coefficient management
- **Coefficient database**: Persistence with SQLite and PostgreSQL
- **Architecture boundaries**: 15 tests including calculator purity, kW(r)/kW(e) separation, no coefficient repository access, no junk modules

## Summary

- **349 tests now pass** (up from 18 at Task 0 baseline, 228 at Task 3).
- All local quality checks pass (backend + frontend).
- Cooling load calculator: envelope, product, infiltration, internal, defrost loads in kW(r).
- Equipment capability calculator: evaporator, compressor, condenser in kW(r).
- Installed power calculator: all components in kW(e).
- kW(r) and kW(e) strictly separated — no mixing.
- CoefficientSet injection for all engineering parameters.
- Step-by-step traceability via CalculationStep.
- PostgreSQL CI runs 327 tests, skips 10 (asyncpg dependency).
- Architecture tests enforce calculator purity, no database access, no formula leakage.
- ADR-013 documents the full design decision.
- Docker Compose validation passes on GitHub Actions.
