# TASK-012 V0.2 Slice 6 Package 2: Release Failure Recovery

This runbook defines the fail-closed recovery boundary for a failed release
attempt. It covers S6-04 failed deployment rollback and S6-05 failed
migration recovery. It is an operator procedure and controlled synthetic
acceptance contract; it does not authorize production execution.

## Scope and authorization

Package 2 consumes observations from a release attempt and reuses the
Package 1 canonical recovery surfaces:

```text
cold_storage.recovery.cli backup
cold_storage.recovery.cli restore-isolated
cold_storage.recovery.cli verify-restore
```

These authorizations remain independent:

```text
TASK012_BACKUP_AUTHORIZED=YES
TASK012_ISOLATED_RESTORE_AUTHORIZED=YES
```

The controlled workflow is synthetic-only. It uses an ephemeral PostgreSQL
service, temporary artifact roots, and locally built test images. It does not
read production databases, artifact stores, registry credentials, or
environment secrets.

## Failure-state decision gate

Capture the following identities before attempting a candidate release:

```text
previous_image_digest
previous_build_commit_sha
previous_build_version
previous_deployment_id
candidate_image_digest
candidate_build_commit_sha
candidate_build_version
candidate_deployment_id
database_environment_id
artifact_environment_id
pre_deployment_schema_head
pre_deployment_database_inventory_digest
pre_deployment_artifact_inventory_digest
backup_id
backup_manifest_digest
```

The canonical classifier is
`cold_storage.recovery.failure_recovery.classify_failure_state`.

Application-only rollback is allowed only when all available authorities are
present, valid, and unchanged:

```text
post_failure_schema_head == pre_deployment_schema_head
post_failure_database_inventory_digest == pre_deployment_database_inventory_digest
post_failure_artifact_inventory_digest == pre_deployment_artifact_inventory_digest
```

The result must be:

```text
failure_state_classification=SCHEMA_AND_DATA_UNCHANGED
recovery_decision=APP_ONLY_ROLLBACK_ALLOWED
```

Schema changes, database or artifact inventory changes, unreadable schema
heads, malformed digests, missing paired observations, or any ambiguity
produce `MIGRATION_RECOVERY_REQUIRED`. Never infer that an unavailable
observation is unchanged.

## Failed deployment rollback

The safe sequence is:

```text
start previous known-good release
capture pre-failure identities
attempt candidate release
observe startup/readiness failure
capture post-failure schema and inventory identities
classify failure state
rollback only to the exact previous image/build/deployment identity
verify /health/live and /health/ready
write and independently verify deployment-rollback-receipt.json
```

The receipt is closed-schema evidence. It binds the previous and failed
candidate image, build, deployment, database/artifact environments, backup
identity, failure classification, recovery decision, rollback identity, and
post-rollback readiness. `rollback_result=PASS` is accepted only after those
fields are recomputed and verified by
`verify_deployment_rollback_receipt`.

Do not treat `docker compose down`, a process restart, a mutable tag, or a
successful container start as release rollback. The previous immutable image
and deployment identity must be restored and observed.

## Failed migration recovery

The application does not own migration downgrade and no automatic downgrade
is permitted:

```text
APPLICATION_RUNS_MIGRATIONS=NO
APPLICATION_RUNS_DOWNGRADE=NO
AUTOMATIC_DOWNGRADE_ALLOWED=NO
```

The recovery sequence is:

```text
create and verify a known-good pre-migration Package 1 backup
attempt the migration
classify transactional rollback or partial mutation
prohibit application-only rollback when state is changed or ambiguous
create a new empty isolated database and artifact root
restore the exact backup with restore-isolated
run independent verify-restore
verify final schema and database/artifact inventory identities
start the previous known-good release only after recovery verification
write and verify migration-recovery-receipt.json
```

A transactional failure may classify as unchanged only after the database
inventory and schema head are independently re-observed. A partial mutation
requires isolated recovery even when a downgrade appears technically
possible. The migration receipt requires
`automatic_downgrade_performed=false`, `recovery_required=true`, distinct
source/target identities, PASS restore and readiness observations, and final
state equal to the pre-migration state.

The controlled acceptance must exercise actual Alembic failure boundaries. It
creates temporary, untracked revisions at runtime and invokes
`alembic upgrade <temporary-revision>` for both scenarios. The transactional
revision performs a real Alembic operation and raises a deterministic failure
marker; the partial revision performs a deliberately separate AUTOCOMMIT
mutation and raises a different marker. The command must exit nonzero, the
marker must be present, and the post-failure inventory must be re-observed
before classification. A SQLAlchemy transaction test or a hand-written SQL
statement without an Alembic command is not sufficient evidence. Temporary
revision files are removed after the step and no tracked Alembic revision is
created.

After the isolated restore and `verify-restore` steps, the workflow starts the
previous known-good release image against the recovered database and recovered
artifact root. `/health/live` must be observed from that process and
`/health/ready` must verify the expected recovered project row and artifact
content. The workflow writes `post-recovery-readiness.json` only after those
checks pass. The migration receipt consumes the observed
`independent_restore_verification`, `post_recovery_live_status`, and
`post_recovery_ready_status` values; it does not manufacture readiness from a
receipt or summary field. The acceptance summary verifies both receipts, the
temporary Alembic result records, and this readiness record before declaring
PASS.

The canonical commands are:

```bash
python -m cold_storage.recovery.cli classify-release-failure \
  --observation /path/to/post-failure-observation.json \
  --output /path/to/classification.json

python -m cold_storage.recovery.cli verify-deployment-rollback \
  --receipt /path/to/deployment-rollback-receipt.json

python -m cold_storage.recovery.cli verify-migration-recovery \
  --receipt /path/to/migration-recovery-receipt.json
```

These commands validate evidence and do not perform a deployment, database
mutation, downgrade, registry operation, signing, promotion, or deployment.

## Controlled acceptance workflow

The canonical Package 2 execution surface is the separate
`.github/workflows/task012-slice6-package2-recovery.yml` workflow. It is
`workflow_dispatch` only, runs on `main`, and requires:

```text
execute_controlled_failure_recovery_acceptance=true
expected_source_sha=<exact github.sha>
```

The workflow checks both the runtime `GITHUB_SHA` and `git rev-parse HEAD`
before starting any synthetic scenario. It has `contents: read` only. Pull
requests and ordinary pushes never execute the workflow, and the Package 2
acceptance is not part of Slice 2 live capture, transport, attestation, or
Assembly dispatch inputs.

The controlled evidence artifact is uploaded only after all checks pass and
contains exactly:

```text
acceptance-summary.json
deployment-rollback-receipt.json
migration-recovery-receipt.json
backup-manifest.json
restore-receipt.json
SHA256SUMS
SHA256SUMS.sha256
```

It must not contain database dumps, artifact archives, PostgreSQL volumes,
Docker image archives, credentials, `.env` files, or raw logs. The summary
records `controlled_synthetic=true`, `production=false`, the workflow run
identity, both failure scenarios, canonical backup/restore/verify results,
`automatic_downgrade_performed=false`, and the final PASS result.

## Production boundary and failure handling

This runbook does not authorize production execution. Provider-specific image
traffic switching, database cutover, storage cutover, secrets, and rollback
ordering remain operator/platform responsibilities under separate approval.

On any missing, malformed, conflicting, or unverifiable identity, stop and
retain the machine-readable failure code. Do not retry against another target,
drop or truncate a production database, overwrite an in-place artifact root,
run `alembic downgrade`, or silently continue with an application-only
rollback. Package 2 implementation remains pending its separate controlled
acceptance and independent review until that workflow has actually passed.
