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

#### D-S2-02.a — In-image immutable build-identity authority

The authoritative source of build identity is **a deterministic file baked
into the backend image at build time**. There is no "build arguments OR
immutable metadata" author choice: the file IS the authority, and any build
argument or label that disagrees with the file MUST fail startup.

At image build time the build pipeline must write:

```text
BUILD_IDENTITY_PATH=/opt/cold-storage/build-identity.json
BUILD_IDENTITY_SCHEMA_VERSION=1
BUILD_IDENTITY_OWNER=root
BUILD_IDENTITY_MODE=0444
```

The file content MUST be deterministic UTF-8 JSON with exactly these keys,
in this order, and no others:

```json
{
  "schema_version": 1,
  "commit_sha": "<40-character lowercase git sha>",
  "version": "<non-empty build version>"
}
```

The build inputs that populate this file are:

```text
COLD_STORAGE_BUILD_COMMIT_SHA
COLD_STORAGE_BUILD_VERSION
```

These inputs are build-time immutable identity. They MUST NOT be re-derived
from the working tree, Git CLI, or `git describe` at runtime.

`COLD_STORAGE_DEPLOYMENT_ID` is **deployment-time runtime identity** and
MUST NOT be written into `/opt/cold-storage/build-identity.json`.

#### D-S2-02.b — Strict-runtime comparison rules

In `staging` and `production`, startup MUST:

1. read the fixed path `/opt/cold-storage/build-identity.json`;
2. validate the file exists, is valid JSON, the field set is exactly the
   three keys above, and `schema_version` equals `1`;
3. verify that the file's `commit_sha` is a 40-character lowercase
   hexadecimal SHA;
4. verify that the file's `version` is non-empty and conforms to the safe
   character contract;
5. compare the runtime `COLD_STORAGE_BUILD_COMMIT_SHA` to the file's
   `commit_sha` byte-for-byte and fail closed on any difference;
6. compare the runtime `COLD_STORAGE_BUILD_VERSION` to the file's
   `version` byte-for-byte and fail closed on any difference;
7. treat `COLD_STORAGE_DEPLOYMENT_ID` as identifying the deployment
   instance only — it MUST NOT override, replace, or back-derive the
   build identity.

The following stable failure codes MUST be used. All emitted messages MUST
pass through the existing redaction authority or a strictly narrower safe
projection; raw file content and raw exception text MUST NOT be returned.

```text
BUILD_IDENTITY_FILE_MISSING
BUILD_IDENTITY_FILE_MALFORMED
BUILD_IDENTITY_SCHEMA_UNSUPPORTED
BUILD_IDENTITY_COMMIT_INVALID
BUILD_IDENTITY_VERSION_INVALID
BUILD_COMMIT_MISMATCH
BUILD_VERSION_MISMATCH
DEPLOYMENT_ID_INVALID
```

#### D-S2-02.c — Required anti-tampering evidence

The implementation MUST demonstrate:

- startup fails when the runtime `COLD_STORAGE_BUILD_COMMIT_SHA` env var is
  overridden to a value that disagrees with the file;
- startup fails when the runtime `COLD_STORAGE_BUILD_VERSION` env var is
  overridden to a value that disagrees with the file;
- mutating only `COLD_STORAGE_DEPLOYMENT_ID` does NOT change the build
  identity reported by the runtime;
- a missing, malformed, or tampered `/opt/cold-storage/build-identity.json`
  file causes startup to fail closed;
- health responses and logs do NOT leak the full file contents;
- the in-container application user cannot modify the root-owned
  mode-`0444` build-identity file;
- the runtime-reported SHA is sourced from the in-image authority file and
  matches the exact expected implementation Head.

```text
STRICT_BUILD_IDENTITY_REQUIRED=YES
RUNTIME_GIT_DISCOVERY_AS_AUTHORITY=NO
BUILD_IDENTITY_SECRET=NO
BUILD_IDENTITY_IN_IMAGE_AUTHORITY=YES
BUILD_IDENTITY_FILE_PATH=/opt/cold-storage/build-identity.json
```

#### D-S2-02.d — Build version character contract

The build version that appears in `/opt/cold-storage/build-identity.json`
and the runtime value `COLD_STORAGE_BUILD_VERSION` MUST both conform to a
single, frozen character contract. There is no second implementation
choice between a "lenient" and a "strict" interpretation of this contract.

```text
BUILD_VERSION_PATTERN=^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$
BUILD_VERSION_MIN_LENGTH=1
BUILD_VERSION_MAX_LENGTH=64
BUILD_VERSION_NORMALIZATION=NONE
BUILD_VERSION_ENCODING=ASCII
```

Contract semantics:

1. The first character MUST be an ASCII letter (`A-Z` or `a-z`) or an ASCII
   digit (`0-9`).
2. Every subsequent character (up to 63 additional bytes) MUST be one of:
   - an ASCII letter;
   - an ASCII digit;
   - `.` (period);
   - `_` (underscore);
   - `+` (plus);
   - `-` (hyphen/minus).
3. The total length MUST be between 1 and 64 ASCII bytes inclusive. The
   value is measured in raw bytes after UTF-8/Unicode decoding; non-ASCII
   bytes are forbidden and cause rejection.
4. There is NO trimming, NO case conversion, NO Unicode normalization
   (NFC/NFKC/NFD/NFKD), and NO other implicit mutation. The value the
   build pipeline wrote into the file is compared as-is.
5. Validation order:
   - the in-image `version` field in
     `/opt/cold-storage/build-identity.json` is validated against the rule
     above;
   - the runtime `COLD_STORAGE_BUILD_VERSION` is validated against the
     same rule;
   - only after both values pass the same rule are they compared to each
     other byte-for-byte (D-S2-02.b step 6).
6. The following inputs MUST all fail closed with the stable failure code
   `BUILD_IDENTITY_VERSION_INVALID`:
   - the empty string;
   - any leading punctuation (e.g. `.1.0`, `_v1`, `-v1`, `+v1`);
   - any embedded or trailing whitespace;
   - `/` or `\` (forward or backslash);
   - any non-ASCII byte (Unicode of any kind);
   - any control character (including `\n`, `\t`, `\r`, NUL, etc.);
   - any value longer than 64 bytes.

```text
BUILD_VERSION_ASCII_ONLY=YES
BUILD_VERSION_SLASH_FORBIDDEN=YES
BUILD_VERSION_WHITESPACE_FORBIDDEN=YES
BUILD_VERSION_NON_ASCII_FORBIDDEN=YES
BUILD_VERSION_CONTROL_CHAR_FORBIDDEN=YES
BUILD_VERSION_LEADING_PUNCTUATION_FORBIDDEN=YES
BUILD_VERSION_NORMALIZATION_FORBIDDEN=YES
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

#### D-S2-03.a — Mandatory probe-timeout configuration keys

The following canonical configuration keys are **frozen** as the single
mechanism for bounding startup and readiness probe execution. There is no
implementation-defined alternative for "how long a probe may take".

```text
COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS
COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS
```

#### D-S2-03.b — Numeric contract

```text
STARTUP_PROBE_TIMEOUT_MIN_SECONDS=1
STARTUP_PROBE_TIMEOUT_MAX_SECONDS=120
READINESS_PROBE_TIMEOUT_MIN_SECONDS=1
READINESS_PROBE_TIMEOUT_MAX_SECONDS=30
```

- staging and production MUST explicitly provide both values;
- local/test MAY use the documented non-production defaults
  `LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS=30` and
  `LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS=5`;
- values MUST be finite positive integers; zero, negative, non-integer,
  NaN, Infinity, or out-of-range values are configuration errors and MUST
  cause startup to fail closed.

#### D-S2-03.c — Per-probe timeout budget

```text
PROBE_TIMEOUT_BUDGET_TYPE=PER_PROBE
STARTUP_PROBE_TIMEOUT_SCOPE=EACH_MANDATORY_STARTUP_PROBE
READINESS_PROBE_TIMEOUT_SCOPE=EACH_MANDATORY_DYNAMIC_PROBE
PROBE_EXECUTION_MODEL=IMPLEMENTATION_DEFINED_BOUNDED
AGGREGATE_PROBE_TIMEOUT_FORMULA=
MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT
AGGREGATE_PROBE_TIMEOUT_FORMULA_SEMANTICS=CONSERVATIVE_UPPER_BOUND
AGGREGATE_TIMEOUT_EQUALITY_REQUIRED=NO
```

- every mandatory probe has an independent timeout upper bound;
- earlier probes that complete quickly MUST NOT lend their remaining time
  to later probes;
- this contract does NOT mandate that all probes run strictly serially.
  An implementation MAY execute probes serially, in parallel, or under a
  bounded mixed model, provided that:
  - every probe has an independent timeout;
  - the total execution does not produce unbounded workers, threads,
    tasks, connections, or singleton state;
  - every timeout maps to the correct stable failure code;
  - bounded completion is observed within the conservative upper bound
    below;
- the conservative aggregate upper bound on a complete startup/readiness
  evaluation is
  `MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT`.
  This product is a **conservative upper bound**, NOT a required exact
  duration. Serial execution may approach this bound; parallel or
  partially-parallel execution may complete faster. Acceptance asserts
  bounded completion, observation below the contract upper bound, and
  correct failure classification; acceptance does NOT assert equality
  with the product;
- implementations MUST use a dependency-native timeout or another
  cancellable, bounded mechanism; implementing timeout by spawning
  unbounded background threads or tasks is FORBIDDEN.

#### D-S2-03.d — Timeout outcome contract

```text
STARTUP_TIMEOUT_RESULT=PROCESS_STARTUP_FAIL_CLOSED
READINESS_TIMEOUT_HTTP_STATUS=503
LIVENESS_DURING_READINESS_TIMEOUT=200
RAW_TIMEOUT_EXCEPTION_EXPOSED=false
```

- on startup probe timeout, startup MUST fail closed with the stable
  failure code `STARTUP_PROBE_TIMEOUT`;
- on readiness probe timeout, readiness MUST return HTTP 503 with the
  stable failure code `READINESS_PROBE_TIMEOUT`;
- liveness MUST continue to return HTTP 200 even while readiness reports
  503 due to probe timeout;
- timeout results MUST carry a safe `check_code` only; raw exception
  text, DSNs, SQL, secrets, tokens, and unsafe paths MUST NOT be exposed.

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

#### D-S2-04.a — Per-probe timeout application

Each of the mandatory readiness gates above MUST be executed under the
per-probe timeout budget specified in D-S2-03.c. A timeout on any one
gate MUST yield the readiness HTTP 503 response with the stable failure
code `READINESS_PROBE_TIMEOUT` (D-S2-03.d). The overall readiness
evaluation MUST NOT exceed the conservative upper bound
`MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT` defined in
D-S2-03.c; the implementation MUST NOT assert equality with that
product.

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
or in-memory implementations. The implementation must address, at minimum:

- `FakeAgentModelGateway`;
- process-local/in-memory `CoefficientService` HTTP route wiring.

This section distinguishes **two** outcomes that must not be conflated:

- the canonical strict-mode contract behavior for each capability
  (D-S2-06.a and D-S2-06.b) — the capability is un-instantiated and its
  HTTP routes are un-registered, the process starts normally, and the
  relevant HTTP request returns a normal `404`;
- the defensive invariant behavior (D-S2-06.c) — invoked only when a
  capability that should be un-instantiated is actually reachable at
  startup; the process MUST fail closed with the stable failure code
  `UNSAFE_STRICT_CAPABILITY_WIRING`.

The canonical outcome is NOT a synonym for the defensive outcome, and
the defensive outcome is NOT an alternate implementation of the
canonical outcome. An implementation MUST satisfy both: produce the
canonical outcome for every named capability AND keep the defensive
invariant satisfied.

```text
CANONICAL_STRICT_CAPABILITY_OUTCOME=ROUTES_NOT_REGISTERED
CANONICAL_STRICT_CAPABILITY_HTTP_RESULT=404
DEFENSIVE_INVARIANT_VIOLATION_OUTCOME=STARTUP_FAIL_CLOSED
DEFENSIVE_INVARIANT_FAILURE_CODE=UNSAFE_STRICT_CAPABILITY_WIRING
P1_001_WORDING_CORRECTED=YES
CANONICAL_AND_DEFENSIVE_OUTCOMES_DISTINGUISHED=YES
```

#### D-S2-06.a — `FakeAgentModelGateway`

In `staging` and `production`:

- the `FakeAgentModelGateway` class must NOT be instantiated;
- any HTTP route or surface that depends on the fake gateway must NOT be
  registered;
- the model-backed HTTP surface on the planning-agent must report
  `PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE=NOT_REGISTERED`;
- a request to that surface must yield a normal route-not-found result
  (`EXPECTED_HTTP_RESULT=404`), not an internal capability-state exposure;
- the un-registered capability must NOT be disguised as a readiness failure;
- `local` and `test` behavior must remain unchanged;
- this Slice must NOT implement a real model provider.

```text
FAKE_AGENT_GATEWAY_STRICT_MODE_OUTCOME=CAPABILITY_NOT_REGISTERED
FAKE_AGENT_GATEWAY_STRICT_MODE_INSTANTIATION=FORBIDDEN
PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE=NOT_REGISTERED
EXPECTED_HTTP_RESULT=404
```

#### D-S2-06.b — In-memory `CoefficientService` HTTP wiring

In `staging` and `production`:

- a process-in-memory `CoefficientService()` instance must NOT be instantiated
  as an HTTP route backend;
- any coefficient HTTP route that depends on that in-memory instance must NOT
  be registered;
- the coefficient HTTP surface must report
  `COEFFICIENT_HTTP_ROUTE_STRICT_MODE=NOT_REGISTERED`;
- a request to that surface must yield a normal route-not-found result
  (`EXPECTED_HTTP_RESULT=404`);
- `local` and `test` behavior must remain unchanged;
- this Slice must NOT redesign coefficient persistence or implement a
  replacement service.

```text
IN_MEMORY_COEFFICIENT_HTTP_STRICT_MODE_OUTCOME=ROUTES_NOT_REGISTERED
IN_MEMORY_COEFFICIENT_SERVICE_STRICT_MODE_INSTANTIATION=FORBIDDEN
COEFFICIENT_HTTP_ROUTE_STRICT_MODE=NOT_REGISTERED
EXPECTED_HTTP_RESULT=404
```

#### D-S2-06.c — Defensive strict-mode admission assertion

In addition to the per-capability outcomes above, strict-mode startup MUST
execute a defensive assertion that **zero** unsafe strict-capability wirings
remain reachable:

- the startup gate must enumerate every known fake/in-memory strict-mode
  capability and confirm that each one is un-instantiated, un-wired, or
  un-registered;
- the expected count of reachable unsafe strict capabilities is exactly zero
  (`STRICT_UNSAFE_CAPABILITY_COUNT_REQUIRED=0`);
- if any unsafe strict capability is reachable, startup MUST fail closed with
  the stable failure code `UNSAFE_STRICT_CAPABILITY_WIRING` and must NOT
  silently continue, log-and-pass, or degrade to a soft warning;
- this defensive assertion is independent of D-S2-06.a and D-S2-06.b: even if
  those outcomes are correctly applied, a future regression that
  accidentally re-introduces a fake/in-memory strict capability (for example
  via a refactor that re-wires the route table) MUST still be caught by
  startup.

```text
STRICT_UNSAFE_CAPABILITY_COUNT_REQUIRED=0
STRICT_UNSAFE_CAPABILITY_FAILURE_CODE=UNSAFE_STRICT_CAPABILITY_WIRING
```

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
- write `/opt/cold-storage/build-identity.json` at build time with
  `owner=root`, `mode=0444`, and the deterministic JSON contract specified
  in D-S2-02.a; the file is the in-image authoritative build identity and
  runtime identity is validated against it (see D-S2-02.b and
  D-S2-02.c); this contract does NOT permit a "build arguments OR
  immutable metadata" author choice.

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
- lifecycle/draining state;
- in-image build-identity file failure (missing, malformed, unsupported
  schema, invalid commit, invalid version, runtime mismatch);
- probe-timeout failure on a mandatory startup or readiness probe.

Logs and endpoint responses must use the existing redaction authority or a
strictly narrower safe projection. Raw exception interpolation is forbidden.

```text
STABLE_FAILURE_CODES_REQUIRED=YES
RAW_EXCEPTION_TEXT_IN_HEALTH_RESPONSE=NO
RAW_SECRET_OR_DSN_IN_EVIDENCE=NO
```

#### D-S2-12.a — Frozen stable failure codes (scope-limited to this contract)

The table below freezes a **scope-limited** set of failure codes. This
sub-section deliberately does NOT claim to enumerate every Slice 2 failure
code, and does NOT claim that "if a failure is not in this table, an
implementation may invent a new code for it".

```text
D_S2_12A_SCOPE=NEW_CODES_EXPLICITLY_INTRODUCED_BY_SLICE2_CONTRACT
D_S2_12A_EXHAUSTIVE_FOR_ALL_SLICE2_FAILURES=NO

| Condition | Failure code |
|---|---|
| `/opt/cold-storage/build-identity.json` missing | `BUILD_IDENTITY_FILE_MISSING` |
| `/opt/cold-storage/build-identity.json` unreadable or unparseable | `BUILD_IDENTITY_FILE_MALFORMED` |
| `schema_version` not equal to `1` | `BUILD_IDENTITY_SCHEMA_UNSUPPORTED` |
| file `commit_sha` not a 40-char lowercase hex SHA | `BUILD_IDENTITY_COMMIT_INVALID` |
| file `version` empty or violates safe-character contract | `BUILD_IDENTITY_VERSION_INVALID` |
| runtime `COLD_STORAGE_BUILD_COMMIT_SHA` differs from file | `BUILD_COMMIT_MISMATCH` |
| runtime `COLD_STORAGE_BUILD_VERSION` differs from file | `BUILD_VERSION_MISMATCH` |
| `COLD_STORAGE_DEPLOYMENT_ID` empty/malformed when required | `DEPLOYMENT_ID_INVALID` |
| startup probe exceeded per-probe timeout | `STARTUP_PROBE_TIMEOUT` |
| readiness probe exceeded per-probe timeout | `READINESS_PROBE_TIMEOUT` |
| exact schema-head verification failed, no timeout | `DATABASE_SCHEMA_HEAD_INVALID` |
| any unsafe strict capability reachable at startup | `UNSAFE_STRICT_CAPABILITY_WIRING` |

This scope-limited table is governed by the following explicit contract
clauses:

1. The table freezes **only** the failure codes that this Slice 2 contract
   itself explicitly introduces. These are the new codes for:
   - build identity (file, schema, commit, version);
   - deployment ID;
   - startup/readiness probe timeouts;
   - unsafe strict capability wiring.
2. The table is **not** the complete catalog of all Slice 2 failure codes.
   Adding a code to the table, removing one, or redefining the scope of the
   table is a contract amendment requiring a new authorization round.
3. A failure category that is not listed in this table MUST NOT be merged
   into any arbitrary existing code and MUST NOT be freely named by the
   implementation.
4. Other failure categories — including configuration identity, database
   connectivity, schema head, artifact storage, coefficient readiness, and
   lifecycle/draining state — MUST continue to use their pre-existing
   stable classification authority (e.g. Slice 1 codes or other contract
   provisions that already cover them). If an implementation discovers
   that no pre-existing stable code covers a category it must report, the
   implementation MUST stop and request a contract amendment; it MUST
   NOT invent a new code on its own authority.
5. Renaming any code listed in the table is forbidden; reusing a listed
   code for a different condition is forbidden.

```text
FAILURE_CODE_TABLE_EXHAUSTIVE=NO
UNDEFINED_FAILURE_CODE_CREATION_BY_IMPLEMENTER=FORBIDDEN
```

#### D-S2-12.a.v0.2 — Narrow schema-head classification amendment (V0.2 amendment)

This amendment is a **scope-limited** extension of D-S2-12.a. It freezes
exactly one additional stable failure code — `DATABASE_SCHEMA_HEAD_INVALID`
— for the exact schema-head mandatory probe defined in D-S2-01 and
implemented by the `database_exact_alembic_head` probe. It does NOT
introduce any other new code, does NOT redesign Slice 2, and does NOT
relax any clause in this contract.

Frozen failure code:

```text
NEW_STABLE_FAILURE_CODE=DATABASE_SCHEMA_HEAD_INVALID
NEW_STABLE_FAILURE_CODE_COUNT=1
```

The code is the **only** public failure code introduced by this
amendment. It applies **only** to the exact schema-head mandatory probe
in strict production (staging or production) runtime, and **only** when
the failure is not a measured per-probe timeout.

Internal closed-set of non-timeout reasons (NOT public stable codes):

```text
PACKAGED_HEAD_MISSING
PACKAGED_HEAD_UNREADABLE
PACKAGED_HEAD_MALFORMED
PACKAGED_HEAD_ZERO
PACKAGED_HEAD_MULTIPLE
DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION
DATABASE_HEAD_ZERO
DATABASE_HEAD_MULTIPLE
DATABASE_HEAD_MALFORMED
DATABASE_HEAD_MISMATCH
UNKNOWN_SCHEMA_IDENTITY
```

Every internal reason above MUST project to the public code
`DATABASE_SCHEMA_HEAD_INVALID`. The internal reasons MUST NOT be
introduced as new public stable codes.

Mandatory timeout-vs-non-timeout projection:

```text
ACTUAL_STARTUP_TIMEOUT              -> STARTUP_PROBE_TIMEOUT
ACTUAL_READINESS_TIMEOUT            -> READINESS_PROBE_TIMEOUT
NON_TIMEOUT_SCHEMA_HEAD_FAILURE     -> DATABASE_SCHEMA_HEAD_INVALID
```

Forbidden projections:

```text
GENERIC_EXCEPTION_TO_TIMEOUT        = false
ANY_NON_PASS_TO_TIMEOUT             = false
SCHEMA_HEAD_MISMATCH_TO_TIMEOUT     = false
```

`STARTUP_PROBE_TIMEOUT` and `READINESS_PROBE_TIMEOUT` are produced
**only** when a `BlockingProbeTimeout` (or its concrete equivalents)
actually raised, or when a dependency-native timeout is actually
reported, or when the measured execution exceeded the configured budget.
A non-timeout schema-head failure MUST NOT be projected to a timeout
code. A category that has no existing stable classification authority
MUST stop and request a contract amendment; it MUST NOT borrow a
timeout code.

Exact-head verification behavior (unmodified from D-S2-01):

```text
APPLICATION_VERIFIES_EXACT_SCHEMA_HEAD    = YES
MULTIPLE_HEADS_FAIL_CLOSED                = YES
APPLICATION_RUNS_MIGRATIONS               = NO
```

The expected repository-supported Alembic Head is deployment-artifact
identity and must not be supplied as a freely mutable runtime override.

`DATABASE_SCHEMA_HEAD_INVALID` MUST NOT be used for any of:

```text
DATABASE_CONNECTION_FAILURE
DATABASE_CONNECTION_TIMEOUT
STARTUP_PROBE_TIMEOUT
READINESS_PROBE_TIMEOUT
BUILD_IDENTITY_FAILURE
DEPLOYMENT_ID_FAILURE
COEFFICIENT_READINESS_FAILURE
ARTIFACT_STORAGE_FAILURE
STRICT_CAPABILITY_FAILURE
LIFECYCLE_OR_DRAINING_FAILURE
MIGRATION_PROCESS_FAILURE
```

Acceptance obligations added by this amendment:

```text
PACKAGED_HEAD_MISSING                       -> DATABASE_SCHEMA_HEAD_INVALID
PACKAGED_HEAD_MALFORMED                     -> DATABASE_SCHEMA_HEAD_INVALID
PACKAGED_HEAD_MULTIPLE                      -> DATABASE_SCHEMA_HEAD_INVALID
DATABASE_HEAD_ZERO                          -> DATABASE_SCHEMA_HEAD_INVALID
DATABASE_HEAD_MULTIPLE                      -> DATABASE_SCHEMA_HEAD_INVALID
DATABASE_HEAD_MALFORMED                     -> DATABASE_SCHEMA_HEAD_INVALID
DATABASE_HEAD_MISMATCH                      -> DATABASE_SCHEMA_HEAD_INVALID
DATABASE_HEAD_EXACT_MATCH                   -> PASS
ACTUAL_STARTUP_TIMEOUT                      -> STARTUP_PROBE_TIMEOUT
ACTUAL_READINESS_TIMEOUT                    -> READINESS_PROBE_TIMEOUT
```

No new acceptance matrix entries are added for database connection,
artifact storage, coefficient, draining, or observability.

Safe projection — health response MAY expose only:

```text
{
  "status": "not_ready",
  "state": "<safe lifecycle state>",
  "check_code": "DATABASE_SCHEMA_HEAD_INVALID"
}
```

Safe projection MUST NOT expose:

```text
raw exception text
database URL or DSN
password
secret
SQL statement
full filesystem path
database Head value
packaged Head value
Alembic row contents
```

Logs MAY record:

```text
probe=database_exact_alembic_head
check_code=DATABASE_SCHEMA_HEAD_INVALID
```

Logs MUST NOT record the raw database Head value or the raw packaged
Head value.

Governance boundary for this amendment:

```text
THIS_AMENDMENT_IS_V0_2_SLICE2_ONLY                   = YES
THIS_AMENDMENT_AUTHORIZES_PR76_IMPLEMENTATION        = NO
DRAFT_PR_CREATION_CREATES_AUTHORITY                  = NO
READY_CREATES_IMPLEMENTATION_AUTHORITY               = NO
AMENDMENT_MERGE_REQUIRED                             = YES
POST_MERGE_MAIN_IDENTITY_REQUIRED                    = YES
FRESH_PR76_IMPLEMENTATION_AUTHORIZATION_REQUIRED     = YES
PR76_REMAINS_DRAFT                                   = YES
PR76_MUTATION_AUTHORIZED                             = NO
NO_STEP_IMPLIES_THE_NEXT                             = YES
```

Clauses that this amendment does NOT modify:

```text
- D-S2-01 (migration ownership, exact schema-head verification)
- D-S2-12.a table rows other than the single inserted row above
- D-S2-03 (probe budgets)
- D-S2-06 (strict capability admission)
- D-S2-08 (production entrypoint)
- D-S2-10 (draining lifecycle)
- Section 7 (path allowlist)
- Section 8 (semantic mutation limits)
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
- capability admission decisions for fake/in-memory wiring;
- for each illegal probe-timeout value (zero, negative, non-integer, NaN,
  Infinity, out-of-range), the configuration is rejected;
- forced probe timeout maps to the stable failure code
  `STARTUP_PROBE_TIMEOUT` or `READINESS_PROBE_TIMEOUT`;
- forced probe-timeout execution completes within the conservative upper
  bound `MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT` and does
  NOT assert equality with the product;
- build version character contract (D-S2-02.d):
  - `BUILD_VERSION_VALID_MIN_BOUNDARY_TEST=REQUIRED` — a 1-character
    value matching the pattern passes;
  - `BUILD_VERSION_VALID_MAX_BOUNDARY_TEST=REQUIRED` — a 64-character
    value matching the pattern passes;
  - `BUILD_VERSION_WHITESPACE_REJECTION_TEST=REQUIRED` — embedded or
    trailing whitespace is rejected with `BUILD_IDENTITY_VERSION_INVALID`;
  - `BUILD_VERSION_SLASH_REJECTION_TEST=REQUIRED` — `/` or `\` is rejected
    with `BUILD_IDENTITY_VERSION_INVALID`;
  - `BUILD_VERSION_UNICODE_REJECTION_TEST=REQUIRED` — any non-ASCII byte
    is rejected with `BUILD_IDENTITY_VERSION_INVALID`;
  - `BUILD_VERSION_LEADING_PUNCTUATION_REJECTION_TEST=REQUIRED` — leading
    `.`, `_`, `+`, or `-` is rejected with
    `BUILD_IDENTITY_VERSION_INVALID`;
  - `BUILD_VERSION_OVERLENGTH_REJECTION_TEST=REQUIRED` — any value over
    64 bytes is rejected with `BUILD_IDENTITY_VERSION_INVALID`.

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
- no DSN, password, token, secret, or unsafe path appears in evidence;
- when a mandatory database probe is forced to exceed its per-probe
  timeout, readiness returns HTTP 503 with stable failure code
  `READINESS_PROBE_TIMEOUT`;
- while readiness reports 503 due to probe timeout, liveness continues to
  return HTTP 200;
- the overall readiness evaluation completes within the conservative
  upper bound defined in D-S2-03.c; equality with the product is NOT
  asserted; bounded completion, classification correctness, and absence
  of unbounded resources are asserted.

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
  production resource;
- when a mandatory probe is forced to exceed its per-probe timeout, the
  probe completes within the conservative upper bound defined in
  D-S2-03.c and `/health/ready` returns HTTP 503 with the stable failure
  code `READINESS_PROBE_TIMEOUT` (or startup fails closed with
  `STARTUP_PROBE_TIMEOUT`); equality with the product
  `MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT` is NOT asserted;
- after a forced probe timeout and a subsequent shutdown/retry cycle,
  no timeout worker, thread, connection, or singleton state is left
  behind;
- timeout evidence is redacted (no raw exception, DSN, secret, or unsafe
  path);
- the in-container application user cannot modify the root-owned
  mode-`0444` `/opt/cold-storage/build-identity.json` file;
- overriding `COLD_STORAGE_BUILD_COMMIT_SHA` at runtime to disagree with
  the file causes startup to fail with `BUILD_COMMIT_MISMATCH`;
- overriding `COLD_STORAGE_BUILD_VERSION` at runtime to disagree with
  the file causes startup to fail with `BUILD_VERSION_MISMATCH`;
- mutating only `COLD_STORAGE_DEPLOYMENT_ID` does not change the reported
  build identity;
- the image contains a `/opt/cold-storage/build-identity.json` whose
  `version` field satisfies D-S2-02.d; supplying an image with a
  whitespace-bearing, slash-bearing, non-ASCII, leading-punctuation, or
  over-length `version` causes startup to fail with
  `BUILD_IDENTITY_VERSION_INVALID`.

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
- no second configuration or redaction authority is introduced;
- the defensive strict-mode capability admission assertion
  (`STRICT_UNSAFE_CAPABILITY_COUNT_REQUIRED=0`) runs at startup and fails
  closed with `UNSAFE_STRICT_CAPABILITY_WIRING` if violated;
- the `/opt/cold-storage/build-identity.json` authority is the single
  source of truth for build commit and version at runtime — no
  re-derivation from the working tree or Git CLI;
- probe timeouts are bounded per probe and do not rely on unbounded
  background threads or tasks;
- the probe aggregate upper bound `MANDATORY_PROBE_COUNT ×
  CONFIGURED_PER_PROBE_TIMEOUT` is enforced as a **conservative upper
  bound**; tests assert completion within the bound and correct failure
  classification, never equality with the product;
- the build version character contract (D-S2-02.d) is enforced for both
  the in-image `version` and the runtime `COLD_STORAGE_BUILD_VERSION`;
  whitespace, slash, non-ASCII, leading-punctuation, control-character,
  empty, and over-length values are rejected with
  `BUILD_IDENTITY_VERSION_INVALID`.

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
- strict artifact and capability admission checks;
- in-image build-identity authority and runtime mismatch tests;
- forced readiness-probe timeout → HTTP 503 + stable failure code
  `READINESS_PROBE_TIMEOUT`, with liveness remaining 200.

### `compose-config`

Owns:

- root local Compose syntax validation;
- production Compose syntax validation;
- backend image build;
- non-root image assertion;
- migration plus application container smoke;
- live/ready endpoint smoke;
- exact build identity assertion (SHA from `/opt/cold-storage/build-identity.json`
  equals the exact expected implementation Head);
- in-container application user cannot modify the root-owned `0444`
  build-identity file;
- secret and artifact persistence assertions appropriate to the CI environment;
- forced startup/readiness probe timeout smoke (bounded completion + 503).

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
- `/opt/cold-storage/build-identity.json` authority and anti-tampering
  smoke (commit-mismatch, version-mismatch, missing-file, malformed-file,
  unprivileged-write-rejected, runtime-SHA-equals-implementation-Head);
- forced startup-probe timeout smoke (`STARTUP_PROBE_TIMEOUT`);
- forced readiness-probe timeout smoke
  (`READINESS_PROBE_TIMEOUT` + HTTP 503 + liveness 200 + no leftover
  workers/threads/connections/singletons);
- defensive strict-capability admission assertion smoke
  (`STRICT_UNSAFE_CAPABILITY_COUNT_REQUIRED=0`);
- probe aggregate upper bound smoke — confirms forced probe timeout
  completes within the conservative upper bound defined in D-S2-03.c and
  records that equality with the product is NOT asserted;
- build version character contract (D-S2-02.d) smoke — covers both the
  in-image `version` and runtime `COLD_STORAGE_BUILD_VERSION` for the
  valid 1-byte and 64-byte boundaries, plus whitespace, slash, non-ASCII,
  leading-punctuation, control-character, empty, and over-length
  rejection paths;
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
FROZEN_DESIGN_DECISION_COUNT=12
P1_001_RESOLVED=YES
P1_002_RESOLVED=YES
P1_003_RESOLVED=YES
P1_001_WORDING_CORRECTED=YES
P1_004_RESOLVED=YES
P1_005_RESOLVED=YES
P1_006_RESOLVED=YES
BUILD_VERSION_CONTRACT_FROZEN=YES
FAILURE_CODE_TABLE_EXHAUSTIVE=NO
UNDEFINED_FAILURE_CODE_CREATION_BY_IMPLEMENTER=FORBIDDEN
PROBE_AGGREGATE_TIMEOUT_IS_UPPER_BOUND=YES
PROBE_TIMEOUT_EQUALITY_ASSERTION_REQUIRED=NO
CANONICAL_AND_DEFENSIVE_OUTCOMES_DISTINGUISHED=YES
FUTURE_MAXIMUM_CHANGED_PATH_COUNT=20
FUTURE_CREATE_PATH_COUNT=12
FUTURE_MODIFY_PATH_COUNT=8
FUTURE_DELETE_PATH_COUNT=0
IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
DOCUMENT_STATUS=FROZEN_CANDIDATE_ON_BRANCH
BINDING_CONTRACT_ON_MAIN=NO
TASK012_SLICE2_CONTRACT_FIXUP_R2_COMPLETE=YES
STOPPED_AWAITING_NEW_EXACT_HEAD_CI_AND_REVIEW=YES
```
