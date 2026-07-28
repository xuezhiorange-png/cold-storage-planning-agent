# TASK-012 Slice 2 — Deployment Artifact and Startup Lifecycle Contract

## 1. Document status and authority

```text
TASK=TASK-012
SLICE=2
SLICE_NAME=DEPLOYMENT_ARTIFACT_AND_STARTUP_LIFECYCLE
DOCUMENT_KIND=IMPLEMENTATION_CONTRACT
DOCUMENT_STATUS=FROZEN_CANDIDATE_ON_BRANCH
SOURCE_ISSUE=73
SOURCE_REVIEW=TASK012_POST_SLICE1_NEXT_SLICE_READ_ONLY_SCOPE_REVIEW
IMPLEMENTATION_BASE=main@16abd0e1367e9f2c6f1ea9c0983803f166bebda2
PREDECESSOR_PR=74
PREDECESSOR_HEAD=0b72dc6111eaad5228c1e8de2fa01fe2d97f331b
PREDECESSOR_MERGE_COMMIT=16abd0e1367e9f2c6f1ea9c0983803f166bebda2
```

This document freezes the proposed implementation boundary for TASK-012 Slice 2.
It does not authorize implementation by itself.

The text becomes binding repository authority only after all of the following
have been separately authorized and verified:

1. this contract PR passes exact-head CI and independent engineering review;
2. Draft-to-Ready transition is separately authorized and completed;
3. Merge is separately authorized and completed;
4. the merge commit is verified as the current `main` identity.

```text
FREEZE_TEXT_ON_BRANCH_CREATES_IMPLEMENTATION_AUTHORITY=NO
PR_CREATION_CREATES_IMPLEMENTATION_AUTHORITY=NO
READY_CREATES_IMPLEMENTATION_AUTHORITY=NO
MERGE_PLUS_POST_MERGE_MAIN_IDENTITY_REQUIRED_FOR_BINDING_AUTHORITY=YES
SLICE2_IMPLEMENTATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
```

## 2. Context

TASK-012 Slice 1, merged through PR #74, established the canonical
`local`, `test`, `staging`, and `production` environment model; deterministic
configuration precedence; strict-environment validation; secret and DSN
redaction; and database, secret, and artifact environment identity checks.

Slice 2 builds only the deployment artifact and process lifecycle foundation
on top of that merged baseline. It does not reopen or redesign Slice 1.

The repository state at the implementation base has these relevant gaps:

- `/health/live` and `/health/ready` are static success responses;
- the existing startup readiness gate validates approved coefficient coverage
  in production but is not the full runtime dependency readiness authority;
- staging is a strict configuration environment but does not yet have a frozen
  runtime startup/readiness contract equivalent to production;
- the root Compose file is local infrastructure only and contains no application
  image, production secret injection, artifact volume, migration job, or build
  identity;
- CI validates Compose syntax but does not build or smoke-test a backend image;
- migration execution ownership and application schema-head verification are not
  frozen as a deployment lifecycle contract;
- production capability admission for fake or in-memory adapters is not frozen;
- shutdown ordering and readiness draining are not machine-verifiable.

## 3. Slice objective

Slice 2 shall establish a portable backend runtime and container foundation
with fail-closed startup and machine-verifiable health semantics.

The implementation shall provide:

1. an immutable backend build and deployment identity;
2. a production-oriented backend container image;
3. a separate production Compose surface without tracked plaintext secrets;
4. an explicit external migration owner and ordering contract;
5. startup validation before the application accepts requests;
6. distinct startup, liveness, and readiness semantics;
7. dynamic dependency-aware readiness;
8. staging and production runtime strictness;
9. artifact-storage lifecycle validation;
10. bounded shutdown with readiness draining and dependency disposal;
11. deterministic container smoke evidence in CI;
12. safe, redacted, machine-readable lifecycle failure evidence.

```text
SLICE2_PRIMARY_OUTCOME=BACKEND_RUNTIME_AND_CONTAINER_FOUNDATION
FAIL_CLOSED_STARTUP_REQUIRED=YES
STATIC_READY_RESPONSE_ALLOWED=NO
TRACKED_PLAINTEXT_PRODUCTION_SECRET_ALLOWED=NO
APPLICATION_AUTO_MIGRATION_ALLOWED=NO
AUTOMATIC_DOWNGRADE_ALLOWED=NO
```

## 4. Explicit non-goals

The following are outside this Slice:

```text
EXTERNAL_CLOUD_PROVISIONING=NO
EXTERNAL_PRODUCTION_DEPLOYMENT=NO
PRODUCTION_CREDENTIAL_CREATION=NO
PRODUCTION_CREDENTIAL_DISCLOSURE=NO
REGISTRY_PUSH=NO
TAG_CREATION=NO
RELEASE_CREATION=NO
FRONTEND_PRODUCTION_IMAGE=NO
REVERSE_PROXY_OR_TLS_TERMINATION=NO
OBSERVABILITY_METRICS_AND_ALERTING=NO
DISTRIBUTED_TRACING_IMPLEMENTATION=NO
BACKUP_RESTORE_IMPLEMENTATION=NO
AUTOMATED_ROLLBACK_ORCHESTRATOR=NO
AGENT_MODEL_GATEWAY_IMPLEMENTATION=NO
COEFFICIENT_DOMAIN_REDESIGN=NO
BUSINESS_FORMULA_CHANGE=NO
DATABASE_SCHEMA_CHANGE=NO
ALEMBIC_REVISION_CREATION=NO
TASK011_DEFERRED_SCOPE=NO
ISSUE72_SCOPE=NO
```

This Slice may fail closed when a production capability is backed by an
unapproved fake or in-memory adapter. It may not implement a replacement model
provider or redesign the coefficient domain.

## 5. Portable and provider-specific boundaries

The following requirements are portable and must not depend on a specific
cloud provider:

- OCI-compatible backend image;
- environment/secret injection through runtime configuration;
- external migration job ownership;
- build and deployment identity;
- health endpoint semantics;
- database and schema-head checks;
- persistent artifact directory checks;
- graceful shutdown behavior;
- deterministic smoke commands and exit codes.

Provider-specific manifests, managed database products, secret-manager APIs,
load-balancer annotations, registry credentials, autoscaling, and cloud resource
provisioning are explicitly deferred.

```text
PORTABLE_RUNTIME_CONTRACT=REQUIRED
PROVIDER_SPECIFIC_DEPLOYMENT_MANIFEST=DEFERRED
```

## 6. Frozen design decisions

### D-S2-01 — Migration ownership and ordering

The migration owner is a separate one-shot deployment process or Compose
service. The application process must not execute Alembic upgrades or downgrades.

Required ordering:

1. database service becomes reachable;
2. migration process executes `alembic upgrade head` and exits successfully;
3. application process starts;
4. application verifies one exact repository-supported Alembic head before
   becoming ready.

The application must reject:

- an unreachable database;
- a database behind the expected head;
- a database ahead of the packaged expected head;
- multiple database heads;
- multiple repository heads;
- an unknown or malformed schema identity.

```text
MIGRATION_OWNER=EXTERNAL_ONE_SHOT_PROCESS
APPLICATION_RUNS_MIGRATIONS=NO
APPLICATION_RUNS_DOWNGRADE=NO
APPLICATION_VERIFIES_EXACT_SCHEMA_HEAD=YES
MULTIPLE_HEADS_FAIL_CLOSED=YES
```

### D-S2-02 — Build and deployment identity

The canonical identity inputs are:

```text
COLD_STORAGE_BUILD_COMMIT_SHA
COLD_STORAGE_BUILD_VERSION
COLD_STORAGE_DEPLOYMENT_ID
```

For staging and production:

- all three values are required;
- commit SHA must be a full 40-character lowercase hexadecimal Git SHA;
- version must be non-empty and safe for machine-readable evidence;
- deployment ID must be an opaque, non-secret identifier;
- values must be included in safe lifecycle evidence;
- values must not be inferred from a mutable working tree at runtime;
- malformed, missing, or contradictory identity fails startup.

Local and test may use explicit test identities or a documented non-production
fallback, but they may never claim production readiness.

```text
STRICT_BUILD_IDENTITY_REQUIRED=YES
RUNTIME_GIT_DISCOVERY_AS_AUTHORITY=NO
BUILD_IDENTITY_SECRET=NO
```

### D-S2-03 — Startup, liveness, and readiness semantics

Startup is a pre-service lifecycle gate executed before the process is allowed
to report ready. Startup validates static and boot-time dependencies.

Liveness means only that the application process and request loop are alive.
It must not query the database, migration state, Redis, artifact storage, or
external services.

Readiness is dynamic and dependency-aware. It must return:

- HTTP 200 only when all mandatory readiness gates pass;
- HTTP 503 when any mandatory gate fails or shutdown draining has started.

The response body must contain stable check codes and status values only. It
must not contain raw exception text, SQL, DSNs, passwords, tokens, secret mount
contents, or unsafe filesystem details.

```text
STARTUP_SEMANTICS=PRE_SERVICE_FAIL_CLOSED
LIVENESS_SEMANTICS=PROCESS_ONLY
READINESS_SEMANTICS=DYNAMIC_DEPENDENCY_AWARE
READINESS_FAILURE_HTTP_STATUS=503
HEALTH_RESPONSE_SECRET_SAFE=YES
```

### D-S2-04 — Mandatory readiness dependency set

Readiness must evaluate these mandatory gates:

1. lifecycle initialization completed;
2. process is not draining or shutting down;
3. database connectivity succeeds;
4. database schema has the exact allowed Alembic head;
5. declared environment and resource identities remain valid;
6. artifact storage is correctly isolated, exists, and is writable;
7. approved coefficient startup readiness is satisfied for strict modes;
8. build and deployment identity is valid.

Redis is not a mandatory readiness dependency in this Slice because the current
application runtime does not establish Redis as a required production service.
It must not be added merely because the local Compose file contains Redis.

```text
REDIS_MANDATORY_READINESS_DEPENDENCY=NO
DEPENDENCY_INVENTION_ALLOWED=NO
```

### D-S2-05 — Staging strictness

Staging and production use the same classes of startup and readiness checks.
They differ only by declared environment identity, deployment identity, database,
secrets, artifact storage, and operator-controlled runtime resources.

Staging must not fall through a local/test skip path.

```text
STAGING_RUNTIME_STRICTNESS=PRODUCTION_EQUIVALENT_CHECK_CLASSES
STAGING_USES_LOCAL_OR_TEST_SKIP=NO
```

### D-S2-06 — Production capability admission

Strict-environment startup must identify production capabilities wired to fake
or in-memory implementations.

At minimum, the implementation must address:

- `FakeAgentModelGateway`;
- process-local/in-memory `CoefficientService` HTTP route wiring.

For each capability, the implementation must choose one of these two outcomes
and test it explicitly:

1. the capability is not registered/exposed in staging and production; or
2. strict startup rejects the process because the capability is not production
   admissible.

The implementation may not add a real model provider, redesign coefficient
persistence, or silently leave unsafe strict-mode wiring active.

```text
FAKE_AGENT_GATEWAY_STRICT_MODE_SILENT_ADMISSION=FORBIDDEN
IN_MEMORY_COEFFICIENT_HTTP_STRICT_MODE_SILENT_ADMISSION=FORBIDDEN
REPLACEMENT_PROVIDER_IMPLEMENTATION_AUTHORIZED=NO
```

### D-S2-07 — Artifact storage ownership

For staging and production, artifact storage must:

- use the Slice 1 canonical configuration authority;
- use an absolute path outside the repository;
- reside on a separately declared persistent volume or operator-owned mount;
- match the declared artifact environment identity;
- exist or be created only within the explicitly configured storage root;
- be writable by the non-root application user;
- reject symlink/path escape and cross-environment paths;
- fail startup or readiness without disclosing unsafe path details.

```text
STRICT_ARTIFACT_STORAGE_PERSISTENT=YES
STRICT_ARTIFACT_STORAGE_REPOSITORY_RELATIVE=NO
STRICT_ARTIFACT_STORAGE_WRITABLE_CHECK=YES
```

### D-S2-08 — Backend image contract

The backend image must:

- be built from `backend/Dockerfile`;
- use a pinned major/minor Python runtime compatible with project metadata;
- install dependencies from the repository lockfile without updating it;
- copy only required runtime source and migration assets;
- run as a non-root user;
- expose the configured application port without hard-coding production host
  credentials;
- use the repository-owned production entrypoint;
- not bake secrets, `.env` files, local databases, test outputs, or report
  artifacts into the image;
- carry build identity through explicit build arguments or immutable image
  metadata and validate the corresponding runtime identity.

```text
BACKEND_IMAGE_RUNS_AS_ROOT=NO
SECRETS_BAKED_IN_IMAGE=NO
LOCKFILE_UPDATE_AUTHORIZED=NO
```

### D-S2-09 — Production Compose contract

`docker-compose.production.yml` is a portable local/operator verification
surface, not a claim of production deployment certification.

It must define, at minimum:

- PostgreSQL with a health check and persistent database volume;
- a one-shot migration service;
- the backend application service;
- a persistent artifact volume;
- ordering that requires successful migration before application readiness;
- runtime secret/config references without tracked plaintext production values;
- build/deployment identity injection;
- backend liveness and readiness health checks.

The existing root `docker-compose.yml` remains the local development
infrastructure surface and is not modified by this Slice.

```text
ROOT_COMPOSE_CLASSIFICATION=LOCAL_DEVELOPMENT
ROOT_COMPOSE_MUTATION_AUTHORIZED=NO
PRODUCTION_COMPOSE_DEPLOYMENT_CERTIFICATION=NO
```

### D-S2-10 — Shutdown and failed-startup cleanup

Shutdown ordering is:

1. mark readiness unavailable and enter draining state;
2. stop admitting new work;
3. allow a bounded grace period for in-flight work;
4. dispose database resources;
5. clear runtime singletons/state;
6. terminate.

A failed startup must clean any partially initialized engine, services, and
runtime state before propagating failure. A second initialization attempt in a
test process must not inherit stale state from the failed attempt.

```text
READINESS_DRAIN_BEFORE_RESOURCE_DISPOSAL=YES
UNBOUNDED_SHUTDOWN_WAIT=NO
FAILED_STARTUP_PARTIAL_STATE_ALLOWED=NO
```

### D-S2-11 — Frontend topology

This Slice is a backend/runtime foundation only. It does not create a frontend
image, reverse proxy, static-file server, or full-stack deployment topology.
Those require a separate contract.

```text
FRONTEND_RUNTIME_TOPOLOGY=DEFERRED
BACKEND_ONLY_CONTAINER_FOUNDATION=YES
```

### D-S2-12 — Evidence and failure classification

Startup and readiness failures must expose stable machine-readable classes.
At minimum, distinguish:

- configuration identity failure;
- build/deployment identity failure;
- database connectivity failure;
- schema-head mismatch;
- artifact storage failure;
- coefficient readiness failure;
- production capability admission failure;
- lifecycle/draining state.

Logs and endpoint responses must use the existing redaction authority or a
strictly narrower safe projection. Raw exception interpolation is forbidden.

```text
STABLE_FAILURE_CODES_REQUIRED=YES
RAW_EXCEPTION_TEXT_IN_HEALTH_RESPONSE=NO
RAW_SECRET_OR_DSN_IN_EVIDENCE=NO
```

## 7. Exact future implementation path allowlist

This contract freezes a maximum of exactly 20 tracked paths for a future Slice 2
implementation PR.

```text
MAXIMUM_CHANGED_PATH_COUNT=20
CREATE_PATH_COUNT=12
MODIFY_PATH_COUNT=8
DELETE_PATH_COUNT=0
UNLISTED_TRACKED_PATH_AUTHORIZED=NO
```

### 7.1 CREATE — exactly 12 paths

```text
backend/Dockerfile
docker-compose.production.yml
backend/src/cold_storage/bootstrap/deployment_identity.py
backend/src/cold_storage/bootstrap/runtime_readiness.py
backend/src/cold_storage/bootstrap/production_entrypoint.py
backend/tests/unit/test_deployment_identity.py
backend/tests/unit/test_runtime_readiness.py
backend/tests/integration/test_startup_lifecycle_sqlite.py
backend/tests/integration/test_startup_lifecycle_postgresql.py
backend/tests/integration/test_health_endpoints.py
backend/tests/architecture/test_deployment_startup_boundaries.py
docs/runbooks/TASK-012-slice2-deployment-startup.md
```

### 7.2 MODIFY — exactly 8 paths

```text
.env.example
backend/src/cold_storage/bootstrap/environment_model.py
backend/src/cold_storage/bootstrap/settings.py
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/startup_readiness.py
.github/workflows/ci.yml
Makefile
```

### 7.3 DELETE

```text
NONE
```

### 7.4 Explicitly forbidden paths and surfaces

The following remain forbidden even if an implementation author believes they
would simplify the work:

```text
backend/alembic/versions/**
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/reports/**
backend/src/cold_storage/evaluation/**
frontend/**
docker-compose.yml
uv.lock
backend/uv.lock
```

No directory-wide interpretation is permitted. Only the 20 exact paths listed
above may change.

## 8. Semantic mutation limits by allowed path

### `.env.example`

May add non-secret example keys for build identity, deployment identity, and
lifecycle behavior. It may not contain production values, credentials, or real
DSNs.

### `environment_model.py` and `settings.py`

May add only settings required by this contract and strict validation for those
settings. Slice 1 source precedence, legacy behavior, resource identity, and
redaction contracts must remain intact.

### `app.py`

May replace static readiness behavior with lifecycle-owned health delegation and
apply strict capability admission. It may not change business endpoint schemas,
calculation behavior, or domain semantics.

### `dependencies.py`

May make initialization transactional, register lifecycle/readiness state, and
provide bounded shutdown cleanup. It may not introduce import-time singletons or
new domain services.

### `startup_readiness.py`

May broaden strict-mode invocation from production-only to staging and
production and integrate its existing coefficient result into the aggregate
runtime readiness authority. It may not redesign coefficient approval logic.

### `.github/workflows/ci.yml`

May add only the container build, production Compose validation, migration/app
smoke, and tests required by this contract. It may not publish images, create
releases, deploy, or add external cloud credentials.

### `Makefile`

May add deterministic local verification commands for production Compose,
migration, startup, smoke, and cleanup. It may not perform cloud deployment or
destructive database downgrade.

## 9. Acceptance matrix

### 9.1 Unit acceptance

Required tests:

- exact build commit SHA validation;
- required staging/production build and deployment identity;
- malformed and contradictory identity rejection;
- safe identity representation;
- mandatory readiness-gate aggregation;
- stable failure-code mapping;
- health projection redaction;
- staging and production strictness parity;
- local/test non-production behavior;
- failed startup cleanup and idempotent retry;
- readiness draining transition;
- capability admission decisions for fake/in-memory wiring.

### 9.2 SQLite acceptance

SQLite acceptance is limited to local/test lifecycle compatibility and health
state-machine behavior. SQLite must not be accepted as a staging or production
database.

Required evidence:

- local/test application startup succeeds with explicitly isolated SQLite;
- liveness does not query the database;
- readiness reflects initialization and draining state;
- shutdown disposes the engine and clears state;
- failed initialization leaves no singleton leakage;
- strict environment plus SQLite fails closed;
- health output contains no secret or unsafe exception text.

### 9.3 PostgreSQL acceptance

Required evidence:

- staging startup executes strict checks;
- production startup executes strict checks;
- database connectivity failure is classified and redacted;
- exact unique Alembic head passes;
- behind, ahead, unknown, and multiple-head states fail closed;
- coefficient startup readiness participates in aggregate readiness;
- artifact storage identity and writability are validated;
- capability admission is enforced;
- application does not run migrations;
- readiness returns 503 after mandatory dependency failure;
- liveness remains process-only;
- shutdown draining changes readiness before engine disposal;
- no DSN, password, token, secret, or unsafe path appears in evidence.

### 9.4 Container and Compose acceptance

Required evidence:

- `docker compose -f docker-compose.production.yml config` passes;
- backend image builds from a clean checkout;
- image runs as a non-root user;
- image contains no tracked `.env`, local SQLite database, test output, or
  generated artifact directory;
- production Compose contains no plaintext production credential;
- migration service succeeds before application service starts;
- application refuses an unmigrated database;
- application starts after successful migration;
- `/health/live` returns 200;
- `/health/ready` returns 200 only after all gates pass;
- `/health/ready` returns 503 when a mandatory gate is forced to fail;
- runtime-reported build SHA equals the exact expected implementation Head;
- artifact volume persists across application container replacement;
- cleanup removes test containers without deleting an operator-owned external
  production resource.

### 9.5 Static and architecture acceptance

Required evidence:

```text
RUFF_CHECK=PASS
RUFF_FORMAT_CHECK=PASS
MYPY=PASS
ARCHITECTURE_TESTS=PASS
GIT_DIFF_CHECK=PASS
SECRET_SCAN=PASS
EXACT_PATH_ALLOWLIST=PASS
DELETE_PATH_COUNT=0
```

Architecture tests must enforce:

- the application process does not invoke Alembic upgrade/downgrade;
- liveness does not call dependency probes;
- readiness owns dependency probes through the canonical runtime authority;
- strict environments cannot silently admit fake/in-memory production wiring;
- raw exception text is not returned by health endpoints;
- no second configuration or redaction authority is introduced.

## 10. CI ownership

The existing four-job workflow remains the top-level ownership model.

### `backend-sqlite`

Owns:

- unit tests;
- local/test lifecycle tests;
- health state-machine tests;
- architecture tests;
- Ruff lint and format checks;
- mypy.

### `backend-postgresql`

Owns:

- staging/production startup lifecycle tests;
- database connectivity classification;
- exact Alembic-head verification;
- PostgreSQL readiness behavior;
- coefficient readiness integration;
- strict artifact and capability admission checks.

### `compose-config`

Owns:

- root local Compose syntax validation;
- production Compose syntax validation;
- backend image build;
- non-root image assertion;
- migration plus application container smoke;
- live/ready endpoint smoke;
- exact build identity assertion;
- secret and artifact persistence assertions appropriate to the CI environment.

### `frontend`

Remains unchanged and continues to own the existing frontend quality gate.

```text
NEW_TOP_LEVEL_WORKFLOW_JOB_AUTHORIZED=NO
IMAGE_REGISTRY_PUSH_AUTHORIZED=NO
CI_DEPLOYMENT_AUTHORIZED=NO
CI_RELEASE_CREATION_AUTHORIZED=NO
```

## 11. Required implementation evidence

A future implementation PR must record:

```text
IMPLEMENTATION_BASE_SHA
IMPLEMENTATION_HEAD_SHA
COMMIT_COUNT
CHANGED_PATH_COUNT
CREATE_PATH_COUNT
MODIFY_PATH_COUNT
DELETE_PATH_COUNT
UNAUTHORIZED_PATH_COUNT
```

It must also record exact-head results for:

- focused unit and lifecycle tests;
- SQLite acceptance;
- PostgreSQL acceptance;
- architecture tests;
- production Compose config;
- backend image build;
- container migration/application smoke;
- liveness/readiness smoke;
- Ruff;
- format check;
- mypy;
- secret scan;
- `git diff --check`.

CI evidence must identify the workflow run, exact Head SHA, every job conclusion,
and whether any rerun occurred. A rerun requires separate authorization when
repository governance requires it.

## 12. Implementation governance

After this contract becomes binding on `main`, Slice 2 implementation still
requires a separate explicit authorization containing:

- exact implementation base SHA;
- exact branch name;
- this contract path and binding merge SHA;
- the exact 20-path maximum allowlist;
- implementation semantics and acceptance gates;
- Draft PR requirement;
- explicit prohibition of Ready, Merge, tag, Release, and deployment.

The implementation sequence is:

```text
BINDING_CONTRACT_ON_MAIN
-> SEPARATE_IMPLEMENTATION_AUTHORIZATION
-> FORWARD_ONLY_IMPLEMENTATION_COMMITS
-> DRAFT_PR
-> EXACT_HEAD_CI
-> INDEPENDENT_ENGINEERING_REVIEW
-> SEPARATE_READY_AUTHORIZATION
-> SEPARATE_FINAL_PRE_MERGE_REVIEW
-> SEPARATE_MERGE_AUTHORIZATION
-> POST_MERGE_MAIN_IDENTITY_VERIFICATION
```

No stage authorizes the next stage.

## 13. Hard stop conditions

This contract-authoring PR must remain Draft until separately authorized.
Creating or merging the contract does not authorize implementation.

```text
CONTRACT_PR_DRAFT_REQUIRED=YES
CONTRACT_READY_AUTHORIZED=NO
CONTRACT_MERGE_AUTHORIZED=NO
SLICE2_BRANCH_CREATION_AUTHORIZED_BY_CONTRACT=NO
SLICE2_IMPLEMENTATION_AUTHORIZED=NO
SLICE2_CODE_CHANGE_AUTHORIZED=NO
SLICE2_TEST_CHANGE_AUTHORIZED=NO
SLICE2_DOCKER_CHANGE_AUTHORIZED=NO
SLICE2_COMPOSE_CHANGE_AUTHORIZED=NO
SLICE2_WORKFLOW_CHANGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
ISSUE_MUTATION_AUTHORIZED=NO
BRANCH_DELETE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
```

## 14. Contract completion marker

```text
TASK012_SLICE2_CONTRACT_TEXT_COMPLETE=YES
TASK012_SLICE2_TARGET=DEPLOYMENT_ARTIFACT_AND_STARTUP_LIFECYCLE
TASK012_SLICE2_MAX_CHANGED_PATHS=20
TASK012_SLICE2_CREATE_PATHS=12
TASK012_SLICE2_MODIFY_PATHS=8
TASK012_SLICE2_DELETE_PATHS=0
TASK012_SLICE2_ACCEPTANCE_MATRIX_FROZEN=YES
TASK012_SLICE2_CI_OWNERSHIP_FROZEN=YES
TASK012_SLICE2_IMPLEMENTATION_AUTHORIZED=NO
TASK012_PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
STOPPED_AWAITING_CHARLES_CONTRACT_REVIEW=YES
```
