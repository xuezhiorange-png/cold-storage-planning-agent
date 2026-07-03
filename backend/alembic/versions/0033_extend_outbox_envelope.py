"""0033: extend outbox envelope and add FAILED state.

Revision ID: 0033_extend_outbox_envelope
Revises: 451311827adf
Create Date: 2026-07-03

Adds to ``orchestration_audit_outbox``:
- event_schema_version, actor, correlation_id, occurred_at, payload_hash, envelope_hash
- claim_token, last_error_class, last_error_at, failed_at
- Updates ck_outbox_status_nullity to include FAILED state
- Adds immutability trigger on outbox after initial insert
- Adds trigger enforcing AuditEvent existence for PUBLISHED outbox rows
- Adds PG AuditEvent identity immutability trigger

Post-add backfill: sets meaningful legacy values for pre-existing rows.
SQLite: adds triggers for immutability and PUBLISHED-requires-AuditEvent.
"""

from collections.abc import Sequence
import hashlib

import sqlalchemy as sa

from alembic import op

revision: str = "0033_extend_outbox_envelope"
down_revision: str | None = "451311827adf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMU_ENVELOPE_FN = """\
CREATE OR REPLACE FUNCTION trg_immutable_outbox_envelope()
RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'PUBLISHED' THEN
    RAISE EXCEPTION 'Cannot modify published outbox event %', OLD.id;
  END IF;
  IF OLD.status = 'FAILED' THEN
    RAISE EXCEPTION 'Cannot modify failed outbox event %', OLD.id;
  END IF;
  IF NEW.event_identity IS DISTINCT FROM OLD.event_identity
     OR NEW.event_type IS DISTINCT FROM OLD.event_type
     OR NEW.event_schema_version IS DISTINCT FROM OLD.event_schema_version
     OR NEW.aggregate_type IS DISTINCT FROM OLD.aggregate_type
     OR NEW.aggregate_id IS DISTINCT FROM OLD.aggregate_id
     OR NEW.actor IS DISTINCT FROM OLD.actor
     OR NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
     OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
     OR NEW.payload::text IS DISTINCT FROM OLD.payload::text
     OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
     OR NEW.envelope_hash IS DISTINCT FROM OLD.envelope_hash
     OR NEW.request_id IS DISTINCT FROM OLD.request_id
     OR NEW.identity_id IS DISTINCT FROM OLD.identity_id
     OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
     OR NEW.calculation_run_id IS DISTINCT FROM OLD.calculation_run_id
     OR NEW.source_binding_id IS DISTINCT FROM OLD.source_binding_id THEN
    RAISE EXCEPTION
      'Cannot modify immutable audit envelope fields on outbox event %',
      OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""

_PUB_REQUIRES_AUDITEVENT_FN = """\
CREATE OR REPLACE FUNCTION trg_outbox_published_requires_auditevent()
RETURNS trigger AS $$
BEGIN
  IF NEW.status = 'PUBLISHED' AND OLD.status != 'PUBLISHED' THEN
    IF NOT EXISTS (
      SELECT 1 FROM audit_events
      WHERE outbox_event_id = NEW.event_identity
    ) THEN
      RAISE EXCEPTION
        'PUBLISHED outbox event % has no matching AuditEvent', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""

_IMMUTABLE_AUDIT_EVENT_IDENTITY_FN = """\
CREATE OR REPLACE FUNCTION trg_immutable_audit_event_identity()
RETURNS trigger AS $$
BEGIN
  IF OLD.outbox_event_id IS NOT NULL
     AND NEW.outbox_event_id IS DISTINCT FROM OLD.outbox_event_id THEN
    RAISE EXCEPTION 'Cannot modify audit event outbox_event_id %', OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""


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
    # 1. Add new columns
    cols = [
        ("event_schema_version", sa.String(50), "1.0"),
        ("actor", sa.String(100), ""),
        ("correlation_id", sa.String(128), ""),
        ("payload_hash", sa.String(128), ""),
    ]
    for name, typ, default in cols:
        op.add_column(
            "orchestration_audit_outbox",
            sa.Column(name, typ, nullable=False, server_default=default),
        )

    op.add_column(
        "orchestration_audit_outbox",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.add_column(
        "orchestration_audit_outbox",
        sa.Column("envelope_hash", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "orchestration_audit_outbox",
        sa.Column("claim_token", sa.String(36), nullable=True),
    )
    op.add_column(
        "orchestration_audit_outbox",
        sa.Column("last_error_class", sa.String(200), nullable=True),
    )
    op.add_column(
        "orchestration_audit_outbox",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orchestration_audit_outbox",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Drop old CHECK constraint and recreate with FAILED support
    op.execute(
        "ALTER TABLE orchestration_audit_outbox DROP CONSTRAINT IF EXISTS ck_outbox_status_nullity"
    )
    op.execute(
        "ALTER TABLE orchestration_audit_outbox "
        "ADD CONSTRAINT ck_outbox_status_nullity CHECK ("
        "( status = 'PENDING'"
        "  AND claimed_at IS NULL AND claimed_by IS NULL"
        "  AND claim_token IS NULL AND claim_expires_at IS NULL"
        "  AND published_at IS NULL AND failed_at IS NULL )"
        " OR ("
        "  status = 'PROCESSING'"
        "  AND claimed_at IS NOT NULL AND claimed_by IS NOT NULL"
        "  AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL"
        "  AND published_at IS NULL AND failed_at IS NULL )"
        " OR ("
        "  status = 'PUBLISHED'"
        "  AND published_at IS NOT NULL"
        "  AND failed_at IS NULL"
        "  AND claimed_at IS NULL AND claimed_by IS NULL"
        "  AND claim_token IS NULL AND claim_expires_at IS NULL )"
        " OR ("
        "  status = 'FAILED'"
        "  AND failed_at IS NOT NULL"
        "  AND published_at IS NULL"
        "  AND claimed_at IS NULL AND claimed_by IS NULL"
        "  AND claim_token IS NULL AND claim_expires_at IS NULL )"
        ")"
    )

    # 3. Backfill meaningful legacy values for pre-existing rows
    # Use Python-side computation to compute real envelope hashes
    _pg_backfill_envelopes()

    # 4. Immutable envelope trigger
    op.execute(_IMMU_ENVELOPE_FN)
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope ON orchestration_audit_outbox")
    op.execute(
        "CREATE TRIGGER trg_immutable_outbox_envelope "
        "BEFORE UPDATE ON orchestration_audit_outbox "
        "FOR EACH ROW EXECUTE FUNCTION trg_immutable_outbox_envelope()"
    )

    # 4b. Drop server defaults on audit fields — production code must supply
    # explicit values; missing audit fields must fail closed.
    for col in [
        "actor",
        "correlation_id",
        "payload_hash",
        "envelope_hash",
        "event_schema_version",
    ]:
        op.execute(f"ALTER TABLE orchestration_audit_outbox ALTER COLUMN {col} DROP DEFAULT")
    op.execute("ALTER TABLE orchestration_audit_outbox ALTER COLUMN occurred_at DROP DEFAULT")

    # 5. Published requires AuditEvent
    op.execute(_PUB_REQUIRES_AUDITEVENT_FN)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_outbox_published_requires_auditevent "
        "ON orchestration_audit_outbox"
    )
    op.execute(
        "CREATE TRIGGER trg_outbox_published_requires_auditevent "
        "BEFORE UPDATE ON orchestration_audit_outbox "
        "FOR EACH ROW EXECUTE FUNCTION "
        "trg_outbox_published_requires_auditevent()"
    )

    # 6. AuditEvent identity immutability trigger
    op.execute(_IMMUTABLE_AUDIT_EVENT_IDENTITY_FN)
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_audit_event_identity ON audit_events")
    op.execute(
        "CREATE TRIGGER trg_immutable_audit_event_identity "
        "BEFORE UPDATE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION trg_immutable_audit_event_identity()"
    )


def _pg_backfill_envelopes() -> None:
    """Backfill legacy outbox rows with real envelope hashes via Python-side computation.

    Reads the real association fields (request_id, identity_id, attempt_id,
    calculation_run_id, source_binding_id) when present so the hash matches
    what ``compute_envelope_hash`` would produce for production events.
    """
    from cold_storage.modules.orchestration.application.outbox_identity import (
        canonical_json,
        compute_envelope_hash,
    )

    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT id, event_identity, event_type, event_schema_version, "
            "aggregate_type, aggregate_id, actor, correlation_id, occurred_at, "
            "payload, payload_hash, request_id, identity_id, attempt_id, "
            "calculation_run_id, source_binding_id "
            "FROM orchestration_audit_outbox WHERE actor = ''"
        )
    )
    rows = result.fetchall()
    for row in rows:
        (
            row_id,
            event_identity,
            event_type,
            event_schema_version,
            aggregate_type,
            aggregate_id,
            actor,
            correlation_id,
            occurred_at,
            payload,
            payload_hash,
            request_id,
            identity_id,
            attempt_id,
            calculation_run_id,
            source_binding_id,
        ) = row

        # Compute real payload hash from the stored payload
        payload_str = canonical_json(payload)
        real_payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        envelope_hash = compute_envelope_hash(
            event_schema_version=event_schema_version or "1.0",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor="legacy-system",
            correlation_id=f"legacy:{row_id}",
            occurred_at=occurred_at,
            request_id=request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
            calculation_run_id=calculation_run_id,
            source_binding_id=source_binding_id,
            payload=payload if isinstance(payload, dict) else {},
            event_identity=event_identity,
        )

        bind.execute(
            sa.text(
                "UPDATE orchestration_audit_outbox "
                "SET actor = :actor, "
                "correlation_id = :correlation_id, "
                "payload_hash = :payload_hash, "
                "envelope_hash = :envelope_hash, "
                "event_schema_version = :event_schema_version "
                "WHERE id = :row_id"
            ),
            {
                "actor": "legacy-system",
                "correlation_id": f"legacy:{row_id}",
                "payload_hash": real_payload_hash,
                "envelope_hash": envelope_hash,
                "event_schema_version": event_schema_version or "1.0",
                "row_id": row_id,
            },
        )


def _pg_downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_outbox_published_requires_auditevent "
        "ON orchestration_audit_outbox"
    )
    op.execute("DROP FUNCTION IF EXISTS trg_outbox_published_requires_auditevent()")
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope ON orchestration_audit_outbox")
    op.execute("DROP FUNCTION IF EXISTS trg_immutable_outbox_envelope()")
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_audit_event_identity ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS trg_immutable_audit_event_identity()")

    # Restore old CHECK constraint
    op.execute(
        "ALTER TABLE orchestration_audit_outbox DROP CONSTRAINT IF EXISTS ck_outbox_status_nullity"
    )
    op.execute(
        "ALTER TABLE orchestration_audit_outbox "
        "ADD CONSTRAINT ck_outbox_status_nullity CHECK ("
        "( status = 'PENDING'"
        "  AND claimed_at IS NULL AND claimed_by IS NULL"
        "  AND claim_expires_at IS NULL"
        "  AND published_at IS NULL )"
        " OR ("
        "  status = 'PROCESSING'"
        "  AND claimed_at IS NOT NULL AND claimed_by IS NOT NULL"
        "  AND claim_expires_at IS NOT NULL"
        "  AND published_at IS NULL )"
        " OR ("
        "  status = 'PUBLISHED'"
        "  AND published_at IS NOT NULL )"
        ")"
    )

    for col in [
        "failed_at",
        "last_error_at",
        "last_error_class",
        "claim_token",
        "envelope_hash",
        "payload_hash",
        "occurred_at",
        "correlation_id",
        "actor",
        "event_schema_version",
    ]:
        op.drop_column("orchestration_audit_outbox", col)


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    with op.batch_alter_table("orchestration_audit_outbox") as batch_op:
        batch_op.add_column(
            sa.Column(
                "event_schema_version",
                sa.String(50),
                nullable=False,
                server_default="1.0",
            )
        )
        batch_op.add_column(sa.Column("actor", sa.String(100), nullable=False, server_default=""))
        batch_op.add_column(
            sa.Column("correlation_id", sa.String(128), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(datetime('now'))"),
            )
        )
        batch_op.add_column(
            sa.Column("payload_hash", sa.String(128), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("envelope_hash", sa.String(128), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("claim_token", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("last_error_class", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))

        batch_op.drop_constraint("ck_outbox_status_nullity", type_="check")
        batch_op.create_check_constraint(
            "ck_outbox_status_nullity",
            "(status = 'PENDING' AND claimed_at IS NULL AND claimed_by IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND published_at IS NULL AND failed_at IS NULL) "
            "OR (status = 'PROCESSING' AND claimed_at IS NOT NULL "
            "AND claimed_by IS NOT NULL AND claim_token IS NOT NULL "
            "AND claim_expires_at IS NOT NULL "
            "AND published_at IS NULL AND failed_at IS NULL) "
            "OR (status = 'PUBLISHED' AND published_at IS NOT NULL "
            "AND failed_at IS NULL "
            "AND claimed_at IS NULL AND claimed_by IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL) "
            "OR (status = 'FAILED' AND failed_at IS NOT NULL "
            "AND published_at IS NULL "
            "AND claimed_at IS NULL AND claimed_by IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL)",
        )

    # Backfill meaningful legacy values with real envelope hashes
    _sqlite_backfill_envelopes()

    # SQLite has no ALTER COLUMN DROP DEFAULT — recreate the table without
    # server defaults so production INSERTs must supply audit fields explicitly.
    with op.batch_alter_table(
        "orchestration_audit_outbox",
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "event_schema_version",
            server_default=None,
            existing_type=sa.String(50),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "actor",
            server_default=None,
            existing_type=sa.String(100),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "correlation_id",
            server_default=None,
            existing_type=sa.String(128),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "occurred_at",
            server_default=None,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "payload_hash",
            server_default=None,
            existing_type=sa.String(128),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "envelope_hash",
            server_default=None,
            existing_type=sa.String(128),
            existing_nullable=False,
        )

    # ── SQLite triggers ───────────────────────────────────────────────

    # 1. trg_immutable_outbox_envelope: BEFORE UPDATE, check envelope immutability
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope")
    op.execute(
        "CREATE TRIGGER trg_immutable_outbox_envelope "
        "BEFORE UPDATE ON orchestration_audit_outbox "
        "FOR EACH ROW "
        "WHEN "
        "  OLD.status = 'PUBLISHED' OR OLD.status = 'FAILED' "
        "  OR NEW.event_identity IS NOT OLD.event_identity "
        "  OR NEW.event_type IS NOT OLD.event_type "
        "  OR NEW.event_schema_version IS NOT OLD.event_schema_version "
        "  OR NEW.aggregate_type IS NOT OLD.aggregate_type "
        "  OR NEW.aggregate_id IS NOT OLD.aggregate_id "
        "  OR NEW.actor IS NOT OLD.actor "
        "  OR NEW.correlation_id IS NOT OLD.correlation_id "
        "  OR NEW.occurred_at IS NOT OLD.occurred_at "
        "  OR NEW.payload IS NOT OLD.payload "
        "  OR NEW.payload_hash IS NOT OLD.payload_hash "
        "  OR NEW.envelope_hash IS NOT OLD.envelope_hash "
        "  OR NEW.request_id IS NOT OLD.request_id "
        "  OR NEW.identity_id IS NOT OLD.identity_id "
        "  OR NEW.attempt_id IS NOT OLD.attempt_id "
        "  OR NEW.calculation_run_id IS NOT OLD.calculation_run_id "
        "  OR NEW.source_binding_id IS NOT OLD.source_binding_id "
        "BEGIN "
        "  SELECT RAISE(ABORT, 'Cannot modify immutable audit envelope fields on outbox event'); "
        "END"
    )

    # 2. trg_outbox_published_requires_auditevent: BEFORE UPDATE, PUBLISHED requires AuditEvent
    op.execute("DROP TRIGGER IF EXISTS trg_outbox_published_requires_auditevent")
    op.execute(
        "CREATE TRIGGER trg_outbox_published_requires_auditevent "
        "BEFORE UPDATE ON orchestration_audit_outbox "
        "FOR EACH ROW "
        "WHEN NEW.status = 'PUBLISHED' AND OLD.status != 'PUBLISHED' "
        "  AND NOT EXISTS (SELECT 1 FROM audit_events WHERE outbox_event_id = NEW.event_identity) "
        "BEGIN "
        "  SELECT RAISE(ABORT, 'PUBLISHED outbox event has no matching AuditEvent'); "
        "END"
    )

    # 3. trg_audit_event_outbox_id_immutable: BEFORE UPDATE on audit_events
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_outbox_id_immutable")
    op.execute(
        "CREATE TRIGGER trg_audit_event_outbox_id_immutable "
        "BEFORE UPDATE ON audit_events "
        "FOR EACH ROW "
        "WHEN NEW.outbox_event_id IS NOT OLD.outbox_event_id "
        "BEGIN "
        "  SELECT RAISE(ABORT, 'Cannot modify audit_events.outbox_event_id'); "
        "END"
    )


def _sqlite_backfill_envelopes() -> None:
    """Backfill legacy SQLite outbox rows with real envelope hashes.

    Reads the real association fields (request_id, identity_id, attempt_id,
    calculation_run_id, source_binding_id) when present so the hash matches
    what ``compute_envelope_hash`` would produce for production events.
    """
    from cold_storage.modules.orchestration.application.outbox_identity import (
        canonical_json,
        compute_envelope_hash,
    )

    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT id, event_identity, event_type, event_schema_version, "
            "aggregate_type, aggregate_id, actor, correlation_id, occurred_at, "
            "payload, payload_hash, request_id, identity_id, attempt_id, "
            "calculation_run_id, source_binding_id "
            "FROM orchestration_audit_outbox WHERE actor = ''"
        )
    )
    rows = result.fetchall()
    for row in rows:
        (
            row_id,
            event_identity,
            event_type,
            event_schema_version,
            aggregate_type,
            aggregate_id,
            actor,
            correlation_id,
            occurred_at,
            payload,
            payload_hash,
            request_id,
            identity_id,
            attempt_id,
            calculation_run_id,
            source_binding_id,
        ) = row

        # Compute real payload hash from the stored payload
        payload_str = canonical_json(payload)
        real_payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        envelope_hash = compute_envelope_hash(
            event_schema_version=event_schema_version or "1.0",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor="legacy-system",
            correlation_id=f"legacy:{row_id}",
            occurred_at=occurred_at,
            request_id=request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
            calculation_run_id=calculation_run_id,
            source_binding_id=source_binding_id,
            payload=payload if isinstance(payload, dict) else {},
            event_identity=event_identity,
        )

        bind.execute(
            sa.text(
                "UPDATE orchestration_audit_outbox "
                "SET actor = :actor, "
                "correlation_id = :correlation_id, "
                "payload_hash = :payload_hash, "
                "envelope_hash = :envelope_hash, "
                "event_schema_version = :event_schema_version "
                "WHERE id = :row_id"
            ),
            {
                "actor": "legacy-system",
                "correlation_id": f"legacy:{row_id}",
                "payload_hash": real_payload_hash,
                "envelope_hash": envelope_hash,
                "event_schema_version": event_schema_version or "1.0",
                "row_id": row_id,
            },
        )


def _sqlite_downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope")
    op.execute("DROP TRIGGER IF EXISTS trg_outbox_published_requires_auditevent")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_outbox_id_immutable")

    with op.batch_alter_table("orchestration_audit_outbox") as batch_op:
        batch_op.drop_constraint("ck_outbox_status_nullity", type_="check")
        batch_op.create_check_constraint(
            "ck_outbox_status_nullity",
            "(status = 'PENDING' AND claimed_at IS NULL AND claimed_by IS NULL "
            "AND claim_expires_at IS NULL AND published_at IS NULL) "
            "OR (status = 'PROCESSING' AND claimed_at IS NOT NULL "
            "AND claimed_by IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND published_at IS NULL) "
            "OR (status = 'PUBLISHED' AND published_at IS NOT NULL)",
        )
        for col in [
            "failed_at",
            "last_error_at",
            "last_error_class",
            "claim_token",
            "envelope_hash",
            "payload_hash",
            "occurred_at",
            "correlation_id",
            "actor",
            "event_schema_version",
        ]:
            batch_op.drop_column(col)
