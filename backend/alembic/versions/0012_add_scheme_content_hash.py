"""0012_add_scheme_content_hash

Adds content_hash column to scheme_runs for persisted provenance.
Previously the hash was only computed at query time, which could not
detect database-level tampering of scheme run data.

Revision ID: 0012_add_scheme_content_hash
Revises: 0011_fix_supersedes_fk
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_add_scheme_content_hash"
down_revision = "0011_fix_supersedes_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheme_runs",
        sa.Column("content_hash", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheme_runs", "content_hash")
