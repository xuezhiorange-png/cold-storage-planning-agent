# V0.5 Controlled Acceptance Runbook

This runbook assembles **bounded V0.5 P5 controlled acceptance evidence** for the
canonical persisted five-stage workbench. It proves the local/CI path is ready for
a later `v0.5.0` release gate. It does **not** execute controlled acceptance
dispatch, create tags, publish GitHub Releases, or deploy production.

## Scope and boundaries

- Planning/concept-design assistant only — not construction design, registered
  engineering, or field equipment control.
- Core path completes without live MiMo or model API keys.
- Demo coefficients remain `source_type=demo`, `validity_status` in
  `{unverified, conflict}`, and `requires_review=true`.
- V0.5 proof uses `POST .../five-stage-execution` only. V0.4 `planning-run` is
  **not** V0.5 canonical proof.
- `power_configuration` is supplemental only and must not satisfy canonical
  `installed_power`.

## Source identity gates (frozen baseline)

Record these when assembling evidence for independent review:

```text
BASE_MAIN_SHA=7e187d52198d708bdaa5006ca48c7da880983286
BASE_TREE=3a2497b025a2413c3b9c2f4af9b6a6628714aea6
PREVIOUS_RELEASE_TAG=v0.4.0
PROPOSED_FUTURE_RELEASE=v0.5.0
CI_GATE=main@BASE_MAIN_SHA with CI green (recorded separately; not implied by local PASS)
```

Later gates remain **UNAUTHORIZED** in this package:

```text
MERGE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
```

## Prerequisites

- Repository checkout at `main@7e187d52198d708bdaa5006ca48c7da880983286` or later
  with V0.5 P0–P4 assets present.
- Python tooling via `uv` (see `docs/DEVELOPMENT.md`).
- For PostgreSQL matrix cells: `DATABASE_BACKEND=postgresql` with a reachable test
  database (see CI job configuration).

## Step 1 — Local bounded verification (sqlite)

From the repository root:

```bash
make lint
make typecheck
make verify-v05-p5-controlled-acceptance
```

`verify-v05-p5-controlled-acceptance` runs:

- `backend/tests/architecture/test_v05_p5_controlled_acceptance_contract.py`
- `backend/tests/integration/test_v05_p5_controlled_acceptance_sqlite.py`
- `backend/tests/integration/test_v05_p4_local_sample_smoke.py`

Equivalent direct invocation:

```bash
cd backend && PYTHONPATH=src uv run pytest \
  tests/architecture/test_v05_p5_controlled_acceptance_contract.py \
  tests/integration/test_v05_p5_controlled_acceptance_sqlite.py \
  tests/integration/test_v05_p4_local_sample_smoke.py \
  -q
```

## Step 2 — PostgreSQL matrix (CI parity)

PostgreSQL cells run in CI when `DATABASE_BACKEND=postgresql`:

```bash
cd backend && PYTHONPATH=src DATABASE_BACKEND=postgresql uv run pytest \
  tests/integration/test_v05_p5_controlled_acceptance_postgresql.py \
  -q
```

Do not treat sqlite-only PASS as postgresql parity.

## Step 3 — Sample seed sanity (operator smoke)

Optional operator smoke after `make migrate`:

```bash
make seed-v05-sample
make smoke-v05-local
```

The seed loader calls public APIs only:

1. `POST /api/v1/projects`
2. `POST /api/v1/projects/{id}/versions/{version}/five-stage-execution`

It does **not** call `planning-run` or Alembic.

Persisted canonical calculators:

- `cold_room_zone_plan`
- `cooling_load`
- `equipment`
- `installed_power`
- `investment_estimate`

## Evidence cells checklist

| # | Cell | Pass signal |
| --- | --- | --- |
| 1 | Source identity recorded | contract + runbook contain `BASE_MAIN_SHA` / `BASE_TREE` |
| 2 | Explicit-input sample seed | `samples/v05-local-workbench` via five-stage-execution |
| 3 | Canonical five + lineage | ids, hashes, upstream keys match P0 DAG |
| 4 | Restart persistence | same ids/hashes after reopen |
| 5 | Missing KEY fail-closed | `condensing_temperature_c`, `zone_area` → atomic failure |
| 6 | Consumers read persisted rows | workflow/scheme/report use `installed_power` |
| 7 | Demo markings preserved | demo/unverified/requires_review |
| 8 | Agent optional | agent_assistance not fake-available |

## What this runbook does not do

```text
ANNOTATED_V0_5_0_TAG=NO
GITHUB_RELEASE_V0_5_0=NO
CONTROLLED_ACCEPTANCE_EXECUTION_DISPATCH=NO
PRODUCTION_COMPOSE=NO
V03_P5_STAGE_ENGINE=NO
V03_SCENARIO_A_B_C=NO
```

Tag, Release, merge, and controlled-acceptance execution require separate later
authorization tracked in issue #169.

## Related docs

- `docs/tasks/V0_5-P5-controlled-acceptance-contract.md` — frozen P5 contract
- `docs/tasks/V0_5-P0-five-stage-workbench-contract.md` — P0 five-stage contract
- `docs/runbooks/v05-local-run.md` — operator local workbench path (P4)
- Parent tracking: GitHub issue #163 (V0.5 umbrella), issue #169 (P5 tracking)
