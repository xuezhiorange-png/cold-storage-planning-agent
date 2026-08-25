# V0.6 Pilot Runbook — Five-Stage Review and Formal Delivery

This runbook is the operator path for the **V0.6 formal delivery sample**:
migrate, seed the bundled explicit-input project, exercise the canonical
five-stage chain, optional scheme comparison, and the report review-to-formal
closure path — without production deployment, tag, or release.

Parent tracking: GitHub issue #176. Package tracking: #181. Dispatch: #194.

## Scope and boundaries

- This is a **concept-design planning assistant**, not construction design,
  registered engineering, or field equipment control.
- Demo coefficients remain `source_type=demo`, `validity_status=unverified`,
  and `requires_review=true`. Treat every numeric output as review-required.
- The **core local path does not require live MiMo** or any model API key.
- This runbook does **not** authorize production deployment, formula recut,
  coefficient promotion, tag, or GitHub Release.
- V0.6 uses `POST .../five-stage-execution` for canonical five-stage proof.
  It does **not** use V0.4 `planning-run`.
- Formal export without a trusted `mark_reviewed` proof must remain
  **409 ExportPermissionError** (fail-closed).

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
```

Verify restart-stable IDs/hashes and formal delivery closure:

```bash
make verify-v06-sample
```

Start the backend API:

```bash
make dev
```

### What the seed step creates

The seed step creates (or reuses) project **V0.6 正式交付示例项目** and
persists the canonical five-stage chain through current public APIs:

1. `POST /api/v1/projects`
2. `POST /api/v1/projects/{id}/versions/{version}/five-stage-execution`
3. `GET /api/v1/demo/scheme-comparison` (bootstraps the demo weight set only)
4. `POST /api/v1/projects/{id}/versions/{version}/scheme-runs` when available
5. `POST /api/v1/reports` → `generate` → `submit-review` → `mark-reviewed` → `approve`
6. `POST /api/v1/reports/{id}/revisions/{n}/render` for formal `zh-CN` / `en-US`
   `docx` + `pdf`, then artifact download

Persisted canonical calculation rows:

- `cold_room_zone_plan`
- `cooling_load`
- `equipment`
- `installed_power`
- `investment_estimate`

`power_configuration` is supplemental only and must not satisfy the canonical
`installed_power` slot.

### Trusted seed actor (not production RBAC)

The loader overrides the HTTP actor to `v06-local-trusted-reviewer` **only
inside the seed-process TestClient** so `mark-reviewed` can persist the
trusted proof required for formal export. Default HTTP actor `system` is not
trusted and formal render without that proof stays **409**.

This override is a **local seed convenience**, not production RBAC.

### Manual verification

```bash
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/api/v1/projects | jq '.[] | select(.name=="V0.6 正式交付示例项目")'
```

Replace `<project-id>` from the seed output:

```bash
curl -s "http://127.0.0.1:8000/api/v1/projects/<project-id>/versions/1/calculations" | jq '.[].calculator_name'
```

## Path B — Docker Compose PostgreSQL (optional)

Root `docker-compose.yml` starts **PostgreSQL and Redis only**. It does not
start the backend container.

```bash
docker compose up -d
```

Configure PostgreSQL explicitly and run migrations before seeding:

```bash
export COLD_STORAGE_DATABASE_BACKEND=postgresql
export COLD_STORAGE_DATABASE_URL=postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage
make migrate
make seed-v06-sample
make verify-v06-sample
```

## Sample fixture location

Authoritative fixture:

```text
samples/v06-formal-delivery/manifest.json
```

Fields:

- `project` — create-project payload
- `engineering_input_bundle` — explicit `EngineeringInputBundleV1` leaves
- `five_stage_execution.idempotency_key` — stable idempotency key for seeding

Loader module:

```text
backend/src/cold_storage/bootstrap/v06_sample_loader.py
```

Re-run seeding safely; it is idempotent by project name and idempotency key.
The loader assumes schema is already at Alembic head — run `make migrate` first.

## Fail-closed behavior

| Condition | Expected behavior |
| --- | --- |
| Scheme weight set unavailable | `scheme-runs` skipped or fails; five-stage report APIs still run from persisted calculators |
| `mark-reviewed` without trusted actor | Rejected; formal render returns **409** |
| Formal render before approval | **409 ExportPermissionError** |
| Missing `COLD_STORAGE_STORAGE_DIR` at render time | Render service fails closed (configure storage for formal artifacts) |
| Production report seam blocks formal generate | Documented fail-closed; do not patch reports production from this package |

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `no such table` / migration errors | Run `make migrate` before `make seed-v06-sample`. |
| Missing canonical five rows | Re-run `make seed-v06-sample` and inspect `GET .../calculations`. |
| `verify-v06-sample` formal render 409 | Confirm trusted seed actor path; report must reach `approved`. |
| Scheme run 422 weight set not found | Call `GET /api/v1/demo/scheme-comparison` once, then retry seed. |
| Only three V0.4 calculators present | You likely seeded the V0.4 sample; use `make seed-v06-sample`. |

## Related docs

- `docs/DEVELOPMENT.md` — install, quality gates, PostgreSQL testing notes
- `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md` — frozen V0.6 contract
- `docs/runbooks/v05-local-run.md` — V0.5 local five-stage workbench sample
- Parent tracking: GitHub issue #176 (umbrella), package issue #181 (P4B), dispatch #194
