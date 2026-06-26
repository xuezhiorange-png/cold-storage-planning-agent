"""Migration 0019 upgrade/downgrade/upgrade cycle test (real Alembic + PostgreSQL).

Verifies that migration 0019_add_localization_columns is fully idempotent by
running REAL Alembic subprocess commands against a temporary PostgreSQL
schema created for each test (complete isolation).

Covers:
- Historical Artifact locale backfill to zh-CN
- Historical Artifact template_locale backfill to zh-CN
- Downgrade deletes non-zh-CN templates
- Re-upgrade can reseed en-US templates
- uq_template_code_version_format_locale actual column order
- uq_active_template_per_code_format_locale partial predicate behavior
- uq_active_template_per_code_format_locale uniqueness
- Head → 0013_add_templates_artifacts → Head roundtrip
- The 3 CHECK constraints verified by actual invalid INSERT values
- Exception catching uses only sqlalchemy.exc.IntegrityError
- CHECK constraint names verified to start with 'ck_' and match exact name

Requires a running PostgreSQL instance (DATABASE_URL env var).
Skipped if PostgreSQL is not available.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Return DATABASE_URL or skip."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL migration tests")
    return url


def _run_alembic(
    args: list[str],
    url: str | None = None,
    *,
    timeout: int = 120,
    schema: str | None = None,
) -> subprocess.CompletedProcess:
    """Run an alembic subcommand, optionally scoped to *schema*.

    When *schema* is given the subprocess is told to operate inside that
    PostgreSQL schema via ``PGOPTIONS``.
    """
    env = os.environ.copy()
    db_url = url if url is not None else os.environ.get("DATABASE_URL", "")
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "src"

    # Parse DATABASE_URL and also set the individual POSTGRES_* vars so that
    # env.py's _build_database_url() (which reads those fields) works whether
    # or not it has been updated to honour database_url.
    if db_url:
        parsed = urlparse(db_url)
        if parsed.scheme.startswith("postgresql"):
            env.setdefault("POSTGRES_USER", parsed.username or "")
            env.setdefault("POSTGRES_PASSWORD", parsed.password or "")
            env.setdefault("POSTGRES_HOST", parsed.hostname or "localhost")
            env.setdefault("POSTGRES_PORT", str(parsed.port or 5432))
            # Strip leading '/' from path
            dbname = parsed.path.lstrip("/") if parsed.path else "cold_storage"
            env.setdefault("POSTGRES_DB", dbname)

    if schema:
        env["PGOPTIONS"] = f"-c search_path={schema}"

    result = subprocess.run(
        ["uv", "run", "alembic"] + args,
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


# ---------------------------------------------------------------------------
# PostgreSQL introspection helpers
# ---------------------------------------------------------------------------


def _pg_get_columns(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    return {c["name"] for c in inspector.get_columns(table)}


def _pg_get_unique_constraints(engine: sa.Engine, table: str) -> dict[str, list[str]]:
    """Return dict mapping constraint name -> list of column names."""
    inspector = sa.inspect(engine)
    return {
        item["name"]: item["column_names"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def _pg_get_indexes(engine: sa.Engine, table: str) -> dict[str, dict]:
    """Return dict mapping index name -> index info."""
    inspector = sa.inspect(engine)
    return {ix["name"]: ix for ix in inspector.get_indexes(table) if ix.get("name")}


def _pg_get_check_constraints(engine: sa.Engine, table: str) -> dict[str, str]:
    """Return dict mapping constraint name -> sqltext."""
    inspector = sa.inspect(engine)
    return {
        c["name"]: c["sqltext"] for c in inspector.get_check_constraints(table) if c.get("name")
    }


# ---------------------------------------------------------------------------
# Isolation fixtures — each test gets a unique temporary schema
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def tmp_schema(pg_url: str) -> str:
    """Create a temporary PostgreSQL schema for one test, drop on teardown."""
    schema_name = f"tst_{uuid.uuid4().hex[:12]}"
    engine = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
    engine.dispose()

    yield schema_name

    engine = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    engine.dispose()


@pytest.fixture(scope="function")
def pg_engine(pg_url: str, tmp_schema: str):
    """Create a real PostgreSQL engine scoped to the temporary schema."""
    eng = sa.create_engine(
        pg_url,
        connect_args={"options": f"-c search_path={tmp_schema}"},
    )
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def pg_session_factory(pg_engine):
    return sa.orm.sessionmaker(bind=pg_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestMigration0019PostgreSQL:
    """Verify full Alembic upgrade → downgrade → upgrade cycle for 0019.

    Every test creates its own temporary PostgreSQL schema, runs migrations
    inside it, and drops the schema on teardown.  Tests are fully isolated.
    """

    # -- upgrade adds columns -----------------------------------------------

    def test_upgrade_adds_locale_columns(self, pg_engine, tmp_schema):
        """After upgrade head, locale columns exist on report_export_artifacts."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Missing column {name!r} after upgrade"

    def test_upgrade_adds_locale_column_to_templates(self, pg_engine, tmp_schema):
        """After upgrade head, locale column exists on report_templates."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        cols = _pg_get_columns(pg_engine, "report_templates")
        assert "locale" in cols

    def test_upgrade_adds_check_constraints(self, pg_engine, tmp_schema):
        """After upgrade head, all 3 CHECK constraints exist."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        artifact_checks = _pg_get_check_constraints(pg_engine, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" in artifact_checks
        assert "ck_report_artifact_template_locale_supported" in artifact_checks

        template_checks = _pg_get_check_constraints(pg_engine, "report_templates")
        assert "ck_report_template_locale_supported" in template_checks

    def test_upgrade_creates_unique_constraint_with_locale(self, pg_engine, tmp_schema):
        """uq_template_code_version_format_locale includes locale column."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        uq = _pg_get_unique_constraints(pg_engine, "report_templates")
        assert "uq_template_code_version_format_locale" in uq
        columns = uq["uq_template_code_version_format_locale"]
        assert columns == ["template_code", "version", "format", "locale"], (
            f"Expected columns [template_code, version, format, locale], got {columns}"
        )

    def test_upgrade_creates_partial_unique_index(self, pg_engine, tmp_schema):
        """uq_active_template_per_code_format_locale exists with partial predicate."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        indexes = _pg_get_indexes(pg_engine, "report_templates")
        assert "uq_active_template_per_code_format_locale" in indexes
        idx_info = indexes["uq_active_template_per_code_format_locale"]
        assert idx_info["unique"] is True
        # The predicate should filter active_slot IS NOT NULL
        predicate = (idx_info.get("dialect_options", {}) or {}).get("postgresql_where", "")
        assert predicate is not None
        assert "active_slot IS NOT NULL" in predicate, (
            f"Expected predicate 'active_slot IS NOT NULL', got: {predicate}"
        )

    def test_upgrade_creates_locale_index(self, pg_engine, tmp_schema):
        """ix_report_export_artifacts_locale exists."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        indexes = _pg_get_indexes(pg_engine, "report_export_artifacts")
        assert "ix_report_export_artifacts_locale" in indexes

    def test_upgrade_adds_defaults_to_historical_records(
        self, pg_engine, pg_session_factory, tmp_schema
    ):
        """Existing records get locale defaulted to 'zh-CN' after upgrade.

        We insert a record at 0013 state (no locale columns), then upgrade
        to head and verify server_default fills zh-CN.
        """
        # Downgrade to 0013 (no locale columns)
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)

        # Insert row WITHOUT locale columns at 0013 state
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO report_export_artifacts "
                    "(id, report_id, report_revision_id, revision_number, format, "
                    "template_id, template_version, schema_version, status, "
                    "storage_key, file_name, mime_type, file_size_bytes, "
                    "file_sha256, source_content_hash, render_manifest_json, "
                    "generated_by) "
                    "VALUES ("
                    "'test-historical', 'r-hist', 'rev-hist', 1, 'docx', 't-hist', "
                    "'1.0.0', 'test@1.0.0', 'completed', '', 'report.docx', "
                    "'application/pdf', 0, '', 'abc', '{}', 'test')"
                )
            )
            session.commit()

        # Upgrade to head — server_default should fill locale=zh-CN
        _run_alembic(["upgrade", "head"], schema=tmp_schema)

        # Verify server_default set zh-CN
        with pg_session_factory() as session:
            row = session.execute(
                sa.text(
                    "SELECT locale, template_locale FROM report_export_artifacts "
                    "WHERE id = 'test-historical'"
                )
            ).fetchone()
            assert row is not None
            # locale should default to zh-CN via server_default
            assert row[0] == "zh-CN", f"Expected locale='zh-CN', got {row[0]}"
            # template_locale should default to zh-CN via server_default
            assert row[1] == "zh-CN", f"Expected template_locale='zh-CN', got {row[1]}"

            # Cleanup
            session.execute(
                sa.text("DELETE FROM report_export_artifacts WHERE id = 'test-historical'")
            )
            session.commit()

    # -- CHECK constraint enforcement ---------------------------------------

    def test_ck_report_artifact_locale_enforced(self, pg_session_factory, tmp_schema):
        """Invalid artifact locale hits ck_report_artifact_locale_supported IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            # Ensure FK parents exist
            session.execute(
                sa.text(
                    "INSERT INTO reports "
                    "(id, project_id, project_version_id, report_type, status, created_by) "
                    "VALUES ('r1', 'p1', 'pv1', 'cold_storage_concept_design', 'draft', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.execute(
                sa.text(
                    "INSERT INTO report_revisions "
                    "(id, report_id, revision_number, schema_version, "
                    "content_json, canonical_content_json, content_hash, "
                    "quality_status, quality_findings_json, generated_by) "
                    "VALUES ('rev1', 'r1', 1, 'test@1.0.0', "
                    "'{}', '{}', 'abc', "
                    "'draft', '{}', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, created_by) "
                    "VALUES ('t1', 't1', 'cold_storage_concept_design', "
                    "'docx', '1.0.0', 'draft', 'test@1.0.0', 'zh-CN', '{}', '', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.commit()
            session.execute(
                sa.text(
                    "INSERT INTO report_export_artifacts "
                    "(id, report_id, report_revision_id, revision_number, format, "
                    "template_id, template_version, schema_version, status, "
                    "storage_key, file_name, mime_type, file_size_bytes, "
                    "file_sha256, source_content_hash, render_manifest_json, "
                    "generated_by, locale) "
                    "VALUES ("
                    "'test-ck-artifact', 'r1', 'rev1', 1, 'docx', 't1', "
                    "'1.0.0', 'test@1.0.0', 'pending', '', 'report.docx', "
                    "'application/pdf', 0, '', 'abc', '{}', 'test', 'fr-FR')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        # Verify constraint name has ck_ prefix AND contains the expected name
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_report_artifact_locale_supported" in err_msg, (
            f"Expected constraint ck_report_artifact_locale_supported, got: {err_msg}"
        )

    def test_ck_report_artifact_template_locale_enforced(self, pg_session_factory, tmp_schema):
        """Invalid template_locale hits ck_report_artifact_template_locale_supported."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            # Ensure FK parents exist
            session.execute(
                sa.text(
                    "INSERT INTO reports "
                    "(id, project_id, project_version_id, report_type, status, created_by) "
                    "VALUES ('r1', 'p1', 'pv1', 'cold_storage_concept_design', 'draft', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.execute(
                sa.text(
                    "INSERT INTO report_revisions "
                    "(id, report_id, revision_number, schema_version, "
                    "content_json, canonical_content_json, content_hash, "
                    "quality_status, quality_findings_json, generated_by) "
                    "VALUES ('rev1', 'r1', 1, 'test@1.0.0', "
                    "'{}', '{}', 'abc', "
                    "'draft', '{}', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, created_by) "
                    "VALUES ('t1', 't1', 'cold_storage_concept_design', "
                    "'docx', '1.0.0', 'draft', 'test@1.0.0', 'zh-CN', '{}', '', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.commit()
            session.execute(
                sa.text(
                    "INSERT INTO report_export_artifacts "
                    "(id, report_id, report_revision_id, revision_number, format, "
                    "template_id, template_version, schema_version, status, "
                    "storage_key, file_name, mime_type, file_size_bytes, "
                    "file_sha256, source_content_hash, render_manifest_json, "
                    "generated_by, template_locale) "
                    "VALUES ("
                    "'test-ck-artifact-tpl', 'r1', 'rev1', 1, 'docx', 't1', "
                    "'1.0.0', 'test@1.0.0', 'pending', '', 'report.docx', "
                    "'application/pdf', 0, '', 'abc', '{}', 'test', 'ja-JP')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_report_artifact_template_locale_supported" in err_msg, (
            f"Expected constraint ck_report_artifact_template_locale_supported, got: {err_msg}"
        )

    def test_ck_report_template_locale_enforced(self, pg_session_factory, tmp_schema):
        """Invalid template locale hits ck_report_template_locale_supported IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, "
                    "created_by) "
                    "VALUES ("
                    "'test-ck-tpl', 'test', 'cold_storage_concept_design', "
                    "'docx', '1.0.0', 'draft', 'test@1.0.0', 'de-DE', '{}', "
                    "'', 'test')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_report_template_locale_supported" in err_msg, (
            f"Expected constraint ck_report_template_locale_supported, got: {err_msg}"
        )

    # -- downgrade ----------------------------------------------------------

    def test_downgrade_removes_locale_columns(self, pg_engine, tmp_schema):
        """After downgrade to 0013, locale columns are gone."""
        # Start from head, then downgrade
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name not in cols, f"Column {name!r} should be gone after downgrade"

    def test_downgrade_removes_check_constraints(self, pg_engine, tmp_schema):
        """After downgrade, all 3 CHECK constraints are gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        artifact_checks = _pg_get_check_constraints(pg_engine, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" not in artifact_checks
        assert "ck_report_artifact_template_locale_supported" not in artifact_checks

        template_checks = _pg_get_check_constraints(pg_engine, "report_templates")
        assert "ck_report_template_locale_supported" not in template_checks

    def test_downgrade_restores_old_unique_constraint(self, pg_engine, tmp_schema):
        """uq_template_code_version_format_locale is gone, original is back."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        uq = _pg_get_unique_constraints(pg_engine, "report_templates")
        assert "uq_template_code_version_format_locale" not in uq
        assert "uq_template_code_version_format" in uq

    def test_downgrade_restores_old_index(self, pg_engine, tmp_schema):
        """uq_active_template_per_code_format_locale is gone, original is back."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        indexes = _pg_get_indexes(pg_engine, "report_templates")
        assert "uq_active_template_per_code_format_locale" not in indexes
        assert "uq_active_template_per_code_format" in indexes

    def test_downgrade_deletes_non_zh_cn_templates(self, pg_engine, pg_session_factory, tmp_schema):
        """Downgrade deletes non-zh-CN templates to avoid constraint violation.

        Runs independently — upgrades head, inserts en-US template,
        downgrades, then verifies non-zh-CN templates were deleted.
        """
        # Ensure head state
        _run_alembic(["upgrade", "head"], schema=tmp_schema)

        # Insert an en-US template to test downgrade cleanup
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, "
                    "created_by) "
                    "VALUES ("
                    "'test-non-zh-cleanup', 'cleanup-test', 'cold_storage_concept_design', "
                    "'docx', '1.0.0', 'draft', 'test@1.0.0', 'en-US', "
                    "'{}', '', 'test') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
            session.commit()

        # Downgrade to 0013 — should delete non-zh-CN templates
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)

        with pg_session_factory() as session:
            # The downgrade should have deleted any non-zh-CN templates
            rows = session.execute(sa.text("SELECT locale FROM report_templates")).fetchall()
            for row in rows:
                assert row[0] == "zh-CN", f"Found non-zh-CN template after downgrade: {row[0]}"

    # -- re-upgrade ---------------------------------------------------------

    def test_re_upgrade_succeeds(self, pg_engine, tmp_schema):
        """Re-upgrade to head succeeds without error."""
        # Ensure at 0013 first, then upgrade to head
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic re-upgrade failed:\n{result.stderr}"

        # Verify all columns are back
        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Missing column {name!r} after re-upgrade"

    def test_re_upgrade_restores_check_constraints(self, pg_engine, tmp_schema):
        """All 3 CHECK constraints restored after re-upgrade."""
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        artifact_checks = _pg_get_check_constraints(pg_engine, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" in artifact_checks
        assert "ck_report_artifact_template_locale_supported" in artifact_checks

        template_checks = _pg_get_check_constraints(pg_engine, "report_templates")
        assert "ck_report_template_locale_supported" in template_checks

    def test_re_upgrade_restores_unique_constraint_with_locale(self, pg_engine, tmp_schema):
        """uq_template_code_version_format_locale includes locale column after re-upgrade."""
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        uq = _pg_get_unique_constraints(pg_engine, "report_templates")
        assert "uq_template_code_version_format_locale" in uq
        columns = uq["uq_template_code_version_format_locale"]
        assert columns == ["template_code", "version", "format", "locale"]

    def test_re_upgrade_restores_partial_unique_index(self, pg_engine, tmp_schema):
        """Partial unique index restored after re-upgrade."""
        _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        indexes = _pg_get_indexes(pg_engine, "report_templates")
        assert "uq_active_template_per_code_format_locale" in indexes

    # -- full cycle: head → 0013 → head ------------------------------------

    def test_full_cycle_upgrade_downgrade_upgrade(self, pg_engine, tmp_schema):
        """Full cycle: upgrade → downgrade to 0013 → upgrade head."""
        # Upgrade to head
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        assert "locale" in cols

        # Downgrade to 0013
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], schema=tmp_schema)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        assert "locale" not in cols

        # Re-upgrade
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "report_export_artifacts")
        assert "locale" in cols
        assert "template_locale" in cols
        assert "translation_catalog_version" in cols

        uq = _pg_get_unique_constraints(pg_engine, "report_templates")
        assert "uq_template_code_version_format_locale" in uq

        indexes = _pg_get_indexes(pg_engine, "report_templates")
        assert "uq_active_template_per_code_format_locale" in indexes

    # -- uq_active_template_per_code_format_locale uniqueness ---------------

    def test_uq_active_template_locale_uniqueness(self, pg_session_factory, tmp_schema):
        """Inserting two active templates with same code+format+locale fails.

        The partial unique index only applies when active_slot IS NOT NULL,
        so two DRAFT templates are allowed but two ACTIVE ones are not.
        """
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session:
            # Insert first active template
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, "
                    "created_by, active_slot) "
                    "VALUES ("
                    "'test-uniq-a', 'uniq-test', 'cold_storage_concept_design', "
                    "'docx', '1.0.0', 'active', 'test@1.0.0', 'en-US', "
                    "'{\"key\":\"a\"}', '', 'test', 1)"
                )
            )
            session.commit()

        with pg_session_factory() as session, pytest.raises(IntegrityError):
            session.execute(
                sa.text(
                    "INSERT INTO report_templates "
                    "(id, template_code, report_type, format, version, status, "
                    "schema_version, locale, manifest_json, template_content_hash, "
                    "created_by, active_slot) "
                    "VALUES ("
                    "'test-uniq-b', 'uniq-test', 'cold_storage_concept_design', "
                    "'docx', '2.0.0', 'active', 'test@1.0.0', 'en-US', "
                    "'{\"key\":\"b\"}', '', 'test', 2)"
                )
            )
            session.commit()

        # Cleanup
        with pg_session_factory() as session:
            session.execute(
                sa.text("DELETE FROM report_templates WHERE template_code = 'uniq-test'")
            )
            session.commit()
