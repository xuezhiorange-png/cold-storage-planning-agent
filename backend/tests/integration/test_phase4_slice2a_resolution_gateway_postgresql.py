"""Phase 4 Issue #35 Slice 2A — production-mode resolution gateway tests (PG mirror).

PostgreSQL parity mirror of
``test_phase4_slice2a_resolution_gateway_sqlite.py``.

Per Charles's Slice 2A constraint: the Hermes sandbox does **not**
expose a PostgreSQL service. The integration tests in this file
are guarded by ``pytest.mark.postgresql`` and require the
``pg_engine`` fixture defined in ``backend/tests/integration/conftest.py``
(which provisions a real PostgreSQL 14 container). The file is
shipped in Slice 2A so the test surface is auditable and CI-
ready; the tests are **not executed locally** as part of Slice
2A delivery.

The CI runs the parity matrix via the existing
``backend-postgresql`` workflow job.

Tests (parity with SQLite):

1. ``test_pg_app_env_production_fails_closed_when_all_stages_missing_approved``
2. ``test_pg_app_env_production_passes_when_all_stages_have_approved``
3. ``test_pg_app_env_development_skips_readiness_check``
4. ``test_pg_strict_resolver_rejects_demo_in_production_use_case``
5. ``test_pg_strict_resolver_rejects_ambiguous_latest_in_production_use_case``
6. ``test_pg_production_use_case_without_resolver_keeps_legacy_p3_behavior``

Note: ``test_app_env_test_skips_readiness_check`` is not mirrored:
its assertion is identical for every backend; the SQLite case
already exercises the path.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import cold_storage.modules.schemes.infrastructure.orm  # noqa: F401
from cold_storage.bootstrap.mode import AppMode
from cold_storage.bootstrap.settings import Settings
from cold_storage.bootstrap.startup_readiness import (
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
from cold_storage.modules.orchestration.application.ports import (
    OrchestrationIdentityRepository,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    VerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# Skip the entire module when running outside the CI environment
# that provides ``pg_engine``.  The standard
# ``backend-postgresql`` CI job is the source of truth for this
# parity coverage.
pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------------
# Engine helper — preserves the live URL so the password stays in-memory
# (SQLAlchemy strips the password when ``str(sa_url)`` is rendered).
# ---------------------------------------------------------------------------


def _fresh_pg_engine(pg_engine: Engine) -> Engine:
    """Build a fresh PG engine reusing the live URL."""
    return create_engine(pg_engine.url, poolclass=NullPool)


# ---------------------------------------------------------------------------
# Pre-state seeding helpers
# ---------------------------------------------------------------------------


def _seed_revision(
    pg_engine: Engine,
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
    """Insert one definition + one revision row directly into the PG schema."""
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientDefinitionRecord,
        CoefficientRevisionRecord,
    )

    definition_id = f"def-pg-{code}"
    revision_id = f"rev-pg-{code}-{revision_number}"
    with sessionmaker(bind=pg_engine, expire_on_commit=False)() as session:
        session.add(
            CoefficientDefinitionRecord(
                id=definition_id,
                code=code,
                name=code,
                description=f"slice2a PG test {code}",
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
    pg_engine: Engine,
    *,
    code: str,
    revision_number: int,
    status: str,
    source_type: str,
    source_reference: str | None,
    approved_at: _dt.datetime | None = None,
) -> str:
    """Add a sibling revision to a seeded PG definition (same code)."""
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientRevisionRecord,
    )

    definition_id = f"def-pg-{code}"
    revision_id = f"rev-pg-{code}-{revision_number}"
    with sessionmaker(bind=pg_engine, expire_on_commit=False)() as session:
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


def _make_settings(app_env: str) -> Settings:
    """Construct Settings with the requested ``app_env`` value only."""
    return Settings.model_validate({"app_env": app_env})


# ---------------------------------------------------------------------------
# Use case fixtures — a stub OrchestrationService for the strict gate.
# ---------------------------------------------------------------------------


class _StubOrchestrationService(OrchestrationService):
    """Bare stub. The strict gate raises before Transaction A."""

    def __init__(self) -> None:  # noqa: D401 - intentional stub
        pass


class _NullVerificationReadPort(VerificationReadPort):
    """VerificationReadPort stub; tests must raise in the strict gate first."""

    def load_verification_state(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError(
            "Slice 2A PG tests must raise in the strict gate before any"
            " Transaction A read;"
            f" got args={args!r} kwargs={kwargs!r}"
        )


class _NullIdentityRepository(OrchestrationIdentityRepository):
    """Identity-port stub mirroring the SQLite mirror.

    Slice 2C requires the use case to receive an
    :class:`OrchestrationIdentityRepository` by injection; the
    Slice 2A strict-resolver gate raises before the fingerprint
    read-path is reached, so this stub raises if any production
    source-binding path accidentally reaches it.
    """

    def get_fingerprint(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover
        raise AssertionError(
            "Slice 2A PG tests must raise in the strict gate before any"
            " fingerprint read;"
            f" got args={args!r} kwargs={kwargs!r}"
        )

    def get_calculator_version_vector(self, *args: Any, **kwargs: Any) -> dict[str, str]:  # pragma: no cover
        raise AssertionError(
            "Slice 2A PG tests must raise in the strict gate before any"
            " calculator-version-vector read;"
            f" got args={args!r} kwargs={kwargs!r}"
        )

    def get_or_create(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover
        raise AssertionError(
            "Slice 2A PG tests must raise in the strict gate before any"
            " identity create;"
            f" got args={args!r} kwargs={kwargs!r}"
        )

    def set_authoritative_attempt(self, *args: Any, **kwargs: Any) -> bool:  # pragma: no cover
        raise AssertionError(
            "Slice 2A PG tests must raise in the strict gate before any"
            " authoritative-attempt write;"
            f" got args={args!r} kwargs={kwargs!r}"
        )


# ---------------------------------------------------------------------------
# Test 1 — production mode fails closed on PG when no approved rows exist
# ---------------------------------------------------------------------------


def test_pg_app_env_production_fails_closed_when_all_stages_missing_approved(
    pg_engine: Engine,
) -> None:
    """PG parity: production startup aborts without approved rows."""
    _fresh_pg_engine(pg_engine).dispose()
    Base.metadata.create_all(pg_engine)
    settings = _make_settings("production")

    with pytest.raises(StartupReadinessError) as excinfo:
        run_startup_readiness_or_raise(settings=settings, engine=pg_engine)

    error = excinfo.value
    assert isinstance(error, StartupReadinessError)
    assert error.ready is False
    missing_stages = {entry["stage_name"] for entry in error.buckets["missing"]}
    assert missing_stages == {"zone", "cooling_load", "equipment", "power", "investment"}


# ---------------------------------------------------------------------------
# Test 2 — production mode passes when every required stage has approved
# ---------------------------------------------------------------------------


def test_pg_app_env_production_passes_when_all_stages_have_approved(
    pg_engine: Engine,
) -> None:
    """PG parity: production startup succeeds with a complete approved set."""
    _fresh_pg_engine(pg_engine).dispose()
    Base.metadata.create_all(pg_engine)
    for category in {"zone", "cooling_load", "equipment", "power", "investment"}:
        _seed_revision(
            pg_engine,
            code=f"prod-pg-{category}",
            category=category,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-9999",
        )

    settings = _make_settings("production")
    outcome = run_startup_readiness_or_raise(settings=settings, engine=pg_engine)
    assert outcome.mode is AppMode.PRODUCTION
    assert outcome.executed is True
    assert outcome.result is not None
    assert outcome.result["ready"] is True
    assert outcome.result["missing"] == []


# ---------------------------------------------------------------------------
# Test 3 — development mode skips the readiness check on PG
# ---------------------------------------------------------------------------


def test_pg_app_env_development_skips_readiness_check(pg_engine: Engine) -> None:
    """PG parity: development mode runs demo-only seed without raising."""
    _fresh_pg_engine(pg_engine).dispose()
    Base.metadata.create_all(pg_engine)
    settings = _make_settings("development")

    outcome = run_startup_readiness_or_raise(settings=settings, engine=pg_engine)
    assert outcome.mode is AppMode.DEVELOPMENT
    assert outcome.executed is False
    assert outcome.result is None


# ---------------------------------------------------------------------------
# Test 4 — strict resolver rejects demo coefficients via use case
# ---------------------------------------------------------------------------


def test_pg_strict_resolver_rejects_demo_in_production_use_case(
    pg_engine: Engine,
) -> None:
    """PG parity: use case with strict resolver + demo-only seed fails closed."""
    _fresh_pg_engine(pg_engine).dispose()
    Base.metadata.create_all(pg_engine)
    for category in {"zone", "cooling_load", "equipment", "power", "investment"}:
        _seed_revision(
            pg_engine,
            code=f"usedemo-pg-{category}",
            category=category,
            status="approved",
            source_type="demo",
            source_reference="STANDARD:ISO-9999",
        )

    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_resolver,
    )

    resolver = compose_production_coefficient_resolver(engine=pg_engine)
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        identity_repository=_NullIdentityRepository(),
        coefficient_resolver=resolver,
    )

    with pytest.raises((DemoCoefficientInProductionError, MissingApprovedCoefficientError)):
        use_case._gate_production_resolver()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 5 — strict resolver rejects ambiguous "latest" rows on PG
# ---------------------------------------------------------------------------


def test_pg_strict_resolver_rejects_ambiguous_latest_in_production_use_case(
    pg_engine: Engine,
) -> None:
    """PG parity: two eligible revisions + no explicit id → typed error."""
    _fresh_pg_engine(pg_engine).dispose()
    Base.metadata.create_all(pg_engine)

    approved_at = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)
    _seed_revision(
        pg_engine,
        code="ambig-power",
        category="power",
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9999",
        revision_number=1,
        approved_at=approved_at,
    )
    _add_revision_to_existing_definition(
        pg_engine,
        code="ambig-power",
        revision_number=2,
        status="approved",
        source_type="standard",
        source_reference="STANDARD:ISO-9999",
        approved_at=approved_at,
    )
    for category in {"zone", "cooling_load", "equipment", "investment"}:
        _seed_revision(
            pg_engine,
            code=f"ok-pg-{category}",
            category=category,
            status="approved",
            source_type="standard",
            source_reference="STANDARD:ISO-9999",
        )

    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_resolver,
    )

    resolver = compose_production_coefficient_resolver(engine=pg_engine)
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        identity_repository=_NullIdentityRepository(),
        coefficient_resolver=resolver,
    )

    with pytest.raises(AmbiguousLatestRowError):
        use_case._gate_production_resolver()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 6 — legacy Phase 3 wiring preserved when resolver=None
# ---------------------------------------------------------------------------


def test_pg_production_use_case_without_resolver_keeps_legacy_p3_behavior() -> None:
    """PG parity: ``coefficient_resolver=None`` skips the strict gate."""
    use_case = ProductionSourceBindingUseCase(
        service=_StubOrchestrationService(),  # type: ignore[arg-type]
        verification_read_port=_NullVerificationReadPort(),
        identity_repository=_NullIdentityRepository(),
        coefficient_resolver=None,
    )
    assert use_case._coefficient_resolver is None  # noqa: SLF001

    # Defensive reading of the module — same as SQLite mirror.
    src_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src/cold_storage/modules/orchestration/application/production_source_binding.py"
    )
    src = src_path.read_text(encoding="utf-8")
    assert "if self._coefficient_resolver is not None:" in src
    assert "self._gate_production_resolver()" in src
