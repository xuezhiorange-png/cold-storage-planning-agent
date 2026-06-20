# AGENTS.md

## Project Rules

This repository implements the Cold Storage Planning Design Agent V1 for conceptual cold-room planning for blueberry and produce processing facilities.

## Architecture

- Use a module-first modular monolith. Do not introduce microservices in V1.
- Backend modules live under `backend/src/cold_storage/modules/<module>/`.
- Dependencies flow from API to Application to Domain.
- Infrastructure implements ports defined by Domain or Application layers.
- Deterministic engineering calculators live in `calculations/domain` and must not access databases, files, HTTP, Redis, environment variables, model SDKs, or mutable global state.

## Safety

- The system is a planning and concept-design assistant, not a construction drawing or final equipment selection system.
- Do not claim to replace design institutes, registered engineers, fire review, structural design, electrical construction design, pressure-piping design, or final equipment selection.
- Demo coefficients must be marked `demo`, `unverified`, and `requires_review=true`.

## Code Quality

- Do not create vague dumping-ground files such as `utils.py`, `helpers.py`, `misc.py`, `managers.py`, `common_service.py`, `base_manager.py`, `service_v2.py`, or `temp.py`.
- Keep business rules in the owning module.
- Keep API routes free of engineering formulas.
- Keep Vue components free of engineering formulas.
- Reports read persisted calculation results and must not recalculate formulas.

## CodeGraph

If a `.codegraph/` directory exists at the repository root, use CodeGraph before grep/find or direct file reading when locating or understanding code.
