"""add coefficient registry tables

Revision ID: 0004_add_coefficient_registry
Revises: 0003_add_version_metadata
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_coefficient_registry"
down_revision: str | None = "0003_add_version_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valid revision statuses for check constraint
_VALID_REVISION_STATUSES = "'draft', 'unverified', 'reviewed', 'approved', 'withdrawn'"
_VALID_SOURCE_TYPES = (
    "'standard', 'book', 'manufacturer', 'enterprise_standard', "
    "'historical_project', 'engineering_judgement', 'demo', 'unknown'"
)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # -----------------------------------------------------------------
    # coefficient_definitions
    # -----------------------------------------------------------------
    op.create_table(
        "coefficient_definitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=200), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("canonical_unit", sa.String(length=50), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="decimal"),
        sa.Column("scope_type", sa.String(length=50), nullable=False, server_default="global"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1") if dialect == "sqlite" else sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # -----------------------------------------------------------------
    # coefficient_revisions
    # -----------------------------------------------------------------
    op.create_table(
        "coefficient_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "coefficient_definition_id",
            sa.String(length=36),
            sa.ForeignKey("coefficient_definitions.id"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("value_decimal", sa.String(length=50), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="demo"),
        sa.Column("source_title", sa.String(length=300), nullable=True),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("source_page", sa.String(length=100), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applicable_product_type", sa.String(length=100), nullable=True),
        sa.Column("applicable_zone_type", sa.String(length=100), nullable=True),
        sa.Column("applicable_process_type", sa.String(length=100), nullable=True),
        sa.Column("supersedes_revision_id", sa.String(length=36), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False, server_default="system"),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "coefficient_definition_id",
            "revision_number",
            name="uq_coefficient_def_revision",
        ),
    )

    # -----------------------------------------------------------------
    # Check constraints (dialect-specific)
    # -----------------------------------------------------------------
    if dialect == "sqlite":
        # SQLite: check constraints via batch_alter_table
        with op.batch_alter_table("coefficient_revisions") as batch_op:
            batch_op.create_check_constraint(
                "ck_coefficient_revision_status",
                sa.text(f"status IN ({_VALID_REVISION_STATUSES})"),
            )
            batch_op.create_check_constraint(
                "ck_coefficient_revision_source_type",
                sa.text(f"source_type IN ({_VALID_SOURCE_TYPES})"),
            )
    else:
        op.create_check_constraint(
            "ck_coefficient_revision_status",
            "coefficient_revisions",
            sa.text(f"status IN ({_VALID_REVISION_STATUSES})"),
        )
        op.create_check_constraint(
            "ck_coefficient_revision_source_type",
            "coefficient_revisions",
            sa.text(f"source_type IN ({_VALID_SOURCE_TYPES})"),
        )

    # -----------------------------------------------------------------
    # Indexes for common queries
    # -----------------------------------------------------------------
    op.create_index(
        "ix_coefficient_definitions_code",
        "coefficient_definitions",
        ["code"],
    )
    op.create_index(
        "ix_coefficient_definitions_category",
        "coefficient_definitions",
        ["category"],
    )
    op.create_index(
        "ix_coefficient_revisions_definition_id",
        "coefficient_revisions",
        ["coefficient_definition_id"],
    )
    op.create_index(
        "ix_coefficient_revisions_status",
        "coefficient_revisions",
        ["status"],
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    # Drop indexes
    op.drop_index("ix_coefficient_revisions_status", table_name="coefficient_revisions")
    op.drop_index("ix_coefficient_revisions_definition_id", table_name="coefficient_revisions")
    op.drop_index("ix_coefficient_definitions_category", table_name="coefficient_definitions")
    op.drop_index("ix_coefficient_definitions_code", table_name="coefficient_definitions")

    # Drop check constraints
    if dialect == "sqlite":
        with op.batch_alter_table("coefficient_revisions") as batch_op:
            batch_op.drop_constraint("ck_coefficient_revision_source_type", type_="check")
            batch_op.drop_constraint("ck_coefficient_revision_status", type_="check")
    else:
        op.drop_constraint(
            "ck_coefficient_revision_source_type",
            "coefficient_revisions",
            type_="check",
        )
        op.drop_constraint(
            "ck_coefficient_revision_status",
            "coefficient_revisions",
            type_="check",
        )

    # Drop tables (order: revisions first due to FK)
    op.drop_table("coefficient_revisions")
    op.drop_table("coefficient_definitions")
