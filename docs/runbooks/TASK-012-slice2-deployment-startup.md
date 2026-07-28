# TASK-012 Slice 2 — Deployment and Startup Operations Runbook

This runbook is the operator-facing companion to the binding contract
`docs/tasks/TASK-012-slice2-deployment-startup-lifecycle-contract.md`.
Every command below targets the lifecycle boundaries frozen by that
contract; nothing here re-opens Slice 1 design decisions.

## 1. Build identity authority

The single source of truth for build identity at runtime is the
in-image authority file `/opt/cold-storage/build-identity.json`,
written at image build time by `backend/Dockerfile`. The bootstrap
layer (`bootstrap.deployment_identity`) cross-checks the file against
`COLD_STORAGE_BUILD_COMMIT_SHA` and `COLD_STORAGE_BUILD_VERSION`.

| Failure code                | Trigger                                              |
| --------------------------- | ---------------------------------------------------- |
| `BUILD_IDENTITY_FILE_MISSING` | Image omitted the file.                              |
| `BUILD_IDENTITY_FILE_MALFORMED` | File is unreadable JSON or has the wrong key set. |
| `BUILD_IDENTITY_SCHEMA_UNSUPPORTED` | `schema_version != 1`.                       |
| `BUILD_IDENTITY_COMMIT_INVALID` | `commit_sha` is not 40-char lowercase hex.       |
| `BUILD_IDENTITY_VERSION_INVALID` | `version` violates the ASCII 1..64 character contract. |
| `BUILD_COMMIT_MISMATCH`     | Runtime env differs from the file's `commit_sha`.    |
| `BUILD_VERSION_MISMATCH`    | Runtime env differs from the file's `version`.       |
| `DEPLOYMENT_ID_INVALID`     | `COLD_STORAGE_DEPLOYMENT_ID` does not match the deployment-id pattern. |

Operators MUST NOT edit `/opt/cold-storage/build-identity.json` inside
a running container. The image is the only legitimate writer. To
change build identity, rebuild the image with new
`COLD_STORAGE_BUILD_COMMIT_SHA` / `COLD_STORAGE_BUILD_VERSION` args.

## 2. Probe timeouts

Two env vars bind the startup and readiness probe budget:

| Env var                                  | Default                  | Required in  |
| ---------------------------------------- | ------------------------ | ------------ |
| `COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS`   | 30 (local/test)         | staging/production |
| `COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS` | 5  (local/test)         | staging/production |

Validation ranges (`bootstrap.runtime_readiness`):

| Variable                  | Min (s) | Max (s) |
| ------------------------- | ------- | ------- |
| startup probe timeout     | 1       | 120     |
| readiness probe timeout   | 1       | 30      |

A forced probe timeout fails closed with `STARTUP_PROBE_TIMEOUT` or
`READINESS_PROBE_TIMEOUT` respectively. While readiness reports 503
due to probe timeout, **liveness continues to return 200**.

The contract section D-S2-03.c forbids asserting equality with
`MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT`. Tests assert
completion within the conservative upper bound, not exact equality.

## 3. Lifecycle state machine

| State                | Trigger                                  | Effect on `/health/live` | Effect on `/health/ready` |
| -------------------- | ---------------------------------------- | ------------------------ | ------------------------ |
| `INITIALIZING`       | Process boot, before startup probes run. | 200                      | 503                       |
| `READY`              | All startup probes passed; defenses satisfied. | 200                      | 200                       |
| `DRAINING`           | `SIGTERM` or `SIGINT` received, before engine disposal. | 200                  | 503                       |
| `SHUTDOWN_COMPLETE`  | Engine disposed, dependencies cleared.   | 503 (process exiting)    | 503                       |

Liveness MUST NOT probe the database. Readiness owns dependency probes
through `bootstrap.runtime_readiness.run_readiness_phase`. The
shutdown ordering (D-S2-10) is:

1. mark readiness unavailable (state → `DRAINING`);
2. stop admitting new work;
3. bounded grace period;
4. dispose database engine and other dependencies;
5. clear runtime singletons/state;
6. terminate.

## 4. Production Compose operations

The production Compose surface is `docker-compose.production.yml` at
the repository root. It defines three services:

| Service     | Purpose                                                    |
| ----------- | ---------------------------------------------------------- |
| `postgres`  | Health-checked PostgreSQL with a persistent volume.        |
| `migration` | One-shot Alembic upgrade, declared in CI for image equality. |
| `backend`   | Runtime application, liveness/readiness health checks.     |

The volume `artifact_data` is mounted on
`/opt/cold-storage/artifacts` so application container replacement
preserves generated reports. Operators MUST NOT mount this path onto
a path that contains `.git`, an `admin/` directory, or any path
component matching `local`, `test`, or `staging` (per the existing
strict-environment validator).

### 4.1 Build invocation

```bash
COLD_STORAGE_BUILD_COMMIT_SHA="$(git rev-parse HEAD)" \
COLD_STORAGE_BUILD_VERSION="v0.1.0" \
docker compose -f docker-compose.production.yml build --pull
```

The CI runner supplies these exactly. Local operators may use the
documented non-production defaults baked into the Dockerfile, but they
MUST NOT claim production readiness without the explicit strict
env vars below.

### 4.2 Run invocation

```bash
POSTGRES_USER=cold_storage \
POSTGRES_PASSWORD='<operator-supplied via secret manager>' \
POSTGRES_DB=cold_storage \
COLD_STORAGE_BUILD_COMMIT_SHA="$(git rev-parse HEAD)" \
COLD_STORAGE_BUILD_VERSION="v0.1.0" \
COLD_STORAGE_DEPLOYMENT_ID="deploy-$(date -u +%Y%m%d%H%M%S)" \
COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS=120 \
COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS=30 \
docker compose -f docker-compose.production.yml up -d
```

Cleanup of test containers MUST NOT delete operator-owned external
production resources. The CI runner provides its own ephemeral
`postgres_data` and `artifact_data` volumes.

## 5. Fail-closed troubleshooting

If startup blocks with `BUILD_*` or `DEPLOYMENT_ID_INVALID`:

1. Re-derive the `commit_sha` and `version` from the *intended* image:
   `docker inspect --format='{{index .Config.Labels "cold-storage.build.commit_sha"}}' <image>`.
2. Compare against `COLD_STORAGE_BUILD_COMMIT_SHA` /
   `COLD_STORAGE_BUILD_VERSION` declared in the operator environment.
3. If they disagree, fix the deployment manifest — DO NOT mutate the
   in-image file or relax the runtime env var.
4. If they agree, the file is corrupted: rebuild the image, do not
   patch the running container.

If startup blocks with `STARTUP_PROBE_TIMEOUT` /
`READINESS_PROBE_TIMEOUT`:

1. Inspect `bootstrap.runtime_readiness` probe outcomes in the
   operator log (the existing redaction authority MUST be in effect).
2. The aggregate upper bound is conservative; serial execution may
   approach it; parallel execution may complete faster. Do NOT tune
   the value to "exactly" meet the bound.
3. If the per-probe budget genuinely must rise, raise it within the
   documented bounds (`[1, 120]` for startup, `[1, 30]` for
   readiness). Do not bypass the validator.

If `UNSAFE_STRICT_CAPABILITY_WIRING` is raised:

1. This is a defensive assertion triggered because a registered
   strict-mode capability is reachable. It SHOULD NOT happen in
   production; if it does, the canonical code path (D-S2-06.a/b) has
   regressed. Open a contract-amendment discussion before relaxing.
2. Do NOT silence the assertion or comment it out. The contract
   forbids it.

## 6. Strict capability enumeration

Two registered strict-mode capabilities MUST NOT be reachable as HTTP
route backends in staging or production:

| Capability                                       | Where it could leak                          |
| ------------------------------------------------ | -------------------------------------------- |
| `PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE`    | `FakeAgentModelGateway` route registration.  |
| `COEFFICIENT_HTTP_ROUTE_STRICT_MODE`             | Process-in-memory `CoefficientService()` route. |

The defense-in-depth assertion in
`bootstrap.runtime_readiness.assert_no_unsafe_strict_capabilities`
enumerates these at startup. Any new strict-mode capability MUST be
added to the registry in the same PR that introduces the capability;
free-form additions elsewhere are forbidden.

## 7. CI ownership

The four top-level jobs remain the owning authority:

| Job                  | Owns                                                                            |
| -------------------- | ------------------------------------------------------------------------------- |
| `backend-sqlite`     | unit, local/test lifecycle, health state-machine, architecture, ruff, mypy.     |
| `backend-postgresql` | staging/production startup lifecycle, exact Alembic head, coefficient readiness, strict artifact/capability admission, in-image build-identity authority. |
| `compose-config`     | root + production Compose syntax, image build, non-root assertion, migration/application smoke, live/ready smoke, exact build identity assertion, in-container user cannot modify `0444` file, secret and artifact persistence, forced startup/readiness timeout smoke. |
| `frontend`           | Existing frontend quality gate.                                                 |

No top-level job may push an image, perform a deployment, or create a
release. Any smoke command above MUST be deterministic and exit the
process on failure with the stable failure code.
