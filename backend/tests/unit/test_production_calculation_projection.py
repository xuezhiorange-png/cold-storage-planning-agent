"""Unit tests for the project-version projection helper (Phase 2).

The projection helper is the *only* code path that turns an
approved project version snapshot into a typed
``CalculatorInputProjection``.  These tests verify:

* The typed DTO is built from the approved snapshot
* Identity fields (actor / correlation_id / database_backend)
  are threaded onto the projection
* Required fields per calculation type are validated
* Unknown database_backend values fail closed
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    ApprovedProjectVersionSnapshot,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    InvalidProjectInputError,
)
from cold_storage.modules.orchestration.application.production_calculation.projection import (
    project_calculator_input,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType


def _approved_version() -> ApprovedProjectVersionSnapshot:
    return ApprovedProjectVersionSnapshot(
        project_id="proj-1",
        project_version_id="v-1",
        version_number=1,
        version_status="APPROVED",
        is_archived=False,
        approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        approved_by="user-1",
        input_snapshot={
            "daily_inbound_mass_kg": 5000.0,
            "working_time_h_per_day": 8.0,
            "finished_storage_days": 5.0,
            "packaging_storage_days": 3.0,
            "precooling_required_ratio": 0.8,
        },
    )


class TestProjectCalculatorInputSuccess:
    def test_zone_projection_carries_inputs(self) -> None:
        v = _approved_version()
        proj = project_calculator_input(
            calculation_type=CalculationType.ZONE,
            raw_inputs=v.input_snapshot,
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="sqlite",
        )
        assert proj.calculation_type is CalculationType.ZONE
        assert proj.raw_inputs == dict(v.input_snapshot)
        assert proj.actor == "actor-1"
        assert proj.correlation_id == "corr-1"
        assert proj.database_backend == "sqlite"
        assert proj.upstream_calculation_ids == {}

    def test_cooling_load_projection_threads_upstream(self) -> None:
        proj = project_calculator_input(
            calculation_type=CalculationType.COOLING_LOAD,
            raw_inputs={"zones": [], "coefficients": {}},
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="postgresql",
            upstream_calculation_ids={"zone": "calculation-zone-1"},
        )
        assert proj.calculation_type is CalculationType.COOLING_LOAD
        assert proj.database_backend == "postgresql"
        assert proj.upstream_calculation_ids == {"zone": "calculation-zone-1"}

    def test_investment_projection_carries_inputs(self) -> None:
        proj = project_calculator_input(
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
        assert proj.calculation_type is CalculationType.INVESTMENT
        assert proj.raw_inputs["position_count"] == 100

    def test_inputs_are_defensively_copied(self) -> None:
        original = {
            "total_area_m2": 1000.0,
            "refrigerated_area_m2": 800.0,
            "frozen_area_m2": 200.0,
            "position_count": 100,
            "total_power_kw": 150.0,
        }
        proj = project_calculator_input(
            calculation_type=CalculationType.INVESTMENT,
            raw_inputs=original,
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="sqlite",
        )
        original["total_area_m2"] = 9999.0  # mutate
        assert proj.raw_inputs["total_area_m2"] == 1000.0


class TestProjectCalculatorInputFailure:
    @pytest.mark.parametrize(
        "calc_type,missing",
        [
            (CalculationType.ZONE, "precooling_required_ratio"),
            (CalculationType.COOLING_LOAD, "coefficients"),
            (CalculationType.EQUIPMENT, "coefficients"),
            (CalculationType.POWER, "compressor_input_power_kw_e"),
            (
                CalculationType.INVESTMENT,
                "total_area_m2",
            ),
        ],
    )
    def test_missing_required_field_fails_closed(
        self, calc_type: CalculationType, missing: str
    ) -> None:
        # Build a complete payload, then remove one field.
        if calc_type is CalculationType.ZONE:
            raw = {
                "daily_inbound_mass_kg": 1.0,
                "working_time_h_per_day": 1.0,
                "finished_storage_days": 1.0,
                "packaging_storage_days": 1.0,
                "precooling_required_ratio": 0.5,
            }
        elif calc_type is CalculationType.COOLING_LOAD:
            raw = {"zones": []}
        elif calc_type is CalculationType.EQUIPMENT:
            raw = {"systems": []}
        elif calc_type is CalculationType.POWER:
            raw = {
                "evaporator_fan_power_kw_e": 1.0,
                "condenser_fan_power_kw_e": 1.0,
            }
        else:
            raw = {
                "refrigerated_area_m2": 1.0,
                "frozen_area_m2": 1.0,
                "position_count": 1,
                "total_power_kw": 1.0,
            }
        raw.pop(missing, None)

        with pytest.raises(InvalidProjectInputError) as exc:
            project_calculator_input(
                calculation_type=calc_type,
                raw_inputs=raw,
                actor="actor-1",
                correlation_id="corr-1",
                database_backend="sqlite",
            )
        assert exc.value.field == missing

    def test_unsupported_database_backend(self) -> None:
        raw = {
            "total_area_m2": 1.0,
            "refrigerated_area_m2": 1.0,
            "frozen_area_m2": 1.0,
            "position_count": 1,
            "total_power_kw": 1.0,
        }
        with pytest.raises(InvalidProjectInputError) as exc:
            project_calculator_input(
                calculation_type=CalculationType.INVESTMENT,
                raw_inputs=raw,
                actor="actor-1",
                correlation_id="corr-1",
                database_backend="mysql",
            )
        assert exc.value.field == "database_backend"
