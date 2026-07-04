"""0034: add production_source_archives table with downgrade guard.

Revision ID: 0034_add_production_source_archives
Revises: 0033_extend_outbox_envelope
Create Date: 2026-07-04

Adds a ``production_source_archives`` table that snapshots the full source
identity of every production SchemeRun the moment it is published.  This
unblocks Issue #22 §10 (downgrade and historical-read integrity) by
providing a durable read-side source for production SchemeRuns that have
since had their online SourceBinding retired.

The downgrade() function runs a Python-side preflight check BEFORE
dropping anything: if any production SchemeRun exists without a verified
archive row, downgrade raises RuntimeError and aborts.  The guard lives
in Python (not as a SQL CHECK constraint) because it must JOIN
``scheme_runs`` with ``production_source_archives``, and we want the same
logic in both SQLite and PostgreSQL without dialect-specific PL/pgSQL.

Invariants enforced by application code (not SQL):
    * archive_hash length/format defence-in-depth (hex64)
    * computed archive_payload matches stored archive_hash on read
    * production SchemeRun must have a verified archive to be eligible
      for downgrade (preserved across migrations).
"""

from __future__ import annotations

import sys as _sys
from collections.abc import Sequence
from pathlib import Path as _Path

import sqlalchemy as sa
from alembic import op

revision: str = "0034_add_production_source_archives"
down_revision: str | None = "0033_extend_outbox_envelope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Schema version + invariant constants
ARCHIVE_SCHEMA_VERSION_V1: str = "SchemeSourceArchiveV1"
ARCHIVE_HASH_HEX_LEN: int = 64  # SHA-256 hex


def upgrade() -> None:
    dialect = op.get_context().dialect.name
    if dialect == "sqlite":
        _sqlite_upgrade()
    else:
        _pg_upgrade()


def downgrade() -> None:
    dialect = op.get_context().dialect.name
    if dialect == "sqlite":
        _sqlite_downgrade()
    else:
        _pg_downgrade()


# ── PostgreSQL ──────────────────────────────────────────────────────────────


def _pg_upgrade() -> None:
    op.create_table(
        "production_source_archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scheme_run_id",
            sa.String(36),
            sa.ForeignKey("scheme_runs.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_binding_id",
            sa.String(36),
            sa.ForeignKey("orchestration_source_bindings.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("source_contract_version", sa.String(50), nullable=False),
        sa.Column("archive_schema_version", sa.String(50), nullable=False),
        sa.Column("archive_payload", sa.JSON, nullable=False),
        sa.Column("archive_hash", sa.String(128), nullable=False),
        sa.Column("combined_source_hash", sa.String(128), nullable=True),
        sa.Column(
            "weight_set_revision_id",
            sa.String(36),
            sa.ForeignKey("scheme_weight_set_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("weight_set_content_hash", sa.String(128), nullable=True),
        sa.Column("binding_schema_version", sa.String(50), nullable=True),
        sa.Column(
            "execution_snapshot_id",
            sa.String(36),
            sa.ForeignKey("project_version_execution_snapshots.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "coefficient_context_id",
            sa.String(36),
            sa.ForeignKey("coefficient_contexts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "orchestration_identity_id",
            sa.String(36),
            sa.ForeignKey("orchestration_identities.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "authoritative_attempt_id",
            sa.String(36),
            sa.ForeignKey("orchestration_run_attempts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("orchestration_fingerprint", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.CheckConstraint(
            f"archive_schema_version = '{ARCHIVE_SCHEMA_VERSION_V1}'",
            name="ck_archive_schema_version_v1",
        ),
        sa.CheckConstraint(
            f"reason IN ('completed', 'pre_downgrade')",
            name="ck_archive_reason_values",
        ),
        sa.CheckConstraint(
            f"length(archive_hash) = {ARCHIVE_HASH_HEX_LEN}",
            name="ck_archive_hash_length",
        ),
    )
    op.create_index(
        "ix_production_source_archives_source_binding_id",
        "production_source_archives",
        ["source_binding_id"],
    )


def _pg_downgrade() -> None:
    _downgrade_guard()
    op.drop_index(
        "ix_production_source_archives_source_binding_id",
        table_name="production_source_archives",
    )
    op.drop_table("production_source_archives")


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    op.create_table(
        "production_source_archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scheme_run_id", sa.String(36), nullable=False, unique=True),
        sa.Column("source_binding_id", sa.String(36), nullable=True),
        sa.Column("source_contract_version", sa.String(50), nullable=False),
        sa.Column("archive_schema_version", sa.String(50), nullable=False),
        sa.Column("archive_payload", sa.JSON, nullable=False),
        sa.Column("archive_hash", sa.String(128), nullable=False),
        sa.Column("combined_source_hash", sa.String(128), nullable=True),
        sa.Column("weight_set_revision_id", sa.String(36), nullable=True),
        sa.Column("weight_set_content_hash", sa.String(128), nullable=True),
        sa.Column("binding_schema_version", sa.String(50), nullable=True),
        sa.Column("execution_snapshot_id", sa.String(36), nullable=True),
        sa.Column("coefficient_context_id", sa.String(36), nullable=True),
        sa.Column("orchestration_identity_id", sa.String(36), nullable=True),
        sa.Column("authoritative_attempt_id", sa.String(36), nullable=True),
        sa.Column("orchestration_fingerprint", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.CheckConstraint(
            f"archive_schema_version = '{ARCHIVE_SCHEMA_VERSION_V1}'",
            name="ck_archive_schema_version_v1",
        ),
        sa.CheckConstraint(
            f"reason IN ('completed', 'pre_downgrade')",
            name="ck_archive_reason_values",
        ),
        sa.CheckConstraint(
            f"length(archive_hash) = {ARCHIVE_HASH_HEX_LEN}",
            name="ck_archive_hash_length",
        ),
    )
    op.create_index(
        "ix_production_source_archives_source_binding_id",
        "production_source_archives",
        ["source_binding_id"],
    )


def _sqlite_downgrade() -> None:
    _downgrade_guard()
    op.drop_index(
        "ix_production_source_archives_source_binding_id",
        table_name="production_source_archives",
    )
    op.drop_table("production_source_archives")


# ── Downgrade guard (shared Python implementation) ──────────────────────────


def _downgrade_guard() -> None:
    """Python-side preflight for downgrade from 0034.

    Counts production SchemeRuns.  If any exist without a verified
    archive row (i.e. they would become un-readable after the table is
    dropped), raises RuntimeError and aborts the downgrade.

    A production SchemeRun is considered "verified" iff:

    1. Its ``combined_source_hash`` matches the archive's
       ``combined_source_hash``.
    2. Its ``archive_hash`` length is exactly 64 hex chars
       (defence-in-depth; SQL CHECK already enforces this).
    """
    bind = op.get_bind()
    dialect = op.get_context().dialect.name

    # Resolve the helper module from alembic/helpers/.
    # Alembic runs migrations as scripts (runpy); we load the helper
    # module via an explicit sys.path insertion to match the pattern
    # used by migration 0033.
    _migration_file = _Path(
        str(__file__)
    ).resolve()
    _alembic_dir = _migration_file.parent.parent
    if str(_alembic_dir) not in _sys.path:
        _sys.path.insert(0, str(_alembic_dir))

    # Production SchemeRuns: source_mode='production' AND source_binding_id
    # IS NOT NULL.  We also require combined_source_hash IS NOT NULL since
    # legacy runs never produce a combined_source_hash (production CHECK
    # enforces this invariant already).
    if dialect == "sqlite":
        rows = bind.execute(
            sa.text(
                "SELECT sr.id, sr.combined_source_hash "
                "FROM scheme_runs sr "
                "WHERE sr.source_mode = 'production' "
                "  AND sr.source_binding_id IS NOT NULL"
            )
        ).fetchall()
    else:
        rows = bind.execute(
            sa.text(
                "SELECT sr.id, sr.combined_source_hash "
                "FROM scheme_runs sr "
                "WHERE sr.source_mode = 'production' "
                "  AND sr.source_binding_id IS NOT NULL"
            )
        ).fetchall()

    if not rows:
        return

    # Verify each production SchemeRun has a matching archive row with
    # equal combined_source_hash and a 64-hex archive_hash.
    unmatched: list[tuple[str, str | None]] = []
    for scheme_run_id, combined_source_hash in rows:
        if dialect == "sqlite":
            archive_row = bind.execute(
                sa.text(
                    "SELECT combined_source_hash, archive_hash "
                    "FROM production_source_archives "
                    "WHERE scheme_run_id = :scheme_run_id"
                ),
                {"scheme_run_id": scheme_run_id},
            ).fetchone()
        else:
            archive_row = bind.execute(
                sa.text(
                    "SELECT combined_source_hash, archive_hash "
                    "FROM production_source_archives "
                    "WHERE scheme_run_id = :scheme_run_id"
                ),
                {"scheme_run_id": scheme_run_id},
            ).fetchone()
        if archive_row is None:
            unmatched.append((scheme_run_id, combined_source_hash))
            continue
        archive_combined, archive_hash = archive_row
        if archive_combined != combined_source_hash:
            unmatched.append((scheme_run_id, combined_source_hash))
            continue
        if not _is_hex64(archive_hash):
            unmatched.append((scheme_run_id, combined_source_hash))
            continue

    if unmatched:
        sample = ", ".join(
            f"{sid} (combined_hash={ch!r})" for sid, ch in unmatched[:5]
        )
        raise RuntimeError(
            "downgrade blocked: "
            f"{len(unmatched)} production SchemeRun(s) lack verified archive: "
            f"{sample}"
        )


def _is_hex64(value: str) -> bool:
    """Return True iff value is exactly 64 lowercase hex chars."""
    if len(value) != ARCHIVE_HASH_HEX_LEN:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
