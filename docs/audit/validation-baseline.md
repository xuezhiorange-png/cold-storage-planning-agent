# Validation Baseline

Validation was run against the current repository baseline on
`codex/task-0-repository-audit`, updated after Task 2 completion.

Last updated: 2026-06-20 (Task 2 completion — project versioning and immutability)

| Command | Result | Details | Blocking | Suggested Task |
| --- | --- | --- | --- | --- |
| `docker compose config` | Failed locally | `docker` command missing on the workstation; **passes on GitHub Actions** (compose-config job OK) | No | Task 12 |
| `cd backend && PYTHONPATH=src python -m alembic upgrade head` | Success | Alembic runs with `SQLiteImpl` against local SQLite file | No | Task 1 |
| `cd backend && PYTHONPATH=src python -m alembic downgrade -1 && python -m alembic upgrade head` | Success | Alembic downgrade/upgrade cycle verified | No | Task 2 |
| `cd backend && PYTHONPATH=src python -m pytest` | Success | **116 tests passed** (settings, lifecycle, planning orchestration, version state machine, architecture boundaries, plus original tests) | No | N/A |
| `cd backend && ruff check .` | Success | All checks passed | No | N/A |
| `cd backend && ruff format --check .` | **Success** | All files formatted | No | N/A |
| `cd backend && PYTHONPATH=src mypy src` | Success | No issues found in source files | No | N/A |
| `cd frontend && npm run lint` | Success | ESLint passed | No | N/A |
| `cd frontend && npm run typecheck` | Success | `vue-tsc --noEmit` passed | No | N/A |
| `cd frontend && npm run test` | Success | Tests passed | No | N/A |
| `cd frontend && npm run build` | Success with warnings | Build succeeded; Rollup warning on `@vueuse/core` pure comments and large chunk warning over 500 kB | No | Task 10 |

## GitHub Actions (PR #2)

| Job | Status | Notes |
| --- | --- | --- |
| `backend` (lint) | **Passes** | ruff, ruff format, mypy all clean |
| `compose-config` | Pass | Docker Compose config validation OK on CI |
| `frontend` | Pass | All frontend CI checks OK |

## Test Categories (Post Task 2)

- **Settings**: Dual database mode configuration (SQLite and PostgreSQL), explicit env-driven selection
- **Lifecycle**: FastAPI lifespan engine creation/disposal, dependency injection wiring
- **Planning orchestration**: Orchestration logic extracted to `modules/planning/application/service.py`
- **Version state machine**: Full state machine with 6 states, valid transitions, immutability rules
- **Project versioning**: CRUD operations, version creation, input management, snapshots
- **Architecture boundaries**: Import-time singleton removal, domain dependency enforcement

## Summary

- **116 tests now pass** (up from 18 at Task 0 baseline).
- All local quality checks pass (backend + frontend).
- Settings restructured with dual database mode support (SQLite for local dev, PostgreSQL for production).
- Import-time singletons removed; lifecycle managed via FastAPI lifespan.
- Planning orchestration extracted from `bootstrap/app.py` to dedicated application service.
- Project versioning implemented with full state machine and immutability rules.
- Alembic migration adds version metadata columns (parent_version_id, snapshots, timestamps).
- Docker Compose validation is absent locally but passes on GitHub Actions.
- No business logic, engineering formulas, or calculation outputs were changed.
