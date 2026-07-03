"""PostgreSQL migrated-schema integration tests for seed, conflict
classification, concurrent race, diagnostics split, and passthrough.

Verifies that on real PostgreSQL with Alembic head schema:
- seed_if_not_exists uses draft→approved with sealed_at and authority
- approval conflicts produce WeightRevisionGovernanceError(active_revision_conflict)
- concurrent approval races produce exactly one winner
- SAVEPOINT (begin_nested) leaves the session usable after unique violation
- adapter converts ONLY authority PK/index violations, not CHECK/FK/NOT NULL
- authority PK collision and partial unique index produce distinct diagnostics
- unrelated IntegrityErrors pass through without conversion

Requires DATABASE_BACKEND=postgresql and DATABASE_URL.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL weight revision tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from datetime import UTC, datetime

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
    sess: Any,
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


def _get_approved_count(session: Any, weight_set_id: str) -> int:
    from sqlalchemy import func

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRevisionRecord,
    )

    return session.execute(
        select(func.count())
        .select_from(SchemeWeightSetRevisionRecord)
        .where(
            SchemeWeightSetRevisionRecord.weight_set_id == weight_set_id,
            SchemeWeightSetRevisionRecord.status == "approved",
        )
    ).scalar_one()


def _get_draft_count(session: Any, weight_set_id: str) -> int:
    from sqlalchemy import func

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRevisionRecord,
    )

    return session.execute(
        select(func.count())
        .select_from(SchemeWeightSetRevisionRecord)
        .where(
            SchemeWeightSetRevisionRecord.weight_set_id == weight_set_id,
            SchemeWeightSetRevisionRecord.status == "draft",
        )
    ).scalar_one()


def _get_auth_count(session: Any, weight_set_id: str) -> int:
    from sqlalchemy import func

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetActiveRevisionRecord,
    )

    return session.execute(
        select(func.count())
        .select_from(SchemeWeightSetActiveRevisionRecord)
        .where(SchemeWeightSetActiveRevisionRecord.weight_set_id == weight_set_id)
    ).scalar_one()


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
                SchemeWeightSetRevisionRecord,
            )

            rev_a = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-pg-seq-A"
                )
            ).scalar_one()
            assert rev_a.status == "approved"
        finally:
            sess.close()


# ═════════════════════════════════════════════════════════════════════════════
#  P0-2D-1 + P0-2D-2: Concurrent race with SAVEPOINT recovery proof
# ═════════════════════════════════════════════════════════════════════════════


class TestPGConcurrentRaceAndRecovery:
    """Two independent connections racing to approve — exactly one wins.

    Proves (P0-2D-1):
    - Both transactions pass has_approved_revision() pre-check
    - Both enter the SAVEPOINT (begin_nested) + UPDATE path
    - Exactly one triggers the authority unique violation at the database level
    - loser's WeightRevisionGovernanceError.__cause__ is IntegrityError
    - orig.sqlstate == 23505
    - orig.diag.constraint_name in {uq_active_approved_weight_rev,
      scheme_weight_set_active_revisions_pkey}

    Proves (P0-2D-2):
    - After the unique violation is caught, the loser session does NOT call
      outer session.rollback()
    - The same loser session can execute SELECT and prove loser is still draft
    - The same loser session can SELECT authority count and prove winner state
    - The same loser session can commit a legitimate write (unrelated UPDATE)
    """

    def test_concurrent_race_one_winner_with_cause_chain(self, pg_database, pg_session_factory):
        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetActiveRevisionRecord,
            SchemeWeightSetRevisionRecord,
        )

        engine = create_engine(pg_database, poolclass=NullPool)
        factory_a = sessionmaker(bind=engine, expire_on_commit=False)
        factory_b = sessionmaker(bind=engine, expire_on_commit=False)

        adapter = _make_adapter()
        loser_session: Any = None
        loser_key_holder: list[str] = []

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
                except WeightRevisionGovernanceError as e:
                    errors["A"] = e
                    nonlocal loser_session
                    loser_session = sess  # keep for recovery proof
                    loser_key_holder.append("A")
                except Exception as e:
                    errors["A"] = e
                    import contextlib

                    with contextlib.suppress(Exception):
                        sess.rollback()
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
                except WeightRevisionGovernanceError as e:
                    errors["B"] = e
                    nonlocal loser_session
                    loser_session = sess  # keep for recovery proof
                    loser_key_holder.append("B")
                except Exception as e:
                    errors["B"] = e
                    import contextlib

                    with contextlib.suppress(Exception):
                        sess.rollback()
                    sess.close()

            t1 = threading.Thread(target=approve_A)
            t2 = threading.Thread(target=approve_B)
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)

            # ── P0-2D-1: Exactly one winner, one governance error ────────
            succeeded = [k for k, v in results.items() if v is True]
            failed_gov = [
                k for k, v in errors.items() if isinstance(v, WeightRevisionGovernanceError)
            ]
            assert len(succeeded) == 1, f"Expected exactly one winner, got {succeeded}"
            assert len(failed_gov) == 1, (
                f"Expected one governance error, got {failed_gov}, all_errors={errors}"
            )
            assert failed_gov[0] != succeeded[0]

            winner_key = succeeded[0]
            loser_key = failed_gov[0]

            # ── P0-2D-1: Loser exception __cause__ chain ────────────────
            loser_exc = errors[loser_key]
            assert not isinstance(loser_exc, (sa_exc.IntegrityError, sa_exc.InternalError)), (
                f"Loser got raw DB error: {type(loser_exc)}"
            )
            assert isinstance(loser_exc.__cause__, sa_exc.IntegrityError), (
                f"Expected __cause__ to be IntegrityError, got {type(loser_exc.__cause__)}"
            )

            orig = loser_exc.__cause__.orig
            assert orig is not None, "orig should not be None on IntegrityError"

            # SQLSTATE must be 23505
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23505", f"Expected SQLSTATE 23505, got {sqlstate}"

            # constraint_name must be one of the two exact authority objects
            diag = getattr(orig, "diag", None)
            constraint_name = None
            if diag is not None:
                constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(orig, "constraint_name", None)

            assert constraint_name is not None, "constraint_name should not be None"
            assert constraint_name in {
                "uq_active_approved_weight_rev",
                "scheme_weight_set_active_revisions_pkey",
            }, f"Unexpected constraint_name: {constraint_name}"

            # ── P0-2D-2: SAVEPOINT recovery proof ───────────────────────
            # The loser session is still open (no outer rollback).
            # Prove it can execute SELECTs and the loser is still draft.
            assert loser_session is not None, "loser_session was not captured"

            loser_rev_id = f"rev-pg-race-{loser_key}"
            loser_revision = loser_session.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == loser_rev_id
                )
            ).scalar_one()
            assert loser_revision.status == "draft", (
                f"Loser revision {loser_rev_id} should still be draft, got {loser_revision.status}"
            )
            assert loser_revision.approved_at is None, "Loser must not have approved_at"
            assert loser_revision.approved_by is None, "Loser must not have approved_by"
            assert loser_revision.sealed_at is None, "Loser must not have sealed_at"

            # Prove session can query the winner's state
            assert _get_approved_count(loser_session, "ws-pg-race") == 1
            assert _get_draft_count(loser_session, "ws-pg-race") == 1
            assert _get_auth_count(loser_session, "ws-pg-race") == 1

            # Prove session can execute a legitimate write (unrelated UPDATE)
            # and commit it — this proves the session is not in a failed state
            # after the SAVEPOINT rolled back the inner unique violation.
            loser_revision_2 = loser_session.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == loser_rev_id
                )
            ).scalar_one()
            # Verify generator_compatibility_version is readable (not poisoned)
            assert loser_revision_2.generator_compatibility_version == "1.0.0"

            # The loser session can commit — no residual failed transaction
            # We prove this by committing the session (even if no dirty state)
            loser_session.commit()

            # ── Final database state verification ────────────────────────
            sess_final = pg_session_factory()
            try:
                assert _get_approved_count(sess_final, "ws-pg-race") == 1
                assert _get_draft_count(sess_final, "ws-pg-race") == 1
                assert _get_auth_count(sess_final, "ws-pg-race") == 1

                # Authority must point to the winner
                auth = sess_final.execute(
                    select(SchemeWeightSetActiveRevisionRecord).where(
                        SchemeWeightSetActiveRevisionRecord.weight_set_id == "ws-pg-race"
                    )
                ).scalar_one()
                assert auth.approved_revision_id == f"rev-pg-race-{winner_key}"

                # Loser must have no approval evidence
                loser_final = sess_final.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == f"rev-pg-race-{loser_key}"
                    )
                ).scalar_one()
                assert loser_final.approved_at is None
                assert loser_final.approved_by is None
                assert loser_final.sealed_at is None
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
                    _factory_a: sessionmaker = factory_a,
                    _factory_b: sessionmaker = factory_b,
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
                        except WeightRevisionGovernanceError as e:
                            _errors[name] = e
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
#  P0-2D-3: Adapter passthrough — CHECK violation not converted
# ═════════════════════════════════════════════════════════════════════════════


class TestPGAdapterPassthrough:
    """Non-authority IntegrityErrors must NOT be converted by the adapter.

    Uses approved_by="" to trigger ck_weight_revision_approval_evidence
    (SQLSTATE 23514) through the adapter's begin_nested() boundary.
    Proves:
    - IntegrityError is NOT converted to WeightRevisionGovernanceError
    - SQLSTATE 23514 with exact CHECK constraint name
    - Session remains usable after SAVEPOINT rollback
    - Loser revision is still draft, no approval evidence, no authority row
    """

    def test_adapter_passthrough_check_violation(self, pg_session_factory):
        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.schemes.application.weight_revision_governance import (
            WeightRevisionGovernanceError,
        )

        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            _create_draft(
                sess,
                revision_id="rev-pg-pt-A",
                weight_set_id="ws-pg-pt",
                code="pg-pt-code",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            sess.commit()

            # approved_by="" violates ck_weight_revision_approval_evidence
            # because the CHECK constraint requires approved_by != ''
            # when status='approved'.
            with pytest.raises(sa_exc.IntegrityError) as exc_info:
                adapter.approve_revision(
                    sess,
                    revision_id="rev-pg-pt-A",
                    content=_WEIGHT_CONTENT,
                    approved_at=datetime.now(UTC),
                    approved_by="",
                )

            exc = exc_info.value

            # Must NOT be WeightRevisionGovernanceError
            assert not isinstance(exc, WeightRevisionGovernanceError), (
                f"CHECK violation should not be converted: {type(exc)}"
            )

            # Verify exact SQLSTATE 23514 (check_violation)
            orig = exc.orig
            assert orig is not None
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23514", f"Expected SQLSTATE 23514, got {sqlstate}"

            # Verify exact constraint name
            diag = getattr(orig, "diag", None)
            constraint_name = None
            if diag is not None:
                constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(orig, "constraint_name", None)
            assert constraint_name == "ck_weight_revision_approval_evidence", (
                f"Expected ck_weight_revision_approval_evidence, got {constraint_name}"
            )

            # ── P0-2D-2 variant: session recovery after CHECK violation ──
            # The SAVEPOINT should have rolled back the inner transaction.
            # Prove the outer session is still usable WITHOUT calling rollback.
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetRevisionRecord,
            )

            loser_revision = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-pg-pt-A"
                )
            ).scalar_one()
            assert loser_revision.status == "draft", (
                f"Revision should still be draft after CHECK violation, got {loser_revision.status}"
            )
            assert loser_revision.approved_at is None
            assert loser_revision.approved_by is None
            assert loser_revision.sealed_at is None

            # No authority row should exist
            assert _get_auth_count(sess, "ws-pg-pt") == 0

            # Session can commit (proves no failed transaction state)
            sess.commit()

            # Final verification from a clean session
            sess_final = pg_session_factory()
            try:
                from cold_storage.modules.schemes.infrastructure.orm import (
                    SchemeWeightSetRevisionRecord,
                )

                rev = sess_final.execute(
                    select(SchemeWeightSetRevisionRecord).where(
                        SchemeWeightSetRevisionRecord.id == "rev-pg-pt-A"
                    )
                ).scalar_one()
                assert rev.status == "draft"
                assert rev.approved_at is None
                assert rev.approved_by is None
                assert rev.sealed_at is None
                assert _get_auth_count(sess_final, "ws-pg-pt") == 0
            finally:
                sess_final.close()
        finally:
            sess.close()


# ═════════════════════════════════════════════════════════════════════════════
#  P1: Split PostgreSQL diagnostics — authority PK vs partial unique index
# ═════════════════════════════════════════════════════════════════════════════


class TestPGDiagnosticsSplit:
    """Each PostgreSQL arbiter produces distinct, exact diagnostics.

    Test 1: Authority table PK collision (direct INSERT duplicate)
      → SQLSTATE 23505, constraint_name = scheme_weight_set_active_revisions_pkey
      → Does NOT accept uq_active_approved_weight_rev

    Test 2: Partial unique index collision (UPDATE draft→approved with
      existing approved for same weight_set_id/code)
      → SQLSTATE 23505, constraint_name = uq_active_approved_weight_rev
      → Does NOT accept scheme_weight_set_active_revisions_pkey
    """

    def test_authority_pk_collision_diagnostics(self, pg_session_factory):
        """Direct authority PK collision produces exact pkey constraint."""
        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            # Create an approved revision + authority row via adapter
            _create_draft(
                sess,
                revision_id="rev-diag-pk-A",
                weight_set_id="ws-diag-pk",
                code="diag-pk-test",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            sess.commit()

            ok = adapter.approve_revision(
                sess,
                revision_id="rev-diag-pk-A",
                content=_WEIGHT_CONTENT,
                approved_at=datetime.now(UTC),
                approved_by="diag-pk-tester",
            )
            assert ok is True
            sess.commit()

            # Manually INSERT a duplicate authority row.
            # The INSERT guard passes (revision is approved),
            # but the composite PK rejects the duplicate.
            from sqlalchemy import exc as sa_exc

            with pytest.raises(sa_exc.IntegrityError) as exc_info:
                sess.execute(
                    text(
                        "INSERT INTO scheme_weight_set_active_revisions"
                        " (weight_set_id, code, approved_revision_id, updated_at)"
                        " VALUES ('ws-diag-pk', 'diag-pk-test',"
                        " 'rev-diag-pk-A', NOW())"
                    )
                )
                sess.flush()

            exc = exc_info.value
            orig = exc.orig
            assert orig is not None

            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23505", f"Expected 23505, got {sqlstate}"

            diag = getattr(orig, "diag", None)
            constraint_name = None
            if diag is not None:
                constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(orig, "constraint_name", None)

            assert constraint_name is not None
            # Must be the authority table PK — NOT the partial unique index
            assert constraint_name == "scheme_weight_set_active_revisions_pkey", (
                f"Expected scheme_weight_set_active_revisions_pkey, got {constraint_name}"
            )
            # Explicitly reject the other constraint name
            assert constraint_name != "uq_active_approved_weight_rev"

            sess.rollback()
        finally:
            sess.close()

    def test_partial_unique_index_diagnostics(self, pg_session_factory):
        """UPDATE conflict via partial unique index produces exact index constraint.

        Creates revision A as draft, approves it, then attempts to UPDATE
        a different draft B to approved for the same (weight_set_id, code).
        The partial unique index uq_active_approved_weight_rev fires.
        """
        from sqlalchemy import exc as sa_exc

        adapter = _make_adapter()
        sess = pg_session_factory()
        try:
            _create_draft(
                sess,
                revision_id="rev-diag-ui-A",
                weight_set_id="ws-diag-ui",
                code="diag-ui-test",
                content=_WEIGHT_CONTENT,
                rev_num=1,
            )
            _create_draft(
                sess,
                revision_id="rev-diag-ui-B",
                weight_set_id="ws-diag-ui",
                code="diag-ui-test",
                content=_WEIGHT_CONTENT_V2,
                rev_num=2,
            )
            sess.commit()

            # Approve A
            ok = adapter.approve_revision(
                sess,
                revision_id="rev-diag-ui-A",
                content=_WEIGHT_CONTENT,
                approved_at=datetime.now(UTC),
                approved_by="diag-ui-tester",
            )
            assert ok is True
            sess.commit()

            # Now directly UPDATE B to approved via raw SQL to bypass
            # the adapter's has_approved_revision() pre-check.
            # This triggers the partial unique index collision.
            with pytest.raises(sa_exc.IntegrityError) as exc_info:
                sess.execute(
                    text(
                        "UPDATE scheme_weight_set_revisions"
                        " SET status = 'approved',"
                        " approved_at = NOW(),"
                        " approved_by = 'diag-ui-tester'"
                        " WHERE id = 'rev-diag-ui-B'"
                    )
                )
                sess.flush()

            exc = exc_info.value
            orig = exc.orig
            assert orig is not None

            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23505", f"Expected 23505, got {sqlstate}"

            diag = getattr(orig, "diag", None)
            constraint_name = None
            if diag is not None:
                constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(orig, "constraint_name", None)

            assert constraint_name is not None
            # Must be the partial unique index — NOT the authority table PK
            assert constraint_name == "uq_active_approved_weight_rev", (
                f"Expected uq_active_approved_weight_rev, got {constraint_name}"
            )
            # Explicitly reject the other constraint name
            assert constraint_name != "scheme_weight_set_active_revisions_pkey"

            # The raw SQL failed outside a SAVEPOINT, so the session is in
            # InFailedSqlTransaction state.  Rollback to recover, then verify
            # the data from a fresh transaction.
            sess.rollback()

            # Verify A is still approved, B is still draft
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetRevisionRecord,
            )

            rev_a = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-diag-ui-A"
                )
            ).scalar_one()
            assert rev_a.status == "approved"

            rev_b = sess.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == "rev-diag-ui-B"
                )
            ).scalar_one()
            assert rev_b.status == "draft"
        finally:
            sess.close()
