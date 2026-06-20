# Validation Baseline

Validation was run against the current repository baseline on
`codex/task-0-repository-audit`.

| Command | Result | Details | Blocking | Suggested Task |
| --- | --- | --- | --- | --- |
| `uv --version` | Success | `uv 0.11.17` available locally | No | N/A |
| `docker compose config` | Failed | `docker` command missing on the workstation | Environment issue | Task 12 |
| `cd backend && PYTHONPATH=src UV_CACHE_DIR=../.uv-cache uv run alembic upgrade head` | Success | Alembic runs with `SQLiteImpl` against local SQLite file | No | Task 1 |
| `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest` | Success | 18 tests passed; 1 FastAPI/Starlette deprecation warning from `testclient` | No | Task 1 |
| `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check .` | Success | All checks passed | No | N/A |
| `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff format --check .` | Failed | `src/cold_storage/bootstrap/demo_overview.py` and `src/cold_storage/modules/calculations/domain/investment.py` would be reformatted | Code issue | Task 1 |
| `cd backend && UV_CACHE_DIR=../.uv-cache uv run mypy src` | Success | No issues found in 37 source files | No | N/A |
| `cd frontend && npm run lint` | Success | ESLint passed | No | N/A |
| `cd frontend && npm run typecheck` | Success | `vue-tsc --noEmit` passed | No | N/A |
| `cd frontend && npm run test` | Success | 11 tests passed | No | N/A |
| `cd frontend && npm run build` | Success with warnings | Build succeeded; Rollup warning on `@vueuse/core` pure comments and large chunk warning over 500 kB | No | Task 10 |

## Summary

- The current repository is runnable for backend and frontend quality checks.
- The local machine does not currently support Docker-based validation.
- The most immediate code-level validation gap is backend formatting drift.
- Current migration validation only proves SQLite baseline behavior, not the
  target PostgreSQL path described in repo docs.
