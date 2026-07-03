"""0033: extend outbox envelope and add FAILED state.

Revision ID: 0033_extend_outbox_envelope
Revises: 451311827adf
Create Date: 2026-07-03

Adds to ``orchestration_audit_outbox``:
- event_schema_version, actor, correlation_id, occurred_at, payload_hash
- claim_token, last_error_class, last_error_at, failed_at
- Updates ck_outbox_status_nullity to include FAILED state
- Adds immutability trigger on outbox after initial insert
- Adds trigger enforcing AuditEvent existence for PUBLISHED outbox rows
"""

from collections.abc import Sequence

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
  IF NEW.event_identity != OLD.event_identity
     OR NEW.event_type != OLD.event_type
     OR NEW.event_schema_version != OLD.event_schema_version
     OR NEW.aggregate_type != OLD.aggregate_type
     OR NEW.aggregate_id != OLD.aggregate_id
     OR NEW.actor != OLD.actor
     OR NEW.correlation_id != OLD.correlation_id
     OR NEW.occurred_at != OLD.occurred_at
     OR NEW.payload::text != OLD.payload::text
     OR NEW.payload_hash != OLD.payload_hash THEN
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

    # 3. Immutable envelope trigger
    op.execute(_IMMU_ENVELOPE_FN)
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope ON orchestration_audit_outbox")
    op.execute(
        "CREATE TRIGGER trg_immutable_outbox_envelope "
        "BEFORE UPDATE ON orchestration_audit_outbox "
        "FOR EACH ROW EXECUTE FUNCTION trg_immutable_outbox_envelope()"
    )

    # 4. Published requires AuditEvent
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


def _pg_downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_outbox_published_requires_auditevent "
        "ON orchestration_audit_outbox"
    )
    op.execute("DROP FUNCTION IF EXISTS trg_outbox_published_requires_auditevent()")
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope ON orchestration_audit_outbox")
    op.execute("DROP FUNCTION IF EXISTS trg_immutable_outbox_envelope()")

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


def _sqlite_downgrade() -> None:
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
            "payload_hash",
            "occurred_at",
            "correlation_id",
            "actor",
            "event_schema_version",
        ]:
            batch_op.drop_column(col)
