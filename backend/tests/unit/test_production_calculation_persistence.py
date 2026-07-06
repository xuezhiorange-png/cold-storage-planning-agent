"""Unit tests for the future CalculationRun persistence port (Phase 2).

The Phase 2 persistence port is an **interface only** — no real
SQLAlchemy adapter is wired.  These tests verify:

* The pure mapper converts an :class:`AdapterResult` into a
  :class:`CalculationRunDraft` with the threaded identity fields
* The in-memory test double captures staged drafts
* The mapper never writes to the database (no session used)
"""

from __future__ import annotations

from typing import Any

import pytest

from cold_storage.modules.orchestration.application.production_calculation import (
    adapters,
    projection,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterProvenance,
    AdapterResult,
    AdapterWarning,
)
from cold_storage.modules.orchestration.application.production_calculation.persistence import (
    CalculationRunDraft,
    InMemoryCalculationRunPersistencePort,
    map_adapter_result_to_draft,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType


def _adapter_result() -> AdapterResult:
    return AdapterResult(
        calculation_type=CalculationType.INVESTMENT,
        payload={"total_investment_cny": 1234.56},
        content_hash="a" * 64,  # placeholder; validator only called manually
        requires_review=True,
        warnings=(AdapterWarning(code="W1", message="warning-1", details={"k": "v"}),),
        blockers=(),
        provenance=AdapterProvenance(
            formulas=(),
            coefficients=(),
            source_references=(),
            assumptions=(),
        ),
        calculator_name="investment_estimate",
        calculator_version="1.0.0",
        calculator_success=True,
    )


class TestMapAdapterResultToDraft:
    def test_identity_fields_are_threaded(self) -> None:
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="postgresql",
        )
        assert draft.actor == "actor-1"
        assert draft.correlation_id == "corr-1"
        assert draft.database_backend == "postgresql"
        assert draft.calculation_type is CalculationType.INVESTMENT
        assert draft.calculator_name == "investment_estimate"
        assert draft.calculator_version == "1.0.0"
        assert draft.requires_review is True
        assert draft.content_hash == "a" * 64
        assert draft.payload == {"total_investment_cny": 1234.56}

    def test_warnings_are_serialised(self) -> None:
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
        )
        assert len(draft.warnings) == 1
        assert draft.warnings[0]["code"] == "W1"
        assert draft.warnings[0]["details"] == {"k": "v"}

    def test_upstream_calculation_ids_carried(self) -> None:
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
            upstream_calculation_ids={"zone": "calculation-zone-1"},
        )
        assert draft.upstream_calculation_ids == {"zone": "calculation-zone-1"}

    def test_empty_upstream_defaults_to_empty_dict(self) -> None:
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
        )
        assert draft.upstream_calculation_ids == {}

    def test_draft_is_pure_value_object(self) -> None:
        # ``CalculationRunDraft`` is a frozen dataclass; mutation
        # must fail.
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
        )
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            draft.actor = "mutated"  # type: ignore[misc]


class TestInMemoryPersistencePort:
    def test_stage_draft_appends_and_returns_id(self) -> None:
        port = InMemoryCalculationRunPersistencePort()
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
        )
        draft_id_1 = port.stage_draft(None, draft=draft)
        draft_id_2 = port.stage_draft(None, draft=draft)
        assert draft_id_1 == "draft-1"
        assert draft_id_2 == "draft-2"
        assert len(port.staged) == 2
        assert port.staged[0] is draft
        assert port.staged[1] is draft

    def test_session_is_ignored(self) -> None:
        port = InMemoryCalculationRunPersistencePort()
        draft = map_adapter_result_to_draft(
            adapter_result=_adapter_result(),
            actor="a",
            correlation_id="c",
            database_backend="sqlite",
        )
        # Pass a sentinel session — the in-memory port MUST NOT
        # touch it (the contract forbids session use).
        sentinel: Any = object()
        port.stage_draft(sentinel, draft=draft)
        assert len(port.staged) == 1


class TestEndToEndAdapterToDraft:
    def test_draft_built_from_real_adapter(self) -> None:
        # End-to-end: the real investment adapter feeds into the
        # mapper, and the draft is captured by the in-memory
        # port.
        proj = projection.project_calculator_input(
            calculation_type=CalculationType.INVESTMENT,
            raw_inputs={
                "total_area_m2": 1000.0,
                "refrigerated_area_m2": 800.0,
                "frozen_area_m2": 200.0,
                "position_count": 100,
                "total_power_kw": 150.0,
            },
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="sqlite",
        )
        adapter_result = adapters.InvestmentAdapter().execute(proj)
        draft = map_adapter_result_to_draft(
            adapter_result=adapter_result,
            actor=proj.actor,
            correlation_id=proj.correlation_id,
            database_backend=proj.database_backend,
        )
        port = InMemoryCalculationRunPersistencePort()
        port.stage_draft(None, draft=draft)
        assert isinstance(draft, CalculationRunDraft)
        assert port.staged[0] is draft
        assert draft.requires_review is True  # demo coefficients
        assert len(draft.warnings) >= 1
