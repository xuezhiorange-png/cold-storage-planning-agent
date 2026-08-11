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
--no-privileges`. Database credentials are passed to the child process only
through `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`; the full
URL is never placed in argv. The child is invoked with `shell=False`.

The database inventory contains the packaged schema head, every application
table, row count, and a deterministic logical SHA-256 digest. Rows are
ordered by primary key; tables without a primary key use a canonical row
ordering. The artifact inventory contains the sorted storage-root-relative
path, size, and SHA-256 for every regular file.

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
hashes. It also checks for unvalidated PostgreSQL constraints and runs the
existing packaged schema-head/readiness primitives against the isolated
target. A successful run writes `restore-receipt.json`; the receipt contains
identities, digests, statuses, and verification time, but no URL, password,
DSN, absolute artifact path, SQL, or traceback.

## Independent verification

The receipt is not authority by itself. Run:

```bash
python -m cold_storage.recovery.cli verify-restore \
  --backup-bundle /path/to/backup-root/<backup-id> \
  --receipt /path/to/restore-receipt/restore-receipt.json
```

`verify-restore` revalidates the backup bundle, reconnects to the target,
recomputes the database and artifact inventories, rechecks the schema head,
constraints, and isolated readiness, and compares those observations with
the receipt. A forged `verification_result=PASS` is rejected.

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
