# V0.7 Trust-Loop Runbook — Operator Sample and Formal Delivery

This runbook is the operator path for the **V0.7 trust-loop sample**: migrate
schema, seed the bundled sample through current public APIs (five-stage +
production scheme + report lifecycle), and verify the full review/formal export
loop on **unmodified** `create_app`.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- Demo coefficients remain `source_type=demo`, `validity_status=unverified` or
  `conflict`, and `requires_review=true`. Treat every numeric output as
  review-required.
- The core local path does **not** require live MiMo or any model API key.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, GitHub Release, or P7 controlled acceptance
  dispatch.
- V0.7 uses `POST .../five-stage-execution` and
  `POST .../production-scheme-runs` only. It does **not** use V0.4
  `planning-run`, legacy `POST .../scheme-runs`, or
  `GET /api/v1/demo/scheme-comparison` as report authority.
- Report `mark-reviewed` in the seed loader uses a **local TestClient actor
  override** (`v07-local-trusted-reviewer`). This is **not** production RBAC.
  The default HTTP actor (`system`) is untrusted and must fail closed for
  `mark_reviewed`.

## Prerequisites

- Python tooling via `uv` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@e6ad66e` or later with V0.7 P3A/P3B merged.
- Optional: Docker Engine for PostgreSQL support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v07-sample
make verify-v07-sample
```

`make verify-v07-sample` runs the bounded loader verify path:

1. Five-stage persistence through public APIs
2. Frozen production weight revision seed (`wsr-production-default-v1`)
3. `POST .../production-scheme-runs` with `profile_codes=["balanced"]`
4. Report create/generate with `project_summary` and
   `scheme_comparison.review_authority`
5. `submit-review` → trusted `mark-reviewed` → `approve`
6. Formal `zh-CN`/`en-US` DOCX+PDF render and artifact download
7. Restart stability for calculation and report hashes
8. Untrusted `mark-reviewed` fail-closed check

Start the backend API for manual inspection:

```bash
make dev
```

In a second terminal, start the frontend workbench:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Open `http://localhost:5173`.

### Load the sample project

The seed step creates (or reuses) project **V0.7 信任闭环操作员示例项目** and
persists the canonical five-stage chain plus a production scheme run:

1. `POST /api/v1/projects`
2. `POST /api/v1/projects/{id}/versions/{version}/five-stage-execution`
3. `POST /api/v1/projects/{id}/versions/{version}/production-scheme-runs`

Persisted canonical calculation rows:

- `cold_room_zone_plan`
- `cooling_load`
- `equipment`
- `installed_power`
- `investment_estimate`

`power_configuration` is supplemental only and must not satisfy the canonical
`installed_power` slot.

#### Workbench binding options

**Option 1 — UI picker:** use the project list and open
**V0.7 信任闭环操作员示例项目**.

**Option 2 — engineering inputs route:** navigate to
`/workbench/engineering-inputs` after selecting the seeded project.

**Option 3 — direct localStorage binding:** after seeding, note the printed
`V07_SAMPLE_PROJECT_ID` and set browser localStorage key
`cold_storage_workbench_context` to:

```json
{"projectId":"<project-id>","versionNumber":1}
```

### Production scheme run (workbench)

On the calculations / five-stage progress view, use **生产方案评分** to call
`POST .../production-scheme-runs` with:

```json
{
  "profile_codes": ["balanced"],
  "weight_set_revision_id": "wsr-production-default-v1",
  "profile_parameters": {}
}
```

The UI displays persisted run metadata only — it does not compute engineering
values in Vue.

### Report trust-loop (workbench)

Navigate to **报告输出** (`/workbench/reports`):

1. Create and generate a report from the bound project version.
2. Inspect persisted `project_summary` and `scheme_comparison.review_authority`
   shown from the exported JSON (read-only).
3. Request review actions through the export panel (backend revalidates).
4. After approval, render formal `zh-CN`/`en-US` DOCX/PDF when workflow
   eligibility allows.

## Path B — PostgreSQL

Ensure PostgreSQL is running (for example `make up`), then:

```bash
export DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_URL=postgresql://cold_storage:cold_storage@localhost:5432/cold_storage
make migrate
make seed-v07-sample
make verify-v07-sample
```

Integration tests under `backend/tests/integration/test_v07_p5_operator_sample_postgresql.py`
mirror this path.

## Operator verification commands

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
pytest tests/integration/test_v07_p5_operator_sample_sqlite.py -q
```

When PostgreSQL is available:

```bash
DATABASE_BACKEND=postgresql pytest tests/integration/test_v07_p5_operator_sample_postgresql.py -q
```

## What this runbook does not do

- Does not modify `v06_sample_loader.py` or weaken V0.6 fail-closed evidence.
- Does not promote demo coefficients or recut calculator formulas.
- Does not claim production RBAC for trusted review actions.
- Does not bind demo `GET /api/v1/demo/scheme-comparison` to the sample version.
- Does not run Alembic inside the loader (run `make migrate` first).

## Related contracts

- `docs/tasks/V0_7-P0-trust-loop-contract.md`
- `docs/tasks/V0_7-P3A-report-production-composition-contract.md`
- `docs/tasks/V0_7-P3B-production-scheme-public-api-contract.md`
- `docs/tasks/V0_7-P5-operator-sample-runbook-contract.md`
