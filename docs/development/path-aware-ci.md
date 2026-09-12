# Local feedback and path-aware clean-environment CI

Task: `CI_PATH_AWARE_TEST_MATRIX_R1`.
Baseline: `3ffb3790f85a990283ce972733c3f43b44d1e899`.

Local tests are the primary development feedback loop. GitHub CI verifies the
selected scope in a clean environment. This scope-specific guidance supersedes
the older all-lanes validation example in CONTRIBUTING.md; it does not relax
production, database, release or deployment checks.

## Selection policy

`scripts/ci/classify_changes.py` uses Python's standard library. No path-filter
action or external service decides which checks run. File paths are obtained
with `git diff --no-renames --name-only -z`; deletions and both sides of moves
are included. Paths are never interpolated into shell commands.

| Changed paths | Scope | Required regular jobs |
| --- | --- | --- |
| Only docs/** and/or backend/tests/architecture/** | DOCS_ARCHITECTURE_ONLY | lightweight |
| backend/src/** or non-architecture backend/tests/** (with optional docs) | BACKEND | backend-sqlite, backend-postgresql, compose-config, release-evidence, recovery-foundation |
| Only frontend/** | FRONTEND | frontend, release-evidence |
| backend + frontend | BACKEND_FRONTEND | all six original jobs |
| frontend + docs/architecture | FULL | all six original jobs, so contract checks still run |
| Infrastructure, dependencies, CI itself | FULL (DATABASE_INFRA_FULL) | all six original jobs |
| Unknown, empty, invalid or unavailable diff | FULL | all six original jobs |

FULL always takes precedence. Infrastructure includes `.github/**`,
`scripts/ci/**` (including its tests), `backend/alembic/**`, `deployment/**`,
Dockerfile/Dockerfile.* anywhere, docker-compose*/compose*.yml or .yaml,
`backend/alembic.ini`, all backend bootstrap/release modules, backend
infrastructure directories and backend config.py/settings.py/entrypoint.py.
Dependency/manifests include pyproject.toml, requirements*.txt/*.in,
package.json, package-lock.json, npm-shrinkwrap.json, uv.lock, other *.lock,
Pipfile, poetry/pdm locks, yarn.lock, pnpm-lock.yaml, bun.lock/bun.lockb,
Cargo/go/Gemfile manifests and locks, .python-version/.node-version/.nvmrc/.npmrc.
Other unrecognized paths (including root Makefile or .env.example) also force
FULL. These rules precede the language prefixes; frontend dependency changes
therefore run FULL, not just frontend. Unknown paths never select lightweight.

Backend changes keep all existing SQLite/PostgreSQL tests, architecture, lint,
mypy, migration roundtrips, Compose production-image/empty-volume/readiness
checks, recovery foundation and release evidence. This intentionally retains
the production checks even for a backend-only change. Frontend keeps its
existing lint, tests, typecheck and build.

## Events and final status

- `pull_request`: exact event `pull_request.base.sha` → `pull_request.head.sha`.
  `github.sha` is deliberately not used for this diff because it can identify
  a synthetic merge. Test execution can still use checkout's normal merge ref.
- `push`: event `before` → `github.sha`.
- Zero SHAs, branch creation/deletion, missing commits/event data, invalid SHA,
  empty diff or unrecognized events select FULL. SHA values must resolve to
  commits. A non-UTF-8 filename also fails safe to FULL.
- `workflow_dispatch`: FULL by default. All existing manual inputs, job names
  and authorization conditions remain unchanged. Classification never enables
  live capture, transport, attestation, assembly or controlled recovery.

`classify-changes` runs its own unit tests on every event, emits the selection
to the job summary and checks changed-line whitespace when a validated diff
is available. `lightweight` installs the locked backend environment and runs
architecture/contract tests and ruff; it has no database service, migrations,
image build, Compose smoke, full database suite or frontend build.

`ci-gate` always runs after every selected/optional job. It requires successful
classification and internally consistent outputs. Every required job must
succeed; a required skipped/cancelled/failed job fails the gate. Unselected
jobs may be skipped. An executed manual job failure/cancellation also fails
the gate; its existing authorization condition continues to control whether
it executes. Missing job statuses fail closed. Future branch protection can
require the stable **ci-gate** check; this change does not edit branch protection.

```ini
CI_SELF_CHANGE_FORCES_FULL=true
STABLE_FINAL_CHECK_NAME=ci-gate
MUST_PRESERVE_MANUAL_GATED_WORKFLOWS=true
CURRENT_PR_EXPECTED_SCOPE=FULL
```

## Local commands before a Draft PR

Run from repository root; use Python 3.12+ and the project's uv environment so
historical subprocess tests also resolve the correct python3 executable.

Docs/contracts/architecture-only:

```sh
(cd backend && uv run pytest tests/architecture)
(cd backend && uv run ruff check . && uv run ruff format --check .)
git diff --check
```

Backend changes:

```sh
(cd backend && uv run pytest tests/unit/<relevant-test>.py)
(cd backend && uv run pytest tests/architecture)
(cd backend && PYTHONPATH=src DATABASE_BACKEND=sqlite uv run pytest)
(cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src)
git diff --check
```

Run the repository's PostgreSQL acceptance path locally when changing database
or persistence behavior with a configured local PostgreSQL instance. CI's full
PostgreSQL gate remains required for BACKEND/FULL. Do not skip required tests
or change unrelated expectations to make a lane green.

Frontend changes:

```sh
(cd frontend && npm ci && npm run lint && npm run test && npm run typecheck && npm run build)
git diff --check
```

Classifier/workflow changes require the full GitHub matrix and additionally:

```sh
python3 -m unittest discover -s scripts/ci/tests -v
(cd backend && uv run ruff check --config pyproject.toml ../scripts/ci)
(cd backend && uv run ruff format --check --config pyproject.toml ../scripts/ci)
(cd backend && uv run mypy --strict ../scripts/ci/classify_changes.py ../scripts/ci/ci_gate.py)
python3 scripts/ci/classify_changes.py --paths docs/foo.md
python3 scripts/ci/classify_changes.py --paths .github/workflows/ci.yml
```

Local passing results permit submitting a Draft. They do not authorize Ready,
Merge, release or deployment, and do not substitute for the required clean
GitHub checks before a later Ready decision.

## PR #269 simulation and job comparison

Simulated files:

```text
backend/tests/architecture/test_v22_p0_site_constrained_layout_contract.py
docs/architecture/ADR-044-site-constrained-factory-layout-authority.md
docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md
docs/tasks/V2_2-version-plan.md
```

| Job | Previous docs PR | New docs-only selection |
| --- | --- | --- |
| compose-config (image + PostgreSQL lifecycle smoke) | run | skip |
| backend-sqlite (migrations + full suite) | run | skip |
| backend-postgresql | run | skip |
| frontend | run | skip |
| recovery-foundation (PostgreSQL) | run | skip |
| release-evidence (runtime evidence suites) | run | skip |
| classify-changes | absent | run |
| lightweight (architecture/contracts/lint) | absent | run |
| ci-gate | absent | run |

```ini
PR269_SCOPE=DOCS_ARCHITECTURE_ONLY
BACKEND_FULL=false
FRONTEND=false
DATABASE_INFRA_FULL=false
HEAVY_JOB_COUNT_BEFORE=6
HEAVY_JOB_COUNT_AFTER_FOR_DOCS_ONLY=0
```

Here “heavy jobs” means the six previously unconditional regular lanes; it is
not a duration estimate. Manual gated jobs stay skipped unless separately
authorized through their original conditions. New-branch push with zero before
SHA still runs FULL; a PR event with the four valid paths selects lightweight.

Unit tests also simulate architecture-only, backend-only, frontend-only,
backend+frontend, migration, workflow self-change and unknown paths. No fixed
minute reduction is promised.
