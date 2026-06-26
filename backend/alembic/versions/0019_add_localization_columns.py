"""0019_add_localization_columns

Add locale, translation_catalog_version, and localized_template_content_hash
to report_export_artifacts for i18n/l10n support.

Revision ID: 0019_add_localization_columns
Revises: 0018_add_artifact_claim_version
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_add_localization_columns"
down_revision = "0018_add_artifact_claim_version"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _existing_unique_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item["name"] for item in inspector.get_unique_constraints(table) if item.get("name")}


def _existing_check_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item["name"] for item in inspector.get_check_constraints(table) if item.get("name")}


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    table = "report_export_artifacts"
    cols = _existing_columns(table)

    if "locale" not in cols:
        op.add_column(
            table,
            sa.Column(
                "locale",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'zh-CN'"),
            ),
        )

    if "translation_catalog_version" not in cols:
        op.add_column(
            table,
            sa.Column(
                "translation_catalog_version",
                sa.String(32),
                nullable=False,
                server_default=sa.text("'1.0.0'"),
            ),
        )

    if "localized_template_content_hash" not in cols:
        op.add_column(
            table,
            sa.Column(
                "localized_template_content_hash",
                sa.String(64),
                nullable=False,
                server_default=sa.text("''"),
            ),
        )

    if "template_locale" not in cols:
        op.add_column(
            table,
            sa.Column(
                "template_locale",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'zh-CN'"),
            ),
        )

    if "translation_catalog_content_hash" not in cols:
        op.add_column(
            table,
            sa.Column(
                "translation_catalog_content_hash",
                sa.String(64),
                nullable=False,
                server_default=sa.text("''"),
            ),
        )

    # Recreate template unique constraint to include locale.
    # SQLite: use batch_alter_table (copy-and-move) for constraint changes.
    # PostgreSQL: direct drop + create.
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    existing_constraints = _existing_unique_constraints("report_templates")

    if is_sqlite:
        # SQLite batch mode: recreate table with new constraint
        with op.batch_alter_table("report_templates") as batch_op:
            if "uq_template_code_version_format" in existing_constraints:
                batch_op.drop_constraint(
                    "uq_template_code_version_format",
                    type_="unique",
                )
            batch_op.create_unique_constraint(
                "uq_template_code_version_format_locale",
                ["template_code", "version", "format", "locale"],
            )
    else:
        if "uq_template_code_version_format" in existing_constraints:
            op.drop_constraint(
                "uq_template_code_version_format",
                "report_templates",
                type_="unique",
            )
        if "uq_template_code_version_format_locale" not in existing_constraints:
            op.create_unique_constraint(
                "uq_template_code_version_format_locale",
                "report_templates",
                ["template_code", "version", "format", "locale"],
            )

    # Recreate active template index to include locale
    existing_indexes = _existing_indexes("report_templates")

    if "uq_active_template_per_code_format" in existing_indexes:
        op.drop_index(
            "uq_active_template_per_code_format",
            table_name="report_templates",
        )

    if "uq_active_template_per_code_format_locale" not in existing_indexes:
        op.create_index(
            "uq_active_template_per_code_format_locale",
            "report_templates",
            ["template_code", "format", "locale"],
            unique=True,
            sqlite_where=sa.text("active_slot IS NOT NULL"),
            postgresql_where=sa.text("active_slot IS NOT NULL"),
        )

    # Add index on locale if it does not already exist.
    existing_indexes = _existing_indexes(table)

    if "ix_report_export_artifacts_locale" not in existing_indexes:
        op.create_index(
            "ix_report_export_artifacts_locale",
            table,
            ["locale"],
        )

    # Add CHECK constraints for locale values
    # PostgreSQL: use op.create_check_constraint()
    if not is_sqlite:
        # PostgreSQL: add CHECK constraints
        op.create_check_constraint(
            "ck_report_artifact_locale_supported",
            "report_export_artifacts",
            sa.text("locale IN ('zh-CN', 'en-US')"),
        )
        op.create_check_constraint(
            "ck_report_artifact_template_locale_supported",
            "report_export_artifacts",
            sa.text("template_locale IN ('zh-CN', 'en-US')"),
        )
        op.create_check_constraint(
            "ck_report_template_locale_supported",
            "report_templates",
            sa.text("locale IN ('zh-CN', 'en-US')"),
        )
    else:
        # SQLite: add CHECK constraints via batch_alter_table (rebuilds table)
        with op.batch_alter_table("report_export_artifacts") as batch_op:
            batch_op.create_check_constraint(
                "ck_report_artifact_locale_supported",
                sa.text("locale IN ('zh-CN', 'en-US')"),
            )
            batch_op.create_check_constraint(
                "ck_report_artifact_template_locale_supported",
                sa.text("template_locale IN ('zh-CN', 'en-US')"),
            )
        with op.batch_alter_table("report_templates") as batch_op:
            batch_op.create_check_constraint(
                "ck_report_template_locale_supported",
                sa.text("locale IN ('zh-CN', 'en-US')"),
            )


def downgrade() -> None:
    table = "report_export_artifacts"
    cols = _existing_columns(table)

    is_sqlite = op.get_bind().dialect.name == "sqlite"

    # Remove index first.
    existing_indexes = _existing_indexes(table)

    if "ix_report_export_artifacts_locale" in existing_indexes:
        op.drop_index(
            "ix_report_export_artifacts_locale",
            table_name=table,
        )

    # Drop CHECK constraints before dropping columns
    if not is_sqlite:
        existing_checks = _existing_check_constraints("report_export_artifacts")
        for name in [
            "ck_report_artifact_locale_supported",
            "ck_report_artifact_template_locale_supported",
        ]:
            if name in existing_checks:
                op.drop_constraint(name, "report_export_artifacts", type_="check")

        existing_template_checks = _existing_check_constraints("report_templates")
        if "ck_report_template_locale_supported" in existing_template_checks:
            op.drop_constraint(
                "ck_report_template_locale_supported",
                "report_templates",
                type_="check",
            )
    else:
        # SQLite: remove CHECK constraints via batch_alter_table (rebuilds table)
        existing_checks = _existing_check_constraints("report_export_artifacts")
        with op.batch_alter_table("report_export_artifacts") as batch_op:
            for name in [
                "ck_report_artifact_locale_supported",
                "ck_report_artifact_template_locale_supported",
            ]:
                if name in existing_checks:
                    batch_op.drop_constraint(name, type_="check")

        existing_template_checks = _existing_check_constraints("report_templates")
        with op.batch_alter_table("report_templates") as batch_op:
            if "ck_report_template_locale_supported" in existing_template_checks:
                batch_op.drop_constraint("ck_report_template_locale_supported", type_="check")

    if "localized_template_content_hash" in cols:
        op.drop_column(table, "localized_template_content_hash")

    if "translation_catalog_content_hash" in cols:
        op.drop_column(table, "translation_catalog_content_hash")

    if "template_locale" in cols:
        op.drop_column(table, "template_locale")

    if "translation_catalog_version" in cols:
        op.drop_column(table, "translation_catalog_version")

    if "locale" in cols:
        op.drop_column(table, "locale")

    # Recreate template constraints (revert to locale-free).
    # Strategy: before reverting the unique constraint, delete any non-zh-CN
    # templates that would violate the locale-free uniqueness constraint
    # (same code+version+format but different locales).  This is a safe
    # data-loss strategy because en-US templates are only created by
    # seed_default_templates and can be re-seeded on upgrade.

    existing_constraints = _existing_unique_constraints("report_templates")

    # Delete non-zh-CN templates to avoid unique constraint violation
    op.execute(sa.text("DELETE FROM report_templates WHERE locale != 'zh-CN'"))

    if is_sqlite:
        with op.batch_alter_table("report_templates") as batch_op:
            if "uq_template_code_version_format_locale" in existing_constraints:
                batch_op.drop_constraint(
                    "uq_template_code_version_format_locale",
                    type_="unique",
                )
            batch_op.create_unique_constraint(
                "uq_template_code_version_format",
                ["template_code", "version", "format"],
            )
    else:
        if "uq_template_code_version_format_locale" in existing_constraints:
            op.drop_constraint(
                "uq_template_code_version_format_locale",
                "report_templates",
                type_="unique",
            )
        if "uq_template_code_version_format" not in existing_constraints:
            op.create_unique_constraint(
                "uq_template_code_version_format",
                "report_templates",
                ["template_code", "version", "format"],
            )

    existing_indexes = _existing_indexes("report_templates")

    if "uq_active_template_per_code_format_locale" in existing_indexes:
        op.drop_index(
            "uq_active_template_per_code_format_locale",
            table_name="report_templates",
        )

    if "uq_active_template_per_code_format" not in existing_indexes:
        op.create_index(
            "uq_active_template_per_code_format",
            "report_templates",
            ["template_code", "format"],
            unique=True,
            sqlite_where=sa.text("active_slot IS NOT NULL"),
            postgresql_where=sa.text("active_slot IS NOT NULL"),
        )
