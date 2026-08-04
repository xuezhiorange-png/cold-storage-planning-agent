# TASK-012 / V0.2 Slice 4 — Production Dependency and Persistence Reality Contract

## 1. Authority and version identity

```text
REPOSITORY=xuezhiorange-png/cold-storage-planning-agent
TARGET_VERSION=v0.2.0
RELEASE_CLASS=DEPLOYABLE_SINGLE_INSTANCE
VERSION_THEME=PRODUCTION_READINESS_AND_DEPLOYMENT_HARDENING
PRIMARY_TASK=TASK-012
SOURCE_ISSUE=73
TARGET_SLICE=V0_2_SLICE_4

BASE_BRANCH=main
BASE_SHA=1d661b16b69a08f20d46f8a7a99a0952080b7e61
DOCUMENT_KIND=GAP_IMPLEMENTATION_CONTRACT
DOCUMENT_STATUS=FROZEN_CANDIDATE_ON_BRANCH
```

This document freezes the implementation boundary for the remaining V0.2 Slice 4 production-dependency gaps. It does not authorize implementation, Ready, Merge, deployment, release, or branch deletion.

The version is the top-level authority. This Slice may only close gaps required for the V0.2.0 deployable single-instance user capability. It must not add new product capabilities.

## 2. User capability

```text
USER_CAPABILITY=
A user running the system in staging or production can use the existing
V0.2 production HTTP scope through real database and canonical storage
authorities. A model-backed planning-agent capability that is explicitly
outside V0.2 production scope returns a stable, diagnosable disabled response,
not a fake-backed result and not an accidental route-missing 404.
```

## 3. Deliverables

```text
DELIVERABLE_1=DATABASE_BACKED_COEFFICIENT_HTTP_BINDING
DELIVERABLE_2=EXPLICIT_AGENT_PRODUCTION_SCOPE_EXCLUSION
DELIVERABLE_3=STABLE_DISABLED_AGENT_HTTP_SURFACE
DELIVERABLE_4=STRICT_CAPABILITY_BINDING_AUDIT
DELIVERABLE_5=NON_BLOCKING_DISABLED_CAPABILITY_READINESS
DELIVERABLE_6=AGENT_CAPABILITY_METRIC_BINDING
DELIVERABLE_7=CANONICAL_ENGINE_AND_STORAGE_OWNERSHIP
DELIVERABLE_8=FOCUSED_ACCEPTANCE_AND_ARCHITECTURE_TESTS
DELIVERABLE_9=OPERATOR_RUNBOOK
```

## 4. Slice exit criteria

```text
SLICE4_FAKE_RUNTIME_DEPENDENCY_COUNT=0
SLICE4_IN_MEMORY_PRODUCTION_AUTHORITY_COUNT=0
SLICE4_PRODUCTION_ADAPTER_BINDING=PASS
SLICE4_ARTIFACT_STORAGE_BOUNDARY=PASS

SLICE4_COEFFICIENT_HTTP_DATABASE_BACKED=PASS
SLICE4_AGENT_PRODUCTION_EXCLUSION=PASS
SLICE4_AGENT_DISABLED_HTTP_CONTRACT=PASS
SLICE4_STRICT_CAPABILITY_AUDIT=PASS
SLICE4_DISABLED_CAPABILITY_READINESS=PASS
SLICE4_CAPABILITY_METRIC=PASS
```

A merged PR alone does not satisfy these criteria. Exact-head CI and focused behavioral evidence are required.

---

## D-S4-01 — Production coefficient HTTP authority

All existing coefficient HTTP routes must be registered in every supported mode.

```text
COEFFICIENT_ROUTES_MOUNTED_LOCAL=YES
COEFFICIENT_ROUTES_MOUNTED_TEST=YES
COEFFICIENT_ROUTES_MOUNTED_STAGING=YES
COEFFICIENT_ROUTES_MOUNTED_PRODUCTION=YES

LOCAL_TEST_COEFFICIENT_BACKEND=PROCESS_LOCAL_COEFFICIENT_SERVICE
STAGING_PRODUCTION_COEFFICIENT_BACKEND=DATABASE_COEFFICIENT_SERVICE
```

No new coefficient authority is permitted. The strict path must bind the existing `DatabaseCoefficientService`.

```text
NEW_COEFFICIENT_AUTHORITY=NO
NEW_COEFFICIENT_RULES=NO
NEW_COEFFICIENT_VALUES=NO
NEW_APPROVAL_SEMANTICS=NO
```

### Delayed provider contract

`register_coefficient_routes` must accept a delayed provider instead of a concrete service captured during app construction:

```python
from collections.abc import Callable

CoefficientServiceProvider = Callable[[], CoefficientService]

def register_coefficient_routes(
    app: FastAPI,
    coefficient_service_provider: CoefficientServiceProvider,
) -> None:
    ...
```

Each request resolves the provider inside the request call path.

```text
PROVIDER_RESOLVED_DURING_ROUTE_REGISTRATION=NO
PROVIDER_RESOLVED_BEFORE_LIFESPAN=NO
PROVIDER_RESOLVED_PER_REQUEST=YES

PRODUCTION_PROVIDER=get_production_coefficient_service
PRODUCTION_SERVICE_TYPE=DatabaseCoefficientService
PRODUCTION_SERVICE_CREATED_DURING_INIT_DEPENDENCIES=YES
```

Local and test fixtures may inject process-local services explicitly. The production provider must never branch to an in-memory fallback.

### Canonical engine identity

```text
COEFFICIENT_SERVICE_ENGINE_IS_CANONICAL_ENGINE=YES
COEFFICIENT_SERVICE_ENGINE_IS_READINESS_ENGINE=YES
COEFFICIENT_SERVICE_ENGINE_IS_MIGRATION_TARGET_ENGINE=YES

DUPLICATE_ENGINE_CREATION=PROHIBITED
ROUTE_LEVEL_ENGINE_CREATION=PROHIBITED
PROVIDER_LEVEL_ENGINE_CREATION=PROHIBITED
DATABASE_FAILURE_FALLBACK_TO_IN_MEMORY=NO
INHERITED_IN_MEMORY_CACHE_IS_AUTHORITATIVE=NO
```

The implementation must prove the equivalent of:

```python
get_production_coefficient_service().engine is get_engine()
```

---

## D-S4-02 — Planning-agent V0.2 production scope

The prior TASK-012 decision is binding for this Slice:

```text
PRODUCTION_FAKE_AGENT_GATEWAY_ALLOWED=NO
STAGING_FAKE_AGENT_GATEWAY_ALLOWED=NO
MODEL_BACKED_AGENT_CAPABILITY_INCLUDED_IN_V0_2_PRODUCTION_SCOPE=NO
NEW_AGENT_MODEL_PROVIDER=NO
EXTERNAL_LLM_INTEGRATION=NO
```

Local and test modes may continue using the deterministic fake gateway, which must remain visibly identified as non-production:

```text
provider=fake
production_ready=false
requires_review=true
```

### Strict disabled surface

Staging and production must expose an explicit disabled surface for every currently supported planning-agent endpoint. They must not rely on router omission and an accidental 404.

```text
STRICT_AGENT_ROUTER_MOUNTED=YES
STRICT_AGENT_BACKEND=DISABLED
STRICT_AGENT_HTTP_STATUS=503
STRICT_AGENT_CODE=AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE
STRICT_AGENT_RETRYABLE=NO
```

The stable response envelope is:

```json
{
  "error": {
    "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
    "message": "Model-backed planning agent capability is not included in V0.2 production scope.",
    "details": {
      "retryable": false
    }
  }
}
```

```text
CONTENT_TYPE=application/json
RETRY_AFTER_HEADER_PRESENT=NO
AUTHENTICATION_REQUIRED_BEFORE_DISABLED_RESPONSE=NO
REQUEST_BODY_VALIDATION_REQUIRED_BEFORE_DISABLED_RESPONSE=NO
DATABASE_SESSION_CREATED=NO
AGENT_SERVICE_CREATED=NO
MODEL_GATEWAY_CREATED=NO
TOOL_ADAPTER_CREATED=NO
REPORT_ARTIFACT_STORAGE_CREATED=NO
```

The disabled surface must cover the existing endpoint set:

```text
POST /api/v1/agent/sessions
GET  /api/v1/agent/sessions
GET  /api/v1/agent/sessions/{session_id}
GET  /api/v1/agent/sessions/{session_id}/messages
POST /api/v1/agent/sessions/{session_id}/messages
GET  /api/v1/agent/sessions/{session_id}/turns/{turn_id}
GET  /api/v1/agent/sessions/{session_id}/tool-calls
POST /api/v1/agent/tool-calls/{tool_call_id}/confirm
POST /api/v1/agent/tool-calls/{tool_call_id}/reject
POST /api/v1/agent/sessions/{session_id}/cancel
```

Unknown paths outside this existing endpoint set continue to return ordinary 404. The implementation must not turn every arbitrary `/api/v1/agent/**` path into a product endpoint.

---

## D-S4-03 — Agent construction entry points

Both existing construction entry points are governed:

```text
ENTRY_POINT_1=LegacyPlanningAgentService singleton
ENTRY_POINT_2=PlanningAgentService per-request factory

LEGACY_AGENT_SERVICE_PRODUCTION_FAKE_CONSTRUCTION=PROHIBITED
PER_REQUEST_AGENT_SERVICE_PRODUCTION_FAKE_CONSTRUCTION=PROHIBITED

FAKE_GATEWAY_ALLOWED_ENVIRONMENTS=local,test
FAKE_GATEWAY_ALLOWED_IN_STAGING=NO
FAKE_GATEWAY_ALLOWED_IN_PRODUCTION=NO
FAKE_RESULT_MUST_BE_IDENTIFIED_AS_FAKE=YES
```

The strict disabled router must not depend on the active service factory and must not indirectly invoke:

```text
_get_db_session
_get_planning_agent_service
FakeAgentModelGateway
DefaultAgentModelGateway
ReportArtifactStorage(base_dir="data/report_artifacts")
```

---

## D-S4-04 — Readiness capability projection

Strict environments must expose the following safe capability projection:

```json
{
  "name": "model_backed_agent",
  "status": "disabled",
  "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
  "blocking": false
}
```

```text
AGENT_CAPABILITY_OUT_OF_SCOPE_BLOCKS_READINESS=NO
EXPECTED_DISABLED_CAPABILITY_STATUS=disabled
OVERALL_READINESS_DEPENDS_ON_MANDATORY_CAPABILITIES_ONLY=YES
DISABLED_OPTIONAL_CAPABILITY_CAUSES_HTTP_503_READY=NO
```

When all mandatory database, schema, migration, storage, configuration, and required-dependency probes pass, `/health/ready` remains HTTP 200 even though the model-backed agent capability is disabled.

A safe `capabilities` projection may be added to health evidence, but existing fields must not be removed or renamed:

```text
status
state
check_code
outcomes
```

The capability projection must not expose gateway class names, module paths, authentication-secret state, raw exceptions, tracebacks, internal factories, DSNs, or filesystem paths.

---

## D-S4-05 — Capability metric binding

The existing metric family must be reused.

```text
METRIC_FAMILY=agent_capability_status
NEW_METRIC_FAMILY_COUNT=0
CAPABILITY_LABEL=model_backed_agent

LOCAL_TEST_METRIC_VALUE=1
STAGING_PRODUCTION_METRIC_VALUE=0
```

Bootstrap must register the fixed bounded label before recording it:

```python
metrics.register_capability("model_backed_agent")
metrics.record_capability_status(
    "model_backed_agent",
    is_available=mode in (AppMode.LOCAL, AppMode.TEST),
)
```

Dynamic capability labels are prohibited.

---

## D-S4-06 — Strict capability binding audit

The existing route-prefix-only audit is insufficient for Slice 4 because a database-backed coefficient route and an explicitly disabled agent route are both legitimate strict-mode routes.

```text
ROUTE_PREFIX_ALONE_PROVES_UNSAFE=NO

COEFFICIENT_ROUTE_ALLOWED_BINDING=database_backed
AGENT_ROUTE_ALLOWED_BINDING=disabled

DATABASE_BACKED_COEFFICIENT_ROUTE=ALLOWED
DISABLED_AGENT_ROUTE=ALLOWED
```

The audit must inspect explicit binding identity plus composition-manifest evidence. The following conditions fail closed:

```text
PROCESS_LOCAL_COEFFICIENT_BINDING_IN_STRICT_MODE
FAKE_AGENT_BINDING_IN_STRICT_MODE
MISSING_BINDING_IDENTITY
UNKNOWN_BINDING_IDENTITY
COMPOSITION_MANIFEST_PROVIDER_ERROR
FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED
PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED
```

The existing public failure code remains authoritative:

```text
UNSAFE_STRICT_CAPABILITY_WIRING
```

No synonymous strict-capability failure code may be added.

---

## D-S4-07 — Artifact-storage authority

Slice 4 does not introduce a new storage backend.

```text
NEW_ARTIFACT_STORAGE_BACKEND=NO
REDIS_IMPLEMENTATION_REQUIRED=NO
CLOUD_OBJECT_STORAGE_REQUIRED=NO

COLD_STORAGE_STORAGE_DIR
    -> Settings.storage_dir
    -> canonical production artifact storage
```

A strict disabled agent request must not construct or reach a hard-coded local report-artifact path.

```text
STRICT_AGENT_HARDCODED_ARTIFACT_PATH_REACHABLE=NO
TEMPORARY_STORAGE_PRODUCTION_FALLBACK=NO
ARTIFACT_STORAGE_AUTHORITY_CHANGE=NO
```

---

## D-S4-08 — Lifecycle and resource ownership

Initialization order:

```text
1. canonical Settings
2. canonical engine
3. DatabaseCoefficientService singleton
4. remaining production services
5. startup/readiness probes
6. application becomes READY
```

Failure behavior:

```text
COEFFICIENT_SERVICE_INIT_FAILURE_FAILS_STARTUP=YES
FAILED_INIT_LEAVES_SINGLETON=NO
FAILED_INIT_LEAVES_ENGINE=NO
REINIT_AFTER_FAILED_INIT=SUPPORTED
```

Shutdown behavior:

```text
READINESS_DRAINING_BEFORE_ENGINE_DISPOSE=YES
COEFFICIENT_SINGLETON_CLEARED_ON_SHUTDOWN=YES
ENGINE_DISPOSED_EXACTLY_ONCE=YES
```

---

## D-S4-09 — Acceptance matrix

### Coefficient HTTP

```text
LOCAL_IN_MEMORY_COEFFICIENT_API=PASS
TEST_IN_MEMORY_COEFFICIENT_API=PASS
STAGING_DATABASE_COEFFICIENT_API=PASS
PRODUCTION_DATABASE_COEFFICIENT_API=PASS

CREATE_PERSIST_READBACK=PASS
RESTART_READBACK=PASS
LIST_GET_REVISION_RESOLVE_PARITY=PASS
CANONICAL_ENGINE_IDENTITY=PASS
NO_IN_MEMORY_FALLBACK=PASS
```

SQLite and PostgreSQL paths must be exercised. PostgreSQL is authoritative for the V0.2 production release path.

### Agent disabled behavior

```text
STRICT_AGENT_ALL_KNOWN_ENDPOINTS_RETURN_503=PASS
STRICT_AGENT_EXACT_ERROR_ENVELOPE=PASS
STRICT_AGENT_WITHOUT_AUTH_HEADERS=PASS
STRICT_AGENT_WITH_INVALID_BODY=PASS
STRICT_AGENT_FAKE_CONSTRUCTOR_CALL_COUNT=0
STRICT_AGENT_DB_SESSION_CALL_COUNT=0
STRICT_AGENT_REPORT_STORAGE_CONSTRUCTION_COUNT=0

LOCAL_TEST_AGENT_ACTIVE=PASS
LOCAL_TEST_AGENT_METADATA_PROVIDER_FAKE=PASS
LOCAL_TEST_AGENT_METADATA_PRODUCTION_READY_FALSE=PASS
```

### Readiness and strict audit

```text
STRICT_DATABASE_COEFFICIENT_ROUTE_AUDIT_ALLOWED=PASS
STRICT_DISABLED_AGENT_ROUTE_AUDIT_ALLOWED=PASS
STRICT_FAKE_AGENT_ROUTE_AUDIT_REJECTED=PASS
STRICT_IN_MEMORY_COEFFICIENT_ROUTE_AUDIT_REJECTED=PASS
STRICT_MISSING_BINDING_AUDIT_REJECTED=PASS
STRICT_UNKNOWN_BINDING_AUDIT_REJECTED=PASS

DISABLED_AGENT_BLOCKS_READINESS=NO
AGENT_CAPABILITY_SAFE_PROJECTION=PASS
```

### Metrics

```text
LOCAL_TEST_MODEL_BACKED_AGENT_METRIC=1
STAGING_PRODUCTION_MODEL_BACKED_AGENT_METRIC=0
UNREGISTERED_CAPABILITY_LABEL_REJECTED=PASS
```

### Quality gates

```text
BACKEND_SQLITE=PASS
BACKEND_POSTGRESQL=PASS
ARCHITECTURE_TESTS=PASS
RUFF_CHECK=PASS
RUFF_FORMAT_CHECK=PASS
MYPY=PASS
COMPOSE_CONFIG=PASS
FRONTEND=PASS
EXACT_HEAD_CI=SUCCESS
```

---

## D-S4-10 — Exact future implementation allowlist

```text
FUTURE_IMPLEMENTATION_MAX_CHANGED_PATH_COUNT=17
FUTURE_CREATE_PATH_COUNT=1
FUTURE_MODIFY_PATH_COUNT=16
FUTURE_DELETE_PATH_COUNT=0
```

### CREATE — exactly 1

```text
docs/runbooks/TASK-012-slice4-production-dependency-reality.md
```

### MODIFY — at most these 16 paths

```text
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/production_composition.py
backend/src/cold_storage/bootstrap/runtime_readiness.py
backend/src/cold_storage/modules/coefficients/api/routes.py
backend/src/cold_storage/modules/planning_agent/api/routes.py

backend/tests/integration/test_coefficient_api.py
backend/tests/unit/test_planning_agent_api.py
backend/tests/unit/test_runtime_readiness.py
backend/tests/architecture/test_deployment_startup_boundaries.py
backend/tests/integration/test_startup_lifecycle_sqlite.py
backend/tests/integration/test_startup_lifecycle_postgresql.py
backend/tests/integration/test_health_endpoints.py
backend/tests/test_metrics.py
backend/tests/integration/test_observability.py

docs/runbooks/TASK-012-slice2-deployment-startup.md
```

All other tracked paths are denied by default.

Explicitly prohibited without a separately reviewed contract amendment:

```text
backend/src/cold_storage/modules/coefficients/infrastructure/database.py
backend/src/cold_storage/modules/planning_agent/infrastructure/fake_gateways.py
backend/src/cold_storage/bootstrap/metrics/registry.py
backend/src/cold_storage/bootstrap/settings.py
backend/src/cold_storage/bootstrap/environment_model.py
backend/alembic/**
.github/workflows/**
frontend/**
backend/uv.lock
```

If implementation evidence proves an allowlist-external path is required, work must stop before modifying that path:

```text
STOPPED_CONTRACT_AMENDMENT_REQUIRED=YES
```

The implementation must not mutate first and amend the contract afterward.

---

## D-S4-11 — Version and Slice non-goals

```text
DATABASE_SCHEMA_CHANGE=NO
ALEMBIC_REVISION_CHANGE=NO

NEW_COEFFICIENT_AUTHORITY=NO
NEW_COEFFICIENT_VALUE=NO
NEW_COEFFICIENT_RULE=NO
COEFFICIENT_APPROVAL_REDESIGN=NO

NEW_ENGINEERING_FORMULA=NO
NEW_SCORING_LOGIC=NO
NEW_OPTIMIZATION_ALGORITHM=NO

NEW_AGENT_MODEL_PROVIDER=NO
EXTERNAL_LLM_INTEGRATION=NO
PROMPT_REDESIGN=NO
TOOL_REGISTRY_REDESIGN=NO

REPORT_SEMANTICS_CHANGE=NO
REPORT_TEMPLATE_CHANGE=NO
FRONTEND_CHANGE=NO

NEW_METRIC_FAMILY=NO
AUTHENTICATION_REDESIGN=NO
RBAC_IMPLEMENTATION=NO

BACKUP_RESTORE_DRILL=NO
RELEASE_TAG=NO
PRODUCTION_DEPLOYMENT=NO
```

Backup, restore, failed-deployment rollback, release evidence, Release Notes, tagging, and the end-to-end deployment demo belong to V0.2 Slice 6.

---

## D-S4-12 — Rollback boundary

```text
ROLLBACK_TARGET_SHA=1d661b16b69a08f20d46f8a7a99a0952080b7e61
DATABASE_ROLLBACK_REQUIRED=NO
ALEMBIC_DOWNGRADE_REQUIRED=NO
DATA_MIGRATION_REQUIRED=NO
```

A rollback may restore the pre-Slice behavior:

```text
STRICT_COEFFICIENT_HTTP=404
STRICT_AGENT_HTTP=404
```

After rollback, the system must not claim:

```text
V0_2_PRODUCTION_DEPENDENCY_BINDING=PASS
SLICE4_COMPLETE=YES
```

---

## 5. Governance and binding trigger

This branch and Draft PR are documentation-only. Exactly one tracked file is authorized for the contract PR:

```text
docs/tasks/TASK-012-slice4-production-dependency-reality-contract.md
```

```text
DOCS_ONLY=YES
CONTRACT_CANDIDATE_TEXT_FROZEN=YES
CONTRACT_CURRENTLY_BINDING_ON_MAIN=NO

FREEZE_TEXT_ON_BRANCH_CREATES_IMPLEMENTATION_AUTHORITY=NO
PR_CREATION_CREATES_IMPLEMENTATION_AUTHORITY=NO
READY_CREATES_IMPLEMENTATION_AUTHORITY=NO
MERGE_PLUS_POST_MERGE_MAIN_IDENTITY_REQUIRED_FOR_BINDING_AUTHORITY=YES

SLICE4_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
BRANCH_DELETE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
```

The contract becomes repository-binding authority only after all of the following occur under separate authorization:

1. independent engineering review passes;
2. Draft-to-Ready transition is authorized and completed;
3. Merge is separately authorized and completed;
4. post-merge `main` identity is verified against the merge commit.

A separate Slice 4 implementation authorization is still required after the contract is binding on `main`.

```text
STOPPED_AWAITING_CHARLES_CONTRACT_REVIEW=YES
```
