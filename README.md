# Cold Storage Planning Agent

Cold Storage Planning Agent is a repository for conceptual cold-room planning
for blueberry and produce processing facilities. The system covers project
inputs, deterministic engineering calculations, planning comparisons, knowledge
retrieval, report drafts, and a structured frontend workbench.

This system is a planning assistant, not a construction drawing system. It does
not replace design institutes, registered engineers, formal review workflows,
or final equipment selection.

## Current Baseline

The repository now has a preserved local code baseline tagged
`local-baseline-2026-06-20`. Governance and audit work for the next phase lives
on `codex/task-0-repository-audit`.

Use these documents before changing architecture:

- `docs/audit/current-state.md`
- `docs/audit/validation-baseline.md`
- `docs/audit/gap-analysis.md`
- `docs/roadmap/DEVELOPMENT_PLAN.md`
- `CODEX_TASKS.md`

## Actual Current Tech Stack

- Backend runtime: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- Backend local persistence today: SQLite by default
- Target infrastructure in repo: PostgreSQL and Redis via Docker Compose
- Frontend: Vue 3, TypeScript, Vite, Element Plus, Vue Router, Pinia, ECharts
- Quality tooling: pytest, Ruff, mypy, ESLint, Vue TSC, Vitest

## Commands

```bash
make install
make dev
make up
make down
make migrate
make seed
make test
make lint
make format
make typecheck
make architecture-test
make demo
make clean-dev
```

`make clean-dev` is for local development only and may remove local generated
data.

## Local Backend

```bash
cd backend
UV_CACHE_DIR=../.uv-cache uv sync
PYTHONPATH=src UV_CACHE_DIR=../.uv-cache uv run uvicorn cold_storage.bootstrap.app:create_app --factory --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Current Scope Notes

- Deterministic calculators currently drive engineering numbers.
- Cooling load, equipment capability, and installed power calculators are
  deterministic and traceable (Task 5). kW(r) and kW(e) are strictly separated.
- Fake model gateways are the default.
- Demo coefficients are explicitly unverified and require review.
- OCR is not implemented in V1; scanned PDFs are marked `requires_ocr=true`.
- The repository contains target-architecture docs that are ahead of the
  current implementation. Check `docs/audit/current-state.md` for the gap.

## Calculation Modules (Task 5)

| Calculator | Module | Purpose |
|---|---|---|
| Cooling load | `calculations/domain/cooling_load.py` | Envelope, product, infiltration, internal, defrost loads |
| Equipment capability | `calculations/domain/equipment.py` | Evaporator, compressor, condenser capability |
| Installed power | `calculations/domain/power.py` | Electrical installed capacity (kW(e)) |

See `docs/calculations/` for detailed specifications.
