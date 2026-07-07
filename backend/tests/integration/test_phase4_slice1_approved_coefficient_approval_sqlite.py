"""Phase 4 Issue #35 Slice 1 — integration tests (SQLite).

Five fail-closed integration tests covering the strict
``ApprovedCoefficientResolver`` against a real SQLite database.
Charles's Slice 1 boundary correction (2026-07-07) limits these to
SQLite; PostgreSQL parity coverage is deferred to a later Slice
together with the Phase 4 test parity work. The tests are written
against the production ``SqlAlchemyCoefficientRevisionReadAdapter``
so the end-to-end DB round-trip is exercised.

Test cases (per Charles's Slice 1 instruction §5.6 + §10 parity
matrix, applied to the strict resolver):

1. **Missing required approved coefficient** — no row for the
   requested (stage, calc_type). Resolver returns a plan with
   ``missing`` carrying ``MissingApprovedCoefficientError``.
2. **Demo coefficients only** — only ``source_type=demo`` rows
   exist. Resolver returns missing (production rejects demo).
3. **Stale approval** — only approved row has ``valid_to`` in
   the past. Resolver returns missing (stale = no eligible).
4. **Missing citation** — approved row's ``source_reference`` is
   empty/None. Resolver returns missing.
5. **Invalid citation pattern** — approved row's
   ``source_reference`` carries an unknown pattern. Resolver
   returns missing.

Each test uses ``Base.metadata.create_all(engine)`` to lay down
the schema (including the two log tables added by migration 0038
in the production path). The tests do NOT run alembic against
the temp engine; the migration exists for the production
``alembic upgrade head`` path, and the test path uses the
ORM's table DDL directly.

Per design contract §11 fail-closed invariants, no test asserts
on the human-readable message text — assertions are on typed
exception classes and on dataclass fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.coefficients.application.resolver import (
    ApprovedCoefficientResolver,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    MissingApprovedCoefficientError,
)
from cold_storage.modules.coefficients.infrastructure.approval_adapters import (
    SqlAlchemyCoefficientRevisionReadAdapter,
    SystemClock,
)
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """Build a fresh in-memory SQLite engine with every ORM table present."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def pinned_clock():
    """A pinned clock so ``valid_to`` staleness is deterministic."""

    class _PinnedClock(SystemClock):
        def __init__(self) -> None:
            super().__init__()
            self._now = datetime(2026, 7, 7, 0, 0, 0, tzinfo=UTC)

        def now(self) -> datetime:
            return self._now

    return _PinnedClock()


@pytest.fixture()
def read_adapter(engine):
    return SqlAlchemyCoefficientRevisionReadAdapter(engine)


@pytest.fixture()
def resolver(read_adapter, pinned_clock):
    return ApprovedCoefficientResolver(read_adapter, pinned_clock)


def _seed_definition(session, *, code: str, category: str) -> CoefficientDefinitionRecord:
    definition = CoefficientDefinitionRecord(
        id=f"def-{code}",
        code=code,
        name=code,
        description=f"Test def {code}",
        category=category,
        canonical_unit="ratio",
        value_type="decimal",
        scope_type="global",
        is_active=True,
    )
    session.add(definition)
    session.flush()
    return definition


def _seed_revision(
    session,
    *,
    definition: CoefficientDefinitionRecord,
    status: str = "approved",
    source_type: str = "standard",
    source_reference: str | None = "STANDARD:ISO-12345",
    valid_to: datetime | None = None,
    revision_number: int = 1,
) -> CoefficientRevisionRecord:
    revision = CoefficientRevisionRecord(
        id=f"rev-{definition.code}-{revision_number}",
        coefficient_definition_id=definition.id,
        revision_number=revision_number,
        unit="ratio",
        value_decimal="1.15",
        status=status,
        source_type=source_type,
        source_title="test",
        source_reference=source_reference,
        source_page=None,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
        valid_to=valid_to,
        approved_by="coefficient.reviewer" if status == "approved" else None,
        approved_at=datetime(2026, 1, 1, tzinfo=UTC) if status == "approved" else None,
        created_by="system",
    )
    session.add(revision)
    session.flush()
    return revision


# ---------------------------------------------------------------------------
# Test 1: Missing required approved coefficient
# ---------------------------------------------------------------------------


def test_resolver_missing_approved_returns_typed_missing_error(resolver, session_factory) -> None:
    """No row exists for the requested stage -> typed missing error."""
    with session_factory() as session:
        # Seed an unrelated definition so the DB is non-empty.
        defn = _seed_definition(session, code="other.thing", category="other")
        _seed_revision(session, definition=defn)

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert plan.missing is not None
    assert isinstance(plan.missing, MissingApprovedCoefficientError), (
        f"expected typed MissingApprovedCoefficientError, got {type(plan.missing).__name__}"
    )
    assert plan.missing.stage_name == "power"
    assert plan.missing.calculation_type is None


# ---------------------------------------------------------------------------
# Test 2: Demo coefficients only
# ---------------------------------------------------------------------------


def test_resolver_demo_only_returns_typed_missing_error(resolver, session_factory) -> None:
    """Only ``source_type=demo`` rows exist for the stage -> typed missing error."""
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="demo",
            source_reference="INTERNAL:REF-demo-seed",
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert isinstance(plan.missing, MissingApprovedCoefficientError), (
        "demo-only pool must surface MissingApprovedCoefficientError"
    )


# ---------------------------------------------------------------------------
# Test 3: Stale approval (past valid_to)
# ---------------------------------------------------------------------------


def test_resolver_stale_approval_returns_typed_missing_error(
    resolver, session_factory, pinned_clock
) -> None:
    """Only approved row has ``valid_to`` in the past -> typed missing error.

    Pinned clock is 2026-07-07 00:00 UTC; ``valid_to`` set to
    2026-01-01 (already past) so ``is_stale`` returns True.
    """
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-12345",
            valid_to=datetime(2026, 1, 1, tzinfo=UTC),
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert isinstance(plan.missing, MissingApprovedCoefficientError), (
        "stale approval must surface MissingApprovedCoefficientError, not silent fallback"
    )


# ---------------------------------------------------------------------------
# Test 4: Missing citation
# ---------------------------------------------------------------------------


def test_resolver_missing_citation_returns_typed_missing_error(resolver, session_factory) -> None:
    """Approved row but ``source_reference`` is empty -> typed missing error."""
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="",
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert isinstance(plan.missing, MissingApprovedCoefficientError), (
        "missing citation must surface MissingApprovedCoefficientError"
    )


# ---------------------------------------------------------------------------
# Test 5: Invalid citation pattern
# ---------------------------------------------------------------------------


def test_resolver_invalid_citation_returns_typed_missing_error(resolver, session_factory) -> None:
    """Approved row with a malformed citation -> typed missing error."""
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="unsupported:raw-text-no-scheme",
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert isinstance(plan.missing, MissingApprovedCoefficientError), (
        "invalid citation pattern must surface MissingApprovedCoefficientError"
    )


# ---------------------------------------------------------------------------
# Negative-shape sanity: the resolver never silently picks a row.
# ---------------------------------------------------------------------------


def test_resolver_never_returns_revision_id_when_no_eligible_row(resolver, session_factory) -> None:
    """A sanity check that no positive ``revision_id`` is returned when
    eligible is empty. Combines multiple fail conditions in one DB seed.
    """
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        # Mix: 1 demo, 1 stale, 1 missing-citation
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="demo",
            source_reference="INTERNAL:REF-demo",
            revision_number=1,
        )
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-12345",
            valid_to=datetime(2026, 1, 1, tzinfo=UTC),
            revision_number=2,
        )
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="",
            revision_number=3,
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is None
    assert isinstance(plan.missing, MissingApprovedCoefficientError)


# ---------------------------------------------------------------------------
# Happy-path: exactly one eligible row is resolved without error.
# (Mirror of contract §10 parity row 'CoefficientApprovalService state
# machine' — added here as a healthy baseline so Slice 1's
# pass conditions are visible.)
# ---------------------------------------------------------------------------


def test_resolver_happy_path_resolves_single_eligible_row(resolver, session_factory) -> None:
    """One approved + non-demo + unexpired + cited row exists -> resolved."""
    with session_factory() as session:
        defn = _seed_definition(session, code="power.margin", category="power")
        _seed_revision(
            session,
            definition=defn,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-12345",
            valid_to=datetime(2099, 1, 1, tzinfo=UTC),
        )

    plan = resolver.resolve(stage_name="power", calculation_type=None)

    assert plan.revision_id is not None
    assert plan.missing is None
    assert plan.stage_name == "power"
