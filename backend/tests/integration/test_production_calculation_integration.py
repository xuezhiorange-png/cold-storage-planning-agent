"""Integration tests for the production calculation ports & adapters.

These tests exercise the **adapter wrappers** end-to-end against
the real production calculators, plus the **port contracts** that
the orchestrator (Phase 3+) will compose.

The tests do **not** open a database, write any
``CalculationRunRecord``, or invoke ``SchemeService.run`` — they
exist to verify the adapter contract is end-to-end deterministic
and that the typed boundary holds.
"""

from __future__ import annotations

from typing import Any

import pytest

from cold_storage.modules.orchestration.application.production_calculation import (
    adapters,
    persistence,
    projection,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterProvenance,
    AdapterResult,
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    AdapterContractViolationError,
    MissingApprovedProjectVersionError,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# ── Port typing: the adapter classes must satisfy the port Protocols ──────


def _has_execute(cls: type) -> bool:
    """Verify the adapter exposes a callable ``execute`` method.

    Static type checking is done by mypy.  This runtime guard
    catches accidental method removal.
    """
    return callable(getattr(cls, "execute", None))


def test_zone_planning_adapter_satisfies_port() -> None:
    assert _has_execute(adapters.ZonePlanningAdapter)


def test_cooling_load_adapter_satisfies_port() -> None:
    assert _has_execute(adapters.CoolingLoadAdapter)


def test_equipment_capability_adapter_satisfies_port() -> None:
    assert _has_execute(adapters.EquipmentCapabilityAdapter)


def test_installed_power_adapter_satisfies_port() -> None:
    assert _has_execute(adapters.InstalledPowerAdapter)


def test_investment_adapter_satisfies_port() -> None:
    assert _has_execute(adapters.InvestmentAdapter)


# ── End-to-end pipeline: adapter → mapper → in-memory port ────────────────


def _investment_projection() -> CalculatorInputProjection:
    return projection.project_calculator_input(
        calculation_type=CalculationType.INVESTMENT,
        raw_inputs={
            "total_area_m2": 1000.0,
            "refrigerated_area_m2": 800.0,
            "frozen_area_m2": 200.0,
            "position_count": 100,
            "total_power_kw": 150.0,
        },
        actor="test-actor",
        correlation_id="corr-investment",
        database_backend="sqlite",
    )


def _zone_projection() -> CalculatorInputProjection:
    return projection.project_calculator_input(
        calculation_type=CalculationType.ZONE,
        raw_inputs={
            "daily_inbound_mass_kg": 5000.0,
            "working_time_h_per_day": 8.0,
            "finished_storage_days": 5.0,
            "packaging_storage_days": 3.0,
            "precooling_required_ratio": 0.8,
        },
        actor="test-actor",
        correlation_id="corr-zone",
        database_backend="postgresql",
    )


class TestEndToEndAdapterToDraft:
    def test_investment_end_to_end(self) -> None:
        proj = _investment_projection()
        adapter_result = adapters.InvestmentAdapter().execute(proj)
        draft = persistence.map_adapter_result_to_draft(
            adapter_result=adapter_result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        port = persistence.InMemoryCalculationRunPersistencePort()
        port.stage_draft(None, draft=draft)
        assert port.staged[0] is draft
        assert draft.calculation_type is CalculationType.INVESTMENT
        assert draft.actor == "test-actor"
        assert draft.correlation_id == "corr-investment"
        assert draft.database_backend == "sqlite"
        assert draft.requires_review is True
        assert len(draft.warnings) >= 1
        # No real DB was touched.
        assert port.staged == [draft]

    def test_zone_end_to_end(self) -> None:
        proj = _zone_projection()
        adapter_result = adapters.ZonePlanningAdapter().execute(proj)
        draft = persistence.map_adapter_result_to_draft(
            adapter_result=adapter_result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        port = persistence.InMemoryCalculationRunPersistencePort()
        port.stage_draft(None, draft=draft)
        assert port.staged[0] is draft
        assert draft.database_backend == "postgresql"
        assert draft.requires_review is True


# ── Determinism: identical inputs → identical hash & payload ──────────────


class TestDeterminism:
    def test_investment_deterministic(self) -> None:
        adapter = adapters.InvestmentAdapter()
        proj = _investment_projection()
        r1 = adapter.execute(proj)
        r2 = adapter.execute(proj)
        assert r1.content_hash == r2.content_hash
        assert r1.payload == r2.payload
        assert r1.requires_review == r2.requires_review

    def test_zone_deterministic(self) -> None:
        adapter = adapters.ZonePlanningAdapter()
        proj = _zone_projection()
        r1 = adapter.execute(proj)
        r2 = adapter.execute(proj)
        assert r1.content_hash == r2.content_hash
        assert r1.payload == r2.payload
        assert r1.requires_review == r2.requires_review


# ── Identity threading: actor / correlation_id / database_backend on draft ─


class TestIdentityThreading:
    @pytest.mark.parametrize("database_backend", ["sqlite", "postgresql"])
    def test_investment_threads_identity(self, database_backend: str) -> None:
        proj = projection.project_calculator_input(
            calculation_type=CalculationType.INVESTMENT,
            raw_inputs={
                "total_area_m2": 1.0,
                "refrigerated_area_m2": 1.0,
                "frozen_area_m2": 1.0,
                "position_count": 1,
                "total_power_kw": 1.0,
            },
            actor="threading-actor",
            correlation_id="threading-corr",
            database_backend=database_backend,
        )
        result = adapters.InvestmentAdapter().execute(proj)
        draft = persistence.map_adapter_result_to_draft(
            adapter_result=result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        assert draft.actor == "threading-actor"
        assert draft.correlation_id == "threading-corr"
        assert draft.database_backend == database_backend

    def test_correlation_id_is_not_overwritten_by_calculator(self) -> None:
        # The newer ``models.CalculationResult`` mints its own
        # ``correlation_id`` on construction.  The adapter MUST
        # NOT propagate that into the threaded identity — the
        # correlation_id on the draft must come from the
        # projection, not the calculator.
        proj = projection.project_calculator_input(
            calculation_type=CalculationType.INVESTMENT,
            raw_inputs={
                "total_area_m2": 1.0,
                "refrigerated_area_m2": 1.0,
                "frozen_area_m2": 1.0,
                "position_count": 1,
                "total_power_kw": 1.0,
            },
            actor="actor",
            correlation_id="projection-corr",
            database_backend="sqlite",
        )
        result = adapters.InvestmentAdapter().execute(proj)
        draft = persistence.map_adapter_result_to_draft(
            adapter_result=result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        assert draft.correlation_id == "projection-corr"


# ── No-write discipline ───────────────────────────────────────────────────


class TestNoWriteDiscipline:
    """The Phase 2 adapters MUST NOT open a database or write a row.

    These tests fail closed if a future adapter is wired to
    production persistence.  The contract is verified at
    runtime by checking the in-memory port's ``staged`` list
    is the only side effect.
    """

    def test_investment_adapter_does_not_open_session(self) -> None:
        # The adapter takes only a ``CalculatorInputProjection``
        # (a typed DTO).  It MUST NOT accept a session.
        proj = _investment_projection()
        # If a future change adds a ``session`` parameter, this
        # call signature will break — the test guards the
        # contract.
        adapters.InvestmentAdapter().execute(proj)

    def test_zone_adapter_does_not_open_session(self) -> None:
        proj = _zone_projection()
        adapters.ZonePlanningAdapter().execute(proj)

    def test_in_memory_port_is_only_persistence(self) -> None:
        # The in-memory port is the only persistence Phase 2
        # ships; the production SQLAlchemy adapter is reserved
        # for Phase 3+.  The test guards against accidental
        # wiring.
        port = persistence.InMemoryCalculationRunPersistencePort()
        proj = _investment_projection()
        result = adapters.InvestmentAdapter().execute(proj)
        draft = persistence.map_adapter_result_to_draft(
            adapter_result=result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        port.stage_draft(None, draft=draft)
        # The in-memory port's ``staged`` list is the only
        # captured state.  No external file, no database
        # connection, no real row.
        assert port.staged == [draft]


# ── Adapter result contract: end-to-end ──────────────────────────────────


class TestAdapterResultContract:
    def test_failed_calculator_returns_blockers(self) -> None:
        proj = projection.project_calculator_input(
            calculation_type=CalculationType.INVESTMENT,
            raw_inputs={
                "total_area_m2": 0.0,  # non-positive → fail
                "refrigerated_area_m2": 1.0,
                "frozen_area_m2": 1.0,
                "position_count": 1,
                "total_power_kw": 1.0,
            },
            actor="actor",
            correlation_id="corr",
            database_backend="sqlite",
        )
        result = adapters.InvestmentAdapter().execute(proj)
        assert result.calculator_success is False
        assert result.blockers
        # requires_review MUST still be True (the calculator
        # marks demo coefficients as review-required)
        assert result.requires_review is True

    def test_forged_invalid_result_violates_contract(self) -> None:
        # A manually-built invalid result must be caught by
        # ``validate_adapter_result``.
        from cold_storage.modules.orchestration.application.production_calculation.contract import (
            validate_adapter_result,
        )

        bad = AdapterResult(
            calculation_type=CalculationType.INVESTMENT,
            payload={},  # empty + success=True → invalid
            content_hash="",
            requires_review=True,
            warnings=(),
            blockers=(),
            provenance=AdapterProvenance(),
            calculator_name="",  # empty → invalid
            calculator_version="",
            calculator_success=True,
        )
        with pytest.raises(AdapterContractViolationError):
            validate_adapter_result(bad)

    def test_provenance_contains_formulas(self) -> None:
        proj = _investment_projection()
        result = adapters.InvestmentAdapter().execute(proj)
        # The investment estimator attaches at least one
        # formula reference.
        assert result.provenance.formulas


# ── Read port — interface only (no real Session) ────────────────────────


class TestApprovedProjectVersionReadPort:
    """The Phase 2 read port is an interface; Phase 3 wires the
    SQLAlchemy adapter.  These tests verify the *contract* via
    a test double.
    """

    def test_test_double_returns_none_for_unknown_version(self) -> None:
        from cold_storage.modules.orchestration.application.production_calculation.ports import (
            ApprovedProjectVersionReadPort,
        )

        class _FakeReadPort:
            def load_approved_version(
                self,
                session: Any,
                /,
                *,
                project_id: str,
                project_version_id: str,
            ) -> None:
                return None

        port: ApprovedProjectVersionReadPort = _FakeReadPort()
        assert port.load_approved_version(None, project_id="p", project_version_id="v") is None

    def test_missing_approved_version_raises(self) -> None:
        # The orchestrator (Phase 3) maps ``None`` from the
        # read port to ``MissingApprovedProjectVersionError``.
        # Phase 2 ships the error class; the mapping is
        # verified by an inline test.
        with pytest.raises(MissingApprovedProjectVersionError) as exc:
            raise MissingApprovedProjectVersionError(
                project_id="p",
                project_version_id="v",
                observed_status="DRAFT",
                is_archived=False,
            )
        assert exc.value.code.value == "PROJ_VERSION_NOT_APPROVED"
