# V0.9 Process-Input Runbook — Operator-Minimal Sample

This runbook is the operator path for the **V0.9 operator-minimal sample**: migrate
schema, seed the bundled sample through current public APIs (five KEY leaves only),
and verify five-stage persistence plus draft/formal report export on **unmodified**
`create_app`.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- The manifest contains **only** five `OperatorProcessInputV1` 1.1.0 KEY leaves. The
  backend assembler (P1) expands them into `EngineeringInputBundleV1`; operators
  do not type downstream KEY forms.
- Demo catalog leaves remain `source_type=demo`, `validity_status=unverified` or
  `conflict`, and `requires_review=true`. Treat every numeric output as
  review-required.
- Precooling rooms receive the v05 workbench freezer envelope demo package
  (including `-18°C` room design temperature). These values are **not**
  operator-typed and require engineering review before any production use.
- The core local path does **not** require live MiMo or any model API key.
- `AILY_LIVE_IMPLEMENTATION=NO` — this runbook does not authorize live Aily.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, GitHub Release, or P7 controlled acceptance.
- V0.9 uses `POST .../five-stage-execution` with `operator_process_input`. It
  does **not** use V0.4 `planning-run`, legacy `POST .../scheme-runs`, or
  `GET /api/v1/demo/scheme-comparison` as report authority.
- Report `mark-reviewed` in the seed loader uses a **local TestClient actor
  override** (`v09-local-trusted-reviewer`). This is **not** production RBAC.
  The default HTTP actor (`system`) is untrusted and must fail closed for
  `mark_reviewed`.

## Prerequisites

- Python tooling via `uv` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@567732f` or later with V0.9 P3 merged.
- Optional: Docker Engine for PostgreSQL support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v09-sample
make verify-v09-sample
```

`make verify-v09-sample` runs the bounded loader verify path:

1. Five-stage persistence via `operator_process_input` assembler path
2. Persisted zone plan includes `shipping_channel` and dual precooling schemes
3. Frozen production weight revision seed (`wsr-production-default-v1`)
4. `POST .../production-scheme-runs` with `profile_codes=["balanced"]`
5. Report create/generate with `project_summary` and
   `scheme_comparison.review_authority`
6. **Draft** `zh-CN`/`en-US` DOCX+PDF render **without** `mark_reviewed`
7. `submit-review` → trusted `mark-reviewed` → `approve`
8. **Formal** `zh-CN`/`en-US` DOCX+PDF render and artifact download
9. Restart stability for calculation and report hashes
10. Untrusted `mark-reviewed` fail-closed check

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

The seed step creates (or reuses) project **V0.9 算子最小输入示例项目** and
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
| `finished_storage_days` | 7 | day |
| `frozen_storage_days` | 10 | day |
| `main_packaging_storage_days` | 4 | day |
| `auxiliary_packaging_storage_days` | 12 | day |

All other engineering leaves are supplied by the backend assembler from catalog
and persisted upstream lineage.

#### Workbench binding options

**Option 1 — UI picker:** use the project list and open
**V0.9 算子最小输入示例项目**.

**Option 2 — engineering inputs route:** navigate to
`/workbench/engineering-inputs` after selecting the seeded project.

**Option 3 — direct localStorage binding:** after seeding, note the printed
`V09_SAMPLE_PROJECT_ID` and set browser localStorage key
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

### Report export (workbench)

Navigate to **报告输出** (`/workbench/reports`):

1. Create and generate a report from the bound project version.
2. Inspect persisted `project_summary` and `scheme_comparison.review_authority`
   shown from the exported JSON (read-only).
3. **Draft export** (`mode=draft`) is available before review approval.
4. Request review actions through the export panel (backend revalidates).
5. After approval, render formal `zh-CN`/`en-US` DOCX/PDF when workflow
   eligibility allows.

## Path B — PostgreSQL

Ensure PostgreSQL is running (for example `make up`), then:

```bash
export DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_URL=postgresql://cold_storage:cold_storage@localhost:5432/cold_storage
make migrate
make seed-v09-sample
make verify-v09-sample
```

Integration tests under `backend/tests/integration/test_v09_p6_operator_sample_postgresql.py`
mirror this path.

## Operator verification commands

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
pytest tests/integration/test_v09_p6_operator_sample_sqlite.py -q
```

When PostgreSQL is available:

```bash
DATABASE_BACKEND=postgresql pytest tests/integration/test_v09_p6_operator_sample_postgresql.py -q
```

## Coexistence with V0.7 and V0.8 samples

The V0.7 trust-loop sample (`make seed-v07-sample`) and V0.8 operator-minimal
sample (`make seed-v08-sample`) remain available and unchanged. V0.9 adds a
separate five-KEY path that does not replace earlier samples.

## What this runbook does not do

- Does not modify `v07_sample_loader.py`, `v08_sample_loader.py`, or earlier samples.
- Does not promote demo coefficients or recut calculator formulas.
- Does not claim production RBAC for trusted review actions.
- Does not bind demo `GET /api/v1/demo/scheme-comparison` to the sample version.
- Does not run Alembic inside the loader (run `make migrate` first).
- Does not authorize tag, Release, live Aily, or production deployment.
- Does not output construction drawings.

## Related contracts

- `docs/tasks/V0_9-P0-version-contract.md`
- `docs/tasks/V0_9-P1-operator-key-assembler-contract.md`
- `docs/tasks/V0_9-P6-operator-sample-runbook-contract.md`
