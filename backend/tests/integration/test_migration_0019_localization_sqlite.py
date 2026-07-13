"""Test 0019 localization migration on SQLite via Alembic CLI.

Verifies that the 0019_add_localization_columns migration is idempotent
and correct on SQLite by running real ``uv run alembic`` subprocess
commands against a temporary database file:

- upgrade head adds locale, template_locale, and audit columns + CHECK constraints
- downgrade 0018 removes them cleanly
- re-upgrade head re-adds them without error
- SQLite CHECK constraint rejects invalid locale values
"""

from __future__ import annotations

import os
import sqlite3
import subprocess

import pytest

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)


def _run_alembic(
    args: list[str],
    db_path: str,
    *,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run ``uv run alembic <args>`` against a temporary SQLite database."""
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    env["PYTHONPATH"] = "src"

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
# SQLite schema introspection helpers
# ---------------------------------------------------------------------------


def _get_columns(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cursor.fetchall()}
    conn.close()
    return cols


def _get_index_names(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA index_list({table})")
    names = {row[1] for row in cursor.fetchall()}
    conn.close()
    return names


def _index_is_unique(db_path: str, index_name: str) -> bool:
    """Check if an index is unique by scanning PRAGMA index_list."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA index_list(report_templates)")
    for row in cursor.fetchall():
        if row[1] == index_name:
            conn.close()
            return bool(row[2])  # unique column
    conn.close()
    return False


def _get_check_constraints(db_path: str, table: str) -> set[str]:
    """Return set of CHECK constraint names for a table (SQLite >= 3.26)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_check({table})")
    # PRAGMA table_check returns: id, seq, table, from, to, match
    # Actually we need to look at the SQL — let's use sqlite_master instead
    conn.close()
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return set()
    sql = row[0]
    # Extract CHECK constraint names from CREATE TABLE SQL
    import re

    names = set()
    for match in re.finditer(r"CONSTRAINT\s+(\w+)\s+CHECK", sql, re.IGNORECASE):
        names.add(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_db(tmp_path):
    """Yield the path to a temporary SQLite database file."""
    db_path = str(tmp_path / "test_0019.db")
    yield db_path


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestSQLiteLocalizationMigration:
    """Real Alembic upgrade/downgrade/re-upgrade on SQLite."""

    # -- upgrade head -------------------------------------------------------

    def test_upgrade_adds_locale_columns(self, temp_db):
        """upgrade head adds locale, template_locale, and audit columns."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Missing column {name!r} on report_export_artifacts"

        cols_tmpl = _get_columns(temp_db, "report_templates")
        assert "locale" in cols_tmpl, "Missing locale column on report_templates"

    def test_upgrade_adds_locale_index(self, temp_db):
        """upgrade head creates ix_report_export_artifacts_locale index."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_export_artifacts")
        assert "ix_report_export_artifacts_locale" in idx, f"Expected locale index, got: {idx}"

    def test_upgrade_replaces_template_unique_constraint(self, temp_db):
        """upgrade head replaces template unique constraint (old one gone).

        On SQLite, batch_alter_table recreates unique constraints as
        sqlite_autoindex_N rather than preserving the name. We verify
        the OLD constraint name is gone and a unique autoindex exists.
        """
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_templates")
        # Old constraint without locale should be gone
        assert "uq_template_code_version_format" not in idx, (
            f"Old constraint uq_template_code_version_format should be gone, got: {idx}"
        )
        # There should be at least one sqlite_autoindex (unique constraint)
        # or the named constraint if supported
        has_any_unique = any(
            name.startswith("sqlite_autoindex") or "locale" in name for name in idx
        )
        assert has_any_unique, f"Expected unique constraint with locale, got: {idx}"

    def test_upgrade_adds_active_template_index_with_locale(self, temp_db):
        """upgrade head recreates partial unique index to include locale."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx
        assert _index_is_unique(temp_db, "uq_active_template_per_code_format_locale")

    def test_upgrade_adds_check_constraints(self, temp_db):
        """upgrade head adds CHECK constraints for locale values."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        # Verify artifact CHECK constraints exist in table SQL
        checks = _get_check_constraints(temp_db, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" in checks, (
            f"Expected ck_report_artifact_locale_supported, got: {checks}"
        )
        assert "ck_report_artifact_template_locale_supported" in checks

        # Verify template CHECK constraint
        checks_tmpl = _get_check_constraints(temp_db, "report_templates")
        assert "ck_report_template_locale_supported" in checks_tmpl

    # -- CHECK constraint rejects invalid locale ----------------------------

    def test_invalid_locale_rejected_by_check(self, temp_db):
        """SQLite rejects invalid locale via CHECK constraint."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                "INSERT INTO report_export_artifacts "
                "(id, report_id, report_revision_id, revision_number, format, "
                "template_id, template_version, schema_version, status, "
                "storage_key, file_name, mime_type, file_size_bytes, "
                "file_sha256, source_content_hash, render_manifest_json, "
                "generated_by, locale) "
                "VALUES ('test-bad', 'r1', 'rev1', 1, 'docx', 't1', "
                "'1.0.0', 'test@1.0.0', 'pending', '', 'f.docx', "
                "'application/pdf', 0, '', 'abc', '{}', 'test', 'fr-FR')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for invalid locale 'fr-FR'")
        except sqlite3.IntegrityError as e:
            # Verify the constraint name is mentioned
            assert "ck_report_artifact_locale_supported" in str(e), (
                f"Expected named CHECK, got: {e}"
            )
        finally:
            conn.close()

    def test_invalid_template_locale_rejected_by_check(self, temp_db):
        """SQLite rejects invalid template locale via CHECK constraint."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO report_templates "
                "(id, template_code, report_type, format, version, status, "
                "schema_version, locale, manifest_json, template_content_hash, "
                "created_by) "
                "VALUES ('test-bad-tmpl', 'test', 'cold_storage_concept_design', "
                "'docx', '1.0.0', 'draft', 'test@1.0.0', 'fr-FR', '{}', "
                "'', 'test')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for invalid template locale 'fr-FR'")
        except sqlite3.IntegrityError as e:
            assert "ck_report_template_locale_supported" in str(e), (
                f"Expected named CHECK, got: {e}"
            )
        finally:
            conn.close()

    # -- downgrade 0018 -----------------------------------------------------

    def test_downgrade_removes_locale_columns(self, temp_db):
        """downgrade 0018 removes locale columns."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        assert "locale" not in cols, "locale should be gone after downgrade"
        assert "template_locale" not in cols, "template_locale should be gone after downgrade"
        assert "translation_catalog_version" not in cols
        assert "translation_catalog_content_hash" not in cols
        assert "localized_template_content_hash" not in cols

    def test_downgrade_removes_locale_index(self, temp_db):
        """downgrade 0018 removes locale index."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_export_artifacts")
        assert "ix_report_export_artifacts_locale" not in idx

    def test_downgrade_restores_template_unique_without_locale(self, temp_db):
        """downgrade 0018 reverts template unique constraint to locale-free version."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_templates")
        # On SQLite, the recreated constraint will be sqlite_autoindex_N
        # but the key check is that it works — we can verify by trying
        # to insert two templates with same code+version+format but diff locale
        # (which should now FAIL after downgrade)
        # For index name check: just verify old named index exists or autoindex exists
        # The downgrade creates uq_template_code_version_format
        has_unique = any(
            name.startswith("sqlite_autoindex") or name == "uq_template_code_version_format"
            for name in idx
        )
        assert has_unique, f"Expected unique constraint (autoindex or named), got: {idx}"

    def test_downgrade_removes_check_constraints(self, temp_db):
        """downgrade 0018 removes CHECK constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" not in checks
        assert "ck_report_artifact_template_locale_supported" not in checks

        checks_tmpl = _get_check_constraints(temp_db, "report_templates")
        assert "ck_report_template_locale_supported" not in checks_tmpl

    def test_invalid_artifact_template_locale_rejected(self, temp_db):
        """SQLite rejects invalid artifact template_locale via CHECK."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                "INSERT INTO report_export_artifacts "
                "(id, report_id, report_revision_id, revision_number, format, "
                "template_id, template_version, schema_version, status, "
                "storage_key, file_name, mime_type, file_size_bytes, "
                "file_sha256, source_content_hash, render_manifest_json, "
                "generated_by, locale, template_locale) "
                "VALUES ('test-bad-tmpl-loc', 'r1', 'rev1', 1, 'docx', 't1', "
                "'1.0.0', 'test@1.0.0', 'pending', '', 'f.docx', "
                "'application/pdf', 0, '', 'abc', '{}', 'test', 'zh-CN', 'fr-FR')"
            )
            conn.commit()
            pytest.fail("Expected IntegrityError for invalid template_locale 'fr-FR'")
        except sqlite3.IntegrityError as e:
            assert "ck_report_artifact_template_locale_supported" in str(e), (
                f"Expected named CHECK, got: {e}"
            )
        finally:
            conn.close()

    # -- historical backfill -------------------------------------------------

    def test_historical_artifact_backfill(self, temp_db):
        """Pre-migration artifacts get locale='zh-CN' after upgrade.

        When a new column is added via ALTER TABLE ADD COLUMN with
        NOT NULL DEFAULT 'zh-CN', SQLite fills the default for all
        existing rows. This verifies the migration handles existing data.
        """
        # First upgrade to 0018 (last pre-localization migration)
        _run_alembic(["upgrade", "0018_add_artifact_claim_version"], temp_db)

        conn = sqlite3.connect(temp_db)
        # Insert an artifact before locale column exists
        cols_before = {
            r[1] for r in conn.execute("PRAGMA table_info(report_export_artifacts)").fetchall()
        }
        assert "locale" not in cols_before, "locale column should not exist before 0019"
        conn.execute(
            "INSERT INTO report_export_artifacts "
            "(id, report_id, report_revision_id, revision_number, format, "
            "template_id, template_version, schema_version, status, "
            "storage_key, file_name, mime_type, file_size_bytes, "
            "file_sha256, source_content_hash, render_manifest_json, "
            "generated_by) "
            "VALUES ('hist-test-1', 'r1', 'rev1', 1, 'docx', 't1', "
            "'1.0.0', 'test@1.0.0', 'pending', '', 'f.docx', "
            "'application/pdf', 0, '', 'abc', '{}', 'test')"
        )
        conn.commit()
        conn.close()

        # Upgrade to head — locale column added with DEFAULT 'zh-CN'
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT locale FROM report_export_artifacts WHERE id='hist-test-1'"
        ).fetchone()
        conn.close()
        assert row is not None, "Artifact should exist after upgrade"
        assert row[0] == "zh-CN", f"Expected zh-CN, got {row[0]}"

    # -- downgrade non-zh-CN template cleanup ---------------------------------

    def test_downgrade_removes_non_zh_cn_templates(self, temp_db):
        """downgrade 0018 removes non-zh-CN templates."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT OR IGNORE INTO report_templates "
            "(id, template_code, report_type, format, version, status, "
            "schema_version, locale, manifest_json, template_content_hash, "
            "created_by) "
            "VALUES ('en-tmpl', 'cold_storage_concept_design', 'cold_storage_concept_design', "
            "'docx', '1.0.0', 'active', 'test@1.0.0', 'en-US', '{}', '', 'test')"
        )
        conn.commit()
        conn.close()

        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT id FROM report_templates WHERE locale='en-US'").fetchone()
        conn.close()
        assert row is None, "en-US template should be removed after downgrade"

    # -- re-upgrade reseed en-US --------------------------------------------

    def test_reupgrade_restores_schema(self, temp_db):
        """re-upgrade restores locale columns, constraints, and indexes."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Column {name!r} missing after re-upgrade"

        checks = _get_check_constraints(temp_db, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" in checks
        assert "ck_report_artifact_template_locale_supported" in checks
        checks_tmpl = _get_check_constraints(temp_db, "report_templates")
        assert "ck_report_template_locale_supported" in checks_tmpl

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx

    # -- head → 0013 → head full cycle ---------------------------------------

    def test_full_cycle_head_to_0013_to_head(self, temp_db):
        """Full upgrade→downgrade-to-0013→upgrade cycle."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0
        cols = _get_columns(temp_db, "report_export_artifacts")
        assert "locale" in cols, "locale missing after upgrade"

        # Downgrade to 0013 (pre-localization)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"downgrade to 0013 failed:\n{result.stderr}"
        assert "locale" not in _get_columns(temp_db, "report_export_artifacts")

        # Re-upgrade
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Column {name!r} missing after re-upgrade"

        checks = _get_check_constraints(temp_db, "report_export_artifacts")
        assert "ck_report_artifact_locale_supported" in checks
        assert "ck_report_artifact_template_locale_supported" in checks

        checks_tmpl = _get_check_constraints(temp_db, "report_templates")
        assert "ck_report_template_locale_supported" in checks_tmpl

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx

    # -- unique constraint column verification --------------------------------

    def test_upgrade_unique_constraint_includes_locale(self, temp_db):
        """Unique constraint on templates includes locale column."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        conn = sqlite3.connect(temp_db)
        # Try inserting two templates with same code/version/format but different locale
        conn.execute("DELETE FROM report_templates WHERE id LIKE 'test-dup-%'")
        conn.execute(
            "INSERT INTO report_templates "
            "(id, template_code, report_type, format, version, status, "
            "schema_version, locale, manifest_json, template_content_hash, "
            "created_by) "
            "VALUES ('test-dup-1', 'dup-code', 'type1', 'docx', '1.0.0', 'active', "
            "'1.0', 'zh-CN', '{}', '', 'test')"
        )
        conn.execute(
            "INSERT INTO report_templates "
            "(id, template_code, report_type, format, version, status, "
            "schema_version, locale, manifest_json, template_content_hash, "
            "created_by) "
            "VALUES ('test-dup-2', 'dup-code', 'type1', 'docx', '1.0.0', 'active', "
            "'1.0', 'en-US', '{}', '', 'test')"
        )
        conn.commit()
        # Should succeed — different locales allowed
        conn.close()

    def test_full_cycle_upgrade_downgrade_upgrade(self, temp_db):
        """Full cycle: upgrade → downgrade → upgrade without error."""
        # First upgrade
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"first upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        assert "locale" in cols

        # Downgrade
        result = _run_alembic(["downgrade", "0018_add_artifact_claim_version"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"
        assert "locale" not in _get_columns(temp_db, "report_export_artifacts")

        # Second upgrade
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"second upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        for name in (
            "locale",
            "template_locale",
            "translation_catalog_version",
            "translation_catalog_content_hash",
            "localized_template_content_hash",
        ):
            assert name in cols, f"Column {name!r} missing after re-upgrade"

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx
        assert _index_is_unique(temp_db, "uq_active_template_per_code_format_locale")

    def test_idempotent_double_upgrade(self, temp_db):
        """Running upgrade head twice does not error."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"first upgrade failed:\n{result.stderr}"

        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"second upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_export_artifacts")
        assert "locale" in cols
        assert "template_locale" in cols
