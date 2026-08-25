# V0.6 Pilot Runbook — Five-Stage Review and Formal Delivery

This runbook is the operator path for the **V0.6 local five-stage review and
formal delivery sample**: migrate schema, seed the bundled explicit-input sample
through current public APIs, and verify persisted calculations, optional scheme
comparison, and report lifecycle closure without production deployment.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- Demo coefficients remain `source_type=demo`, `validity_status=unverified` or
  `conflict`, and `requires_review=true`. Treat every numeric output as
  review-required.
- The **core local path does not require live MiMo** or any model API key.
  Agent assistance may show as unavailable; that is expected and must not block
  the five-stage engineering chain or report APIs.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, GitHub Release, or P5 controlled acceptance
  dispatch.
- V0.6 uses `POST .../five-stage-execution` only. It does **not** use V0.4
  `planning-run` as canonical five-stage proof.
- Report `mark-reviewed` in the seed loader uses a **local TestClient actor
  override** (`v06-local-trusted-reviewer`). This is **not** production RBAC.
  The default HTTP actor (`system`) is untrusted and must fail closed for formal
  export without a persisted trusted `mark_reviewed` proof.

## Prerequisites

- Python tooling via `uv` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@dbd03a10` or later with V0.6 P3/P4A assets present.
- Optional: Docker Engine for PostgreSQL support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v06-sample
make verify-v06-sample
```

`make verify-v06-sample` (alias `make smoke-v06-local`) runs the bounded loader
verify path: five-stage persistence, scheme attempt via public APIs when demo
weights are available, report create/generate/submit-review/mark-reviewed/
approve, formal `zh-CN`/`en-US` DOCX+PDF render (or fail-closed `409`), restart
with stable calculation/report hashes, and artifact download.

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

The seed step creates (or reuses) project **V0.6 五阶段正式交付示例项目** and
persists the canonical five-stage chain through current `main` APIs:

1. `POST /api/v1/projects`
2. `POST /api/v1/projects/{id}/versions/{version}/five-stage-execution`

Persisted canonical calculation rows:

- `cold_room_zone_plan`
- `cooling_load`
- `equipment`
- `installed_power`
- `investment_estimate`

`power_configuration` is supplemental only and must not satisfy the canonical
`installed_power` slot.

#### Workbench binding options

**Option 1 — UI picker:** use the project list and open **V0.6 五阶段正式交付示例项目**.

**Option 2 — engineering inputs route:** navigate to
`/workbench/engineering-inputs` after selecting the seeded project.

**Option 3 — direct localStorage binding:** after seeding, note the printed
`V06_SAMPLE_PROJECT_ID` and set browser localStorage key
`cold_storage_workbench_context` to:

```json
{"projectId":"<project-id>","versionNumber":1}
```

Reload the workbench.

### Scheme comparison (public bootstrap, fail-closed on sample version)

The loader bootstraps the demo weight set and exercises scheme comparison through
the existing public demo endpoint (`GET /api/v1/demo/scheme-comparison`).

`POST /api/v1/projects/{id}/versions/{version}/scheme-runs` is **not** invoked on
the sample project version because it persists legacy `source_mode` scheme rows
that make unmodified `create_app` report assembly fail closed in production
scheme readback. Report APIs therefore proceed from persisted five-stage results
only.

### Report lifecycle (verify path)

Existing report APIs only:

```text
POST /api/v1/reports
POST /api/v1/reports/{id}/generate
POST /api/v1/reports/{id}/submit-review
POST /api/v1/reports/{id}/mark-reviewed   (trusted local seed actor only)
POST /api/v1/reports/{id}/approve
POST /api/v1/reports/{id}/revisions/{n}/render  (mode=formal, locale=zh-CN|en-US, format=docx|pdf)
GET  /api/v1/reports/{id}/exports/{artifact_id}/download
```

Formal export without trusted `mark_reviewed` proof returns `409 ExportPermissionError`.

On unmodified `create_app` (the same surface as `make dev`), report
`submit-review` may fail closed with `409` when required sections such as
`project_summary` or `scheme_comparison` are missing from the assembled JSON.
`make verify-v06-sample` records this fail-closed path and still proves report
create/generate, formal render `409`, restart-stable calculation/report hashes,
and untrusted-actor RBAC rejection.

### Verify the sample loaded

```bash
make verify-v06-sample
```

Or manually after `make dev`:

```bash
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/api/v1/projects | jq '.[] | select(.name=="V0.6 五阶段正式交付示例项目")'
```

Replace `<project-id>` from the seed output:

```bash
curl -s "http://127.0.0.1:8000/api/v1/projects/<project-id>/versions/1/calculations" | jq '.[].calculator_name'
```

Expected canonical calculator names are exactly the five listed above.

## Path B — Docker Compose PostgreSQL (optional)

Root `docker-compose.yml` starts **PostgreSQL and Redis only**. It does not
start the backend or frontend containers.

```bash
docker compose up -d
```

Configure PostgreSQL explicitly (`.env.example` documents the keys) and run
migrations against that database URL before seeding:

```bash
export DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_URL=postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage
make migrate
make seed-v06-sample
make verify-v06-sample
```

Continue with `make dev` and the frontend dev server as in Path A.

## Sample fixture location

Authoritative fixture:

```text
samples/v06-formal-delivery/manifest.json
```

Fields:

- `project` — create-project payload
- `engineering_input_bundle` — explicit `EngineeringInputBundleV1` leaves
  (`state=provided` on all KEY leaves, including `condensing_temperature_c`
  and cooling geometry)
- `five_stage_execution.idempotency_key` — stable idempotency key for seeding

Loader module:

```text
backend/src/cold_storage/bootstrap/v06_sample_loader.py
```

Re-run seeding safely; it is idempotent by project name and idempotency key.
The loader assumes schema is already at Alembic head — run ``make migrate`` first.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `no such table` / migration errors | Run `make migrate` before `make seed-v06-sample`. |
| Empty workbench project | Confirm backend is on `:8000` and frontend proxy is running. |
| Missing canonical five rows | Re-run `make seed-v06-sample` and inspect `GET .../calculations`. |
| Scheme run `422` / `409` | Demo bootstrap may be unavailable; reports still proceed from five-stage rows. |
| Legacy `scheme-runs` on sample version | Avoid on sample project; use demo bootstrap only (see above). |
| Formal render `409` | Expected without trusted `mark_reviewed`; use `make verify-v06-sample` path. |
| Agent drawer unavailable | Expected without live MiMo; core five-stage chain still works. |
| Only three V0.4 calculators present | You likely seeded the V0.4 sample; use `make seed-v06-sample`. |

## Related docs

- `docs/DEVELOPMENT.md` — install, quality gates, PostgreSQL testing notes
- `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md` — frozen V0.6 contract
- `docs/runbooks/v05-local-run.md` — V0.5 local five-stage workbench sample
- Parent tracking: GitHub issue #176 (umbrella), #181 (tracking), #194 (dispatch)
