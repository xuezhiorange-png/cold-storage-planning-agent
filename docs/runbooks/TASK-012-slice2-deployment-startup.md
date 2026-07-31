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

## 8. Schema-head classification (V0.2 Slice 2 amendment, D-S2-12.a.v0.2)

The exact schema-head verification probe (probe 4 of the mandatory
readiness tuple) classifies every non-timeout failure as the single
public stable code `DATABASE_SCHEMA_HEAD_INVALID`. The probe runs in
strict modes (staging / production) only; local / test mode skips it.

### 8.1 When this code is produced

The code `DATABASE_SCHEMA_HEAD_INVALID` is produced **only** when the
exact schema-head verification probe runs to completion and reports a
non-timeout failure. The internal closed set of non-timeout reasons
is frozen at exactly 11 entries:

| Internal reason                          | Trigger                                                                            |
| ---------------------------------------- | ---------------------------------------------------------------------------------- |
| `PACKAGED_HEAD_MISSING`                  | `COLD_STORAGE_PACKAGED_ALEMBIC_HEAD` env var is unset or whitespace-only.           |
| `PACKAGED_HEAD_UNREADABLE`               | (Reserved — currently a degenerate case of `PACKAGED_HEAD_MALFORMED`.)              |
| `PACKAGED_HEAD_MALFORMED`                | Packaged head is not a 12-char lowercase hex Alembic revision.                     |
| `PACKAGED_HEAD_ZERO`                     | Packaged head is the empty string after trimming.                                  |
| `PACKAGED_HEAD_MULTIPLE`                 | Packaged head contains `,` (multi-revision values are forbidden).                  |
| `DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION` | The `SELECT version_num FROM alembic_version` query raised an exception.       |
| `DATABASE_HEAD_ZERO`                     | The query returned no rows.                                                        |
| `DATABASE_HEAD_MULTIPLE`                 | (Reserved — same treatment as malformed; row cardinality collapse.)                 |
| `DATABASE_HEAD_MALFORMED`                | Recorded head is not a 12-char lowercase hex Alembic revision.                     |
| `DATABASE_HEAD_MISMATCH`                 | Packaged and recorded heads differ.                                                |
| `UNKNOWN_SCHEMA_IDENTITY`                | Canonical Settings authority is not initialized (configuration bootstrap missing).   |

These reasons MUST NOT be introduced as additional public stable
codes; they all project to the single public code
`DATABASE_SCHEMA_HEAD_INVALID`. The internal reason string is
preserved in the safe detail envelope for log consumption.

### 8.2 When this code is NOT produced

`DATABASE_SCHEMA_HEAD_INVALID` MUST NOT be used for any of:

- Connection-class failures (use the existing `DATABASE_CONNECTION_*` codes).
- Identity / capability / lifecycle / migration / artifact failures
  (those have their own stable codes).
- Genuine timeout events (those map to `STARTUP_PROBE_TIMEOUT` /
  `READINESS_PROBE_TIMEOUT`).

### 8.3 Operator triage

When the readiness endpoint returns 503 with
`check_code=DATABASE_SCHEMA_HEAD_INVALID`:

1. Compare the running image's `COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`
   against the `version_num` recorded in the `alembic_version` table.
   Do NOT log the actual values to the public health endpoint or to
   any operator-visible log line that may be retained — the safe
   projection only records `probe=database_exact_alembic_head` and
   `check_code=DATABASE_SCHEMA_HEAD_INVALID`.
2. If the packaged head is missing or malformed, rebuild the image so
   `COLD_STORAGE_PACKAGED_ALEMBIC_HEAD` is set explicitly at build
   time. The application process NEVER runs migrations (D-S2-01); the
   migration service is the only legitimate writer to the
   `alembic_version` table.
3. If the recorded head is stale, run the dedicated migration service
   to advance the schema; do NOT relax the runtime probe.
4. If the recorded head is malformed, treat the database as corrupt:
   restore from a known-good backup or rebuild the database from
   scratch via the migration service.

### 8.4 Log envelope

Logs MAY record:

```
probe=database_exact_alembic_head
check_code=DATABASE_SCHEMA_HEAD_INVALID
```

Logs MUST NOT record the raw packaged head value or the raw recorded
head value. Logs MUST NOT record the underlying exception text or the
underlying database URL.

### 8.5 Public health response envelope

The `/health/ready` response, when the probe fails, MAY expose only:

```json
{
  "status": "not_ready",
  "state": "<safe lifecycle state>",
  "check_code": "DATABASE_SCHEMA_HEAD_INVALID"
}
```

The response MUST NOT expose the raw exception text, database URL,
DSN, password, secret, SQL, full filesystem path, packaged Head value,
recorded Head value, or Alembic row contents. The application process
MUST NOT execute migrations on behalf of the operator.
