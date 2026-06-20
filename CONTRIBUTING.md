# Contributing

## Branching

- Use task-scoped branches such as `codex/task-1-quality-baseline`.
- Do not commit governance or feature work directly on `main`.
- Do not use force push on shared branches.

## Scope Discipline

- Each PR should solve one bounded task.
- Preserve existing behavior unless the task explicitly changes it.
- Do not add empty placeholder modules for future tasks.
- Record non-trivial architecture decisions in `docs/architecture/`.
- Record temporary compromises in `docs/TECH_DEBT.md`.

## Validation

Run what the repository currently supports before opening a PR:

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

## Sensitive Data

- Never commit `.env`, local databases, caches, uploads, generated reports,
  certificates, or private customer documents.
- Keep `.env.example` as the only tracked environment template.

## Architecture Expectations

- API should call application services instead of embedding engineering logic.
- Domain code must stay framework-free.
- Deterministic engineering calculations must stay outside model prompts and UI
  components.
