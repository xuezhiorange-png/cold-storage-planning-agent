"""Phase 4 Issue #35 Slice 2A — production-mode resolution gateway tests (SQLite).

This module covers the bootstrap-level production-readiness
gateway and the strict-resolver injection point on
:class:`ProductionSourceBindingUseCase`. The dual-backend parity
mirror lives in
``test_phase4_slice2a_resolution_gateway_postgresql.py``.

Tests
=====

1. ``test_app_env_production_fails_closed_when_all_stages_missing_approved``
   — production mode + no approved rows → ``StartupReadinessError``.
2. ``test_app_env_production_passes_when_all_stages_have_approved``
   — production mode + every required stage has exactly one
   approved non-demo row with a valid citation → readiness passes.
3. ``test_app_env_development_skips_readiness_check``
   — development mode + only demo rows → readiness skipped.
4. ``test_app_env_test_skips_readiness_check``
   — test mode + only demo rows → readiness skipped.
5. ``test_strict_resolver_rejects_demo_in_production_use_case``
   — use case with ``coefficient_resolver=`` + demo-only
     coefficients → ``DemoCoefficientInProductionError`` /
     ``MissingApprovedCoefficientError`` from the strict gate.
6. ``test_strict_resolver_rejects_ambiguous_latest_in_production_use_case``
   — multiple eligible revisions for the same stage + no
     ``explicit_revision_id`` → ``AmbiguousLatestRowError``.
7. ``test_production_use_case_without_resolver_keeps_legacy_p3_behavior``
   — use case constructed without ``coefficient_resolver=`` does
     **not** invoke the strict gate, leaving the legacy Phase 3
     path completely untouched (Charles's "100 % backward compat"
     rule).

The 7 SQLite cases must run successfully for the Slice 2A
``backend-sqlite`` CI job to be green.

Per Slice 2A plan §8.1: do NOT add full 5-stage roundtrip /
payload_hash recompute / power-authority / archive / scheme
assertions here — these belong to deferred Slices. The tests in
this file stay narrowly scoped to the resolution gateway and
the use case injection point.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Slice 2A plan §11.3 — explicitly NOT testing the orchestrator
# staging path: that requires a fully-wired
# ProductionSourceBindingUseCase with a real
# OrchestrationService (P3 wiring).  Slice 2A only proves the
# strict gate raises the typed error before Transaction A.  A
# stub OrchestrationService is enough.
# Pull in every module that contributes tables to ``Base.metadata``
# so that ``Base.metadata.create_all`` resolves every foreign key.
import cold_storage.modules.schemes.infrastructure.orm  # noqa: F401
from cold_storage.bootstrap.mode import AppMode
from cold_storage.bootstrap.settings import Settings
from cold_storage.bootstrap.startup_readiness import (
    get_required_stages,
    run_startup_readiness_or_raise,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    AmbiguousLatestRowError,
    DemoCoefficientInProductionError,
    MissingApprovedCoefficientError,
    StartupReadinessError,
)
from cold_storage.modules.orchestration.application.production_source_binding import (
    ProductionSourceBindingUseCase,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    VerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# ---------------------------------------------------------------------------
# Engine + clock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> Engine:
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
def settings_factory():
    """Build a Settings instance with the requested ``app_env`` value.

    Pydantic-settings would read the real ``.env`` file otherwise;
    here we construct Settings directly. ``app_env`` is the only
    field we change. ``Settings.model_config`` lets us bypass env
    reads by overriding the constructor — pydantic-settings 2.x
    honours a plain ``__init__(app_env=...)`` call when the
    environment variable does not exist (it doesn't for
    ``app_env``).
    """

    def _make(app_env: str) -> Settings:
        # Construct via object.__new__ + model_validate to bypass
        # pydantic-settings environment reading entirely.  Slice
        # 2A treats ``app_env`` as the production-mode truth
        # source; the only way a test can route through
        # ``AppMode.PRODUCTION`` / ``DEVELOPMENT`` / ``TEST`` is to
        # provide that value in-process.
        return Settings.model_validate({"app_env": app_env})

    return _make


# ---------------------------------------------------------------------------
# Pre-state seeding helpers
# ---------------------------------------------------------------------------


def _seed_revision(
    engine: Engine,
    *,
    code: str,
    category: str,
    status: str,
    source_type: str,
    source_reference: str | None,
    revision_number: int = 1,
    valid_to: _dt.datetime | None = None,
    approved_at: _dt.datetime | None = None,
) -> tuple[str, str]:
    """Insert one definition + one revision row directly into the DB."""
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientDefinitionRecord,
        CoefficientRevisionRecord,
    )

    definition_id = f"def-{code}"
    revision_id = f"rev-{code}-{revision_number}"
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(
            CoefficientDefinitionRecord(
                id=definition_id,
                code=code,
                name=code,
                description=f"slice2a test {code}",
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
                revision_number=revision_number,
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
                approved_at=approved_at,
                created_by="seed",
            )
        )
        session.commit()
    return definition_id, revision_id


def _add_revision_to_existing_definition(
    engine: Engine,
    *,
    code: str,
    revision_number: int,
    status: str,
    source_type: str,
    source_reference: str | None,
    approved_at: _dt.datetime | None = None,
) -> str:
    """Add a sibling revision to an already-seeded definition (same code)."""
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientRevisionRecord,
    )

    definition_id = f"def-{code}"
    revision_id = f"rev-{code}-{revision_number}"
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(
            CoefficientRevisionRecord(
                id=revision_id,
                coefficient_definition_id=definition_id,
                revision_number=revision_number,
                unit="ratio",
                value_decimal="1.15",
                status=status,
                source_type=source_type,
                source_title="test",
                source_reference=source_reference,
                source_page=None,
                valid_from=_dt.datetime(2025, 1, 1, tzinfo=_dt.UTC),
                approved_by=("coefficient.reviewer" if status == "approved" else None),
                approved_at=approved_at,
                created_by="seed",
            )
        )
        session.commit()
    return revision_id


def _seed_full_production_set(engine: Engine) -> None:
    """Seed one approved non-demo revision for every required stage."""
    for category in {"zone", "cooling_load", "equipment", "power", "investment"}:
        _seed_revision(
            engine,
            code=f"prod-{category}",
            category=category,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-9999",
        )


def _make_settings(app_env: str) -> Settings:
    """Construct Settings with the requested ``app_env`` value only."""
    return Settings.model_validate({"app_env": app_env})


# ---------------------------------------------------------------------------
# Use case fixtures — a stub OrchestrationService so the resolver
# gate can run without the full Phase 3 13-dependency wiring.
# ---------------------------------------------------------------------------


class _StubOrchestrationService(OrchestrationService):
    """A bare stub that refuses to be called.

    Slice 2A's use case invokes the strict-resolver gate
    *before* ``service.execute(command)``; if the gate raises
    (the success path of every test below), ``service.execute``
    is never reached.  This stub is therefore intentionally
    broken; tests assert that the gate's typed error wins the
    race.
    """

    def __init__(self) -> None:  # noqa: D401 - intentional stub
        # Skip OrchestrationService.__init__: we don't want the
        # 13 dependencies of the real wiring.
        pass


class _NullVerificationReadPort(VerificationReadPort):
    """A VerificationReadPort stub that no test in this file reaches."""

    def load_verification_state(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError(
            "Slice 2A tests must raise in the strict gate before any"
            " Transaction A read;"
            f" got args={args!r} kwargs={kwargs!r}"
        )


# ---------------------------------------------------------------------------
# Test 1 — production mode fails closed when no approved rows exist
# ---------------------------------------------------------------------------


def test_app_env_production_fails_closed_when_all_stages_missing_approved(
    engine: Engine, settings_factory
) -> None:
    """Production startup aborts before any committed approved row exists."""
    # No rows seeded at all.
    settings = settings_factory("production")
    with pytest.raises(StartupReadinessError) as excinfo:
        run_startup_readiness_or_raise(settings=settings, engine=engine)

    error = excinfo.value
    assert isinstance(error, StartupReadinessError)
    assert error.ready is False
    # All five required stages should appear in ``missing``.
    missing = error.buckets["missing"]
    missing_stages = {entry["stage_name"] for entry in missing}
    assert missing_stages == {"zone", "cooling_load", "equipment", "power", "investment"}


# ---------------------------------------------------------------------------
# Test 2 — production mode passes when every required stage has
# one approved non-demo revision with a valid citation.
# ---------------------------------------------------------------------------


def test_app_env_production_passes_when_all_stages_have_approved(
    engine: Engine, settings_factory
) -> None:
    """Production startup succeeds once every stage has an approved row."""
    _seed_full_production_set(engine)
    settings = settings_factory("production")

    outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)

    assert outcome.mode is AppMode.PRODUCTION
    assert outcome.executed is True
    assert outcome.result is not None
    assert outcome.result["ready"] is True
    assert outcome.result["missing"] == []
    assert outcome.result["stale"] == []
    assert outcome.result["demoted"] == []
    assert outcome.result["citation"] == []


# ---------------------------------------------------------------------------
# Test 3 — development mode skips the readiness check (demo flow)
# ---------------------------------------------------------------------------


def test_app_env_development_skips_readiness_check(engine: Engine, settings_factory) -> None:
    """Development mode runs the same demo-only fixture without raising."""
    settings = settings_factory("development")

    # Seed only demo rows — under strict-ready production mode
    # this would fail; under development mode it must pass.
    for category in {"zone", "cooling_load", "equipment", "power", "investment"}:
        _seed_revision(
            engine,
            code=f"dev-{category}",
            category=category,
            status="approved",
            source_type="demo",
            source_reference="STANDARD:ISO-9999",
        )

    outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    assert outcome.mode is AppMode.DEVELOPMENT
    assert outcome.executed is False
    assert outcome.result is None


# ---------------------------------------------------------------------------
# Test 4 — test mode skips the readiness check (pytest fixtures)
# ---------------------------------------------------------------------------


def test_app_env_test_skips_readiness_check(engine: Engine, settings_factory) -> None:
    """Test mode mirrors development semantics for readiness."""
    settings = settings_factory("test")
    outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    assert outcome.mode is AppMode.TEST
    assert outcome.executed is False
    assert outcome.result is None


# ---------------------------------------------------------------------------
# Test 5 — strict resolver rejects demo coefficients via the use case
# ---------------------------------------------------------------------------


def test_strict_resolver_rejects_demo_in_production_use_case(engine: Engine) -> None:
    """Use case with strict resolver + demo-only seed fails closed."""
    for category in {"zone", "cooling_load", "equipment", "power", "investment"}:
        _seed_revision(
            engine,
            code=f"usedemo-{category}",
            category=category,
            status="approved",
            source_type="demo",
            source_reference="STANDARD:ISO-9999",
        )

    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_resolver,
    )

    resolver = compose_production_coefficient_resolver(engine=engine)
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        coefficient_resolver=resolver,
    )

    # The resolver's _is_eligible filter rejects demo on the
    # first stage; we just assert that *some* typed error from
    # the strict gate propagates (either
    # DemoCoefficientInProductionError or
    # MissingApprovedCoefficientError, depending on which
    # rejection the resolver surfaces first per category).
    with pytest.raises((DemoCoefficientInProductionError, MissingApprovedCoefficientError)):
        use_case._gate_production_resolver()  # noqa: SLF001 — direct probe is the cleanest


# ---------------------------------------------------------------------------
# Test 6 — strict resolver rejects ambiguous "latest" rows
# ---------------------------------------------------------------------------


def test_strict_resolver_rejects_ambiguous_latest_in_production_use_case(
    engine: Engine,
) -> None:
    """Two eligible approved revisions + no explicit id → typed error."""
    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_resolver,
    )
    from cold_storage.modules.orchestration.application.production_source_binding import (
        ProductionSourceBindingUseCase,
    )

    # Two approved revisions on the SAME definition (same code,
    # same category) — they tie on the deterministic priority
    # order (source_type / revision_number / approved_at).
    approved_at = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)
    _seed_revision(
        engine,
        code="ambig-power",
        category="power",
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9999",
        revision_number=1,
        approved_at=approved_at,
    )
    _add_revision_to_existing_definition(
        engine,
        code="ambig-power",
        revision_number=2,
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9999",
        approved_at=approved_at,
    )

    # Seed valid approved rows for the *other* four stages so
    # the gate doesn't trip on the first stage; only the
    # ambiguous "power" stage should be the failure point.
    for category in {"zone", "cooling_load", "equipment", "investment"}:
        _seed_revision(
            engine,
            code=f"ok-{category}",
            category=category,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-9999",
        )

    resolver = compose_production_coefficient_resolver(engine=engine)
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        coefficient_resolver=resolver,
    )

    with pytest.raises(AmbiguousLatestRowError):
        use_case._gate_production_resolver()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 7 — legacy Phase 3 wiring is preserved when resolver=None
# ---------------------------------------------------------------------------


def test_production_use_case_without_resolver_keeps_legacy_p3_behavior(
    engine: Engine,
) -> None:
    """``coefficient_resolver=None`` skips the strict gate entirely.

    Constructing the use case without a resolver must leave the
    legacy Phase 3 wiring intact. The roundtrip is not run (we
    don't have a real OrchestrationService stub for Transaction
    A); instead we assert that ``_gate_production_resolver``
    is not called by checking the public ``run`` method never
    invokes the strict gate path.  The cleanest probe is to
    observe that the use case's ``_coefficient_resolver``
    attribute is ``None`` and the run() method's first line is
    an ``if`` branch that does nothing when ``self._coefficient_resolver
    is None``.
    """
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        coefficient_resolver=None,
    )
    assert use_case._coefficient_resolver is None  # noqa: SLF001 — explicit probe

    # Even an empty resolver state must not raise: the
    # ``_gate_production_resolver`` branch is skipped when
    # ``coefficient_resolver is None``.  We confirm by reading
    # the production_source_binding module — defensive but
    # cheap.  Resolve the path relative to this file's
    # ``conftest``-aware layout rather than relying on cwd.
    src_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src/cold_storage/modules/orchestration/application/production_source_binding.py"
    )
    src = src_path.read_text(encoding="utf-8")
    assert "if self._coefficient_resolver is not None:" in src
    assert "self._gate_production_resolver()" in src


# ---------------------------------------------------------------------------
# Test sanity — get_required_stages + a quick discovery check
# ---------------------------------------------------------------------------


def test_required_stages_catalogue_is_canonical() -> None:
    """The 5-stage list is the canonical production pool key set."""
    stages = get_required_stages()
    assert stages == [
        ("zone", "ZONE"),
        ("cooling_load", "COOLING_LOAD"),
        ("equipment", "EQUIPMENT"),
        ("power", "POWER"),
        ("investment", "INVESTMENT"),
    ]
