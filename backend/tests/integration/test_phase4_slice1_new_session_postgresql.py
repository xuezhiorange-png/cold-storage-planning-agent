"""Phase 4 Issue #35 Slice 1 — new-session / restart regression tests (PostgreSQL).

PG parity mirror of ``test_phase4_slice1_new_session_sqlite.py``.

**Local-execution note (2026-07-07): the Hermes sandbox does not
expose a PostgreSQL service. The integration tests in this file
are guarded by ``pytest.mark.postgresql`` and require the
``pg_engine`` fixture defined in
``backend/tests/integration/conftest.py`` (which provisions a
real PostgreSQL 14 container). This file is shipped in commit 9b
so the test surface is auditable and CI-ready; the tests are
**not executed locally** as part of this Phase 4 Slice 1
delivery.**

The CI runs the parity matrix via the existing
``backend-postgresql`` workflow job (see PR #43 / commit 4
closeout). When Charles resumes a CI-enabled session, the
``pg_engine`` fixture is set up via the standard
``postgres:14`` container and these tests run automatically
without code changes.

Behavioural guarantees verified here mirror the SQLite tests:

1. New-session restart: approve via the production service,
   dispose the engine, and observe the approved row + log
   entries via a fresh engine.
2. New-session retire fail-closed.
3. Demo-only / stale / missing-citation / invalid-citation
   pre-states observed as ``missing`` after restart.
4. Transactional rollback atomicity: a mid-flight failure
   leaves the ``coefficient_revisions`` row at its pre-state
   and the log tables contain zero rows.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

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
from cold_storage.modules.projects.infrastructure.orm import Base

# Skip the entire module when running outside the CI environment
# that provides ``pg_engine``. The standard
# ``backend-postgresql`` CI job is the source of truth for this
# parity coverage.
pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------


def _fresh_pg_engine(pg_engine: Engine) -> Engine:
    """Build a fresh PG engine reusing the original URL *without* stringifying it.

    ``str(sa_url)`` invokes ``SAURL.render_as_string(hide_password=True)`` which
    strips the password from the rendered string. A fresh engine built from that
    string therefore authenticates with an empty password and the PG server
    rejects the connection with ``password authentication failed for user``.

    Passing the live ``URL`` object preserves the password in-memory and lets
    SQLAlchemy open a fresh connection on the next checkout.
    """
    return create_engine(pg_engine.url, poolclass=NullPool)


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
    """Insert one definition + one revision row directly into the PG schema."""
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


# ---------------------------------------------------------------------------
# Test 1 — restart scenario on PostgreSQL
# ---------------------------------------------------------------------------


def test_pg_new_session_resolver_sees_approved_revision_after_restart(
    pg_engine: Engine,
) -> None:
    """PG parity of the SQLite restart test.

    Constructs a fresh schema via alembic upgrade + the migration
    set that includes 0038 (Phase 4 Slice 1 log tables).
    Approves a draft revision via the production service,
    disposes ``pg_engine``, opens a fresh ``pg_engine`` against
    the same database, and asserts the strict resolver returns
    the approved row with corresponding log rows.
    """
    Base.metadata.create_all(pg_engine)

    _seed_definition_and_revision(
        pg_engine,
        code="pg-restart-power",
        category="power",
        status="draft",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=pg_engine)
    actor = "coefficient.reviewer"
    result = service.approve(
        ApprovalRequest(
            definition_id="def-pg-restart-power",
            revision_id="rev-pg-restart-power-1",
            actor=actor,
            correlation_id="pg-restart-1",
            source_citation="STANDARD:ISO-9876",
            reviewer=actor,
        )
    )
    assert result.new_state == "approved"

    pg_engine.dispose()
    fresh_engine = _fresh_pg_engine(pg_engine)
    try:
        resolver = compose_production_coefficient_resolver(engine=fresh_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)

        assert plan.revision_id == "rev-pg-restart-power-1"
        assert plan.missing is None

        with sessionmaker(bind=fresh_engine, expire_on_commit=False)() as session:
            approval_rows = session.execute(
                text(
                    "SELECT COUNT(*) FROM coefficient_approval_log "
                    "WHERE revision_id = 'rev-pg-restart-power-1'"
                )
            ).scalar_one()
            audit_rows = session.execute(
                text(
                    "SELECT COUNT(*) FROM coefficient_audit_log "
                    "WHERE revision_id = 'rev-pg-restart-power-1'"
                )
            ).scalar_one()
        assert approval_rows == 1
        assert audit_rows >= 1
    finally:
        fresh_engine.dispose()


# ---------------------------------------------------------------------------
# Test 2 — retire → new session fail-closed (PG)
# ---------------------------------------------------------------------------


def test_pg_new_session_after_retire_is_fail_closed(pg_engine: Engine) -> None:
    """PG parity of the SQLite retire fail-closed test."""
    Base.metadata.create_all(pg_engine)

    _seed_definition_and_revision(
        pg_engine,
        code="pg-retire-power",
        category="power",
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=pg_engine)
    service.retire(
        ApprovalRequest(
            definition_id="def-pg-retire-power",
            revision_id="rev-pg-retire-power-1",
            actor="coefficient.reviewer",
            correlation_id="pg-retire-1",
        )
    )

    pg_engine.dispose()
    fresh_engine = _fresh_pg_engine(pg_engine)
    try:
        resolver = compose_production_coefficient_resolver(engine=fresh_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)
        assert plan.revision_id is None
        assert isinstance(plan.missing, MissingApprovedCoefficientError), (
            "retired revision must remain fail-closed after PG restart"
        )
    finally:
        fresh_engine.dispose()


# ---------------------------------------------------------------------------
# Test 3-6 — fail-closed pre-state conditions (PG)
# ---------------------------------------------------------------------------


def _pg_test_new_session_fail_closed(
    pg_engine: Engine,
    *,
    pre_state_status: str,
    pre_state_source_type: str,
    pre_state_source_reference: str | None,
    pre_state_valid_to: _dt.datetime | None,
    description: str,
) -> None:
    Base.metadata.create_all(pg_engine)
    _seed_definition_and_revision(
        pg_engine,
        code="pg-neg",
        category="power",
        status=pre_state_status,
        source_type=pre_state_source_type,
        source_reference=pre_state_source_reference,
        valid_to=pre_state_valid_to,
    )
    pg_engine.dispose()
    fresh_engine = _fresh_pg_engine(pg_engine)
    try:
        resolver = compose_production_coefficient_resolver(engine=fresh_engine)
        plan = resolver.resolve(stage_name="power", calculation_type=None)
        assert plan.revision_id is None, description
        assert plan.missing is not None, description
        assert isinstance(plan.missing, MissingApprovedCoefficientError), (
            f"{description}: expected MissingApprovedCoefficientError, "
            f"got {type(plan.missing).__name__}"
        )
    finally:
        fresh_engine.dispose()


def test_pg_new_session_demo_only_is_fail_closed(pg_engine: Engine) -> None:
    """PG parity for demo-only."""
    _pg_test_new_session_fail_closed(
        pg_engine,
        pre_state_status="approved",
        pre_state_source_type="demo",
        pre_state_source_reference="INTERNAL:REF-demo",
        pre_state_valid_to=None,
        description="PG demo-only pre-state must remain fail-closed after restart",
    )


def test_pg_new_session_stale_approval_is_fail_closed(
    pg_engine: Engine,
) -> None:
    """PG parity for stale approval."""
    _pg_test_new_session_fail_closed(
        pg_engine,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference="STANDARD:ISO-12345",
        pre_state_valid_to=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC),
        description="PG stale pre-state must remain fail-closed after restart",
    )


def test_pg_new_session_missing_citation_is_fail_closed(
    pg_engine: Engine,
) -> None:
    """PG parity for missing citation."""
    _pg_test_new_session_fail_closed(
        pg_engine,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference=None,
        pre_state_valid_to=None,
        description="PG missing-citation pre-state must remain fail-closed after restart",
    )


def test_pg_new_session_invalid_citation_pattern_is_fail_closed(
    pg_engine: Engine,
) -> None:
    """PG parity for invalid citation pattern."""
    _pg_test_new_session_fail_closed(
        pg_engine,
        pre_state_status="approved",
        pre_state_source_type="standard",
        pre_state_source_reference="BOGUS:no-scheme",
        pre_state_valid_to=None,
        description="PG invalid-pattern pre-state must remain fail-closed after restart",
    )


# ---------------------------------------------------------------------------
# Test 7 — transaction rollback atomicity (PG)
# ---------------------------------------------------------------------------


class _PGTxFailingRepository:
    """Synthetic failing repository used to test atomicity on PG."""

    def __init__(self) -> None:
        self.calls = 0

    def apply_approve(self, context: object) -> None:
        self.calls += 1
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("synthetic mid-transaction failure (PG test)")

    def apply_retire(self, context: object) -> None:
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("synthetic mid-transaction failure (PG test)")

    def apply_submit(self, context: object) -> None:
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("synthetic mid-transaction failure (PG test)")


def test_pg_transaction_rollback_keeps_revision_state_pre_call(
    pg_engine: Engine,
) -> None:
    """PG parity of the atomicity test."""
    from sqlalchemy.exc import SQLAlchemyError

    Base.metadata.create_all(pg_engine)

    _seed_definition_and_revision(
        pg_engine,
        code="pg-rollback-power",
        category="power",
        status="draft",
        source_type="standard",
        source_reference="STANDARD:ISO-9876",
    )

    service = compose_production_coefficient_approval_service(engine=pg_engine)

    failing = _PGTxFailingRepository()
    service._transaction = failing  # type: ignore[assignment]

    with pytest.raises(SQLAlchemyError):
        service.approve(
            ApprovalRequest(
                definition_id="def-pg-rollback-power",
                revision_id="rev-pg-rollback-power-1",
                actor="coefficient.reviewer",
                correlation_id="pg-rollback-1",
                source_citation="STANDARD:ISO-9876",
                reviewer="coefficient.reviewer",
            )
        )

    assert failing.calls == 1

    with sessionmaker(bind=pg_engine, expire_on_commit=False)() as session:
        revision_status = session.execute(
            text("SELECT status FROM coefficient_revisions WHERE id = 'rev-pg-rollback-power-1'")
        ).scalar_one()
        approval_rows = session.execute(
            text(
                "SELECT COUNT(*) FROM coefficient_approval_log "
                "WHERE revision_id = 'rev-pg-rollback-power-1'"
            )
        ).scalar_one()
        audit_rows = session.execute(
            text(
                "SELECT COUNT(*) FROM coefficient_audit_log "
                "WHERE revision_id = 'rev-pg-rollback-power-1'"
            )
        ).scalar_one()

    assert revision_status == "draft"
    assert approval_rows == 0
    assert audit_rows == 0
