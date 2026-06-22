"""0011_fix_supersedes_fk

Revision ID: 0011_fix_supersedes_fk
Revises: 0010_add_idempotency_record
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_fix_supersedes_fk"
down_revision = "0010_add_idempotency_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        conn = op.get_bind()
        result = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'report_revisions'::regclass "
                "AND contype = 'f' "
                "AND pg_get_constraintdef(oid) LIKE '%supersedes_revision_id%'"
            )
        )
        row = result.fetchone()
        if row is not None:
            old_name = row[0]
            op.drop_constraint(old_name, "report_revisions", type_="foreignkey")
            op.create_foreign_key(
                "fk_report_revisions_supersedes_revision_id_report_revisions",
                "report_revisions",
                "report_revisions",
                ["supersedes_revision_id"],
                ["id"],
            )
    else:
        # SQLite: recreate table with correct FK via backup-copy pattern.
        # SQLite has no ALTER TABLE for FK changes.
        conn = op.get_bind()
        conn.execute(sa.text("PRAGMA foreign_keys = OFF"))
        # Create new table with correct FK
        conn.execute(
            sa.text(
                "CREATE TABLE report_revisions_new ("
                "id VARCHAR(36) NOT NULL, "
                "report_id VARCHAR(36) NOT NULL, "
                "revision_number INTEGER NOT NULL, "
                "schema_version VARCHAR(64) NOT NULL, "
                "content_json JSON NOT NULL, "
                "canonical_content_json JSON NOT NULL, "
                "content_hash VARCHAR(64) NOT NULL, "
                "quality_status VARCHAR(32) NOT NULL, "
                "quality_findings_json JSON NOT NULL, "
                "generated_by VARCHAR(64) NOT NULL, "
                "generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                "supersedes_revision_id VARCHAR(36), "
                "PRIMARY KEY (id), "
                "CONSTRAINT uq_report_revisions_report_revision "
                "UNIQUE (report_id, revision_number), "
                "FOREIGN KEY(report_id) REFERENCES reports(id), "
                "FOREIGN KEY(supersedes_revision_id) "
                "REFERENCES report_revisions(id)"
                ")"
            )
        )
        # Copy data
        conn.execute(sa.text("INSERT INTO report_revisions_new SELECT * FROM report_revisions"))
        # Swap tables
        conn.execute(sa.text("DROP TABLE report_revisions"))
        conn.execute(sa.text("ALTER TABLE report_revisions_new RENAME TO report_revisions"))
        # Recreate indexes
        conn.execute(
            sa.text("CREATE INDEX ix_report_revisions_report_id ON report_revisions (report_id)")
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_report_revisions_content_hash ON report_revisions (content_hash)"
            )
        )
        conn.execute(sa.text("PRAGMA foreign_keys = ON"))


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_constraint(
            "fk_report_revisions_supersedes_revision_id_report_revisions",
            "report_revisions",
            type_="foreignkey",
        )
        op.create_foreign_key(
            "fk_report_revisions_supersedes_revision_id_reports",
            "report_revisions",
            "reports",
            ["supersedes_revision_id"],
            ["id"],
        )
    else:
        conn = op.get_bind()
        conn.execute(sa.text("PRAGMA foreign_keys = OFF"))
        conn.execute(
            sa.text(
                "CREATE TABLE report_revisions_old ("
                "id VARCHAR(36) NOT NULL, "
                "report_id VARCHAR(36) NOT NULL, "
                "revision_number INTEGER NOT NULL, "
                "schema_version VARCHAR(64) NOT NULL, "
                "content_json JSON NOT NULL, "
                "canonical_content_json JSON NOT NULL, "
                "content_hash VARCHAR(64) NOT NULL, "
                "quality_status VARCHAR(32) NOT NULL, "
                "quality_findings_json JSON NOT NULL, "
                "generated_by VARCHAR(64) NOT NULL, "
                "generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                "supersedes_revision_id VARCHAR(36), "
                "PRIMARY KEY (id), "
                "CONSTRAINT uq_report_revisions_report_revision "
                "UNIQUE (report_id, revision_number), "
                "FOREIGN KEY(report_id) REFERENCES reports(id), "
                "FOREIGN KEY(supersedes_revision_id) REFERENCES reports(id)"
                ")"
            )
        )
        conn.execute(sa.text("INSERT INTO report_revisions_old SELECT * FROM report_revisions"))
        conn.execute(sa.text("DROP TABLE report_revisions"))
        conn.execute(sa.text("ALTER TABLE report_revisions_old RENAME TO report_revisions"))
        conn.execute(
            sa.text("CREATE INDEX ix_report_revisions_report_id ON report_revisions (report_id)")
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_report_revisions_content_hash ON report_revisions (content_hash)"
            )
        )
        conn.execute(sa.text("PRAGMA foreign_keys = ON"))
