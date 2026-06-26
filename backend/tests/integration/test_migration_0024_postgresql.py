"""Migration 0024 upgrade/downgrade/upgrade cycle test (real Alembic + PostgreSQL).

Verifies that migration 0024_receipt_status_deleted_at is fully
idempotent by running REAL Alembic subprocess commands against a temporary
PostgreSQL schema created for each test.

Covers:
- ck_deletion_receipt_status allows 'delete_failed' after upgrade
- deleted_at is nullable and has no default after upgrade
- Downgrade restores original CHECK and NOT NULL + default
- Full roundtrip: upgrade head -> downgrade 0023 -> upgrade head

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
    """Run an alembic subcommand, optionally scoped to *schema*."""
    env = os.environ.copy()
    db_url = url if url is not None else os.environ.get("DATABASE_URL", "")
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "src"

    # Parse DATABASE_URL and set POSTGRES_* vars for env.py compatibility
    if db_url:
        parsed = urlparse(db_url)
        if parsed.scheme.startswith("postgresql"):
            env.setdefault("POSTGRES_USER", parsed.username or "")
            env.setdefault("POSTGRES_PASSWORD", parsed.password or "")
            env.setdefault("POSTGRES_HOST", parsed.hostname or "localhost")
            env.setdefault("POSTGRES_PORT", str(parsed.port or 5432))
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


def _pg_get_column_info(engine: sa.Engine, table: str, column: str) -> dict | None:
    """Return column info dict with keys 'nullable' and 'default'."""
    inspector = sa.inspect(engine)
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return {"nullable": col.get("nullable", True), "default": col.get("default")}
    return None


def _pg_get_unique_constraints(engine: sa.Engine, table: str) -> dict[str, list[str]]:
    """Return dict mapping constraint name -> list of column names."""
    inspector = sa.inspect(engine)
    return {
        item["name"]: item["column_names"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


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
# Shared expected schema — HEAD (0024)
# ---------------------------------------------------------------------------

ALL_DELETION_RECEIPTS_COLUMNS = {
    "storage_key",
    "stale_claim_token",
    "stale_claim_version",
    "reclaim_token",
    "reclaim_version",
    "deleted_at",
    "deletion_hash",
    "status",
}

DELETION_RECEIPTS_CHECK_CONSTRAINTS = {
    "ck_deletion_receipt_stale_version",
    "ck_deletion_receipt_reclaim_version",
    "ck_deletion_receipt_hash",
    "ck_deletion_receipt_status",
}


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestDeletionReceiptMigrationPostgreSQL0024:
    """Verify full Alembic upgrade -> downgrade -> upgrade cycle for 0024.

    Every test creates its own temporary PostgreSQL schema, runs migrations
    inside it, and drops the schema on teardown.  Tests are fully isolated.
    """

    # -- upgrade head (0024) -------------------------------------------------

    def test_upgrade_keeps_deletion_receipts_table(self, pg_engine, tmp_schema):
        """After upgrade head, deletion_receipts table still has all columns."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )

    def test_upgrade_updates_status_check_to_include_delete_failed(self, pg_engine, tmp_schema):
        """After upgrade head, ck_deletion_receipt_status allows delete_failed."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_check_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_check_sql, (
            f"ck_deletion_receipt_status should include 'delete_failed', got: {status_check_sql}"
        )

    def test_upgrade_makes_deleted_at_nullable_and_removes_default(self, pg_engine, tmp_schema):
        """After upgrade head, deleted_at is nullable with no default."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None, "deleted_at column not found"
        assert info["nullable"] is True, (
            f"deleted_at should be nullable, got nullable={info['nullable']}"
        )
        assert info["default"] is None, (
            f"deleted_at should have no default, got: {info['default']!r}"
        )

    # -- CHECK constraint enforcement ---------------------------------------

    def test_ck_deletion_receipt_status_allows_delete_failed(self, pg_session_factory, tmp_schema):
        """INSERT with status='delete_failed' succeeds."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "sk-pg-df",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hash123",
                    "st": "delete_failed",
                },
            )
            session.commit()

    def test_ck_deletion_receipt_status_rejects_unknown(self, pg_session_factory, tmp_schema):
        """INSERT with unknown status hits IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "sk-pg-bad",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hash789",
                    "st": "unknown",
                },
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_deletion_receipt_status" in err_msg, (
            f"Expected constraint ck_deletion_receipt_status, got: {err_msg}"
        )

    # -- Downgrade 0023 (revert 0024 changes) --------------------------------

    def test_downgrade_restores_status_check_to_original(self, pg_engine, tmp_schema):
        """Downgrade to 0023 restores original status CHECK (no delete_failed)."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_check_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" not in status_check_sql, (
            f"ck_deletion_receipt_status should NOT include 'delete_failed', "
            f"got: {status_check_sql}"
        )

    def test_downgrade_restores_deleted_at_not_null_and_default(self, pg_engine, tmp_schema):
        """Downgrade to 0023 restores deleted_at NOT NULL + default."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None, "deleted_at column not found"
        assert info["nullable"] is False, (
            f"deleted_at should be NOT NULL, got nullable={info['nullable']}"
        )
        assert info["default"] is not None, "deleted_at should have a default after downgrade"

    # -- Re-upgrade head -----------------------------------------------------

    def test_re_upgrade_restores_all(self, pg_engine, tmp_schema):
        """Re-upgrade to head restores 0024 schema changes."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        # Table exists with all columns
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        # CHECK constraints exist with new status values
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        assert set(checks.keys()) == DELETION_RECEIPTS_CHECK_CONSTRAINTS
        status_check_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_check_sql

        # deleted_at nullable with no default
        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True
        assert info["default"] is None

    # -- Runtime behaviour: deleted_at semantics in DB -----------------------

    def test_receipt_intent_has_null_deleted_at(self, pg_session_factory, tmp_schema):
        """INSERT with status='intent' results in NULL deleted_at."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "sk-pg-intent",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hash456",
                    "st": "intent",
                },
            )
            session.commit()

            row = session.execute(
                sa.text("SELECT deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-intent"},
            ).fetchone()
            assert row is not None
            assert row[0] is None, f"deleted_at should be NULL for intent, got: {row[0]!r}"

    def test_receipt_delete_failed_has_null_deleted_at(self, pg_session_factory, tmp_schema):
        """INSERT with status='delete_failed' results in NULL deleted_at."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "sk-pg-df2",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hashabc",
                    "st": "delete_failed",
                },
            )
            session.commit()

            row = session.execute(
                sa.text("SELECT deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-df2"},
            ).fetchone()
            assert row is not None
            assert row[0] is None, f"deleted_at should be NULL for delete_failed, got: {row[0]!r}"

    def test_receipt_deleted_has_actual_deleted_at(self, pg_session_factory, tmp_schema):
        """INSERT with status='deleted' and explicit deleted_at works."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status, deleted_at) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st, :da)"
                ),
                {
                    "sk": "sk-pg-del",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hashdef",
                    "st": "deleted",
                    "da": "2026-06-25 12:00:00",
                },
            )
            session.commit()

            row = session.execute(
                sa.text("SELECT deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-del"},
            ).fetchone()
            assert row is not None
            assert row[0] is not None, "deleted_at should NOT be NULL for deleted receipt"

    # Cross-head upgrade: 0024 (published) → head (through 0025)

    def test_postgresql_upgrade_from_published_0024_revision(self, pg_engine, tmp_schema):
        """Upgrade from OLD 0024 revision to head works and adds 0025 columns."""
        # 1. Upgrade to OLD 0024 revision
        result = _run_alembic(
            ["upgrade", "0024_fix_receipt_status_and_deleted_at"],
            schema=tmp_schema,
        )
        assert result.returncode == 0, f"upgrade to 0024 failed:\n{result.stderr}"

        # Verify 0024 schema is in place
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )
        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True, "deleted_at should be nullable"

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_sql, (
            f"ck_deletion_receipt_status should include 'delete_failed', got: {status_sql}"
        )

        # Verify deletion_outbox does NOT yet have 0025 columns
        outbox_cols_before = _pg_get_columns(pg_engine, "deletion_outbox")
        assert "claim_token" not in outbox_cols_before
        assert "claim_version" not in outbox_cols_before
        assert "locked_at" not in outbox_cols_before
        assert "lock_expires_at" not in outbox_cols_before

        # 2. Upgrade head — should apply 0025
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"upgrade to head (through 0025) failed:\n{result.stderr}"

        # Verify 0025 columns now exist in deletion_outbox
        outbox_cols_after = _pg_get_columns(pg_engine, "deletion_outbox")
        for col in ("claim_token", "claim_version", "locked_at", "lock_expires_at"):
            assert col in outbox_cols_after, (
                f"deletion_outbox should have {col} after head, got: {outbox_cols_after}"
            )

        # Verify 0025 CHECK constraint on claim_version
        outbox_checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        assert "ck_deletion_outbox_claim_version" in outbox_checks, (
            f"Expected ck_deletion_outbox_claim_version, got: {list(outbox_checks.keys())}"
        )

        # Verify 0024 schema still intact
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS
        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_sql

    def test_postgresql_published_0024_data_survives_upgrade(
        self, pg_session_factory, pg_engine, tmp_schema
    ):
        """Data inserted under published 0024 persists after upgrade through 0025."""
        # 1. Upgrade to OLD 0024 revision
        result = _run_alembic(
            ["upgrade", "0024_fix_receipt_status_and_deleted_at"],
            schema=tmp_schema,
        )
        assert result.returncode == 0, f"upgrade to 0024 failed:\n{result.stderr}"

        # 2. Insert test data (a receipt with status='delete_failed' and deleted_at=NULL)
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "***",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hash_cross_pg_001",
                    "st": "delete_failed",
                },
            )
            session.commit()

        # Verify the data was inserted correctly
        with pg_session_factory() as session:
            row = session.execute(
                sa.text("SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "***"},
            ).fetchone()
            assert row is not None
            assert row[0] == "delete_failed", f"Expected delete_failed, got {row[0]!r}"
            assert row[1] is None, "deleted_at should be NULL for delete_failed receipt"

        # 3. Record alembic_version = '0024_fix_receipt_status_and_deleted_at'
        with pg_session_factory() as session:
            version_row = session.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).fetchone()
            assert version_row is not None
            assert version_row[0] == "0024_fix_receipt_status_and_deleted_at", (
                f"Expected version 0024_fix_receipt_status_and_deleted_at, got {version_row[0]!r}"
            )

        # 4. Run alembic upgrade head — goes through 0025
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"upgrade head failed:\n{result.stderr}"

        # 5. Verify the test data still exists in deletion_receipts
        with pg_session_factory() as session:
            row = session.execute(
                sa.text("SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "***"},
            ).fetchone()
            assert row is not None, "Data should survive upgrade through 0025"
            assert row[0] == "delete_failed", (
                f"status should still be 'delete_failed', got {row[0]!r}"
            )
            assert row[1] is None, "deleted_at should still be NULL"

        # 6. Verify deletion_receipts.status allows 'delete_failed'
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_sql, (
            f"ck_deletion_receipt_status should include 'delete_failed', got: {status_sql}"
        )

        # 7. Verify deleted_at is nullable
        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True, "deleted_at should be nullable"

        # 8. Verify deletion_outbox has 0025 columns
        outbox_cols = _pg_get_columns(pg_engine, "deletion_outbox")
        for col in ("claim_token", "claim_version", "locked_at", "lock_expires_at"):
            assert col in outbox_cols, (
                f"deletion_outbox should have {col} after head, got: {outbox_cols}"
            )

    # -- Downgrade with delete_failed data -----------------------------------

    def test_postgresql_0024_downgrade_with_delete_failed_row(
        self, pg_session_factory, pg_engine, tmp_schema
    ):
        """Downgrade from 0024 with a delete_failed receipt normalizes the row."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"upgrade failed:\n{result.stderr}"

        # Insert a delete_failed receipt row
        with pg_session_factory() as session:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES (:sk, :sct, :scv, :rt, :rv, :dh, :st)"
                ),
                {
                    "sk": "sk-pg-downgrade-df",
                    "sct": "tok1",
                    "scv": 0,
                    "rt": "tok2",
                    "rv": 0,
                    "dh": "hash123",
                    "st": "delete_failed",
                },
            )
            session.commit()

        # Verify the row
        with pg_session_factory() as session:
            row = session.execute(
                sa.text("SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-downgrade-df"},
            ).fetchone()
            assert row is not None
            assert row[0] == "delete_failed"
            assert row[1] is None

        # Downgrade to 0023 — should normalize the delete_failed row
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], schema=tmp_schema)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        # Verify the row was converted: status='intent', deleted_at is set
        with pg_session_factory() as session:
            row = session.execute(
                sa.text("SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-downgrade-df"},
            ).fetchone()
            assert row is not None, "Row should still exist after downgrade"
            assert row[0] == "intent", f"Expected status='intent' after downgrade, got: {row[0]!r}"
            assert row[1] is not None, "deleted_at should be set after downgrade normalization"

        # Verify old CHECK constraint is in place
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" not in status_sql

        # Upgrade head again — should work
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        # Verify row is still there after re-upgrade
        with pg_session_factory() as session:
            row = session.execute(
                sa.text("SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=:sk"),
                {"sk": "sk-pg-downgrade-df"},
            ).fetchone()
            assert row is not None
            assert row[0] == "intent"

    # -- Full roundtrip -----------------------------------------------------

    def test_postgresql_0024_roundtrip(self, pg_engine, tmp_schema):
        """Full roundtrip: upgrade head -> downgrade 0023 -> upgrade head."""
        # 1. upgrade to head (0024)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True
        assert info["default"] is None

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_sql

        # 2. downgrade to 0023
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], schema=tmp_schema)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is False
        assert info["default"] is not None

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" not in status_sql

        # 3. re-upgrade to head (0024)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        info = _pg_get_column_info(pg_engine, "deletion_receipts", "deleted_at")
        assert info is not None
        assert info["nullable"] is True
        assert info["default"] is None

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        status_sql = checks.get("ck_deletion_receipt_status", "")
        assert "delete_failed" in status_sql
