# TASK-012 V0.2 Slice 6 Package 1: Data Recovery Foundation

This runbook defines the operator-facing recovery authority for S6-01,
S6-02, and S6-03. It is a controlled data-recovery procedure, not a
deployment or release-promotion procedure.

## Scope and authorization

The package provides:

- a PostgreSQL custom-format logical backup;
- a deterministic, independently hashed artifact-storage archive;
- exact inventories for database rows and artifact files;
- restore to a new empty PostgreSQL database and empty artifact root; and
- an independent post-restore verifier and receipt.

The following authorizations are separate and do not inherit from one another:

```text
TASK012_BACKUP_AUTHORIZED=YES
TASK012_ISOLATED_RESTORE_AUTHORIZED=YES
```

Real production backup and restore require a separate live-evidence
authorization. CI uses only an ephemeral PostgreSQL service and temporary
artifact directories.

## Backup prerequisites

The source must expose these environment variables. The values are read by
the process but never written to the bundle or receipt:

```text
COLD_STORAGE_DATABASE_URL
COLD_STORAGE_STORAGE_DIR
COLD_STORAGE_ENVIRONMENT_ID
COLD_STORAGE_DATABASE_ENVIRONMENT_ID
COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID
```

The database URL must identify a PostgreSQL database. The three environment
identities must be explicit and non-empty. `COLD_STORAGE_STORAGE_DIR` is the
source artifact root; it is scanned as a directory containing only regular
files and directories. Symlinks, hardlinks, device files, FIFOs, and sockets
are rejected.

Retention is bounded to 1 through 3650 days. The default is 30 days and the
chosen value is recorded in the manifest together with UTC `created_at` and
`expires_at`. There is no implicit infinite-retention mode.

## Create and verify a backup

The only canonical operator command is:

```bash
export TASK012_BACKUP_AUTHORIZED=YES
python -m cold_storage.recovery.cli backup \
  --execute-backup \
  --backup-root /path/outside-the-source-storage \
  --retention-days 30
```

The command first requires both the CLI flag and the authorization
environment variable. Without both, it exits with
`BACKUP_EXECUTION_NOT_AUTHORIZED` before opening the database or reading the
artifact payload.

The bundle is published atomically as:

```text
<backup-root>/<backup-id>/
  backup-manifest.json
  database.dump
  database-inventory.json
  artifacts.tar
  artifact-inventory.json
  SHA256SUMS
  SHA256SUMS.sha256
```

The manifest is closed and records the backup identity, source resource
identities, packaged Alembic schema head, retention window, and the digests
of the dump, inventories, and archive. `verification_result=PASS` is written
only after the exact seven-file shape, internal checksums, manifest digests,
inventory schemas, and archive safety checks pass.

`database.dump` is produced by `pg_dump --format=custom --no-owner
--no-privileges --snapshot <exported-snapshot>`. The backup keeps a PostgreSQL
`REPEATABLE READ, READ ONLY` exporter transaction open while `pg_dump` runs and
while the database inventory is queried through that same connection. The
snapshot identifier is process-local and is never written to the bundle.
Database credentials are passed to the child process only through `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`; the full URL is never
placed in argv. The child is invoked with `shell=False`.

The database inventory contains the packaged schema head, every application
table, row count, and a deterministic logical SHA-256 digest. Rows are
ordered by primary key; tables without a primary key use a canonical row
ordering. The artifact archive is created first, and the artifact inventory is
derived by re-reading the completed tar payload, not by scanning the live
source a second time. The archive-derived inventory contains the sorted
storage-root-relative path, size, and SHA-256 for every regular file. Bundle
validation recomputes that inventory from `artifacts.tar` and rejects any
archive/inventory disagreement.

## Isolated restore prerequisites

The target must be independently identified with:

```text
COLD_STORAGE_RESTORE_DATABASE_URL
COLD_STORAGE_RESTORE_STORAGE_DIR
COLD_STORAGE_RESTORE_ENVIRONMENT_ID
COLD_STORAGE_RESTORE_DATABASE_ENVIRONMENT_ID
COLD_STORAGE_RESTORE_ARTIFACT_ENVIRONMENT_ID
```

The target database must be reachable and empty of application-owned tables.
The target artifact root must be absent or empty. The source and target
environment identities must differ. The source and target database host,
port, and database name are compared; if independence cannot be proven, the
restore stops with `RESTORE_TARGET_ISOLATION_UNVERIFIED`. The restore never
drops a database, truncates a schema, or overwrites an existing target.

## Restore to isolation

The canonical restore command accepts one complete bundle directory:

```bash
export TASK012_ISOLATED_RESTORE_AUTHORIZED=YES
python -m cold_storage.recovery.cli restore-isolated \
  --execute-restore \
  --backup-bundle /path/to/backup-root/<backup-id> \
  --output-dir /path/to/restore-receipt
```

Before any target database mutation, the command verifies the exact bundle
file set, the sidecar and `SHA256SUMS`, all five payload digests, the closed
manifest, the inventory schemas, and `verification_result=PASS`.

It then runs `pg_restore --exit-on-error --no-owner --no-privileges` into the
empty target database. The artifact archive is validated member-by-member
before extraction. Absolute paths, `..`, backslash ambiguity, symlinks,
hardlinks, special files, and duplicate output paths are rejected. Extraction
is staged and only promoted into the empty target root after the archive
inventory matches.

After restore, the command recomputes the target schema head, every database
table logical digest, row count, artifact path set, file sizes, and file
hashes. The staged artifact tree is checked before promotion and the final
target root is scanned again after promotion; only the final scan can supply
the receipt's artifact observations. It also checks for unvalidated PostgreSQL
constraints and runs the existing packaged schema-head/readiness primitives
against the isolated target. A successful run writes `restore-receipt.json`;
the receipt contains identities, expected and actual digests, counts, all
verification statuses, and verification time, but no URL, password, DSN,
absolute artifact path, SQL, or traceback.

## Independent verification

The receipt is not authority by itself. Run:

```bash
python -m cold_storage.recovery.cli verify-restore \
  --backup-bundle /path/to/backup-root/<backup-id> \
  --receipt /path/to/restore-receipt/restore-receipt.json
```

`verify-restore` revalidates the backup bundle, reconnects to the target,
recomputes the database and artifact inventories, rechecks the schema head,
constraints, and isolated readiness, and compares those observations with the
receipt. It also rebinds every receipt authority field, including the manifest
digest, expected schema and inventory digests, table/file counts, all status
fields, and source/target identities. A forged `verification_result=PASS` or
forged expected authority field is rejected.

## Failure handling

Stable failure classes include:

```text
BACKUP_EXECUTION_NOT_AUTHORIZED
BACKUP_DATABASE_FAILED
BACKUP_ARTIFACT_FAILED
BACKUP_SCHEMA_IDENTITY_INVALID
BACKUP_BUNDLE_INCOMPLETE
BACKUP_CHECKSUM_MISMATCH
RESTORE_EXECUTION_NOT_AUTHORIZED
RESTORE_BUNDLE_INVALID
RESTORE_TARGET_NOT_EMPTY
RESTORE_ARTIFACT_TARGET_NOT_EMPTY
RESTORE_TARGET_ISOLATION_UNVERIFIED
RESTORE_DATABASE_FAILED
RESTORE_ARTIFACT_FAILED
RESTORE_SCHEMA_MISMATCH
RESTORE_DATABASE_INVENTORY_MISMATCH
RESTORE_ARTIFACT_INVENTORY_MISMATCH
RESTORE_CONSTRAINT_VERIFICATION_FAILED
RESTORE_READINESS_FAILED
RESTORE_RECEIPT_INVALID
```

Any failure is fail-closed. The operator must retain the safe failure code
and inspect the isolated target; the command does not retry against another
database or silently fall back to the source. Do not use `DROP DATABASE`,
`TRUNCATE`, or a migration downgrade as a substitute for restore.

## Controlled operational acceptance

The canonical live validation surface is the separately guarded
`controlled-recovery-acceptance` job in `.github/workflows/ci.yml`. It is
available only from `workflow_dispatch` on `main` and requires both:

```text
execute_controlled_recovery_acceptance=true
expected_recovery_source_sha=<exact github.sha>
```

The recovery input is intentionally separate from the Slice 2
`expected_rc_source_sha`. The dispatch must set every Slice 2 live phase to
`false`; the workflow rejects mixed capture, transport, attestation, or
Assembly authorization. A source SHA mismatch fails before backup with
`RECOVERY_SOURCE_SHA_MISMATCH`. Pull requests and ordinary pushes keep this
job skipped while the normal `recovery-foundation` CI gate continues to run.

This acceptance uses only an ephemeral PostgreSQL service, two different
ephemeral databases, and a temporary synthetic artifact root. It seeds fixed
application and audit records, creates fixed artifact files, and marks the
run `CONTROLLED_SYNTHETIC_DATA=YES` and `REAL_PRODUCTION_DATA=NO`. It never
reads production secrets, production databases, production volumes, or
production artifact storage. The source and target environment identities,
database identities, and artifact roots are distinct. The target database
and artifact root must be empty before `restore-isolated` runs.

The job calls the three canonical Package 1 CLI surfaces in order:

```text
backup --execute-backup
restore-isolated --execute-restore
verify-restore
```

It verifies the backup's exact seven-file bundle and runs the independent
restore verifier after the restore command. It records source database and
artifact inventory digests before recovery and recomputes both after
verification; a mismatch fails the job. No failure is converted to a
successful exit and no failed acceptance artifact is uploaded.

Only a successful acceptance uploads the operational evidence artifact named
`task012-controlled-recovery-<run-id>-<run-attempt>` with compression level 0,
non-overwrite semantics, and a fixed retention period. The uploaded payload
is exactly seven files and deliberately excludes `database.dump`,
`artifacts.tar`, PostgreSQL data directories, source/target temporary files,
and credentials:

```text
acceptance-summary.json
backup-manifest.json
database-inventory.json
artifact-inventory.json
restore-receipt.json
SHA256SUMS
SHA256SUMS.sha256
```

`acceptance-summary.json` records the workflow identity, controlled source and
target identities, backup and receipt digests, the three PASS stages, source
unchanged results, and `acceptance_result=PASS`. `SHA256SUMS` covers the five
JSON files and `SHA256SUMS.sha256` covers the checksum manifest. The job
summary records the upload Artifact ID, Artifact digest, run identity, and
the same controlled acceptance status. This Artifact is operational
acceptance evidence, not a copy of the backup payload.

This surface is an authorization/readiness boundary only. It is not executed
by this implementation PR. After review, merge, and post-merge CI, one
explicit workflow dispatch may run the complete backup -> isolated restore ->
independent verify-restore sequence for S6-01/S6-02/S6-03 live closure review.

### Controlled recovery acceptance live history

The first controlled acceptance dispatch was run once and failed before any
backup or restore operation:

```text
RUN_ID=31461529093
RUN_ATTEMPT=1
HEAD_SHA=45c114d8a55e5cf2cfa2564e33fbb9cc5dc8924c
RESULT=FAIL
FAILED_STEP=Seed deterministic controlled source data
FAILURE_CLASS=SEED_FIXTURE_SCHEMA_CONTRACT_MISMATCH
ROOT_CAUSE=audit_events.outbox_event_id omitted from controlled seed
BACKUP_EXECUTED=NO
RESTORE_EXECUTED=NO
ARTIFACT_COUNT=0
PRODUCTION_DATA_TOUCHED=NO
```

The migrated Alembic schema requires `audit_events.outbox_event_id` to be
non-null and unique. The deterministic seed now binds the audit row to
`legacy-audit:<audit_event_id>` and verifies that value after insertion. A
real PostgreSQL integration regression executes the complete three-row seed
against the migrated schema inside a rolled-back transaction. This correction
changes the fixture and its regression coverage only; it does not change
recovery core, migrations, ORM contracts, or the Slice 2 live evidence
surface.

## What this does not prove

This package closes the implementation surface for S6-01 backup, S6-02
isolated restore, and S6-03 restored-data verification. It does not prove:

- failed deployment rollback (S6-04);
- failed migration recovery (S6-05);
- the final V0.2 release evidence bundle (S6-06);
- the V0.2 end-to-end operational acceptance (S6-07);
- production deployment, promotion, registry identity, OIDC, signing, or
  attestation; or
- a real production backup/restore event.

The Slice 2 reproducible build, transport, attestation, and six-file
assembly evidence remains the existing release authority and is not copied
into this recovery package.
