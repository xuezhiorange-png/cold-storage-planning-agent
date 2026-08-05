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
DOCS_PR_BASE_SHA=1d661b16b69a08f20d46f8a7a99a0952080b7e61
SOURCE_REVIEW_COMMENT_ID=5181834263
CONTRACT_REVISION=R2
DOCUMENT_KIND=GAP_IMPLEMENTATION_CONTRACT
DOCUMENT_STATUS=CORRECTED_CANDIDATE_ON_BRANCH
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
DELIVERABLE_4=ZERO_PRODUCTION_REACHABLE_FAKE_AGENT_CONSTRUCTION
DELIVERABLE_5=STRICT_CAPABILITY_BINDING_AUDIT
DELIVERABLE_6=NON_BLOCKING_DISABLED_CAPABILITY_READINESS
DELIVERABLE_7=AGENT_CAPABILITY_METRIC_BINDING
DELIVERABLE_8=CANONICAL_ENGINE_AND_STORAGE_OWNERSHIP
DELIVERABLE_9=ACTIVE_REPORT_ARTIFACT_STORAGE_BINDING
DELIVERABLE_10=FOCUSED_ACCEPTANCE_AND_ARCHITECTURE_TESTS
DELIVERABLE_11=OPERATOR_RUNBOOK
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
SLICE4_DEMO_FAKE_PATH_EXCLUDED_FROM_STRICT_MODE=PASS
SLICE4_STRICT_CAPABILITY_AUDIT=PASS
SLICE4_DISABLED_CAPABILITY_READINESS=PASS
SLICE4_CAPABILITY_METRIC=PASS
SLICE4_ACTIVE_REPORT_STORAGE_CANONICAL=PASS
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

Each request resolves the provider exactly once inside the request call path.

```text
PROVIDER_RESOLVED_DURING_ROUTE_REGISTRATION=NO
PROVIDER_RESOLVED_BEFORE_LIFESPAN=NO
PROVIDER_RESOLVED_PER_REQUEST=YES
PROVIDER_CALL_COUNT_PER_REQUEST=1

PRODUCTION_PROVIDER=get_production_coefficient_service
PRODUCTION_SERVICE_TYPE=DatabaseCoefficientService
PRODUCTION_SERVICE_CREATED_DURING_INIT_DEPENDENCIES=YES
```

Local and test fixtures may inject process-local services explicitly. The production provider must never branch to an in-memory fallback.

If the production accessor is invoked before dependency initialization has published the singleton, the HTTP layer must return the following stable response and must not create a fallback service:

```text
UNINITIALIZED_PROVIDER_HTTP_STATUS=503
UNINITIALIZED_PROVIDER_CODE=PRODUCTION_DEPENDENCIES_NOT_INITIALIZED
UNINITIALIZED_PROVIDER_RETRYABLE=YES
```

```json
{
  "error": {
    "code": "PRODUCTION_DEPENDENCIES_NOT_INITIALIZED",
    "message": "Production dependencies are not initialized.",
    "details": {
      "retryable": true
    }
  }
}
```

A database operation failure after provider resolution is not an authorization to switch to process-local state. It must remain a database-path failure and follow the existing exception/observability authority.

### Database-backed method coverage

Every method reached by the existing coefficient HTTP surface must execute against the database-backed implementation:

```text
create_definition=DATABASE_BACKED
list_definitions=DATABASE_BACKED
get_definition=DATABASE_BACKED
create_revision=DATABASE_BACKED
list_revisions=DATABASE_BACKED
get_revision=DATABASE_BACKED
mark_revision_reviewed=DATABASE_BACKED
approve_revision=DATABASE_BACKED
withdraw_revision=DATABASE_BACKED
resolve_coefficient_set=DATABASE_BACKED
```

No listed method may inherit an authoritative process-local implementation.

```text
PARENT_IN_MEMORY_METHOD_FALLBACK=PROHIBITED
PARENT_CACHE_AS_READ_AUTHORITY=PROHIBITED
DATABASE_ERROR_TO_PARENT_METHOD_FALLBACK=PROHIBITED
```

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

### Transaction boundary

Slice 4 binds the existing database authority; it does not redesign coefficient approval transactions.

```text
HTTP_REQUEST_WIDE_SHARED_SESSION_REQUIRED=NO
DATABASE_COEFFICIENT_SERVICE_EXISTING_SESSION_OWNERSHIP_PRESERVED=YES
COEFFICIENT_APPROVAL_TRANSACTION_REDESIGN=NO
SECOND_ENGINE_DISPOSAL_AUTHORITY=NO
```

Existing transactional approval services and repositories remain authoritative where already used. Direct coefficient registry HTTP methods may continue to own their current per-method database sessions, provided all listed persistence and restart-readback acceptance tests pass.

---

## D-S4-02 — Planning-agent V0.2 production scope

Canonical names and mode classes:

```text
CANONICAL_CAPABILITY_NAME=model_backed_agent
NON_STRICT_MODES=local,test
STRICT_MODES=staging,production
```

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

### HTTP boundary

```text
KNOWN_ENDPOINT_WITH_DECLARED_METHOD=503_DISABLED_ENVELOPE
KNOWN_ENDPOINT_WITH_UNDECLARED_METHOD=405
UNKNOWN_AGENT_PATH=404
HEAD_ON_KNOWN_ENDPOINT_WITHOUT_DECLARED_HEAD=405
OPTIONS_ON_KNOWN_ENDPOINT_WITHOUT_CORS_OVERRIDE=405
TRAILING_SLASH_VARIANT=307_REDIRECT_TO_CANONICAL_PATH
ALLOW_HEADER_ON_405=YES
STRICT_DISABLED_ENDPOINTS_INCLUDED_IN_OPENAPI=YES
OPENAPI_DOCUMENTS_503_DISABLED_RESPONSE=YES
```

Unknown paths outside the existing endpoint set remain ordinary 404. The implementation must not turn every arbitrary `/api/v1/agent/**` path into a product endpoint.

The declared method on a known endpoint must return 503 before authentication, request-body validation, database dependency resolution, or resource lookup. Framework-level 404, 405, and 307 responses do not use the disabled capability envelope.

---

## D-S4-03 — All production-reachable fake-agent construction entry points

The prior contract listed only two construction paths. The complete current production-reachable inventory is:

```text
ENTRY_POINT_1=LegacyPlanningAgentService singleton in bootstrap.dependencies
ENTRY_POINT_2=PlanningAgentService per-request factory in bootstrap.app
ENTRY_POINT_3=build_demo_overview direct LegacyPlanningAgentService(FakeAgentModelGateway()) call
```

All three are governed.

```text
LEGACY_AGENT_SERVICE_PRODUCTION_FAKE_CONSTRUCTION=PROHIBITED
PER_REQUEST_AGENT_SERVICE_PRODUCTION_FAKE_CONSTRUCTION=PROHIBITED
DEMO_OVERVIEW_PRODUCTION_FAKE_CONSTRUCTION=PROHIBITED

FAKE_GATEWAY_ALLOWED_ENVIRONMENTS=local,test
FAKE_GATEWAY_ALLOWED_IN_STAGING=NO
FAKE_GATEWAY_ALLOWED_IN_PRODUCTION=NO
FAKE_RESULT_MUST_BE_IDENTIFIED_AS_FAKE=YES
```

The strict disabled agent router must not depend on the active service factory and must not indirectly invoke:

```text
_get_db_session
_get_planning_agent_service
FakeAgentModelGateway
DefaultAgentModelGateway
ReportArtifactStorage(base_dir="data/report_artifacts")
```

### Demo overview boundary

`GET /api/v1/demo/overview` is not part of the V0.2 strict production HTTP scope because its current implementation directly invokes the fake model gateway.

```text
STRICT_DEMO_OVERVIEW_ROUTE_MOUNTED=NO
STRICT_DEMO_OVERVIEW_HTTP_STATUS=404
STRICT_BUILD_DEMO_OVERVIEW_CALL_COUNT=0
STRICT_DEMO_OVERVIEW_FAKE_GATEWAY_CONSTRUCTOR_CALL_COUNT=0

LOCAL_TEST_DEMO_OVERVIEW_ROUTE_MOUNTED=YES
LOCAL_TEST_DEMO_OVERVIEW_FAKE_METADATA_VISIBLE=YES
```

This Slice does not require changing the internal demo algorithm. It requires preventing that fake-backed function from being reachable in staging or production.

The implementation must search and test all direct constructors of:

```text
FakeAgentModelGateway(
DefaultAgentModelGateway(
LegacyPlanningAgentService(
PlanningAgentService(
```

No unlisted strict-runtime construction path may remain.

---

## D-S4-04 — Readiness capability projection

The canonical capability name is shared by readiness, metrics, and strict audit:

```text
CANONICAL_CAPABILITY_NAME=model_backed_agent
```

Every successfully created application instance exposes a top-level `capabilities` array on every `/health/ready` response branch, including ready, not-ready, configuration-failure, draining, and shutdown responses.

The array is sorted lexicographically by `name`.

Strict modes expose:

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

Local and test modes expose:

```json
[
  {
    "name": "model_backed_agent",
    "status": "available",
    "code": null,
    "blocking": false
  }
]
```

```text
CAPABILITIES_FIELD_LOCATION=TOP_LEVEL
CAPABILITIES_FIELD_PRESENT_ALL_READY_RESPONSE_BRANCHES=YES
CAPABILITIES_FIELD_PRESENT_ALL_FOUR_MODES=YES
CAPABILITY_ORDER=LEXICOGRAPHIC_BY_NAME
CAPABILITY_STATUS_VALUES=available,disabled

AGENT_CAPABILITY_OUT_OF_SCOPE_BLOCKS_READINESS=NO
EXPECTED_DISABLED_CAPABILITY_STATUS=disabled
OVERALL_READINESS_DEPENDS_ON_MANDATORY_CAPABILITIES_ONLY=YES
DISABLED_OPTIONAL_CAPABILITY_CAUSES_HTTP_503_READY=NO
```

When all mandatory database, schema, migration, storage, configuration, and required-dependency probes pass, `/health/ready` remains HTTP 200 even though the model-backed agent capability is disabled.

Existing fields must not be removed or renamed. They remain present in the response branches where the existing readiness contract already requires them:

```text
status
state
check_code
outcomes
```

The capability projection must not expose gateway class names, module paths, authentication-secret state, raw exceptions, tracebacks, internal factories, DSNs, or filesystem paths.

```text
STARTUP_CAPABILITY_AUTHORITY_EQUALS_DYNAMIC_READINESS_AUTHORITY=YES
READINESS_CAPABILITY_AUTHORITY_EQUALS_METRIC_AUTHORITY=YES
DISABLED_AGENT_PARTICIPATES_IN_MANDATORY_PROBE_SET=NO
```

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

```text
CAPABILITY_LABEL_REGISTRATION_IDEMPOTENT=YES
REPEATED_APP_CREATION_OVERWRITES_FIXED_GAUGE=YES
STRICT_APP_AFTER_LOCAL_APP_LEAVES_STALE_VALUE_1=NO
LOCAL_APP_AFTER_STRICT_APP_LEAVES_STALE_VALUE_0=NO
TEST_REGISTRY_ISOLATION_OR_EXPLICIT_RESET_REQUIRED=YES
```

The metric value and readiness capability projection must be derived from the same resolved application mode and canonical capability identity.

---

## D-S4-06 — Strict capability binding audit

The existing route-prefix-only audit is insufficient because a database-backed coefficient route and an explicitly disabled agent route are both legitimate strict-mode routes.

```text
ROUTE_PREFIX_ALONE_PROVES_UNSAFE=NO

COEFFICIENT_ROUTE_ALLOWED_BINDING=database_backed
AGENT_ROUTE_ALLOWED_BINDING=disabled

DATABASE_BACKED_COEFFICIENT_ROUTE=ALLOWED
DISABLED_AGENT_ROUTE=ALLOWED
```

### Binding identity authority

The contract freezes two separate evidence authorities that the audit must cross-check:

```text
HTTP_BINDING_REGISTRATION_AUTHORITY=bootstrap.app.create_app
COMPOSITION_EVIDENCE_REGISTRATION_AUTHORITY=bootstrap.dependencies.init_dependencies

HTTP_BINDING_MANIFEST_STORAGE=app.state.strict_capability_bindings
HTTP_BINDING_MANIFEST_TYPE=IMMUTABLE_TUPLE
HTTP_BINDING_REGISTRATION_TIMING=IMMEDIATELY_AFTER_ROUTE_REGISTRATION
HTTP_BINDING_MANIFEST_FREEZE_TIMING=BEFORE_CREATE_APP_RETURNS

COMPOSITION_MANIFEST_PROVIDER_AUTHORITY=bootstrap.dependencies
COMPOSITION_MANIFEST_SNAPSHOT_TYPE=FROZENSET
```

Only the composition root may register HTTP binding identity. Route modules and service providers may not self-register or mutate binding evidence.

```text
ROUTE_MODULE_SELF_REGISTRATION=PROHIBITED
SERVICE_PROVIDER_SELF_ATTESTATION=PROHIBITED
BINDING_MANIFEST_MUTATION_AFTER_APP_FACTORY_RETURN=PROHIBITED
AUDIT_IMPORTS_BUSINESS_SERVICE_TYPES=NO
```

Required exact entries in strict mode:

```text
capability=coefficient_http,binding=database_backed
capability=model_backed_agent,binding=disabled
```

Required positive composition evidence:

```text
DATABASE_COEFFICIENT_SERVICE_INSTANTIATED
```

Forbidden composition evidence:

```text
FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED
PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED
```

The audit must require the HTTP declaration and matching composition evidence. A route declaration of `database_backed` without the positive database-service composition token fails closed.

### Registration and reset rules

```text
DUPLICATE_IDENTICAL_BINDING_REGISTRATION=FAIL
DUPLICATE_CONFLICTING_BINDING_REGISTRATION=FAIL
MISSING_BINDING_IDENTITY=FAIL
UNKNOWN_CAPABILITY_IDENTITY=FAIL
UNKNOWN_BINDING_IDENTITY=FAIL
MISSING_POSITIVE_COMPOSITION_EVIDENCE=FAIL
COMPOSITION_MANIFEST_PROVIDER_ERROR=FAIL

BINDING_MANIFEST_SCOPE=PER_FASTAPI_APP_INSTANCE
REPEATED_CREATE_APP_REUSES_OLD_MANIFEST=NO
GLOBAL_BINDING_MANIFEST_SINGLETON=NO
SHUTDOWN_MUTATES_FROZEN_HTTP_BINDING_MANIFEST=NO
```

The following conditions fail closed:

```text
PROCESS_LOCAL_COEFFICIENT_BINDING_IN_STRICT_MODE
FAKE_AGENT_BINDING_IN_STRICT_MODE
MISSING_BINDING_IDENTITY
UNKNOWN_BINDING_IDENTITY
COMPOSITION_MANIFEST_PROVIDER_ERROR
FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED
PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED
DATABASE_COEFFICIENT_POSITIVE_EVIDENCE_MISSING
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

The authority applies to every production-reachable report artifact path, not only the disabled agent path.

```text
STAGING_PRODUCTION_REPORT_RENDER_STORAGE=Settings.storage_dir
STAGING_PRODUCTION_AGENT_TOOL_REPORT_STORAGE=UNREACHABLE_DISABLED_PATH

STRICT_ACTIVE_REPORT_HARDCODED_DATA_REPORT_ARTIFACTS_ALLOWED=NO
STRICT_AGENT_HARDCODED_ARTIFACT_PATH_REACHABLE=NO
TEMPORARY_STORAGE_PRODUCTION_FALLBACK=NO
ARTIFACT_STORAGE_AUTHORITY_CHANGE=NO
```

The active report HTTP dependency must resolve `Settings.storage_dir` after the canonical settings authority is initialized. It must not construct:

```text
ReportArtifactStorage(base_dir="data/report_artifacts")
```

in staging or production.

Local and test modes may use an explicitly injected temporary path. A repository-relative default is not production authority.

```text
STRICT_REPORT_RENDER_WRITES_BENEATH_CANONICAL_STORAGE_DIR=YES
STRICT_REPORT_RENDER_WRITES_TO_REPOSITORY_DATA_DIR=NO
STRICT_REPORT_STORAGE_PROVIDER_RESOLVED_AFTER_LIFESPAN_INIT=YES
```

Architecture and end-to-end tests must prove both:

1. a strict report render writes only beneath the injected canonical storage directory; and
2. no production-reachable constructor uses the hard-coded `data/report_artifacts` path.

---

## D-S4-08 — Lifecycle and resource ownership

Initialization order:

```text
1. canonical Settings
2. canonical engine
3. DatabaseCoefficientService singleton
4. positive composition evidence publication
5. remaining production services
6. startup/readiness probes and strict capability audit
7. application becomes READY
```

Failure behavior:

```text
COEFFICIENT_SERVICE_INIT_FAILURE_FAILS_STARTUP=YES
FAILED_INIT_LEAVES_SINGLETON=NO
FAILED_INIT_LEAVES_ENGINE=NO
FAILED_INIT_LEAVES_POSITIVE_COMPOSITION_TOKEN=NO
REINIT_AFTER_FAILED_INIT=SUPPORTED
```

`DatabaseCoefficientService` construction itself is not required to query the database. Publication of its singleton and positive composition evidence must be atomic from the perspective of the startup audit.

Shutdown behavior:

```text
READINESS_DRAINING_BEFORE_ENGINE_DISPOSE=YES
COEFFICIENT_SINGLETON_CLEARED_ON_SHUTDOWN=YES
COMPOSITION_EVIDENCE_CLEARED_ON_SHUTDOWN=YES
ENGINE_DISPOSED_EXACTLY_ONCE=YES
```

A delayed provider reference retained by a route may remain callable after shutdown only to produce `PRODUCTION_DEPENDENCIES_NOT_INITIALIZED`; it must not return a stale service holding the disposed engine.

---

## D-S4-09 — Acceptance matrix

### Coefficient HTTP and persistence

```text
LOCAL_IN_MEMORY_COEFFICIENT_API=PASS
TEST_IN_MEMORY_COEFFICIENT_API=PASS
STAGING_DATABASE_COEFFICIENT_API=PASS
PRODUCTION_DATABASE_COEFFICIENT_API=PASS

PROVIDER_RESOLVED_ON_EACH_REQUEST=PASS
PROVIDER_UNINITIALIZED_RETURNS_STABLE_503=PASS
CANONICAL_ENGINE_IDENTITY=PASS
DUPLICATE_ENGINE_COUNT=0
NO_IN_MEMORY_FALLBACK=PASS
```

The database-backed HTTP matrix must exercise every existing route operation:

```text
DEFINITION_CREATE=PASS
DEFINITION_LIST=PASS
DEFINITION_GET=PASS
REVISION_CREATE=PASS
REVISION_LIST=PASS
REVISION_GET=PASS
REVISION_REVIEW=PASS
REVISION_APPROVE=PASS
REVISION_WITHDRAW=PASS
COEFFICIENT_RESOLVE=PASS
```

Required persistence sequence:

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

SQLite and PostgreSQL paths must be exercised. PostgreSQL is authoritative for the V0.2 production release path.

A method-ownership test must verify that all HTTP-reached methods are implemented by `DatabaseCoefficientService` and do not dispatch to process-local parent implementations.

### Agent disabled behavior

```text
STRICT_AGENT_ALL_KNOWN_ENDPOINTS_RETURN_503=PASS
STRICT_AGENT_EXACT_ERROR_ENVELOPE=PASS
STRICT_AGENT_WITHOUT_AUTH_HEADERS=PASS
STRICT_AGENT_WITH_INVALID_BODY=PASS
STRICT_AGENT_UNKNOWN_PATH_RETURNS_404=PASS
STRICT_AGENT_UNDECLARED_METHOD_RETURNS_405=PASS
STRICT_AGENT_TRAILING_SLASH_REDIRECTS_307=PASS
STRICT_AGENT_OPENAPI_DOCUMENTS_DISABLED_SURFACE=PASS

STRICT_AGENT_FAKE_CONSTRUCTOR_CALL_COUNT=0
STRICT_AGENT_DB_SESSION_CALL_COUNT=0
STRICT_AGENT_REPORT_STORAGE_CONSTRUCTION_COUNT=0

LOCAL_TEST_AGENT_ACTIVE=PASS
LOCAL_TEST_AGENT_METADATA_PROVIDER_FAKE=PASS
LOCAL_TEST_AGENT_METADATA_PRODUCTION_READY_FALSE=PASS
```

### Demo fake path

```text
STRICT_DEMO_OVERVIEW_HTTP_STATUS=404
STRICT_BUILD_DEMO_OVERVIEW_CALL_COUNT=0
STRICT_DEMO_FAKE_GATEWAY_CONSTRUCTOR_CALL_COUNT=0
LOCAL_TEST_DEMO_OVERVIEW_HTTP_STATUS=200
LOCAL_TEST_DEMO_OVERVIEW_FAKE_METADATA_VISIBLE=PASS
```

### Readiness and strict audit

```text
STRICT_DATABASE_COEFFICIENT_ROUTE_AUDIT_ALLOWED=PASS
STRICT_DISABLED_AGENT_ROUTE_AUDIT_ALLOWED=PASS
STRICT_FAKE_AGENT_ROUTE_AUDIT_REJECTED=PASS
STRICT_IN_MEMORY_COEFFICIENT_ROUTE_AUDIT_REJECTED=PASS
STRICT_MISSING_BINDING_AUDIT_REJECTED=PASS
STRICT_UNKNOWN_BINDING_AUDIT_REJECTED=PASS
STRICT_MISSING_POSITIVE_DB_EVIDENCE_REJECTED=PASS
STRICT_ROUTE_SELF_ATTESTATION_CANNOT_BYPASS_AUDIT=PASS

DISABLED_AGENT_BLOCKS_READINESS=NO
AGENT_CAPABILITY_SAFE_PROJECTION=PASS
CAPABILITIES_PRESENT_ON_READY_200=PASS
CAPABILITIES_PRESENT_ON_NOT_READY_503=PASS
CAPABILITIES_PRESENT_ON_DRAINING_503=PASS
CAPABILITIES_PRESENT_ON_SHUTDOWN_503=PASS
CAPABILITY_ORDER_STABLE=PASS
```

### Metrics

```text
LOCAL_TEST_MODEL_BACKED_AGENT_METRIC=1
STAGING_PRODUCTION_MODEL_BACKED_AGENT_METRIC=0
UNREGISTERED_CAPABILITY_LABEL_REJECTED=PASS
REPEATED_APP_CREATION_METRIC_NOT_STALE=PASS
```

### Artifact storage

```text
STRICT_REPORT_RENDER_USES_SETTINGS_STORAGE_DIR=PASS
STRICT_REPORT_RENDER_CREATES_ARTIFACT_BENEATH_CANONICAL_DIR=PASS
STRICT_REPORT_RENDER_REPOSITORY_DATA_DIR_WRITE_COUNT=0
STRICT_PRODUCTION_REACHABLE_HARDCODED_STORAGE_CONSTRUCTOR_COUNT=0
```

### Lifecycle

```text
FAILED_INIT_SINGLETON_COUNT=0
FAILED_INIT_ENGINE_COUNT=0
FAILED_INIT_POSITIVE_COMPOSITION_TOKEN_COUNT=0
REINIT_AFTER_FAILURE=PASS
SHUTDOWN_CLEARS_COEFFICIENT_SINGLETON=PASS
POST_SHUTDOWN_PROVIDER_RETURNS_STABLE_503=PASS
ENGINE_DISPOSE_CALL_COUNT=1
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

Static grep alone cannot satisfy the behavioral exit criteria.

---

## D-S4-10 — Exact future implementation allowlist

```text
FUTURE_IMPLEMENTATION_MAX_CHANGED_PATH_COUNT=18
FUTURE_CREATE_PATH_COUNT=1
FUTURE_MODIFY_PATH_COUNT=17
FUTURE_DELETE_PATH_COUNT=0
```

### CREATE — exactly 1

```text
docs/runbooks/TASK-012-slice4-production-dependency-reality.md
```

### MODIFY — at most these 17 paths

```text
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/production_composition.py
backend/src/cold_storage/bootstrap/runtime_readiness.py
backend/src/cold_storage/modules/coefficients/api/routes.py
backend/src/cold_storage/modules/planning_agent/api/routes.py

backend/tests/integration/test_coefficient_api.py
backend/tests/integration/test_coefficient_database.py
backend/tests/unit/test_planning_agent_api.py
backend/tests/unit/test_demo_overview.py
backend/tests/unit/test_runtime_readiness.py
backend/tests/architecture/test_deployment_startup_boundaries.py
backend/tests/integration/test_startup_lifecycle_sqlite.py
backend/tests/integration/test_startup_lifecycle_postgresql.py
backend/tests/integration/test_health_endpoints.py
backend/tests/test_metrics.py
backend/tests/test_reports/test_real_storage_e2e.py
```

All other tracked paths are denied by default.

Explicitly prohibited without a separately reviewed contract amendment:

```text
backend/src/cold_storage/bootstrap/demo_overview.py
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

`bootstrap/demo_overview.py` remains unchanged because strict safety is achieved by making its fake-backed HTTP entry point unreachable in staging and production.

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
DEMO_ALGORITHM_REDESIGN=NO

REPORT_SEMANTICS_CHANGE=NO
REPORT_TEMPLATE_CHANGE=NO
NEW_ARTIFACT_STORAGE_BACKEND=NO
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

The rollback target is not the historical base of this docs-only contract PR.

```text
DOCS_PR_BASE_SHA_IS_IMPLEMENTATION_ROLLBACK_TARGET=NO
ROLLBACK_TARGET_SHA=<SLICE4_IMPLEMENTATION_BASE_SHA_CAPTURED_AT_IMPLEMENTATION_START>
ROLLBACK_TARGET_SHA_SOURCE=AUTHORIZED_MAIN_SHA_USED_TO_CREATE_IMPLEMENTATION_BRANCH
ROLLBACK_TARGET_MUST_EQUAL_IMPLEMENTATION_BRANCH_MERGE_BASE=YES

DATABASE_ROLLBACK_REQUIRED=NO
ALEMBIC_DOWNGRADE_REQUIRED=NO
DATA_MIGRATION_REQUIRED=NO
```

The implementation authorization must freeze the concrete rollback SHA before any tracked implementation mutation.

A rollback may restore the pre-Slice behavior:

```text
STRICT_COEFFICIENT_HTTP=404
STRICT_AGENT_HTTP=404
STRICT_DEMO_OVERVIEW_HTTP=<PRE_SLICE_BEHAVIOR>
STRICT_REPORT_STORAGE=<PRE_SLICE_BEHAVIOR>
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

1. independent engineering review passes against the exact corrected Head;
2. Draft-to-Ready transition is authorized and completed;
3. Merge is separately authorized and completed;
4. post-merge `main` identity is verified against the merge commit.

A separate Slice 4 implementation authorization is still required after the contract is binding on `main`.

```text
STOPPED_AWAITING_CHARLES_CORRECTED_CONTRACT_REVIEW=YES
```
