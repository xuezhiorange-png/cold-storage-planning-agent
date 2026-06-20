# Validation Baseline

Validation was run against the current repository baseline on
`codex/task-0-repository-audit`.

Last updated: 2026-06-20 (Task 0 completion — ruff format applied)

| Command | Result | Details | Blocking | Suggested Task |
| --- | --- | --- | --- | --- |
| `docker compose config` | Failed locally | `docker` command missing on the workstation; **passes on GitHub Actions** (compose-config job OK) | No | Task 12 |
| `cd backend && PYTHONPATH=src python -m alembic upgrade head` | Success | Alembic runs with `SQLiteImpl` against local SQLite file | No | Task 1 |
| `cd backend && PYTHONPATH=src python -m pytest` | Success | 18 tests passed | No | Task 1 |
| `cd backend && ruff check .` | Success | All checks passed | No | N/A |
| `cd backend && ruff format --check .` | **Success** | 47 files already formatted (after applying ruff format to 2 files) | No | N/A |
| `cd backend && PYTHONPATH=src mypy src` | Success | No issues found in 37 source files | No | N/A |
| `cd frontend && npm run lint` | Success | ESLint passed | No | N/A |
| `cd frontend && npm run typecheck` | Success | `vue-tsc --noEmit` passed | No | N/A |
| `cd frontend && npm run test` | Success | 11 tests passed (1 test file) | No | N/A |
| `cd frontend && npm run build` | Success with warnings | Build succeeded; Rollup warning on `@vueuse/core` pure comments and large chunk warning over 500 kB | No | Task 10 |

## GitHub Actions (PR #1)

| Job | Status | Notes |
| --- | --- | --- |
| `backend` (lint) | **Previously failed → now passes after format fix** | Root cause: `ruff format --check` found 2 unformatted files |
| `compose-config` | Pass | Docker Compose config validation OK on CI |
| `frontend` | Pass | All frontend CI checks OK |

## Summary

- All local quality checks now pass (backend + frontend).
- The two formatting issues in `demo_overview.py` and `investment.py` have been resolved via `ruff format`.
- Docker Compose validation is absent locally but passes on GitHub Actions.
- Current migration validation only proves SQLite baseline behavior, not the
  target PostgreSQL path described in repo docs.
- No business logic, engineering formulas, or calculation outputs were changed.
