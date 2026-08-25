# V0.5 Local Five-Stage Runnable Delivery

This runbook is the operator path for the **V0.5 local persisted five-stage
workbench**: run the app locally with SQLite (default) or optional Docker
Compose dependencies, seed the bundled explicit-input sample, and verify the
canonical five-stage chain without production deployment.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- Demo coefficients remain `source_type=demo`, `validity_status=unverified`,
  and `requires_review=true`. Treat every numeric output as review-required.
- The **core local path does not require live MiMo** or any model API key.
  Agent assistance may show as unavailable; that is expected and must not block
  the five-stage engineering chain.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, or GitHub Release.
- V0.5 P4 uses `POST .../five-stage-execution` only. It does **not** use
  V0.4 `planning-run` as canonical five-stage proof.

## Prerequisites

- Python tooling via `uv` and Node.js via `npm` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@b123210` or later with V0.5 P1/P2/P3 assets present.
- Optional: Docker Engine for PostgreSQL/Redis support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v05-sample
```

Start the backend API:

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

The seed step creates (or reuses) project **V0.5 本地五阶段示例项目** and
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

**Option 1 — UI picker:** use the project list and open **V0.5 本地五阶段示例项目**.

**Option 2 — engineering inputs route:** navigate to
`/workbench/engineering-inputs` after selecting the seeded project.

**Option 3 — direct localStorage binding:** after seeding, note the printed
`V05_LOCAL_SAMPLE_PROJECT_ID` and set browser localStorage key
`cold_storage_workbench_context` to:

```json
{"projectId":"<project-id>","versionNumber":1}
```

Reload the workbench.

### Verify the sample loaded

```bash
make smoke-v05-local
```

Or manually:

```bash
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/health/ready
curl -s http://127.0.0.1:8000/api/v1/projects | jq '.[] | select(.name=="V0.5 本地五阶段示例项目")'
```

Replace `<project-id>` from the seed output:

```bash
curl -s "http://127.0.0.1:8000/api/v1/projects/<project-id>/versions/1/calculations" | jq '.[].calculator_name'
```

Expected canonical calculator names are exactly the five listed above. An
optional supplemental `power_configuration` row may appear from legacy paths
but must not replace `installed_power`.

## Path B — Docker Compose support services (optional)

Root `docker-compose.yml` starts **PostgreSQL and Redis only**. It does not
start the backend or frontend containers.

```bash
docker compose up -d
```

Then configure PostgreSQL explicitly (`.env.example` documents the keys) and
run migrations against that database URL before seeding:

```bash
export COLD_STORAGE_DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_URL=postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage
make migrate
make seed-v05-sample
```

Continue with `make dev` and the frontend dev server as in Path A.

## Sample fixture location

Authoritative fixture:

```text
samples/v05-local-workbench/manifest.json
```

Fields:

- `project` — create-project payload
- `engineering_input_bundle` — explicit `EngineeringInputBundleV1` leaves
  (`state=provided` on all KEY leaves, including `condensing_temperature_c`
  and cooling geometry)
- `five_stage_execution.idempotency_key` — stable idempotency key for seeding

Loader module:

```text
backend/src/cold_storage/bootstrap/v05_local_sample.py
```

Re-run seeding safely; it is idempotent by project name and idempotency key.
The loader assumes schema is already at Alembic head — run ``make migrate`` first.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `no such table` / migration errors | Run `make migrate` before `make seed-v05-sample`. |
| Empty workbench project | Confirm backend is on `:8000` and frontend proxy is running. |
| Missing canonical five rows | Re-run `make seed-v05-sample` and inspect `GET .../calculations`. |
| Agent drawer unavailable | Expected without live MiMo; core five-stage chain still works. |
| Only three V0.4 calculators present | You likely seeded the V0.4 sample; use `make seed-v05-sample`. |

## Related docs

- `docs/DEVELOPMENT.md` — install, quality gates, PostgreSQL testing notes
- `docs/tasks/V0_5-P0-five-stage-workbench-contract.md` — frozen five-stage contract
- `docs/runbooks/v04-local-run.md` — V0.4 local three-row planning sample (legacy)
- Parent tracking: GitHub issue #163 (V0.5 umbrella), package issue #168 (P4)
