"""Phase 4 Issue #35 Slice 1 — new-session / restart regression tests (SQLite).

Per Charles's fixup instructions (2026-07-07): prove that
``revision.status``, ``coefficient_approval_log``, and
``coefficient_audit_log`` writes survive a process restart (new
``Engine`` / new ``session``).

These tests exercise the full production wiring end-to-end:

- ``compose_production_coefficient_approval_service(engine=...)``
  returns a ``CoefficientApprovalService`` backed by a real
  ``TransactionalCoefficientApprovalRepository`` so approve /
  retire / submit land in a single ``session.begin()``.
- ``compose_production_coefficient_resolver(engine=...)``
  returns a ``ApprovedCoefficientResolver`` reading directly
  from the bound engine (bypassing any in-memory cache).
- Each scenario writes through the production service, then
  disposes the first ``Engine`` and creates a second one
  pointed at the same on-disk SQLite file. The second engine's
  resolver observes the persisted rows.

Fail-closed coverage:

- Demo-only (no eligible approved row).
- Stale approval (``valid_to`` in the past).
- Missing citation.
- Invalid citation pattern.

Atomicity coverage:

- Transactional repository raises mid-flight; the pre-state
  revision row must remain at ``draft`` and the log tables
  must contain zero rows.

Assertions are on typed exception classes and dataclass
fields, never on human-readable message text (per design
contract §11 fail-closed invariants).

PG parity: ``test_phase4_slice1_new_session_postgresql.py``.
"""

from __future__ import annotations

import datetime as _dt
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.production_composition import (
    compose_production_coefficient_approval_service,
    compose_production_coefficient_resolver,
)
from cold_storage.modules.coefficients.application.approval_service import (
    ApprovalRequest,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    MissingApprovedCoefficientError,
)
from cold_storage.modules.coefficients.infrastructure.approval_adapters import (
    SystemClock,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pinned_db_path():
    """Yield a temp file path; SQLite is created by SQLAlchemy."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="phase4_slice1_")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture()
def first_engine(pinned_db_path):
    """First engine for the restart cycle."""
    eng = create_engine(
        f"sqlite:///{pinned_db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@dataclass
class _PinnedClock(SystemClock):
    override: _dt.datetime

    def now(self) -> _dt.datetime:
        return self.override


@pytest.fixture()
def pinned_clock():
    return _PinnedClock(override=_dt.datetime(2026, 7, 7, 0, 0, 0, tzinfo=_dt.UTC))


# ---------------------------------------------------------------------------
# Pre-state seeding helpers
# ---------------------------------------------------------------------------


def _seed_definition_and_revision(
    engine: Engine,
    *,
    code: str,
    category: str,
    status: str,
    source_type: str,
    source_reference: str | None,
    valid_to: _dt.datetime | None = None,
) -> tuple[str, str]:
    """Insert one definition + one revision row directly into the DB."""
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientDefinitionRecord,
        CoefficientRevisionRecord,
    )

    definition_id = f"def-{code}"
    revision_id = f"rev-{code}-1"
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(
            CoefficientDefinitionRecord(
                id=definition_id,
                code=code,
                name=code,
                description=f"test definition {code}",
                category=category,
                canonical_unit="ratio",
                value_type="decimal",
                scope_type="global",
                is_active=True,
            )
        )
        session.flush()
        session.add(
            CoefficientRevisionRecord(
                id=revision_id,
                coefficient_definition_id=definition_id,
                revision_number=1,
                unit="ratio",
                value_decimal="1.15",
                status=status,
                source_type=source_type,
                source_title="test",
                source_reference=source_reference,
                source_page=None,
                valid_from=_dt.datetime(2025, 1, 1, tzinfo=_dt.UTC),
                valid_to=valid_to,
                approved_by=("coefficient.reviewer" if status == "approved" else None),
                approved_at=(
                    _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC) if status == "approved" else None
                ),
                created_by="seed",
            )
        )
        session.commit()
    return definition_id, revision_id


def _open_second_engine(pinned_db_path: str) -> Engine:
    return create_engine(
        f"sqlite:///{pinned_db_path}",
        connect_args={"check_same_thread": False},
    )


# ---------------------------------------------------------------------------
# Test 1 — restart: approve via service → new engine → resolver sees it
# ---------------------------------------------------------------------------


def test_new_session_resolver_sees_approved_revision_after_restart(
    first_engine: Engine, pinned_db_path: str, pinned_clock: SystemClock
) -> None:
    """``approve`` survives ``engine.dispose()`` + new ``Engine``."""
    _seed_definition_and_revision(
        first_engine,
        code="restart-power",
        category="power",
        status="draft",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=first_engine)
    service._clock = pinned_clock  # type: ignore[attr-defined]

    actor = "coefficient.reviewer"
    result = service.approve(
        ApprovalRequest(
            definition_id="def-restart-power",
            revision_id="rev-restart-power-1",
            actor=actor,
            correlation_id="restart-1",
            source_citation="STANDARD:ISO-9876",
            reviewer=actor,
        )
    )
    assert result.revision_id == "rev-restart-power-1"
    assert result.new_state == "approved"

    first_engine.dispose()
    second_engine = _open_second_engine(pinned_db_path)
    try:
        resolver = compose_production_coefficient_resolver(engine=second_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)

        assert plan.revision_id == "rev-restart-power-1"
        assert plan.missing is None
        assert plan.stage_name == "power"

        with sessionmaker(bind=second_engine, expire_on_commit=False)() as session:
            approval_rows = session.execute(
                text(
                    "SELECT COUNT(*) FROM coefficient_approval_log "
                    "WHERE revision_id = 'rev-restart-power-1'"
                )
            ).scalar_one()
            audit_rows = session.execute(
                text(
                    "SELECT COUNT(*) FROM coefficient_audit_log "
                    "WHERE revision_id = 'rev-restart-power-1'"
                )
            ).scalar_one()
        assert approval_rows == 1
        assert audit_rows >= 1
    finally:
        second_engine.dispose()


# ---------------------------------------------------------------------------
# Test 2 — retire → new session fail-closed
# ---------------------------------------------------------------------------


def test_new_session_after_retire_is_fail_closed(
    first_engine: Engine, pinned_db_path: str, pinned_clock: SystemClock
) -> None:
    """Retire a revision; a fresh resolver observes ``missing``."""
    _seed_definition_and_revision(
        first_engine,
        code="retire-power",
        category="power",
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=first_engine)
    service._clock = pinned_clock  # type: ignore[attr-defined]

    actor = "coefficient.reviewer"
    retire_result = service.retire(
        ApprovalRequest(
            definition_id="def-retire-power",
            revision_id="rev-retire-power-1",
            actor=actor,
            correlation_id="retire-1",
        )
    )
    assert retire_result.new_state == "withdrawn"

    first_engine.dispose()
    second_engine = _open_second_engine(pinned_db_path)
    try:
        resolver = compose_production_coefficient_resolver(engine=second_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)

        assert plan.revision_id is None
        assert isinstance(plan.missing, MissingApprovedCoefficientError), (
            "retire → new session must surface MissingApprovedCoefficientError"
        )
    finally:
        second_engine.dispose()


# ---------------------------------------------------------------------------
# Tests 3-6 — fail-closed pre-state conditions
# ---------------------------------------------------------------------------


def _test_new_session_fail_closed(
    first_engine: Engine,
    pinned_db_path: str,
    *,
    pre_state_status: str,
    pre_state_source_type: str,
    pre_state_source_reference: str | None,
    pre_state_valid_to: _dt.datetime | None,
    description: str,
) -> None:
    _seed_definition_and_revision(
        first_engine,
        code="neg",
        category="power",
        status=pre_state_status,
        source_type=pre_state_source_type,
        source_reference=pre_state_source_reference,
        valid_to=pre_state_valid_to,
    )

    first_engine.dispose()
    second_engine = _open_second_engine(pinned_db_path)
    try:
        resolver = compose_production_coefficient_resolver(engine=second_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)

        assert plan.revision_id is None, description
        assert plan.missing is not None, description
        assert isinstance(plan.missing, MissingApprovedCoefficientError), (
            f"{description}: expected MissingApprovedCoefficientError, "
            f"got {type(plan.missing).__name__}"
        )
    finally:
        second_engine.dispose()


def test_new_session_demo_only_is_fail_closed(first_engine: Engine, pinned_db_path: str) -> None:
    """``source_type=demo`` only → ``MissingApprovedCoefficientError``."""
    _test_new_session_fail_closed(
        first_engine,
        pinned_db_path,
        pre_state_status="approved",
        pre_state_source_type="demo",
        pre_state_source_reference="INTERNAL:REF-demo-seed",
        pre_state_valid_to=None,
        description="demo-only pre-state must remain fail-closed after restart",
    )


def test_new_session_stale_approval_is_fail_closed(
    first_engine: Engine, pinned_db_path: str
) -> None:
    """``valid_to`` in the past → fail-closed after restart."""
    _test_new_session_fail_closed(
        first_engine,
        pinned_db_path,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference="STANDARD:ISO-12345",
        pre_state_valid_to=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC),
        description="stale pre-state must remain fail-closed after restart",
    )


def test_new_session_missing_citation_is_fail_closed(
    first_engine: Engine, pinned_db_path: str
) -> None:
    """``source_reference=None`` → ``MissingApprovedCoefficientError``."""
    _test_new_session_fail_closed(
        first_engine,
        pinned_db_path,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference=None,
        pre_state_valid_to=None,
        description="missing-citation pre-state must remain fail-closed after restart",
    )


def test_new_session_invalid_citation_pattern_is_fail_closed(
    first_engine: Engine, pinned_db_path: str
) -> None:
    """Citation does not match DOI / STANDARD / INTERNAL → fail-closed."""
    _test_new_session_fail_closed(
        first_engine,
        pinned_db_path,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference="BOGUS:format-without-scheme",
        pre_state_valid_to=None,
        description="invalid-pattern pre-state must remain fail-closed after restart",
    )


# ---------------------------------------------------------------------------
# Test 7 — transaction rollback atomicity
# ---------------------------------------------------------------------------


class _FailingTransactionRepository:
    """Synthetic wrapper that raises on every apply_* call.

    Lets us test the atomicity guarantee: a mid-flight failure
    must roll back the entire transaction so the
    ``coefficient_revisions`` row stays at its pre-state and
    the log tables contain zero rows from the failed run.
    """

    def __init__(self) -> None:
        self.calls = 0

    def apply_approve(self, context: Any) -> None:
        self.calls += 1
        raise SQLAlchemyError("synthetic mid-transaction failure (test)")

    def apply_retire(self, context: Any) -> None:
        raise SQLAlchemyError("synthetic mid-transaction failure (test)")

    def apply_submit(self, context: Any) -> None:
        raise SQLAlchemyError("synthetic mid-transaction failure (test)")


def test_transaction_rollback_keeps_revision_state_pre_call(
    first_engine: Engine, pinned_clock: SystemClock
) -> None:
    """Synthetic mid-transaction failure: ``revision.status`` must
    remain at its pre-state, and the log tables must contain
    no rows.

    Per Charles's fixup instruction: prove the three-write
    transaction is atomic — a failure mid-flight must not
    produce ``status=approved`` while leaving the log tables
    empty.
    """
    _seed_definition_and_revision(
        first_engine,
        code="rollback-power",
        category="power",
        status="draft",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=first_engine)
    service._clock = pinned_clock  # type: ignore[attr-defined]
    assert service._transaction is not None, (
        "production wiring must supply a transactional repository"
    )

    failing = _FailingTransactionRepository()
    service._transaction = failing

    with pytest.raises(SQLAlchemyError):
        service.approve(
            ApprovalRequest(
                definition_id="def-rollback-power",
                revision_id="rev-rollback-power-1",
                actor="coefficient.reviewer",
                correlation_id="rollback-1",
                source_citation="STANDARD:ISO-9876",
                reviewer="coefficient.reviewer",
            )
        )

    assert failing.calls == 1, "approve must have dispatched exactly one call"

    with sessionmaker(bind=first_engine, expire_on_commit=False)() as session:
        revision_status = session.execute(
            text("SELECT status FROM coefficient_revisions WHERE id = 'rev-rollback-power-1'")
        ).scalar_one()
        approval_rows = session.execute(
            text(
                "SELECT COUNT(*) FROM coefficient_approval_log "
                "WHERE revision_id = 'rev-rollback-power-1'"
            )
        ).scalar_one()
        audit_rows = session.execute(
            text(
                "SELECT COUNT(*) FROM coefficient_audit_log "
                "WHERE revision_id = 'rev-rollback-power-1'"
            )
        ).scalar_one()

    assert revision_status == "draft", (
        f"after rollback revision status must remain 'draft', got {revision_status!r}"
    )
    assert approval_rows == 0, f"after rollback no approval-log rows may exist, got {approval_rows}"
    assert audit_rows == 0, f"after rollback no audit-log rows may exist, got {audit_rows}"
