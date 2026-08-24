# V0.4 Local Runnable Delivery

This runbook is the operator path for the **V0.4 local persisted workbench**:
run the app locally with SQLite (default) or optional Docker Compose
dependencies, then open the bundled sample project in the workbench.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- Demo coefficients remain `source_type=demo`, `validity_status=unverified`,
  and `requires_review=true`. Treat every numeric output as review-required.
- The **core local path does not require live MiMo** or any model API key.
  Agent assistance may show as unavailable; that is expected in local mode.
- This runbook does **not** authorize production deployment, formula recut,
  tag, or GitHub Release.

## Prerequisites

- Python tooling via `uv` and Node.js via `npm` (see `docs/DEVELOPMENT.md`).
- Repository checkout at `main@05b0fd0` or later with V04-P1/P2/P3 assets present.
- Optional: Docker Engine for PostgreSQL/Redis support services only.

## Path A — SQLite (recommended)

From the repository root:

```bash
cp .env.example .env
make install
make migrate
make seed-v04-sample
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

The seed step creates (or reuses) project **V0.4 本地示例项目** and persists
design inputs plus a planning run through current `main` APIs:

1. `POST /api/v1/projects`
2. `PUT /api/v1/projects/{id}/versions/{version}/inputs`
3. `POST /api/v1/projects/{id}/versions/{version}/planning-run`

Persisted calculation rows today:

- `cold_room_zone_plan`
- `investment_estimate`
- `power_configuration`

Cooling load and equipment persistence remain future scope. This sample does not
invent a second calculator or bypass public APIs.

#### Workbench binding options

**Option 1 — UI picker:** use the project list and open **V0.4 本地示例项目**.

**Option 2 — direct localStorage binding:** after seeding, note the printed
`V04_LOCAL_SAMPLE_PROJECT_ID` and set browser localStorage key
`cold_storage_workbench_context` to:

```json
{"projectId":"<project-id>","versionNumber":1}
```

Reload the workbench.

### Verify the sample loaded

```bash
make smoke-v04-local
```

Or manually:

```bash
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/health/ready
curl -s http://127.0.0.1:8000/api/v1/projects | jq '.[] | select(.name=="V0.4 本地示例项目")'
```

Replace `<project-id>` from the seed output:

```bash
curl -s "http://127.0.0.1:8000/api/v1/projects/<project-id>/versions/1/calculations" | jq '.[].calculator_name'
```

Expected calculator names include `cold_room_zone_plan`,
`investment_estimate`, and `power_configuration`.

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
make seed-v04-sample
```

Continue with `make dev` and the frontend dev server as in Path A.

`docker-compose.production.yml` is a production verification surface and is
out of scope for this local usability runbook.

## Sample fixture location

Authoritative fixture:

```text
samples/v04-local-workbench/manifest.json
```

Fields:

- `project` — create-project payload
- `inputs` — persisted design inputs (`PUT .../inputs`)
- `planning_run_request` — optional planning-run body (empty object uses saved inputs)

Loader module:

```text
backend/src/cold_storage/bootstrap/v04_local_sample.py
```

Re-run seeding safely; it is idempotent by project name. The loader assumes
schema is already at Alembic head — run ``make migrate`` first.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `no such table` / migration errors | Run `make migrate` before `make seed-v04-sample`. |
| Empty workbench project | Confirm backend is on `:8000` and frontend proxy is running. |
| Missing persisted results | Re-run `make seed-v04-sample` and inspect `GET .../calculations`. |
| Agent drawer unavailable | Expected without live MiMo; core planning path still works. |

## Related docs

- `docs/DEVELOPMENT.md` — install, quality gates, PostgreSQL testing notes
- `docs/runbooks/V0_3-P1-review-formal-report-acceptance.md` — controlled
  five-stage production acceptance (separate from this local sample)
- `docs/tasks/V0_4-P5-controlled-acceptance-contract.md` — V0.4 P5 controlled
  acceptance matrix (sqlite; no tag/Release)
- Parent tracking: GitHub issue #150 (V0.4 umbrella), package issues #153 (P3),
  #155/#159 (P5)
