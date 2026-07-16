"""Migrated-schema integration tests for seed and authority conflict.

Uses real Alembic upgrade head (NOT Base.metadata.create_all) to install
database triggers.  Verifies that seed_if_not_exists correctly uses the
draft→approved transition and that authority conflicts are classified as
WeightRevisionGovernanceError(active_revision_conflict).

SQLite-only: skipped when DATABASE_BACKEND is postgresql.
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite migrated-schema tests — use test_production_scheme_postgresql.py for PG",
        allow_module_level=True,
    )

import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.pool import StaticPool

from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeWeightSetActiveRevisionRecord,
    SchemeWeightSetRecord,
    SchemeWeightSetRevisionRecord,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_engine():
    """Create a fresh SQLite database via Alembic upgrade head."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}:\n{r.stdout}")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield engine
    engine.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def session_factory(migrated_engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


@pytest.fixture()
def adapter():
    from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
        SqlAlchemyWeightRevisionApprovalAdapter,
    )

    return SqlAlchemyWeightRevisionApprovalAdapter()


# ── Test data ──────────────────────────────────────────────────────────────

_WEIGHT_CONTENT = {
    "criteria": [
        {
            "criterion_code": "total_area_m2",
            "weight": "0.50",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total area",
        },
        {
            "criterion_code": "investment_cny",
            "weight": "0.50",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Investment",
        },
    ],
    "version": "1.0.0",
}

_WEIGHT_CONTENT_DIFFERENT = {
    "criteria": [
        {
            "criterion_code": "total_area_m2",
            "weight": "0.40",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total area",
        },
        {
            "criterion_code": "investment_cny",
            "weight": "0.60",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Investment",
        },
    ],
    "version": "1.0.0",
}


# ═════════════════════════════════════════════════════════════════════════════
#  Section 六: Migrated-schema seed tests
# ═════════════════════════════════════════════════════════════════════════════


class TestMigratedSchemaSeed:
    """Verify seed_if_not_exists on real migrated schema with triggers."""

    def test_first_seed_success(self, session_factory, adapter):
        """First seed creates draft→approved with sealed_at and authority."""
        sess = session_factory()
        try:
            now = datetime.now(UTC)

            adapter.seed_if_not_exists(
                sess,
                weight_set_id="ws-seed-001",
                code="seed-test",
                name="Seed Test Set",
                revision_id="rev-seed-001",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="test-seeder",
            )
            sess.commit()

            # Re-open session to read committed state
            sess2 = session_factory()
            try:
                # Revision must be approved
                rev = sess2.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-seed-001"
                    )
                ).scalar_one()
                assert rev.status == "approved"
                assert rev.approved_at is not None
                assert rev.approved_by == "test-seeder"
                assert rev.sealed_at is not None

                # Exactly one authority row
                auth = sess2.execute(
                    select(SchemeWeightSetActiveRevisionRecord).where(
                        SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-seed-001"
                    )
                ).scalar_one()
                assert auth.approved_revision_id == "rev-seed-001"
                assert auth.code == "seed-test"
            finally:
                sess2.close()
        finally:
            sess.close()

    def test_repeat_seed_idempotent(self, session_factory, adapter):
        """Seeding twice does not create duplicates."""
        now = datetime.now(UTC)

        # First seed
        sess1 = session_factory()
        try:
            adapter.seed_if_not_exists(
                sess1,
                weight_set_id="ws-seed-002",
                code="seed-repeat",
                name="Repeat Seed Set",
                revision_id="rev-seed-002",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="test-seeder",
            )
            sess1.commit()
        finally:
            sess1.close()

        # Second seed — same revision_id
        sess2 = session_factory()
        try:
            adapter.seed_if_not_exists(
                sess2,
                weight_set_id="ws-seed-002",
                code="seed-repeat",
                name="Repeat Seed Set",
                revision_id="rev-seed-002",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="test-seeder",
            )
            sess2.commit()
        finally:
            sess2.close()

        # Verify exactly one revision and one authority
        sess3 = session_factory()
        try:
            from sqlalchemy import func

            rev_count = sess3.execute(
                select(func.count())
                .select_from(SchemeWeightSetRevisionRecord)
                .where(SchemeWeightSetRevisionRecord.id == "rev-seed-002")
            ).scalar_one()
            assert rev_count == 1

            auth_count = sess3.execute(
                select(func.count())
                .select_from(SchemeWeightSetActiveRevisionRecord)
                .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-seed-002")
            ).scalar_one()
            assert auth_count == 1

            # Content hash must not change
            from cold_storage.modules.schemes.application.weight_revision_governance import (
                _compute_content_hash,
            )

            rev = sess3.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-seed-002"
                )
            ).scalar_one()
            assert rev.content_hash == _compute_content_hash(_WEIGHT_CONTENT)
        finally:
            sess3.close()

    def test_direct_approved_insert_rejected(self, migrated_engine):
        """Direct INSERT of status='approved' must be blocked by trigger."""
        with (
            migrated_engine.connect() as conn,
            pytest.raises(Exception, match="direct INSERT.*forbidden"),
        ):
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_set_revisions"
                    " (id, weight_set_id, code, revision, status,"
                    " content, content_hash,"
                    " generator_compatibility_version)"
                    " VALUES"
                    " ('rev-direct-001', 'ws-001', 'test', 1,"
                    " 'approved', '{}', 'dummy-hash', '1.0.0')"
                )
            )

    def test_direct_approved_insert_rejected_via_orm(self, session_factory):
        """Direct ORM INSERT of approved revision must fail."""
        from sqlalchemy import exc as sa_exc

        sess = session_factory()
        try:
            record = SchemeWeightSetRevisionRecord(
                id="rev-orm-direct-001",
                weight_set_id="ws-orm-001",
                code="test-orm",
                revision=1,
                status="approved",
                content={},
                content_hash="dummy",
                generator_compatibility_version="1.0.0",
                approved_at=datetime.now(UTC),
                approved_by="test",
            )
            sess.add(record)
            with pytest.raises((sa_exc.IntegrityError, sa_exc.InternalError)):
                sess.flush()
        finally:
            sess.close()

    def test_approval_evidence_check(self, session_factory, adapter):
        """Seed must set approved_at and approved_by correctly."""
        now = datetime.now(UTC)
        sess = session_factory()
        try:
            adapter.seed_if_not_exists(
                sess,
                weight_set_id="ws-evidence-001",
                code="evidence-test",
                name="Evidence Test",
                revision_id="rev-evidence-001",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="evidence-user",
            )
            sess.commit()

            sess2 = session_factory()
            try:
                rev = sess2.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-evidence-001"
                    )
                ).scalar_one()
                assert rev.approved_by == "evidence-user"
                assert rev.approved_at is not None
                assert rev.sealed_at is not None
            finally:
                sess2.close()
        finally:
            sess.close()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 七: Real conflict classification tests
# ═════════════════════════════════════════════════════════════════════════════


class TestMigratedSchemaConflictClassification:
    """Verify authority conflict classification on real migrated schema."""

    def _create_draft(self, sess, *, revision_id, weight_set_id, code, content, rev_num=1):
        """Insert a draft revision directly (via ORM, status=draft)."""
        # First create the parent weight set if needed
        existing_ws = sess.execute(
            select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == weight_set_id)
        ).scalar_one_or_none()
        if existing_ws is None:
            ws = SchemeWeightSetRecord(
                id=weight_set_id,
                code=code,
                name="Conflict Test Set",
                revision=1,
                status="draft",
                source_type="system",
                criteria=[],
            )
            sess.add(ws)
            sess.flush()

        rev = SchemeWeightSetRevisionRecord(
            id=revision_id,
            weight_set_id=weight_set_id,
            code=code,
            revision=rev_num,
            status="draft",
            content=content,
            content_hash="will-be-updated",
            generator_compatibility_version="1.0.0",
        )
        sess.add(rev)
        sess.flush()

    def test_conflict_on_second_approval(self, session_factory, adapter):
        """Approve revision A, then approve B for same (ws, code) → governance error."""
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        sess = session_factory()
        try:
            # Create revision A as draft
            self._create_draft(
                sess,
                revision_id="rev-conflict-A",
                weight_set_id="ws-conflict",
                code="conflict-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            # Create revision B as draft (different revision number)
            self._create_draft(
                sess,
                revision_id="rev-conflict-B",
                weight_set_id="ws-conflict",
                code="conflict-code",
                content=_WEIGHT_CONTENT_DIFFERENT,
                rev_num=2,
            )
            sess.commit()

            # Approve A — should succeed
            now_a = datetime.now(UTC)
            result_a = adapter.approve_revision(
                sess,
                revision_id="rev-conflict-A",
                content=_WEIGHT_CONTENT,
                approved_at=now_a,
                approved_by="conflict-tester",
            )
            assert result_a is True
            sess.commit()

            # Approve B — should raise governance error
            now_b = datetime.now(UTC)
            with pytest.raises(WeightRevisionGovernanceError) as exc_info:
                adapter.approve_revision(
                    sess,
                    revision_id="rev-conflict-B",
                    content=_WEIGHT_CONTENT_DIFFERENT,
                    approved_at=now_b,
                    approved_by="conflict-tester",
                )
            assert exc_info.value.code == "active_revision_conflict"

            # Verify: A is still approved, B is still draft
            sess2 = session_factory()
            try:
                rev_a = sess2.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-conflict-A"
                    )
                ).scalar_one()
                assert rev_a.status == "approved"

                rev_b = sess2.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-conflict-B"
                    )
                ).scalar_one()
                assert rev_b.status == "draft"

                # Exactly one authority pointing to A
                auths = (
                    sess2.execute(
                        select(SchemeWeightSetActiveRevisionRecord).where(
                            SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-conflict"
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(auths) == 1
                assert auths[0].approved_revision_id == "rev-conflict-A"
            finally:
                sess2.close()
        finally:
            sess.close()

    def test_concurrent_approval_one_winner(self, session_factory, adapter):
        """Two connections racing to approve — exactly one succeeds."""
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        db_path = None

        # Create engine without StaticPool to simulate real concurrency
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            db_path.unlink(missing_ok=True)
            pytest.fail(f"Alembic upgrade failed:\n{r.stderr}:\n{r.stdout}")

        # Use two separate engines to simulate two connections
        engine_a = create_engine(f"sqlite:///{db_path}")
        engine_b = create_engine(f"sqlite:///{db_path}")

        from sqlalchemy.orm import sessionmaker

        factory_a = sessionmaker(bind=engine_a, expire_on_commit=False)
        factory_b = sessionmaker(bind=engine_b, expire_on_commit=False)

        try:
            # Seed draft revisions in engine_a
            sess_setup = factory_a()
            self._create_draft(
                sess_setup,
                revision_id="rev-race-A",
                weight_set_id="ws-race",
                code="race-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            self._create_draft(
                sess_setup,
                revision_id="rev-race-B",
                weight_set_id="ws-race",
                code="race-code",
                content=_WEIGHT_CONTENT_DIFFERENT,
                rev_num=2,
            )
            sess_setup.commit()
            sess_setup.close()

            results = {}
            errors = {}

            def approve_A():
                sess = factory_a()
                try:
                    ok = adapter.approve_revision(
                        sess,
                        revision_id="rev-race-A",
                        content=_WEIGHT_CONTENT,
                        approved_at=datetime.now(UTC),
                        approved_by="racer-a",
                    )
                    sess.commit()
                    results["A"] = ok
                except Exception as e:
                    errors["A"] = e
                    import contextlib

                    with contextlib.suppress(Exception):
                        sess.rollback()
                finally:
                    sess.close()

            def approve_B():
                # Small delay to increase interleaving chance
                time.sleep(0.01)
                sess = factory_b()
                try:
                    ok = adapter.approve_revision(
                        sess,
                        revision_id="rev-race-B",
                        content=_WEIGHT_CONTENT_DIFFERENT,
                        approved_at=datetime.now(UTC),
                        approved_by="racer-b",
                    )
                    sess.commit()
                    results["B"] = ok
                except Exception as e:
                    errors["B"] = e
                    import contextlib

                    with contextlib.suppress(Exception):
                        sess.rollback()
                finally:
                    sess.close()

            t1 = threading.Thread(target=approve_A)
            t2 = threading.Thread(target=approve_B)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            # Exactly one must succeed.
            # The losing thread MUST surface its conflict as the adapter's typed
            # ``WeightRevisionGovernanceError`` (raised inside the adapter's
            # ``begin_nested()`` savepoint). A raw ``sqlalchemy.exc.IntegrityError``
            # escaping from the adapter would indicate the authority-conflict
            # classifier failed to convert the database-level unique violation —
            # this is a real bug, not a legitimate loser, and must be flagged.
            def _is_loser(exc: BaseException) -> bool:
                return isinstance(exc, WeightRevisionGovernanceError)

            def _is_raw_integrity_loser(exc: BaseException) -> bool:
                from sqlalchemy import exc as _sa_exc

                return isinstance(exc, _sa_exc.IntegrityError)

            succeeded = [k for k, v in results.items() if v is True]
            failed = [k for k, v in errors.items() if _is_loser(v)]
            raw_integrity_losers = [k for k, v in errors.items() if _is_raw_integrity_loser(v)]
            assert len(succeeded) + len(failed) == 2, (
                f"Expected one success and one failure, got "
                f"succeeded={succeeded}, failed={failed}, "
                f"all_results={results}, all_errors={errors}"
            )
            assert len(succeeded) == 1, f"Expected exactly one winner, got {succeeded}"
            assert len(raw_integrity_losers) == 0, (
                f"Expected 0 raw sqlalchemy.exc.IntegrityError losers "
                f"(adapter must convert authority conflicts to "
                f"WeightRevisionGovernanceError), got {raw_integrity_losers}, "
                f"all_errors={errors}"
            )

            # Final state check
            sess_final = factory_a()
            try:
                from sqlalchemy import func

                approved_count = sess_final.execute(
                    select(func.count())
                    .select_from(SchemeWeightSetRevisionRecord)
                    .where(
                        SchemeWeightSetRevisionRecord.weight_set_id == "ws-race",
                        SchemeWeightSetRevisionRecord.status == "approved",
                    )
                ).scalar_one()
                assert approved_count == 1

                auth_count = sess_final.execute(
                    select(func.count())
                    .select_from(SchemeWeightSetActiveRevisionRecord)
                    .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-race")
                ).scalar_one()
                assert auth_count == 1
            finally:
                sess_final.close()

        finally:
            engine_a.dispose()
            engine_b.dispose()
            db_path.unlink(missing_ok=True)

    def test_unrelated_integrity_error_not_converted(self, session_factory, adapter):
        """FK violation or NOT NULL violation must NOT be converted to governance error."""
        # Attempt to seed with a non-existent weight_set_id FK
        # This should fail with a normal IntegrityError, not a governance error
        from sqlalchemy import exc as sa_exc

        sess = session_factory()
        try:
            # Try to approve a revision whose parent ws doesn't exist
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetRevisionRecord,
            )

            rev = SchemeWeightSetRevisionRecord(
                id="rev-fk-fail",
                weight_set_id="nonexistent-ws",
                code="fk-test",
                revision=1,
                status="draft",
                content=_WEIGHT_CONTENT,
                content_hash="dummy",
                generator_compatibility_version="1.0.0",
            )
            sess.add(rev)
            with pytest.raises((sa_exc.IntegrityError, sa_exc.InternalError)):
                sess.flush()
        finally:
            sess.close()


# ── Deterministic classifier regression tests ────────────────────────────────
# These tests exercise ``_is_authority_unique_conflict`` directly with
# SQLAlchemy ``IntegrityError`` objects constructed from real ``sqlite3.IntegrityError``
# messages. They are deterministic: no random timing, no threading, no DB race.


def _build_sqlite_sa_integrity_error(sqlite_msg: str) -> Exception:
    """Build a real ``sqlalchemy.exc.IntegrityError`` whose ``.orig`` is a real
    ``sqlite3.IntegrityError`` carrying the given SQLite error message.

    This mirrors what SQLAlchemy constructs internally when SQLite raises an
    IntegrityError — no mocking of the classifier itself.
    """
    import sqlite3 as _sqlite3

    from sqlalchemy import exc as _sa_exc

    inner = _sqlite3.IntegrityError(sqlite_msg)
    sa_exc_obj = _sa_exc.IntegrityError(
        "(sqlite3.IntegrityError) " + sqlite_msg,
        params={},
        orig=inner,
    )
    return sa_exc_obj


class TestIsAuthorityUniqueConflictSqliteClassifier:
    """Direct, deterministic tests for the SQLite branch of
    ``_is_authority_unique_conflict``. Each test builds a real SA
    ``IntegrityError`` whose ``.orig`` is a real ``sqlite3.IntegrityError``
    carrying the canonical SQLite error message format.
    """

    def test_authority_table_pk_exact_message_returns_true(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "UNIQUE constraint failed: "
            "scheme_weight_set_active_revisions.weight_set_id, "
            "scheme_weight_set_active_revisions.code"
        )
        assert _is_authority_unique_conflict(exc) is True

    def test_revisions_table_synthetic_unique_message_returns_false(self):
        """SQLite does NOT create a partial unique index on
        ``scheme_weight_set_revisions(weight_set_id, code) WHERE status = 'approved'``
        (only PostgreSQL does, in migration 0031).  Therefore the SQLite
        database NEVER produces a ``UNIQUE constraint failed:
        scheme_weight_set_revisions.weight_set_id, scheme_weight_set_revisions.code``
        message.  If such a message ever arrived, it would indicate a schema
        regression — it must NOT be classified as an authority conflict.

        This test pins the contract that the SQLite classifier returns False
        for the synthetic revisions-table unique message.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "UNIQUE constraint failed: "
            "scheme_weight_set_revisions.weight_set_id, "
            "scheme_weight_set_revisions.code"
        )
        assert _is_authority_unique_conflict(exc) is False

    def test_unrelated_table_unique_violation_returns_false(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "UNIQUE constraint failed: some_other_table.col_a, some_other_table.col_b"
        )
        assert _is_authority_unique_conflict(exc) is False

    def test_same_table_wrong_columns_returns_false(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        # Right table, but columns are NOT (weight_set_id, code)
        exc = _build_sqlite_sa_integrity_error(
            "UNIQUE constraint failed: "
            "scheme_weight_set_revisions.id, scheme_weight_set_revisions.code"
        )
        assert _is_authority_unique_conflict(exc) is False

        exc2 = _build_sqlite_sa_integrity_error(
            "UNIQUE constraint failed: "
            "scheme_weight_set_active_revisions.weight_set_id, "
            "scheme_weight_set_active_revisions.revision"
        )
        assert _is_authority_unique_conflict(exc2) is False

    def test_not_null_violation_returns_false(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "NOT NULL constraint failed: scheme_weight_set_revisions.weight_set_id"
        )
        assert _is_authority_unique_conflict(exc) is False

    def test_foreign_key_violation_returns_false(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error("FOREIGN KEY constraint failed")
        assert _is_authority_unique_conflict(exc) is False

    def test_check_violation_returns_false(self):
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error("CHECK constraint failed: status_check")
        assert _is_authority_unique_conflict(exc) is False

    def test_authority_claim_trigger_canonical_message_returns_true(self):
        """Authority-conflict BEFORE UPDATE trigger
        ``trg_authority_check_on_approve`` raises
        ``RAISE(ABORT, 'active_revision_conflict: another revision already
        approved for this weight_set_id/code')`` when a concurrent draft is
        upgraded to approved for a (weight_set_id, code) pair that already
        has an approved revision.  SQLite surfaces the RAISE payload as
        the exact ``sqlite3.IntegrityError`` message (no wrapping).

        The classifier must match this via casefolded FULL-STRING EQUALITY
        — NOT via substring / startswith / regex / token matching.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "active_revision_conflict: "
            "another revision already approved for this weight_set_id/code"
        )
        assert _is_authority_unique_conflict(exc) is True

    def test_trigger_canonical_message_uppercased_returns_true(self):
        """Casefolded equality must accept any-case variations of the
        canonical message (e.g. uppercase, mixed case).  This is the
        'deterministic大小写归一化' the brief allows.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "ACTIVE_REVISION_CONFLICT: ANOTHER REVISION ALREADY APPROVED "
            "FOR THIS WEIGHT_SET_ID/CODE"
        )
        assert _is_authority_unique_conflict(exc) is True

    def test_trigger_token_embedded_in_unrelated_text_returns_false(self):
        """The trigger token ``active_revision_conflict`` MUST NOT be
        accepted when it appears embedded in unrelated text — only the
        exact canonical message authorizes classification.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "some unrelated error containing active_revision_conflict"
        )
        assert _is_authority_unique_conflict(exc) is False

        exc2 = _build_sqlite_sa_integrity_error("active_revision_conflict_but_not_authority")
        assert _is_authority_unique_conflict(exc2) is False

    def test_trigger_message_with_prefix_returns_false(self):
        """A leading prefix on the canonical message MUST be rejected —
        only casefolded FULL-STRING EQUALITY is allowed.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "prefix active_revision_conflict: another revision already "
            "approved for this weight_set_id/code"
        )
        assert _is_authority_unique_conflict(exc) is False

    def test_trigger_message_with_suffix_returns_false(self):
        """A trailing suffix on the canonical message MUST be rejected —
        only casefolded FULL-STRING EQUALITY is allowed.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error(
            "active_revision_conflict: another revision already approved "
            "for this weight_set_id/code extra"
        )
        assert _is_authority_unique_conflict(exc) is False

    def test_trigger_message_incomplete_returns_false(self):
        """Truncated or partial versions of the canonical message MUST be
        rejected.  The full message must arrive intact.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error("active_revision_conflict:")
        assert _is_authority_unique_conflict(exc) is False

        exc2 = _build_sqlite_sa_integrity_error(
            "active_revision_conflict: another revision already approved"
        )
        assert _is_authority_unique_conflict(exc2) is False

    def test_unrelated_trigger_message_returns_false(self):
        """Other trigger messages (e.g. immutability, status-transition) must
        NOT be converted — only the specific ``active_revision_conflict``
        token authorizes classification.
        """
        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _build_sqlite_sa_integrity_error("sealed revision immutability: immutable fields")
        assert _is_authority_unique_conflict(exc) is False

        exc2 = _build_sqlite_sa_integrity_error("invalid status transition")
        assert _is_authority_unique_conflict(exc2) is False

        exc3 = _build_sqlite_sa_integrity_error(
            "direct INSERT of approved is forbidden; use controlled draft→approved transition"
        )
        assert _is_authority_unique_conflict(exc3) is False

    def test_orig_is_none_returns_false(self):
        from sqlalchemy import exc as _sa_exc

        from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
            _is_authority_unique_conflict,
        )

        exc = _sa_exc.IntegrityError("no orig", params={}, orig=None)
        assert _is_authority_unique_conflict(exc) is False


class TestAdapterSqliteConflictConversionDeterministic:
    """Adapter-boundary deterministic test: when the SQLite
    ``trg_authority_check_on_approve`` BEFORE UPDATE trigger fires inside
    the adapter's savepoint, the surfaced exception MUST be
    ``WeightRevisionGovernanceError`` with
    ``error_code="active_revision_conflict"`` and ``__cause__`` being the
    original ``sqlalchemy.exc.IntegrityError``.

    Per brief §六, the test must NOT depend on random timing or thread
    races.  It exercises the *database-level* classifier path by
    temporarily suppressing the application-level check (so the BEFORE
    UPDATE trigger fires inside the savepoint), then verifies the typed
    error + ``__cause__`` contract.

    The test MUST NOT mock the classifier, the database exception
    return-value, or ``WeightRevisionGovernanceError`` itself.  Only
    ``has_approved_revision`` may be patched because it is an
    application-layer short-circuit; the database trigger is the actual
    source of truth on SQLite.
    """

    def test_trigger_authority_conflict_yields_typed_error_with_cause(
        self, session_factory, adapter
    ):
        """Approve revision #1, then attempt to approve revision #2 with the
        same (weight_set_id, code).  We bypass ``has_approved_revision``
        so the savepoint hits the BEFORE UPDATE trigger
        ``trg_authority_check_on_approve``, which raises the canonical
        SQLite message.  The adapter must convert this database-level
        IntegrityError to ``WeightRevisionGovernanceError`` with the
        correct ``code`` and a chained ``__cause__`` of type
        ``sqlalchemy.exc.IntegrityError`` whose ``.orig`` message equals
        the canonical trigger payload.
        """
        import contextlib
        from unittest.mock import patch as _patch

        from sqlalchemy import exc as _sa_exc

        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        sess = session_factory()
        try:
            # Seed parent + first draft, approve it normally
            ws = SchemeWeightSetRecord(
                id="ws-cls-test",
                code="cls-code",
                name="cls",
                revision=1,
                status="approved",
                source_type="system",
                criteria=[],
                requires_review=False,
                approved_at=datetime.now(UTC),
            )
            sess.add(ws)
            rev_a = SchemeWeightSetRevisionRecord(
                id="rev-cls-A",
                weight_set_id="ws-cls-test",
                code="cls-code",
                revision=1,
                status="draft",
                content={"v": 1},
                content_hash="a" * 64,
                generator_compatibility_version="v1",
                approved_at=None,
                approved_by=None,
                sealed_at=None,
            )
            sess.add(rev_a)
            sess.commit()

            ok1 = adapter.approve_revision(
                sess,
                revision_id="rev-cls-A",
                content={"v": 1},
                approved_at=datetime.now(UTC),
                approved_by="cls-tester",
            )
            sess.commit()
            assert ok1 is True

            # Add second draft revision with same (weight_set_id, code)
            rev_b = SchemeWeightSetRevisionRecord(
                id="rev-cls-B",
                weight_set_id="ws-cls-test",
                code="cls-code",
                revision=2,
                status="draft",
                content={"v": 2},
                content_hash="b" * 64,
                generator_compatibility_version="v1",
                approved_at=None,
                approved_by=None,
                sealed_at=None,
            )
            sess.add(rev_b)
            sess.commit()
            sess.close()

            # Now exercise the database-level trigger path.  We patch
            # has_approved_revision to return False so the application-level
            # guard is bypassed and the BEFORE UPDATE trigger
            # trg_authority_check_on_approve fires inside the savepoint.
            # This is the path that the SQLite branch of
            # _is_authority_unique_conflict must classify.
            sess2 = session_factory()
            try:
                with (
                    _patch(
                        "cold_storage.modules.schemes.infrastructure"
                        ".weight_revision_approval_adapter"
                        ".SqlAlchemyWeightRevisionApprovalAdapter"
                        ".has_approved_revision",
                        return_value=False,
                    ),
                    pytest.raises(WeightRevisionGovernanceError) as excinfo,
                ):
                    adapter.approve_revision(
                        sess2,
                        revision_id="rev-cls-B",
                        content={"v": 2},
                        approved_at=datetime.now(UTC),
                        approved_by="cls-tester",
                    )
                # Typed-error contract: code and __cause__ provenance.
                assert excinfo.value.code == "active_revision_conflict"
                assert isinstance(excinfo.value.__cause__, _sa_exc.IntegrityError), (
                    f"Expected __cause__ to be sqlalchemy.exc.IntegrityError, "
                    f"got {type(excinfo.value.__cause__).__name__}: "
                    f"{excinfo.value.__cause__!r}"
                )
                # __cause__.orig message must equal the canonical trigger
                # message (casefolded) — NOT just contain the token.
                orig_msg = str(excinfo.value.__cause__.orig)
                assert orig_msg.casefold() == (
                    "active_revision_conflict: "
                    "another revision already approved for this weight_set_id/code"
                )
            finally:
                with contextlib.suppress(Exception):
                    sess2.rollback()
                sess2.close()
        finally:
            with contextlib.suppress(Exception):
                sess.rollback()
            sess.close()
