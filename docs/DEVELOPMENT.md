# Development

## Environment

- Backend tooling uses `uv`.
- Frontend tooling uses `npm`.
- The repository currently runs locally with SQLite by default unless
  `DATABASE_URL` is overridden.
- Docker Compose defines PostgreSQL and Redis targets, but the current baseline
  does not switch to them automatically.

## Local Setup

```bash
make install
make migrate
make seed
make demo
```

Backend API:

```bash
cd backend
PYTHONPATH=src UV_CACHE_DIR=../.uv-cache uv run uvicorn cold_storage.bootstrap.app:create_app --factory --reload
```

Frontend workbench:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

## Quality Gates

Run before opening or updating a PR:

```bash
cd backend && PYTHONPATH=src UV_CACHE_DIR=../.uv-cache uv run alembic upgrade head
cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest
cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check .
cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff format --check .
cd backend && UV_CACHE_DIR=../.uv-cache uv run mypy src
cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
```

## Branching

- `main` stores the preserved baseline and reviewed merges.
- Task work happens on `codex/task-*` branches.
- Do not do governance or feature work directly on `main`.

## Implementation Discipline

- Preserve existing behavior unless the task explicitly changes it.
- Do not hide failing tests.
- Do not push sensitive files, local databases, caches, or generated reports.
- Record architectural deviations in `docs/TECH_DEBT.md`.
- Record architecture decisions in `docs/architecture/`.
