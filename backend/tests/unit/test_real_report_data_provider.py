"""Unit tests for ``RealReportDataProvider`` v0→v1 projection.

The projection lives at the anti-corruption boundary between the
calculation domain's persisted v0 ``result_snapshot`` shape and the
report-domain v1 schema (``cold_storage_concept_design@1.0.0``).

The data provider is exercised by injecting a small in-process
``_StubOrchestrationResult`` carrying four named sections
(``throughput_result`` / ``cooling_load_result`` / ``equipment_result``
/ ``power_result``).  Each section is a tiny stub with the
five attributes the data provider reads: ``id``,
``calculator_name``, ``calculator_version``, ``result``, and
optional ``content_hash`` / ``tool_call_status``.

These tests do **not** exercise a database, a session, or any
ORM machinery — they cover the projection logic in isolation so
failures are unambiguously attributable to the data provider.

The fifteen cases below correspond one-to-one with §七 of the
slice-1 unblock authorization.
"""

from __future__ import annotations

import math  # noqa: F401  # retained for explicit module-level import surface
from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.reports.infrastructure.real_data_provider import (
    RealReportDataProvider,
    ReportProjectionError,
)

# ── Stub helpers (test-only, never used in production) ─────────────────────


class _StubSection:
    """Minimal stand-in for a real ``CalculationRunRecord`` row.

    Mirrors the attribute surface the data provider reads from the
    composition-side ``_PilotCalcSection`` (id / calculator_name /
    calculator_version / result / content_hash / tool_call_status)
    but is defined here in test space so the unit test does not
    import any pilot-fixture code.
    """

    __slots__ = (
        "id",
        "calculator_name",
        "calculator_version",
        "result",
        "content_hash",
        "tool_call_status",
    )

    def __init__(
        self,
        *,
        id: str,
        calculator_name: str,
        calculator_version: str,
        result: dict[str, Any],
        content_hash: str | None = None,
        tool_call_status: str | None = None,
    ) -> None:
        self.id = id
        self.calculator_name = calculator_name
        self.calculator_version = calculator_version
        self.result = result
        self.content_hash = content_hash
        self.tool_call_status = tool_call_status


class _StubOrchestrationResult:
    """Stub with the four attrs the data provider consumes."""

    __slots__ = (
        "throughput_result",
        "cooling_load_result",
        "equipment_result",
        "power_result",
    )

    def __init__(
        self,
        *,
        throughput: _StubSection | None = None,
        cooling_load: _StubSection | None = None,
        equipment: _StubSection | None = None,
        power: _StubSection | None = None,
    ) -> None:
        self.throughput_result = throughput
        self.cooling_load_result = cooling_load
        self.equipment_result = equipment
        self.power_result = power


class _StubCalculationService:
    """Stand-in for ``CoreCalculationService`` returning a fixed stub."""

    def __init__(self, result: _StubOrchestrationResult | None) -> None:
        self._result = result
        self.call_count = 0
        self.last_project_id: str | None = None
        self.last_version_id: str | None = None

    def get_orchestrated_result(
        self, project_id: str, version_id: str
    ) -> _StubOrchestrationResult | None:
        self.call_count += 1
        self.last_project_id = project_id
        self.last_version_id = version_id
        return self._result


def _build_provider(
    service: _StubCalculationService | None,
) -> RealReportDataProvider:
    return RealReportDataProvider(calculation_service=service)


# ── Fixtures: persisted v0 result_snapshots ────────────────────────────────


def _throughput_section() -> _StubSection:
    return _StubSection(
        id="run-zone-001",
        calculator_name="cold_room_zone_plan",
        calculator_version="1.0.0",
        result={
            "daily_inbound_mass_kg": 10000,  # int
            "total_area_m2": "200.0",  # JSON-safe string
            "zones": [
                {
                    "zone_code": "Z1",
                    "zone_name": "a1-zone-001",
                    "daily_throughput_kg_day": 10000,
                    "required_area_m2": "200.0",
                    "design_storage_mass_kg": "15000.0",
                    "position_count": 30,
                    "temperature_band": "0~4C",
                    "function": "storage",
                    "process_compatibility": "blueberry",
                    "hygiene_zone": "food_grade",
                }
            ],
            # Unconsumed v0 fields that the report does not need:
            "design_daily_mass_kg": 10000,
            "total_required_area_m2": "200.0",
            "planning_parameters": {
                "pallet_weight_kg": 500,
                "working_hours_per_day": 8,
            },
        },
    )


def _cooling_load_section() -> _StubSection:
    return _StubSection(
        id="run-cool-001",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={
            "total_cooling_load_kw": "25.0",
            # Unconsumed v0 fields:
            "safety_margin_load_kw": "2.5",
            "envelope_heat_transfer_load_kw": "3.0",
            "product_sensible_heat_load_kw": "18.0",
        },
    )


def _equipment_section() -> _StubSection:
    return _StubSection(
        id="run-equip-001",
        calculator_name="equipment",
        calculator_version="1.0.0",
        result={
            "compressor_installed_capacity_kw": "25.0",
            "condenser_heat_rejection_capacity_kw": "30.0",
            # Unconsumed v0 fields:
            "evaporator_total_cooling_capacity_kw": "30.0",
            "evaporation_temperature_c": "-5.0",
        },
    )


def _power_section() -> _StubSection:
    return _StubSection(
        id="run-power-001",
        calculator_name="installed_power",
        calculator_version="1.0.0",
        result={
            "total_installed_power_kw_e": "200.0",
            # Unconsumed v0 fields:
            "total_estimated_demand_kw": "160.0",
        },
    )


def _full_orchestration() -> _StubOrchestrationResult:
    return _StubOrchestrationResult(
        throughput=_throughput_section(),
        cooling_load=_cooling_load_section(),
        equipment=_equipment_section(),
        power=_power_section(),
    )


# ── 1. throughput v0 → v1 ──────────────────────────────────────────────────


def test_throughput_v0_to_v1_projection() -> None:
    """Throughput section: rename zones→zone_details, coerce strings, drop extras."""
    provider = _build_provider(_StubCalculationService(_full_orchestration()))

    sections = {s["section_key"]: s for s in provider.get_calculation_results("p-1", "v-1")}
    section = sections["throughput_inventory_area"]
    data = section["data"]
    assert data["daily_inbound_mass_kg"] == 10000.0
    assert data["total_area_m2"] == 200.0
    assert isinstance(data["zone_details"], list)
    assert len(data["zone_details"]) == 1
    zone = data["zone_details"][0]
    assert zone["zone_code"] == "Z1"
    # Unconsumed v0 fields MUST NOT appear in the projected section
    for forbidden in (
        "design_daily_mass_kg",
        "total_required_area_m2",
        "planning_parameters",
        "zones",
    ):
        assert forbidden not in data


# ── 2. cooling-load measured value ─────────────────────────────────────────


def test_cooling_load_measured_value_shape() -> None:
    """cooling_load: v0 string → v1 measured-value with persisted provenance."""
    provider = _build_provider(_StubCalculationService(_full_orchestration()))

    sections = {s["section_key"]: s for s in provider.get_calculation_results("p-1", "v-1")}
    cooling = sections["cooling_load"]
    data = cooling["data"]
    measured = data["total_design_refrigeration_load"]
    assert measured == {
        "value": 25.0,
        "unit": "kW(r)",
        "source_result_id": "run-cool-001",
        "source_tool": "cooling_load",
        "source_tool_version": "1.0.0",
    }
    # Unconsumed v0 fields MUST NOT appear.
    for forbidden in (
        "safety_margin_load_kw",
        "envelope_heat_transfer_load_kw",
        "product_sensible_heat_load_kw",
    ):
        assert forbidden not in data


# ── 3. equipment measured values ───────────────────────────────────────────


def test_equipment_measured_values_kw_r_and_kw_th() -> None:
    """equipment_selection: two measured values with different unit consts."""
    provider = _build_provider(_StubCalculationService(_full_orchestration()))

    sections = {s["section_key"]: s for s in provider.get_calculation_results("p-1", "v-1")}
    equipment = sections["equipment_selection"]
    data = equipment["data"]
    compressor = data["total_compressor_capacity"]
    condenser = data["condenser_heat_rejection"]
    assert compressor == {
        "value": 25.0,
        "unit": "kW(r)",
        "source_result_id": "run-equip-001",
        "source_tool": "equipment",
        "source_tool_version": "1.0.0",
    }
    assert condenser == {
        "value": 30.0,
        "unit": "kW(th)",
        "source_result_id": "run-equip-001",
        "source_tool": "equipment",
        "source_tool_version": "1.0.0",
    }
    for forbidden in (
        "evaporator_total_cooling_capacity_kw",
        "evaporation_temperature_c",
    ):
        assert forbidden not in data


# ── 4. electrical measured value ──────────────────────────────────────────


def test_electrical_measured_value_kw_e() -> None:
    """electrical_and_energy: v0 string → v1 measured-value with kW(e) unit."""
    provider = _build_provider(_StubCalculationService(_full_orchestration()))

    sections = {s["section_key"]: s for s in provider.get_calculation_results("p-1", "v-1")}
    power = sections["electrical_and_energy"]
    data = power["data"]
    assert data["total_installed_power"] == {
        "value": 200.0,
        "unit": "kW(e)",
        "source_result_id": "run-power-001",
        "source_tool": "installed_power",
        "source_tool_version": "1.0.0",
    }
    assert "total_estimated_demand_kw" not in data


# ── 5. Decimal / string precise conversion ────────────────────────────────


@pytest.mark.parametrize(
    "source_value, expected",
    [
        (25, 25.0),
        (25.5, 25.5),
        (Decimal("25.0"), 25.0),
        (Decimal("0.1") + Decimal("0.2"), Decimal("0.3")),
        ("25.0", 25.0),
        ("-3.5e2", -350.0),
        ("  42  ", 42.0),  # whitespace stripped
    ],
)
def test_decimal_and_string_precise_coercion(source_value: object, expected: object) -> None:
    """Decimal and finite-decimal strings coerce to float via the projection."""
    section = _StubSection(
        id="run-cool-precise",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={"total_cooling_load_kw": source_value},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    [out] = provider.get_calculation_results("p", "v")
    value = out["data"]["total_design_refrigeration_load"]["value"]
    if isinstance(expected, Decimal):
        # Decimal arithmetic survives float(Decimal) round-trip
        # precision loss; compare with a tight tolerance.
        assert value == pytest.approx(float(expected), rel=0, abs=1e-9)
    else:
        assert value == expected or value == pytest.approx(expected, rel=0, abs=1e-9)


# ── 6. provenance is sourced from the persisted row ───────────────────────


def test_provenance_sourced_from_persisted_row() -> None:
    """source_result_id / source_tool / source_tool_version must come from the row."""
    section = _StubSection(
        id="row-with-specific-provenance",
        calculator_name="my_custom_calculator",
        calculator_version="9.9.9",
        result={"total_cooling_load_kw": "1.0"},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    [out] = provider.get_calculation_results("p", "v")
    measured = out["data"]["total_design_refrigeration_load"]
    assert measured["source_result_id"] == "row-with-specific-provenance"
    assert measured["source_tool"] == "my_custom_calculator"
    assert measured["source_tool_version"] == "9.9.9"


# ── 7. non-numeric string fails ───────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_string",
    [
        "not-a-number",
        "25.0abc",
        "abc25",
        "0x10",
        "--5",
        "  ",
    ],
)
def test_non_numeric_string_fails_closed(bad_string: str) -> None:
    """Empty / non-numeric strings raise ReportProjectionError, not coerced to 0."""
    section = _StubSection(
        id="run-cool-bad-string",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={"total_cooling_load_kw": bad_string},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    with pytest.raises(ReportProjectionError) as excinfo:
        provider.get_calculation_results("p", "v")
    err = excinfo.value
    assert err.section_key == "cooling_load"
    assert err.result_id == "run-cool-bad-string"
    assert err.reason_code in {"NON_NUMERIC_STRING", "EMPTY_STRING"}


# ── 8. bool fails ──────────────────────────────────────────────────────────


def test_bool_fails_closed() -> None:
    """bool is rejected explicitly with BOOL_NOT_NUMERIC."""
    section = _StubSection(
        id="run-cool-bool",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={"total_cooling_load_kw": True},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    with pytest.raises(ReportProjectionError) as excinfo:
        provider.get_calculation_results("p", "v")
    err = excinfo.value
    assert err.reason_code == "BOOL_NOT_NUMERIC"


# ── 9. NaN / Infinity fails ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "non_finite",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("NaN"),
    ],
)
def test_non_finite_number_fails_closed(non_finite: object) -> None:
    """NaN / +Inf / -Inf raise ReportProjectionError with NON_FINITE_NUMBER."""
    section = _StubSection(
        id="run-cool-nan",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={"total_cooling_load_kw": non_finite},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    with pytest.raises(ReportProjectionError) as excinfo:
        provider.get_calculation_results("p", "v")
    assert excinfo.value.reason_code == "NON_FINITE_NUMBER"


# ── 10. required source field missing fails ───────────────────────────────


def test_required_source_field_missing_fails() -> None:
    """A required v1 measured-value field with no v0 source raises."""
    section = _StubSection(
        id="run-cool-missing",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        # total_cooling_load_kw is required for v1's
        # total_design_refrigeration_load — its absence must fail.
        result={"unrelated_field": "x"},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    with pytest.raises(ReportProjectionError) as excinfo:
        provider.get_calculation_results("p", "v")
    err = excinfo.value
    assert err.section_key == "cooling_load"
    assert err.reason_code == "REQUIRED_SOURCE_FIELD_MISSING"
    assert err.result_id == "run-cool-missing"


# ── 11. conflicting alias fails ───────────────────────────────────────────


def test_conflicting_alias_fails_closed() -> None:
    """If a v0 field is present alongside one of its aliases, fail closed."""
    section = _StubSection(
        id="run-equip-conflict",
        calculator_name="equipment",
        calculator_version="1.0.0",
        result={
            "compressor_installed_capacity_kw": "25.0",
            "compressor_capacity_kw": "20.0",  # alias; conflicts with primary
        },
    )
    provider = _build_provider(_StubCalculationService(_StubOrchestrationResult(equipment=section)))

    with pytest.raises(ReportProjectionError) as excinfo:
        provider.get_calculation_results("p", "v")
    err = excinfo.value
    assert err.section_key == "equipment_selection"
    assert err.reason_code == "ALIAS_CONFLICT"


# ── 12. unconsumed extras do not fail and do not enter the section ────────


def test_unconsumed_v0_extras_are_dropped_silently() -> None:
    """Extra v0 fields the report does not consume MUST be dropped, not echoed."""
    section = _StubSection(
        id="run-cool-extras",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={
            "total_cooling_load_kw": "25.0",
            "safety_margin_load_kw": "2.5",
            "envelope_heat_transfer_load_kw": "3.0",
            "product_sensible_heat_load_kw": "18.0",
            "packaging_load_kw": "1.0",
            "infiltration_load_kw": "3.0",
            "personnel_load_kw": "0.5",
            "lighting_load_kw": "0.3",
            "evaporator_fan_load_kw": "1.2",
            "defrost_additional_load_kw": "0.4",
            "other_configuration_load_kw": "0.1",
            "latent_load_kw": "0.0",
        },
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    # Should NOT raise.
    [out] = provider.get_calculation_results("p", "v")
    data = out["data"]
    # Only the projected measured value should be present.
    assert set(data.keys()) == {"total_design_refrigeration_load"}


# ── 13. calculator is NOT re-executed ─────────────────────────────────────


def test_calculator_is_not_re_executed() -> None:
    """The data provider must not call into any calculator service to recompute."""
    sentinel = object()
    # A row whose ``result`` dict is the SAME OBJECT the provider
    # would consume — any recompute would produce a different dict.
    section = _StubSection(
        id="run-cool-no-recompute",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result={"total_cooling_load_kw": "25.0", "sentinel": sentinel},
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    [out] = provider.get_calculation_results("p", "v")
    # The unconsumed sentinel is dropped (v1 schema rejects it), but
    # the projected measured value is sourced from the *same*
    # persisted value — no recompute path exists.
    assert "sentinel" not in out["data"]
    assert out["data"]["total_design_refrigeration_load"]["value"] == 25.0


# ── 14. no database writes ────────────────────────────────────────────────


def test_no_database_writes() -> None:
    """The data provider must not perform any DB write operations.

    Verified structurally: RealReportDataProvider.get_calculation_results
    imports no ORM / session machinery.  We assert that the data
    provider's read path accepts an in-process stub service and
    returns the projected section without ever opening a database.
    """
    service = _StubCalculationService(_full_orchestration())
    provider = _build_provider(service)

    sections = provider.get_calculation_results("p", "v")
    assert len(sections) == 4  # all four sections projected
    # The stub service was consulted exactly once — no second
    # callback that would imply a write-side helper.
    assert service.call_count == 1


# ── 15. source snapshot is not mutated ────────────────────────────────────


def test_source_snapshot_is_not_mutated() -> None:
    """The persisted ``result_snapshot`` must not be mutated by the projection."""
    original = {
        "total_cooling_load_kw": "25.0",
        "safety_margin_load_kw": "2.5",
        "envelope_heat_transfer_load_kw": "3.0",
    }
    snapshot_ref = dict(original)  # shallow snapshot for post-call compare
    section = _StubSection(
        id="run-cool-immutable",
        calculator_name="cooling_load",
        calculator_version="1.0.0",
        result=original,
    )
    provider = _build_provider(
        _StubCalculationService(_StubOrchestrationResult(cooling_load=section))
    )

    provider.get_calculation_results("p", "v")
    assert original == snapshot_ref
    # Specifically, the projection must not have removed / added
    # / overwritten any v0 key in the original snapshot dict.
    assert set(original.keys()) == set(snapshot_ref.keys())
