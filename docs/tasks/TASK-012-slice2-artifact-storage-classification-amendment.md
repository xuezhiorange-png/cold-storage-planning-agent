# TASK-012 Slice 2 — Artifact Storage Runtime Failure Classification Amendment

## 1. Document status and authority

```text
TASK=TASK-012
SLICE=2
AMENDMENT_NAME=ARTIFACT_STORAGE_RUNTIME_FAILURE_CLASSIFICATION
DOCUMENT_KIND=CONTRACT_AMENDMENT
DOCUMENT_STATUS=FROZEN_CANDIDATE_ON_BRANCH
AUTHORITY_FORM=ADDITIVE_EXTERNAL_AMENDMENT

BASE_CONTRACT_PATH=docs/tasks/TASK-012-slice2-deployment-startup-lifecycle-contract.md
BASE_CONTRACT_MAIN_SHA=ad86ff744b2a3adb4d534ab8581953d9a12b4289
SOURCE_IMPLEMENTATION_PR=76
SOURCE_IMPLEMENTATION_HEAD=a307aa7dbb284a7f1395abbb8d057c293fa0f947
SOURCE_FAILED_CI_RUN=30645027272
SOURCE_ENGINEERING_REVIEW=4830174777
```

This document is a narrow, docs-only amendment to the TASK-012 Slice 2
deployment artifact and startup lifecycle contract.

It exists because the mandatory
`artifact_storage_isolated_exists_writable` probe has a required failure
category, but no pre-existing frozen public stable code covers strict-runtime
artifact storage absence or writability failure. The base contract explicitly
forbids borrowing a timeout code or inventing a public code during
implementation.

This amendment becomes binding repository authority only after all of the
following have occurred:

1. this amendment PR passes exact-head CI;
2. an independent exact-head contract review passes;
3. Draft-to-Ready is separately authorized and completed;
4. Merge is separately authorized and completed;
5. the resulting merge commit is verified as the current `main` identity.

```text
DRAFT_PR_CREATION_CREATES_AUTHORITY=NO
READY_CREATES_IMPLEMENTATION_AUTHORITY=NO
MERGE_WITHOUT_POST_MERGE_MAIN_VERIFICATION_CREATES_AUTHORITY=NO
MERGE_PLUS_POST_MERGE_MAIN_IDENTITY_REQUIRED=YES
THIS_AMENDMENT_AUTHORIZES_PR76_IMPLEMENTATION=NO
PR76_MUTATION_AUTHORIZED=NO
PR76_READY_AUTHORIZED=NO
PR76_MERGE_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
```

## 2. Problem statement

The binding base contract requires artifact storage to be a mandatory startup
and readiness gate in staging and production. It must use the Slice 1 canonical
configuration authority, be isolated, exist, and be writable.

The current PR #76 implementation at
`a307aa7dbb284a7f1395abbb8d057c293fa0f947` has two contract defects:

1. the artifact probe bypasses `Settings.storage_dir` and reads ad-hoc runtime
   variables that are not canonical configuration keys;
2. deterministic non-timeout failures are projected to
   `STARTUP_PROBE_TIMEOUT`.

The affected deterministic conditions include:

```text
CANONICAL_STORAGE_PATH_ABSENT_AFTER_SETTINGS_RESOLUTION
ARTIFACT_STORAGE_DIRECTORY_MISSING_AT_RUNTIME
ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE_AT_RUNTIME
ARTIFACT_STORAGE_PROBE_FILE_IO_FAILURE
```

None of these conditions proves that a configured probe execution budget was
actually exceeded.

```text
NON_TIMEOUT_ARTIFACT_FAILURE_TO_STARTUP_TIMEOUT=FORBIDDEN
NON_TIMEOUT_ARTIFACT_FAILURE_TO_READINESS_TIMEOUT=FORBIDDEN
UNCONTRACTED_PUBLIC_CODE_CREATION=FORBIDDEN
```

## 3. Amendment scope

This amendment freezes exactly one new public stable failure code:

```text
NEW_STABLE_FAILURE_CODE=ARTIFACT_STORAGE_UNAVAILABLE
NEW_STABLE_FAILURE_CODE_COUNT=1
PUBLIC_SUBCODE_COUNT=0
```

`ARTIFACT_STORAGE_UNAVAILABLE` applies only when the mandatory artifact storage
probe completes with a non-timeout failure after canonical runtime
configuration has been resolved, or when that probe detects a defensive
absence of the canonical storage path.

It does not redesign report artifact persistence, storage providers, cloud
mounts, backup, retention, encryption, or report-domain error handling.

## 4. Internal closed set

The following identifiers are internal reasons, not public stable codes:

```text
ARTIFACT_STORAGE_PATH_NOT_CONFIGURED
ARTIFACT_STORAGE_DIRECTORY_MISSING
ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE
ARTIFACT_STORAGE_PROBE_IO_FAILURE
```

```text
INTERNAL_REASON_COUNT=4
INTERNAL_REASONS_ARE_PUBLIC_CODES=NO
```

Every internal reason above MUST project to the single public code
`ARTIFACT_STORAGE_UNAVAILABLE`.

Implementations MUST NOT expose these internal reasons as additional public
`check_code` values, HTTP API enums, CLI exit-code categories, or persisted
public contract values.

## 5. Canonical configuration authority

The canonical configuration chain is frozen as:

```text
COLD_STORAGE_STORAGE_DIR
    -> Slice 1 canonical configuration resolution
    -> Settings.storage_dir
    -> artifact_storage_isolated_exists_writable probe
```

```text
CANONICAL_ENV_KEY=COLD_STORAGE_STORAGE_DIR
CANONICAL_RUNTIME_FIELD=Settings.storage_dir
CANONICAL_STORAGE_AUTHORITY_COUNT=1
```

The following variables are not canonical authority and MUST NOT determine,
override, replace, or backfill the storage path used by the mandatory probe:

```text
COLD_STORAGE_ARTIFACT_STORAGE_DIR
COLD_STORAGE_REPORT_ARTIFACTS_DIR
```

```text
AD_HOC_STORAGE_ENV_AUTHORITY=FORBIDDEN
AD_HOC_STORAGE_ENV_OVERRIDE=FORBIDDEN
```

If these ad-hoc variables are present, the mandatory probe MUST ignore them.
They need not be added to `Settings`, `CANONICAL_KEYS`, `.env.example`, Docker,
Compose, or CI.

This amendment does not weaken existing Slice 1 configuration rules:

- staging and production still require an absolute storage path outside the
  repository;
- declared artifact environment identity remains required and must remain
  consistent;
- canonical Settings construction failures continue to use the existing
  configuration-classification authority;
- a declared artifact environment identity mismatch is not reclassified as
  `ARTIFACT_STORAGE_UNAVAILABLE`;
- an invalid canonical path shape rejected during Settings construction is not
  reclassified as `ARTIFACT_STORAGE_UNAVAILABLE`.

The new code covers the mandatory runtime artifact probe after canonical
Settings resolution, including its defensive path-absence branch.

## 6. Frozen classification matrix

Mandatory projection:

```text
ARTIFACT_STORAGE_PATH_NOT_CONFIGURED       -> ARTIFACT_STORAGE_UNAVAILABLE
ARTIFACT_STORAGE_DIRECTORY_MISSING         -> ARTIFACT_STORAGE_UNAVAILABLE
ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE    -> ARTIFACT_STORAGE_UNAVAILABLE
ARTIFACT_STORAGE_PROBE_IO_FAILURE           -> ARTIFACT_STORAGE_UNAVAILABLE
ARTIFACT_STORAGE_AVAILABLE_AND_WRITABLE     -> PASS

ACTUAL_STARTUP_TIMEOUT                      -> STARTUP_PROBE_TIMEOUT
ACTUAL_READINESS_TIMEOUT                    -> READINESS_PROBE_TIMEOUT
```

Forbidden projection:

```text
ARTIFACT_STORAGE_PATH_NOT_CONFIGURED_TO_TIMEOUT=false
ARTIFACT_STORAGE_DIRECTORY_MISSING_TO_TIMEOUT=false
ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE_TO_TIMEOUT=false
ARTIFACT_STORAGE_PROBE_IO_FAILURE_TO_TIMEOUT=false
GENERIC_EXCEPTION_TO_TIMEOUT=false
ANY_NON_PASS_TO_TIMEOUT=false
```

`STARTUP_PROBE_TIMEOUT` and `READINESS_PROBE_TIMEOUT` may be emitted only for a
real elapsed-budget timeout, a dependency-native timeout that actually
occurred, or a concrete blocking-probe timeout interruption.

A missing directory, permission denial, read-only mount, failed probe-file
create/write/flush/close/remove operation, or other deterministic filesystem
I/O failure is not a timeout merely because it occurs inside a bounded probe.

## 7. Probe semantics

In staging and production, the mandatory probe MUST:

1. obtain the canonical Settings object;
2. read the path only from `Settings.storage_dir`;
3. preserve the existing canonical environment and resource-identity gates;
4. verify that the resolved directory exists;
5. verify writability through a bounded, removable probe artifact or an
   equivalently strong bounded operation;
6. remove the probe artifact when creation succeeded;
7. fail closed if cleanup fails;
8. return `PASS` only when the directory is available and writable;
9. return `ARTIFACT_STORAGE_UNAVAILABLE` for every frozen non-timeout internal
   reason;
10. return a timeout code only for an actual timeout.

The probe MUST NOT:

```text
CREATE_MISSING_PRODUCTION_DIRECTORY
CHANGE_DIRECTORY_PERMISSIONS
CHANGE_DIRECTORY_OWNER
MOUNT_OR_UNMOUNT_STORAGE
FALL_BACK_TO_REPOSITORY_STORAGE
FALL_BACK_TO_TEMPORARY_STORAGE
FALL_BACK_TO_CURRENT_WORKING_DIRECTORY
USE_AD_HOC_ENV_AUTHORITY
EXECUTE_REPORT_RENDERING
PERSIST_BUSINESS_ARTIFACTS
```

The startup/readiness probe is validation only. It is not a storage
provisioner or repair mechanism.

## 8. Safe public projection

A health response MAY expose only the existing safe lifecycle envelope plus the
new stable code, for example:

```json
{
  "status": "not_ready",
  "state": "<safe lifecycle state>",
  "check_code": "ARTIFACT_STORAGE_UNAVAILABLE"
}
```

Public responses MUST NOT expose:

```text
full absolute storage path
host mount path
container volume source
raw OSError text
errno message text
filesystem user or group details
file mode details that reveal deployment internals
probe file name
secret or token
DSN or database URL
traceback
```

Logs MAY record only a narrow safe projection:

```text
probe=artifact_storage_isolated_exists_writable
check_code=ARTIFACT_STORAGE_UNAVAILABLE
internal_reason=<one frozen internal reason identifier>
```

Logs MUST NOT include the full path or raw exception text.

## 9. Code reuse prohibitions

`ARTIFACT_STORAGE_UNAVAILABLE` MUST NOT be used for:

```text
CANONICAL_SETTINGS_CONSTRUCTION_FAILURE
DECLARED_ARTIFACT_ENVIRONMENT_ID_MISMATCH
DATABASE_CONNECTIVITY_FAILURE
DATABASE_SCHEMA_HEAD_INVALID
BUILD_IDENTITY_FAILURE
DEPLOYMENT_ID_FAILURE
COEFFICIENT_READINESS_FAILURE
UNSAFE_STRICT_CAPABILITY_WIRING
LIFECYCLE_OR_DRAINING_FAILURE
REPORT_RENDER_OR_EXPORT_FAILURE
REPORT_ARTIFACT_DOMAIN_VALIDATION_FAILURE
CLOUD_PROVIDER_PROVISIONING_FAILURE
ACTUAL_STARTUP_TIMEOUT
ACTUAL_READINESS_TIMEOUT
```

Likewise, the following existing codes or identifiers MUST NOT be borrowed for
non-timeout artifact runtime failures:

```text
STARTUP_PROBE_TIMEOUT
READINESS_PROBE_TIMEOUT
DATABASE_SCHEMA_HEAD_INVALID
UNSAFE_STRICT_CAPABILITY_WIRING
ConfigurationError
StartupProbeFailure
StartupNonTimeoutProbeFailure
```

Python exception class names are not substitutes for a public stable code.
They may be internal control-flow mechanisms only.

## 10. Acceptance obligations

A future implementation authorized after this amendment becomes binding MUST
demonstrate all of the following:

```text
STRICT_PRODUCTION_CANONICAL_STORAGE_DIR_PRESENT_WRITABLE
    -> PASS

STRICT_STAGING_CANONICAL_STORAGE_DIR_PRESENT_WRITABLE
    -> PASS

ARTIFACT_STORAGE_PATH_NOT_CONFIGURED
    -> ARTIFACT_STORAGE_UNAVAILABLE

ARTIFACT_STORAGE_DIRECTORY_MISSING
    -> ARTIFACT_STORAGE_UNAVAILABLE

ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE
    -> ARTIFACT_STORAGE_UNAVAILABLE

ARTIFACT_STORAGE_PROBE_IO_FAILURE
    -> ARTIFACT_STORAGE_UNAVAILABLE

ACTUAL_STARTUP_TIMEOUT
    -> STARTUP_PROBE_TIMEOUT

ACTUAL_READINESS_TIMEOUT
    -> READINESS_PROBE_TIMEOUT
```

Required regression evidence:

1. strict production succeeds when only `COLD_STORAGE_STORAGE_DIR` provides the
   storage location and the directory is available and writable;
2. strict staging uses the same check class and succeeds under the same
   conditions;
3. `COLD_STORAGE_ARTIFACT_STORAGE_DIR` cannot override the canonical value;
4. `COLD_STORAGE_REPORT_ARTIFACTS_DIR` cannot override the canonical value;
5. a missing directory produces `ARTIFACT_STORAGE_UNAVAILABLE` and never a
   timeout code;
6. an unwritable directory produces `ARTIFACT_STORAGE_UNAVAILABLE` and never a
   timeout code;
7. probe-file I/O failure produces `ARTIFACT_STORAGE_UNAVAILABLE` and never a
   timeout code;
8. a real blocking timeout still produces the appropriate timeout code;
9. public health evidence does not expose a full path or raw exception;
10. local/test behavior remains compatible with the existing base contract;
11. the probe does not create production directories or mutate permissions;
12. the canonical Settings object remains the single configuration authority.

## 11. Future PR #76 correction boundary

This amendment does not authorize code mutation. After it is merged and the
resulting `main` identity is verified, a separate Charles authorization is
required before PR #76 may be updated.

The expected narrow active implementation paths are:

```text
backend/src/cold_storage/bootstrap/runtime_readiness.py
backend/tests/unit/test_runtime_readiness.py
```

```text
EXPECTED_FUTURE_ACTIVE_PATH_MAXIMUM=2
UNLISTED_ACTIVE_PATH_AUTHORIZED=NO
```

The expected correction MUST NOT require active changes to:

```text
backend/src/cold_storage/bootstrap/settings.py
backend/src/cold_storage/bootstrap/environment_model.py
backend/src/cold_storage/bootstrap/resource_identity.py
backend/Dockerfile
docker-compose.production.yml
.github/workflows/ci.yml
.env.example
backend/alembic/**
backend/uv.lock
frontend/**
```

If the implementation cannot satisfy this amendment within the separately
authorized path boundary, it must stop and request a new scope amendment.

## 12. Amendment non-goals

```text
PRODUCTION_STORAGE_PROVISIONING=NO
CLOUD_STORAGE_PROVIDER_SELECTION=NO
OBJECT_STORAGE_IMPLEMENTATION=NO
BACKUP_OR_RESTORE_IMPLEMENTATION=NO
RETENTION_POLICY_CHANGE=NO
REPORT_DOMAIN_ERROR_REDESIGN=NO
DATABASE_SCHEMA_CHANGE=NO
ALEMBIC_REVISION_CREATION=NO
DOCKER_OR_COMPOSE_CHANGE=NO
CI_WORKFLOW_CHANGE=NO
FRONTEND_CHANGE=NO
PR76_READY_TRANSITION=NO
PR76_MERGE=NO
PRODUCTION_DEPLOYMENT=NO
```

## 13. Governance close

```text
THIS_AMENDMENT_IS_V0_2_SLICE2_ONLY=YES
NEW_PUBLIC_STABLE_CODE=ARTIFACT_STORAGE_UNAVAILABLE
NEW_PUBLIC_STABLE_CODE_COUNT=1
INTERNAL_REASON_COUNT=4
PUBLIC_SUBCODE_COUNT=0

DRAFT_PR_CREATION_CREATES_AUTHORITY=NO
READY_CREATES_IMPLEMENTATION_AUTHORITY=NO
AMENDMENT_MERGE_REQUIRED=YES
POST_MERGE_MAIN_IDENTITY_REQUIRED=YES
FRESH_PR76_IMPLEMENTATION_AUTHORIZATION_REQUIRED=YES

PR76_REMAINS_DRAFT=YES
PR76_MUTATION_AUTHORIZED=NO
PR76_READY_AUTHORIZED=NO
PR76_MERGE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=YES
```
