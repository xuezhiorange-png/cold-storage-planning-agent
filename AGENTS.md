# AGENTS.md

## Project Boundary

This repository implements the Cold Storage Planning Agent for cold-room planning
and concept-design assistance for blueberry and other produce processing
facilities.

- The project is a planning and concept-design assistant.
- It does not replace design institutes, registered engineers, fire review,
  structural design, electrical construction design, pressure piping design, or
  final equipment selection.
- It must not claim to output construction drawings.
- It must not directly control field equipment.

## Engineering Calculation Rules

- Large models must not directly calculate engineering values.
- Storage capacity, precooling capacity, room area, cooling load, investment,
  and equipment capability must be produced by deterministic Python services.
- Every calculation result must persist or expose:
  input, units, formulas, calculator version, coefficients, sources,
  assumptions, warnings, and review status.
- Missing key engineering parameters must return an explicit error and must not
  be guessed silently.
- Demo coefficients must always be marked `source_type=demo`,
  `validity_status=unverified`, and `requires_review=true`.

## Architecture Rules

- Use a module-first modular monolith. Do not introduce microservices in V1.
- Backend modules live under `backend/src/cold_storage/modules/<module>/`.
- Dependency direction is `API -> Application -> Domain`.
- Infrastructure implements ports owned by Domain or Application.

### Forbidden dependencies

- Domain must not depend on FastAPI.
- Domain must not depend on SQLAlchemy.
- Domain must not depend on Redis.
- Domain must not depend on model SDKs.
- Calculations must not depend on databases.
- Calculations must not depend on Agent services.
- Calculations must not access the network.
- Agent code must not directly operate ORM models.
- Agent code must not directly obtain database sessions.
- API routes must not contain engineering formulas.
- Vue components must not duplicate engineering formulas.
- Report templates must not duplicate engineering formulas.
- Prompts must not embed full calculation logic.

## Maintainability Rules

- Do not create vague dumping-ground modules such as `utils.py`, `helpers.py`,
  `misc.py`, `managers.py`, `common_service.py`, `base_manager.py`,
  `service_v2.py`, or `temp.py`.
- Business rules belong to the owning module.
- Major architecture changes require a new ADR in `docs/architecture/`.
- Temporary compromises must be recorded in `docs/TECH_DEBT.md`.
- Database schema changes must go through Alembic.
- Approved project versions must not be modified in place.
- Every task must include tests.
- Every PR should cover one well-bounded change set.
- Do not rewrite the whole project in one task.

## Current Baseline Notes

- The current repository baseline still has documented gaps between target
  architecture and implementation. Use `docs/audit/` and `docs/roadmap/` before
  making architecture claims.
- Reports must read persisted calculation results and must not recalculate
  formulas.

## CodeGraph

If a `.codegraph/` directory exists at the repository root, use CodeGraph
before grep/find or direct file reading when locating or understanding code.
