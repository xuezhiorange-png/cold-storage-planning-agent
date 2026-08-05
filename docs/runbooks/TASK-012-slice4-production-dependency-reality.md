# TASK-012 / V0.2 Slice 4 — Production Dependency and Persistence Reality Runbook

## Identity

```text
TARGET_VERSION=v0.2.0
TARGET_SLICE=V0_2_SLICE_4
IMPLEMENTATION_BASE_SHA=cd543644aa9d2c1c2b68c1ebdfff66f4b0c5ebc8
ROLLBACK_TARGET_SHA=cd543644aa9d2c1c2b68c1ebdfff66f4b0c5ebc8
CONTRACT_REVISION=R2
```

This runbook covers the V0.2 single-instance staging/production dependency bindings. It does not authorize deployment, release, backup/restore work, or a model provider.

## Production authorities

```text
COEFFICIENT_HTTP_AUTHORITY=DatabaseCoefficientService
COEFFICIENT_ENGINE_AUTHORITY=bootstrap.dependencies.get_engine
COEFFICIENT_PROVIDER=bootstrap.dependencies.get_production_coefficient_service
REPORT_ARTIFACT_STORAGE_AUTHORITY=Settings.storage_dir
MODEL_BACKED_AGENT_PRODUCTION_STATUS=disabled
CANONICAL_CAPABILITY_NAME=model_backed_agent
```

The coefficient provider is resolved exactly once per HTTP request. Route registration never resolves it before lifespan initialization. No database error or uninitialized dependency condition may construct a process-local coefficient service.

## Expected strict HTTP behavior

Known planning-agent method/path pairs return:

```text
HTTP_STATUS=503
ERROR_CODE=AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE
RETRYABLE=false
```

The disabled response occurs before authentication, request-body validation, database session creation, model gateway construction, tool adapter construction, or report storage construction.

Boundary behavior:

```text
KNOWN_ENDPOINT_UNDECLARED_METHOD=405
UNKNOWN_AGENT_PATH=404
TRAILING_SLASH_VARIANT=307
STRICT_DEMO_OVERVIEW=404
```

The disabled routes remain present in OpenAPI and document the 503 response.

## Readiness and metrics

`GET /health/ready` contains a top-level, lexicographically ordered `capabilities` array on every response branch.

Strict modes project:

```json
[
  {
    "name": "model_backed_agent",
    "status": "disabled",
    "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
    "blocking": false
  }
]
```

Local/test modes project the same capability as `available` with a null code. Disabled optional capability state does not block readiness.

Prometheus reuses:

```text
agent_capability_status{capability="model_backed_agent"}
```

Expected values:

```text
local,test=1
staging,production=0
```

## Strict binding audit

The per-application binding manifest must equal:

```text
(capability=coefficient_http,binding=database_backed)
(capability=model_backed_agent,binding=disabled)
```

Positive composition evidence must include:

```text
DATABASE_COEFFICIENT_SERVICE_INSTANTIATED
```

The following evidence fails closed with `UNSAFE_STRICT_CAPABILITY_WIRING`:

```text
FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED
PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED
COMPOSITION_MANIFEST_PROVIDER_ERROR
missing or unknown binding identity
missing database coefficient positive evidence
strict demo overview route still reachable
```

## Artifact storage verification

Set `COLD_STORAGE_STORAGE_DIR` to an absolute environment-isolated path outside the repository. A strict report render must create artifacts only under that directory. Any production-reachable `ReportArtifactStorage(base_dir="data/report_artifacts")` composition is a contract failure.

## Coefficient persistence acceptance

Exercise this sequence on both SQLite and PostgreSQL; PostgreSQL is authoritative for release acceptance:

```text
CREATE_DEFINITION
CREATE_REVISION
REVIEW_REVISION
APPROVE_REVISION
DISPOSE_FIRST_SERVICE_INSTANCE
CREATE_SECOND_DATABASE_SERVICE_ON_SAME_DATABASE
READ_APPROVED_REVISION
RESOLVE_APPROVED_VALUE
WITHDRAW_REVISION
DISPOSE_SECOND_SERVICE_INSTANCE
CREATE_THIRD_DATABASE_SERVICE_ON_SAME_DATABASE
READ_WITHDRAWN_REVISION
VERIFY_WITHDRAWN_VALUE_NOT_RESOLVED
```

The production service engine identity must satisfy:

```python
get_production_coefficient_service().engine is get_engine()
```

## Failure diagnosis

### `PRODUCTION_DEPENDENCIES_NOT_INITIALIZED`

Meaning: a coefficient HTTP request reached the delayed provider before initialization or after shutdown.

Required response:

```text
HTTP_STATUS=503
RETRYABLE=true
IN_MEMORY_FALLBACK=NO
```

Check lifespan startup completion and dependency initialization logs. Do not seed or construct a process-local service as a workaround.

### `UNSAFE_STRICT_CAPABILITY_WIRING`

Meaning: strict route identity and composition evidence do not agree, a forbidden backend was constructed, or a required binding is missing.

Stop startup. Inspect the per-app binding manifest and composition evidence. Do not bypass the audit.

### Agent capability disabled

`AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE` is expected in V0.2 staging/production and is non-retryable. It is not an outage and must not be converted into a readiness failure.

## Shutdown and reinitialization

Shutdown order remains:

```text
READY -> DRAINING
clear production coefficient singleton
clear composition evidence
single canonical engine dispose
reset readiness and settings authorities
```

A retained coefficient route provider after shutdown must return the stable 503 and must not return a stale service bound to the disposed engine. Reinitialization publishes a fresh service on the fresh canonical engine.

## Rollback

```text
ROLLBACK_TARGET_SHA=cd543644aa9d2c1c2b68c1ebdfff66f4b0c5ebc8
DATABASE_ROLLBACK_REQUIRED=NO
ALEMBIC_DOWNGRADE_REQUIRED=NO
DATA_MIGRATION_REQUIRED=NO
```

Rollback the Slice 4 implementation commit range while preserving the merged R2 contract and unrelated main history. After rollback, do not claim Slice 4 completion or production dependency binding acceptance.
