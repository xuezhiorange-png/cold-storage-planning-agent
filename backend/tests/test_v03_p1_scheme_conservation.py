"""V0.3 P1 production-authority conservation regressions."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cold_storage.modules.schemes.domain.generator import (
    generate_balanced,
    generate_consolidated,
    generate_segmented,
    get_profile,
)
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    PowerResult,
    SchemeCandidate,
    SchemeComparisonResult,
    SchemeGenerationInput,
    ZoneResult,
)
from cold_storage.modules.schemes.domain.scoring import score_candidates
from cold_storage.modules.schemes.domain.validation import validate_candidate

_D = Decimal


def _zone(
    code: str,
    area: str,
    positions: int,
    storage: str,
    *,
    temperature: str = "-25C",
) -> ZoneResult:
    return ZoneResult(
        zone_code=code,
        zone_name=code,
        temperature_level=temperature,
        area_m2=_D(area),
        position_count=positions,
        storage_capacity_kg=_D(storage),
        process_compatibility="raw",
        hygiene_zone="A",
    )


def _input(
    zones: list[ZoneResult],
    *,
    cooling: str = "123.456789",
    operating: str = "234.567891",
    installed: str | None = "345.678912",
    required_storage: Decimal | None = None,
) -> SchemeGenerationInput:
    total_storage = sum((zone.storage_capacity_kg for zone in zones), _D("0"))
    return SchemeGenerationInput(
        project_id="project-v03-p1",
        project_version_id="version-v03-p1",
        weight_set_id="weight-v03-p1",
        profile_codes=["balanced"],
        profile_parameters={},
        source_calculation_ids={},
        source_snapshot_hashes={},
        zone_results=zones,
        investment_result=InvestmentResult(
            total_investment_cny=_D("1000000"),
            zone_investments={},
        ),
        cooling_load_result=CoolingLoadResult(
            design_cooling_load_kw_r=_D(cooling),
            sensible_load_kw_r=_D(cooling),
            infiltration_load_kw_r=_D("0"),
            latent_load_kw_r=_D("0"),
        ),
        equipment_result=EquipmentResult(
            compressor_operating_capacity_kw_r=_D(operating),
            compressor_standby_capacity_kw_r=_D("10"),
            condenser_heat_rejection_kw=_D("400"),
            installed_power_kw_e=_D("100"),
            compressor_installed_capacity_kw_r=(_D(installed) if installed is not None else None),
        ),
        generator_version="1.0.0",
        total_daily_throughput_kg_day=_D("1000"),
        total_storage_capacity_kg=(total_storage if required_storage is None else required_storage),
        total_position_count=sum(zone.position_count for zone in zones),
        power_result=PowerResult(
            total_installed_power_kw_e=_D("100"),
            total_estimated_demand_kw=_D("80"),
            equipment_rows=[],
            summary_rows=[],
            items=[],
            assumptions=[],
        ),
    )


def _candidate_with_profile(
    input_data: SchemeGenerationInput,
    profile_code: str,
    parameters: dict[str, object] | None = None,
) -> SchemeCandidate:
    profile = get_profile(profile_code, parameters)
    if profile_code == "balanced":
        return generate_balanced(input_data, profile)
    if profile_code == "consolidated_large_rooms":
        return generate_consolidated(input_data, profile)
    return generate_segmented(input_data, profile)


@pytest.mark.parametrize(
    ("profile_code", "parameters"),
    [
        ("balanced", None),
        ("consolidated_large_rooms", None),
        ("segmented_small_rooms", {"max_positions_per_room": 2}),
    ],
)
def test_all_generators_conserve_authoritative_cooling_and_compressor_totals(
    profile_code: str,
    parameters: dict[str, object] | None,
) -> None:
    zones = [
        _zone("Z2", "3.3", 4, "40.1"),
        _zone("Z1", "7.7", 5, "60.2", temperature="-18C"),
    ]
    input_data = _input(zones)
    candidate = _candidate_with_profile(input_data, profile_code, parameters)

    assert sum((room.design_cooling_load_kw_r for room in candidate.room_modules), _D("0")) == _D(
        "123.456789"
    )
    assert sum(
        (room.compressor_operating_capacity_kw_r for room in candidate.room_modules), _D("0")
    ) == _D("234.567891")
    assert sum(
        (room.compressor_installed_capacity_kw_r for room in candidate.room_modules), _D("0")
    ) == _D("345.678912")


def test_installed_capacity_none_does_not_synthesize_authority() -> None:
    input_data = _input(
        [_zone("Z1", "10", 5, "100")],
        installed=None,
    )
    candidate = generate_balanced(input_data, get_profile("balanced"))

    assert sum(
        (room.compressor_installed_capacity_kw_r for room in candidate.room_modules), _D("0")
    ) == _D("0")


def test_repeated_generation_keeps_exact_conservation_and_room_order() -> None:
    input_data = _input([_zone("Z1", "3.3", 4, "40.1"), _zone("Z2", "7.7", 5, "60.2")])
    profile = get_profile("segmented_small_rooms", {"max_positions_per_room": 2})

    first = generate_segmented(input_data, profile)
    second = generate_segmented(input_data, profile)

    assert first.room_modules == second.room_modules
    assert first.design_cooling_load_kw_r == second.design_cooling_load_kw_r == _D("123.456789")
    assert (
        first.compressor_operating_capacity_kw_r
        == second.compressor_operating_capacity_kw_r
        == _D("234.567891")
    )
    assert (
        first.compressor_installed_capacity_kw_r
        == second.compressor_installed_capacity_kw_r
        == _D("345.678912")
    )


def test_segmented_storage_conserves_each_source_zone_exactly() -> None:
    zones = [
        _zone("Z1", "10.1", 5, "100.1"),
        _zone("Z2", "8.2", 4, "80.2"),
    ]
    input_data = _input(zones)
    candidate = generate_segmented(
        input_data,
        get_profile("segmented_small_rooms", {"max_positions_per_room": 2}),
    )

    for zone in zones:
        source_code = zone.zone_code
        allocated = sum(
            (
                room.storage_capacity_kg
                for room in candidate.room_modules
                if room.zone_codes[0].split("-S", 1)[0] == source_code
            ),
            _D("0"),
        )
        assert allocated == zone.storage_capacity_kg

    assert sum((room.storage_capacity_kg for room in candidate.room_modules), _D("0")) == sum(
        (zone.storage_capacity_kg for zone in zones), _D("0")
    )


def test_segmented_storage_fix_preserves_area_and_position_split_semantics() -> None:
    zone = _zone("Z1", "10.1", 5, "100.1")
    candidate = generate_segmented(
        _input([zone]),
        get_profile("segmented_small_rooms", {"max_positions_per_room": 2}),
    )
    fraction = _D("1") / _D("3")

    assert [room.area_m2 for room in candidate.room_modules] == [
        _D("10.1") * fraction,
        _D("10.1") * fraction,
        _D("10.1") * fraction,
    ]
    assert [room.position_count for room in candidate.room_modules] == [2, 2, 1]
    assert [room.storage_capacity_kg for room in candidate.room_modules] == [
        _D("100.1") * fraction,
        _D("100.1") * fraction,
        _D("100.1") - (_D("100.1") * fraction) * 2,
    ]


def test_cooling_shortfall_remains_infeasible_under_existing_validator() -> None:
    zones = [_zone("Z1", "10", 5, "100")]
    input_data = _input(zones, cooling="100")
    generated = generate_balanced(input_data, get_profile("balanced"))
    tampered = replace(generated, design_cooling_load_kw_r=_D("99.999"))

    results = validate_candidate(tampered, input_data, {"Z1": zones[0]})
    cooling = next(
        result for result in results if result.constraint_code == "cooling_capacity_adequacy"
    )
    assert cooling.passed is False


def test_compressor_shortfall_remains_infeasible_under_existing_validator() -> None:
    zones = [_zone("Z1", "10", 5, "100")]
    input_data = _input(zones, operating="100", installed="100")
    generated = generate_balanced(input_data, get_profile("balanced"))
    tampered = replace(generated, compressor_installed_capacity_kw_r=_D("99.999"))

    results = validate_candidate(tampered, input_data, {"Z1": zones[0]})
    compressor = next(
        result for result in results if result.constraint_code == "compressor_capacity_adequacy"
    )
    assert compressor.passed is False


def test_storage_shortfall_against_authoritative_requirement_remains_infeasible() -> None:
    zones = [_zone("Z1", "10", 5, "100")]
    input_data = _input(zones, required_storage=_D("100.001"))
    candidate = generate_balanced(input_data, get_profile("balanced"))

    results = validate_candidate(candidate, input_data, {"Z1": zones[0]})
    storage = next(
        result for result in results if result.constraint_code == "storage_capacity_adequacy"
    )
    assert storage.passed is False


def test_no_feasible_candidates_keep_recommendation_empty() -> None:
    input_data = _input([_zone("Z1", "10", 5, "100")])
    candidate = replace(
        generate_balanced(input_data, get_profile("balanced")),
        feasible=False,
    )
    breakdowns = score_candidates([candidate], _weight_set())
    assert len(breakdowns) == 1
    assert breakdowns[0].diagnostic_only is True
    comparison = SchemeComparisonResult(
        candidates=[candidate],
        score_breakdowns=breakdowns,
        recommended_scheme_code=None,
        recommended_reason=None,
        requires_review=True,
    )

    assert comparison.recommended_scheme_code is None


def _weight_set():
    from cold_storage.modules.schemes.domain.models import SchemeWeightSet, WeightCriterion

    criteria = (
        ("total_area_m2", "0.2", "higher_is_better"),
        ("total_position_count", "0.2", "higher_is_better"),
        ("room_module_count", "0.1", "lower_is_better"),
        ("door_count", "0.1", "lower_is_better"),
        ("partition_length_proxy_m", "0.05", "lower_is_better"),
        ("investment_cny", "0.2", "lower_is_better"),
        ("installed_power_kw_e", "0.15", "lower_is_better"),
    )
    return SchemeWeightSet(
        id="weight-v03-p1",
        code="weight-v03-p1",
        name="V0.3 P1 test weights",
        status="approved",
        criteria=[
            WeightCriterion(
                criterion_code=code,
                weight=_D(weight),
                direction=direction,
            )
            for code, weight, direction in criteria
        ],
    )
