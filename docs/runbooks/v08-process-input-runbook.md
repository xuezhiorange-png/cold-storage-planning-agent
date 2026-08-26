# V0.8 Process-Input Runbook — Operator-Minimal Sample

This runbook is the operator path for the **V0.8 operator-minimal sample**: migrate
schema, seed the bundled sample through current public APIs (five KEY leaves only),
and verify five-stage persistence plus the report trust loop on **unmodified**
`create_app`.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- The manifest contains **only** five `OperatorProcessInputV1` KEY leaves. The
  backend assembler (P1) expands them into `EngineeringInputBundleV1`; operators
  do not type downstream KEY forms.
- Demo catalog leaves remain `source_type=demo`, `validity_status=unverified` or
  `conflict`, and `requires_review=true`. Treat every numeric output as
  review-required.
- Precooling rooms receive the v05 workbench freezer envelope demo package
  (including `-18°C` room design temperature). These values are **not**
  operator-typed and require engineering review before any production use.
- The core local path does **not** require live MiMo or any model API key.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, GitHub Release, live Aily, or P4 controlled
  acceptance dispatch.
- V0.8 uses `POST .../five-stage-execution` with `operator_process_input`. It
  does **not** use V0.4 `planning-run`, legacy `POST .../scheme-runs`, or
  `GET /api/v1/demo/scheme-comparison` as report authority.
- Report `mark-reviewed` in the seed loader uses a **local TestClient actor
  override** (`v08-local-trusted-reviewer`). This is **not** production RBAC.
  The default HTTP actor (`system`) is untrusted and must fail closed for
  `mark_reviewed`.

## Prerequisites

- Python tooling via `uv` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@1961d7a` or later with V0.8 P1 merged.
- Optional: Docker Engine for PostgreSQL support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v08-sample
make verify-v08-sample
```

`make verify-v08-sample` runs the bounded loader verify path:

1. Five-stage persistence via `operator_process_input` assembler path
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

The seed step creates (or reuses) project **V0.8 算子最小输入示例项目** and
persists the canonical five-stage chain via the assembler path:

1. `POST /api/v1/projects`
2. `POST /api/v1/projects/{id}/versions/{version}/five-stage-execution`
   with `operator_process_input` (five KEY only) and `idempotency_key`
3. `POST /api/v1/projects/{id}/versions/{version}/production-scheme-runs`

Persisted canonical calculation rows:

- `cold_room_zone_plan`
- `cooling_load`
- `equipment`
- `installed_power`
- `investment_estimate`

`power_configuration` is supplemental only and must not satisfy the canonical
`installed_power` slot.

#### Operator five KEY (manifest)

| Leaf | Value | Unit |
| --- | --- | --- |
| `daily_inbound_mass_kg` | 20000 | kg/day |
| `working_time_h_per_day` | 16 | h/day |
| `finished_storage_days` | 7 | day |
| `packaging_storage_days` | 1 | day |
| `precooling_required_ratio` | 0.6 | ratio |

All other engineering leaves are supplied by the backend assembler from catalog
and persisted upstream lineage.

#### Workbench binding options

**Option 1 — UI picker:** use the project list and open
**V0.8 算子最小输入示例项目**.

**Option 2 — engineering inputs route:** navigate to
`/workbench/engineering-inputs` after selecting the seeded project.

**Option 3 — direct localStorage binding:** after seeding, note the printed
`V08_SAMPLE_PROJECT_ID` and set browser localStorage key
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
make seed-v08-sample
make verify-v08-sample
```

Integration tests under `backend/tests/integration/test_v08_p3_operator_sample_postgresql.py`
mirror this path.

## Operator verification commands

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
pytest tests/integration/test_v08_p3_operator_sample_sqlite.py -q
```

When PostgreSQL is available:

```bash
DATABASE_BACKEND=postgresql pytest tests/integration/test_v08_p3_operator_sample_postgresql.py -q
```

## Coexistence with V0.7 sample

The V0.7 trust-loop sample (`make seed-v07-sample`) remains available and
unchanged. V0.8 adds a separate operator-minimal path that does not replace
the full-bundle V0.7 sample.

## What this runbook does not do

- Does not modify `v07_sample_loader.py` or `samples/v07-trust-loop/**`.
- Does not promote demo coefficients or recut calculator formulas.
- Does not claim production RBAC for trusted review actions.
- Does not bind demo `GET /api/v1/demo/scheme-comparison` to the sample version.
- Does not run Alembic inside the loader (run `make migrate` first).
- Does not authorize tag, Release, live Aily, or production deployment.

## Related contracts

- `docs/tasks/V0_8-P0-operator-minimal-input-contract.md`
- `docs/tasks/V0_8-P1-process-input-assembler-contract.md`
- `docs/tasks/V0_8-P3-operator-sample-runbook-contract.md`
