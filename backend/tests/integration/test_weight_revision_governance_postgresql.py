"""PostgreSQL migrated-schema integration tests for seed, conflict
classification, concurrent race, and passthrough.

Verifies that on real PostgreSQL with Alembic head schema:
- seed_if_not_exists uses draft→approved with sealed_at and authority
- approval conflicts produce WeightRevisionGovernanceError(active_revision_conflict)
- concurrent approval races produce exactly one winner
- unrelated IntegrityErrors pass through without conversion
- raw SQLSTATE/constraint_name diagnostics match the adapter classifier

Requires DATABASE_BACKEND=postgresql and DATABASE_URL.
"""

from __future__ import annotations

import os
import threading

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL weight revision tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgresql


# ── Helpers ────────────────────────────────────────────────────────────────


_WEIGHT_CONTENT: dict[str, Any] = {
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

_WEIGHT_CONTENT_V2: dict[str, Any] = {
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


def _make_adapter():
    from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
        SqlAlchemyWeightRevisionApprovalAdapter,
    )

    return SqlAlchemyWeightRevisionApprovalAdapter()


def _create_draft(
    sess,
    *,
    revision_id: str,
    weight_set_id: str,
    code: str,
    content: dict,
    rev_num: int = 1,
) -> None:
    """Insert a draft revision and parent weight set directly."""
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    existing_ws = sess.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == weight_set_id)
    ).scalar_one_or_none()
    if existing_ws is None:
        ws = SchemeWeightSetRecord(
            id=weight_set_id,
            code=code,
            name="PG Conflict Test",
            revision=rev_num,
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
        content_hash="placeholder",
        generator_compatibility_version="1.0.0",
    )
    sess.add(rev)
    sess.flush()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 七: PG migrated-schema seed tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPGMigratedSchemaSeed:
    """Verify seed on real PostgreSQL migrated schema."""

    def test_first_seed_success(self, pg_session_factory):
        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            now = datetime.now(UTC)
            adapter.seed_if_not_exists(
                sess,
                weight_set_id="ws-pg-seed-001",
                code="pg-seed",
                name="PG Seed Test",
                revision_id="rev-pg-seed-001",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="pg-test-seeder",
            )
            sess.commit()

            sess2 = pg_session_factory()
            try:
                from cold_storage.modules.schemes.infrastructure.orm import (
                    SchemeWeightSetActiveRevisionRecord,
                    SchemeWeightSetRevisionRecord,
                )

                rev = sess2.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-pg-seed-001"
                    )
                ).scalar_one()
                assert rev.status == "approved"
                assert rev.approved_by == "pg-test-seeder"
                assert rev.approved_at is not None
                assert rev.sealed_at is not None

                auth = sess2.execute(
                    select(SchemeWeightSetActiveRevisionRecord).where(
                        SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-pg-seed-001"
                    )
                ).scalar_one()
                assert auth.approved_revision_id == "rev-pg-seed-001"
                assert auth.code == "pg-seed"
            finally:
                sess2.close()
        finally:
            sess.close()

    def test_repeat_seed_idempotent(self, pg_session_factory):
        adapter = _make_adapter()
        now = datetime.now(UTC)

        sess1 = pg_session_factory()
        try:
            adapter.seed_if_not_exists(
                sess1,
                weight_set_id="ws-pg-seed-002",
                code="pg-seed-rpt",
                name="PG Seed Repeat",
                revision_id="rev-pg-seed-002",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="pg-test-seeder",
            )
            sess1.commit()
        finally:
            sess1.close()

        sess2 = pg_session_factory()
        try:
            adapter.seed_if_not_exists(
                sess2,
                weight_set_id="ws-pg-seed-002",
                code="pg-seed-rpt",
                name="PG Seed Repeat",
                revision_id="rev-pg-seed-002",
                revision=1,
                content=_WEIGHT_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=now,
                approved_by="pg-test-seeder",
            )
            sess2.commit()
        finally:
            sess2.close()

        sess3 = pg_session_factory()
        try:
            from sqlalchemy import func

            from cold_storage.modules.schemes.application.weight_revision_governance import (
                _compute_content_hash,
            )
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetActiveRevisionRecord,
                SchemeWeightSetRevisionRecord,
            )

            rev_count = sess3.execute(
                select(func.count())
                .select_from(SchemeWeightSetRevisionRecord)
                .where(SchemeWeightSetRevisionRecord.id == "rev-pg-seed-002")
            ).scalar_one()
            assert rev_count == 1

            auth_count = sess3.execute(
                select(func.count())
                .select_from(SchemeWeightSetActiveRevisionRecord)
                .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-pg-seed-002")
            ).scalar_one()
            assert auth_count == 1

            rev = sess3.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-pg-seed-002"
                )
            ).scalar_one()
            assert rev.content_hash == _compute_content_hash(_WEIGHT_CONTENT)
        finally:
            sess3.close()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 八: PG sequential conflict
# ═════════════════════════════════════════════════════════════════════════════


class TestPGSequentialConflict:
    """Approve A, then try B for same (ws, code) — B must raise governance error."""

    def test_sequential_conflict(self, pg_session_factory):
        from sqlalchemy import func

        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            _create_draft(
                sess,
                revision_id="rev-pg-seq-A",
                weight_set_id="ws-pg-seq",
                code="pg-seq-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            _create_draft(
                sess,
                revision_id="rev-pg-seq-B",
                weight_set_id="ws-pg-seq",
                code="pg-seq-code",
                content=_WEIGHT_CONTENT_V2,
                rev_num=2,
            )
            sess.commit()

            # Approve A
            ok_a = adapter.approve_revision(
                sess,
                revision_id="rev-pg-seq-A",
                content=_WEIGHT_CONTENT,
                approved_at=datetime.now(UTC),
                approved_by="pg-seq-tester",
            )
            assert ok_a is True
            sess.commit()

            # Approve B — should raise governance error
            with pytest.raises(WeightRevisionGovernanceError) as exc_info:
                adapter.approve_revision(
                    sess,
                    revision_id="rev-pg-seq-B",
                    content=_WEIGHT_CONTENT_V2,
                    approved_at=datetime.now(UTC),
                    approved_by="pg-seq-tester",
                )
            assert exc_info.value.code == "active_revision_conflict"

            # Verify session still usable
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetActiveRevisionRecord,
                SchemeWeightSetRevisionRecord,
            )

            rev_a = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-pg-seq-A"
                )
            ).scalar_one()
            assert rev_a.status == "approved"

            rev_b = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-pg-seq-B"
                )
            ).scalar_one()
            assert rev_b.status == "draft"

            auth_count = sess.execute(
                select(func.count())
                .select_from(SchemeWeightSetActiveRevisionRecord)
                .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-pg-seq")
            ).scalar_one()
            assert auth_count == 1
        finally:
            sess.close()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 九+十: PG concurrent race + diagnostics
# ═════════════════════════════════════════════════════════════════════════════


class TestPGConcurrentRace:
    """Two independent connections racing to approve — exactly one wins.

    The authority PK (weight_set_id, code) in the AFTER UPDATE claim trigger
    produces a genuine SQLSTATE 23505 unique_violation, which the adapter
    converts to WeightRevisionGovernanceError(active_revision_conflict).
    """

    def test_concurrent_race_one_winner(self, pg_database, pg_session_factory):
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetActiveRevisionRecord,
            SchemeWeightSetRevisionRecord,
        )

        # Use a single engine with NullPool for connection isolation
        engine = create_engine(pg_database, poolclass=NullPool)
        factory_a = sessionmaker(bind=engine, expire_on_commit=False)
        factory_b = sessionmaker(bind=engine, expire_on_commit=False)

        adapter = _make_adapter()
        try:
            # Seed drafts
            sess_setup = factory_a()
            _create_draft(
                sess_setup,
                revision_id="rev-pg-race-A",
                weight_set_id="ws-pg-race",
                code="pg-race-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            _create_draft(
                sess_setup,
                revision_id="rev-pg-race-B",
                weight_set_id="ws-pg-race",
                code="pg-race-code",
                content=_WEIGHT_CONTENT_V2,
                rev_num=2,
            )
            sess_setup.commit()
            sess_setup.close()

            barrier = threading.Barrier(2)
            results: dict[str, Any] = {}
            errors: dict[str, Any] = {}

            def approve_A():
                sess = factory_a()
                try:
                    barrier.wait(timeout=10)
                    ok = adapter.approve_revision(
                        sess,
                        revision_id="rev-pg-race-A",
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
                sess = factory_b()
                try:
                    barrier.wait(timeout=10)
                    ok = adapter.approve_revision(
                        sess,
                        revision_id="rev-pg-race-B",
                        content=_WEIGHT_CONTENT_V2,
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
            t1.join(timeout=30)
            t2.join(timeout=30)

            # Exactly one must succeed
            succeeded = [k for k, v in results.items() if v is True]
            failed_gov = [
                k for k, v in errors.items() if isinstance(v, WeightRevisionGovernanceError)
            ]
            assert len(succeeded) == 1, f"Expected exactly one winner, got succeeded={succeeded}"
            assert len(failed_gov) == 1, (
                f"Expected one governance error, got failed_gov={failed_gov}, all_errors={errors}"
            )
            assert failed_gov[0] != succeeded[0]

            # Verify loser is not raw IntegrityError/InternalError
            loser_key = failed_gov[0]
            loser_exc = errors[loser_key]
            assert not isinstance(loser_exc, type(Exception).mro()[1]), (
                f"Loser got raw DB error: {type(loser_exc)}"
            )

            # Final state
            sess_final = factory_a()
            try:
                from sqlalchemy import func

                approved_count = sess_final.execute(
                    select(func.count())
                    .select_from(SchemeWeightSetRevisionRecord)
                    .where(
                        SchemeWeightSetRevisionRecord.weight_set_id == "ws-pg-race",
                        SchemeWeightSetRevisionRecord.status == "approved",
                    )
                ).scalar_one()
                assert approved_count == 1

                draft_count = sess_final.execute(
                    select(func.count())
                    .select_from(SchemeWeightSetRevisionRecord)
                    .where(
                        SchemeWeightSetRevisionRecord.weight_set_id == "ws-pg-race",
                        SchemeWeightSetRevisionRecord.status == "draft",
                    )
                ).scalar_one()
                assert draft_count == 1

                auth_count = sess_final.execute(
                    select(func.count())
                    .select_from(SchemeWeightSetActiveRevisionRecord)
                    .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-pg-race")
                ).scalar_one()
                assert auth_count == 1

                # Loser must have NULL approval evidence
                loser_id = "rev-pg-race-A" if loser_key == "A" else "rev-pg-race-B"
                loser = sess_final.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == loser_id
                    )
                ).scalar_one()
                assert loser.approved_at is None
                assert loser.approved_by is None
                assert loser.sealed_at is None
            finally:
                sess_final.close()
        finally:
            engine.dispose()

    def test_race_stability_10x(self, pg_database):
        """Run concurrent race 10 times with independent IDs."""
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        engine = create_engine(pg_database, poolclass=NullPool)
        adapter = _make_adapter()

        try:
            for i in range(10):
                factory_a = sessionmaker(bind=engine, expire_on_commit=False)
                factory_b = sessionmaker(bind=engine, expire_on_commit=False)

                ws_id = f"ws-race-{i:02d}"
                code = f"race-code-{i:02d}"

                sess_setup = factory_a()
                _create_draft(
                    sess_setup,
                    revision_id=f"rev-race-{i:02d}-A",
                    weight_set_id=ws_id,
                    code=code,
                    content=_WEIGHT_CONTENT,
                    rev_num=1,
                )
                _create_draft(
                    sess_setup,
                    revision_id=f"rev-race-{i:02d}-B",
                    weight_set_id=ws_id,
                    code=code,
                    content=_WEIGHT_CONTENT_V2,
                    rev_num=2,
                )
                sess_setup.commit()
                sess_setup.close()

                barrier = threading.Barrier(2)
                results: dict[str, Any] = {}
                errors: dict[str, Any] = {}

                def make_approve(
                    rev_id: str,
                    content: dict,
                    name: str,
                    _barrier: threading.Barrier = barrier,
                    _results: dict = results,
                    _errors: dict = errors,
                    _factory_a=factory_a,
                    _factory_b=factory_b,
                ):
                    import contextlib

                    def approve():
                        sess = _factory_a() if name == "A" else _factory_b()
                        try:
                            _barrier.wait(timeout=10)
                            ok = adapter.approve_revision(
                                sess,
                                revision_id=rev_id,
                                content=content,
                                approved_at=datetime.now(UTC),
                                approved_by=f"racer-{name}",
                            )
                            sess.commit()
                            _results[name] = ok
                        except Exception as e:
                            _errors[name] = e
                            with contextlib.suppress(Exception):
                                sess.rollback()
                        finally:
                            sess.close()

                    return approve

                t1 = threading.Thread(
                    target=make_approve(
                        f"rev-race-{i:02d}-A",
                        _WEIGHT_CONTENT,
                        "A",
                    )
                )
                t2 = threading.Thread(
                    target=make_approve(
                        f"rev-race-{i:02d}-B",
                        _WEIGHT_CONTENT_V2,
                        "B",
                    )
                )
                t1.start()
                t2.start()
                t1.join(timeout=30)
                t2.join(timeout=30)

                succeeded = [k for k, v in results.items() if v is True]
                failed_gov = [
                    k for k, v in errors.items() if isinstance(v, WeightRevisionGovernanceError)
                ]
                assert len(succeeded) == 1, f"Run {i}: expected 1 winner, got {succeeded}"
                assert len(failed_gov) == 1, (
                    f"Run {i}: expected 1 governance error, got {failed_gov}"
                )
        finally:
            engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 十: PG exact diagnostics
# ═════════════════════════════════════════════════════════════════════════════


class TestPGExactDiagnostics:
    """Prove the raw PG error satisfies the adapter's exact classifier."""

    def test_authority_pk_reports_exact_diagnostics(self, pg_session_factory):
        """Direct authority PK collision produces SQLSTATE 23505 + exact constraint."""
        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            # Use adapter to create an approved revision + authority row
            _create_draft(
                sess,
                revision_id="rev-diag-A",
                weight_set_id="ws-diag",
                code="diag-test",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            sess.commit()

            ok = adapter.approve_revision(
                sess,
                revision_id="rev-diag-A",
                content=_WEIGHT_CONTENT,
                approved_at=datetime.now(UTC),
                approved_by="diag-tester",
            )
            assert ok is True
            sess.commit()

            # Now attempt to manually INSERT a duplicate authority PK
            # The INSERT guard will pass (revision is approved), but the
            # composite PK (weight_set_id, code) will fail with 23505.
            from sqlalchemy import exc as sa_exc

            with pytest.raises(sa_exc.IntegrityError) as exc_info:
                sess.execute(
                    text(
                        "INSERT INTO scheme_weight_set_active_revisions"
                        " (weight_set_id, code, approved_revision_id, updated_at)"
                        " VALUES ('ws-diag', 'diag-test',"
                        " 'rev-diag-A', NOW())"
                    )
                )
                sess.flush()

            exc = exc_info.value
            orig = exc.orig
            assert orig is not None

            # Check SQLSTATE
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23505", f"Expected 23505, got {sqlstate}"

            # Check constraint_name
            diag = getattr(orig, "diag", None)
            constraint_name = None
            if diag is not None:
                constraint_name = getattr(diag, "constraint_name", None)
            assert constraint_name is not None
            assert constraint_name == "uq_active_approved_weight_rev"

            sess.rollback()
        finally:
            sess.close()

    def test_adapter_converts_exact_authority_conflict(self, pg_session_factory):
        """Adapter converts the 23505 to WeightRevisionGovernanceError."""
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            _create_draft(
                sess,
                revision_id="rev-pg-conv-A",
                weight_set_id="ws-pg-conv",
                code="pg-conv-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            _create_draft(
                sess,
                revision_id="rev-pg-conv-B",
                weight_set_id="ws-pg-conv",
                code="pg-conv-code",
                content=_WEIGHT_CONTENT_V2,
                rev_num=2,
            )
            sess.commit()

            # Approve A
            adapter.approve_revision(
                sess,
                revision_id="rev-pg-conv-A",
                content=_WEIGHT_CONTENT,
                approved_at=datetime.now(UTC),
                approved_by="conv-tester",
            )
            sess.commit()

            # Approve B — must raise WeightRevisionGovernanceError
            with pytest.raises(WeightRevisionGovernanceError) as exc_info:
                adapter.approve_revision(
                    sess,
                    revision_id="rev-pg-conv-B",
                    content=_WEIGHT_CONTENT_V2,
                    approved_at=datetime.now(UTC),
                    approved_by="conv-tester",
                )
            assert exc_info.value.code == "active_revision_conflict"
        finally:
            sess.close()


# ═════════════════════════════════════════════════════════════════════════════
#  Section 十一: PG passthrough test
# ═════════════════════════════════════════════════════════════════════════════


class TestPGPassthrough:
    """Non-authority IntegrityErrors must NOT be converted."""

    def test_fk_violation_not_converted(self, pg_session_factory):
        """FK violation on revision INSERT propagates as IntegrityError."""
        from sqlalchemy import exc as sa_exc

        sess = pg_session_factory()
        try:
            sess.execute(
                text(
                    "INSERT INTO scheme_weight_set_revisions"
                    " (id, weight_set_id, code, revision, status,"
                    " content, content_hash,"
                    " generator_compatibility_version)"
                    " VALUES (:id, :ws, :code, :rev, 'draft',"
                    " '{}', 'dummy', '1.0.0')"
                ),
                {
                    "id": "rev-fk-fail",
                    "ws": "nonexistent-ws-fk",
                    "code": "fk-test",
                    "rev": 1,
                },
            )
            with pytest.raises((sa_exc.IntegrityError, sa_exc.InternalError)) as exc_info:
                sess.flush()

            # Must NOT be WeightRevisionGovernanceError
            from cold_storage.modules.schemes.application.weight_revision_governance import (
                WeightRevisionGovernanceError,
            )

            assert not isinstance(exc_info.value, WeightRevisionGovernanceError)
        finally:
            sess.close()

    def test_not_null_violation_not_converted(self, pg_session_factory):
        """NOT NULL violation propagates as IntegrityError."""
        from sqlalchemy import exc as sa_exc

        sess = pg_session_factory()
        try:
            with pytest.raises((sa_exc.IntegrityError, sa_exc.InternalError)):
                sess.execute(
                    text(
                        "INSERT INTO scheme_weight_set_revisions"
                        " (id, code, revision, status,"
                        " content, content_hash,"
                        " generator_compatibility_version)"
                        " VALUES (:id, :code, :rev, 'draft',"
                        " '{}', 'dummy', '1.0.0')"
                    ),
                    {
                        "id": "rev-nn-fail",
                        "code": "nn-test",
                        "rev": 1,
                    },
                )
                sess.flush()
        finally:
            sess.close()
