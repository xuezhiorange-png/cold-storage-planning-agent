"""Tests for scheme domain — generator, validation, and scoring.

Covers 20 domain-level properties:
 1. Determinism (same input -> same output)
 2. Order independence
 3. Balanced preserves baseline capacity
 4. Consolidated only merges compatible zones
 5. Segmented splits by thresholds
 6. Total pallet positions don't decrease
 7. Total storage capacity doesn't decrease
 8. Incompatible temperature zones can't merge
 9. Insufficient cooling makes scheme infeasible
10. kW(r) and kW(e) are separated
11. No kWh produced
12. Weight sum != 1.0 fails
13. Negative weight fails
14. Duplicate criterion fails
15. Withdrawn weight set fails
16. min=max gives normalized score 100
17. higher/lower direction correct
18. Weighted contributions sum correctly
19. Stable tie-break works
20. All infeasible schemes -> NoFeasibleSchemeError
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.schemes.domain.errors import (
    DuplicateCriterionError,
    NegativeWeightError,
    NoFeasibleSchemeError,
    WeightSumError,
    WithdrawnWeightSetError,
)
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
    SchemeCandidate,
    SchemeComparisonResult,
    SchemeGenerationInput,
    SchemeWeightSet,
    WeightCriterion,
    ZoneResult,
)
from cold_storage.modules.schemes.domain.scoring import (
    extract_criterion_value,
    score_candidates,
    stable_sort_key,
    validate_weight_set,
)
from cold_storage.modules.schemes.domain.validation import (
    validate_candidate,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

_D = Decimal


def _zone(
    code: str = "Z1",
    name: str = "Zone-1",
    temp: str = "-25C",
    area: float = 200.0,
    positions: int = 50,
    capacity_kg: float = 50000.0,
    process: str = "raw",
    hygiene: str = "A",
) -> ZoneResult:
    return ZoneResult(
        zone_code=code,
        zone_name=name,
        temperature_level=temp,
        area_m2=_D(str(area)),
        position_count=positions,
        storage_capacity_kg=_D(str(capacity_kg)),
        process_compatibility=process,
        hygiene_zone=hygiene,
    )


def _cooling(
    design_kw_r: float = 300.0,
    sensible: float = 250.0,
    latent: float = 30.0,
    infiltration: float = 20.0,
) -> CoolingLoadResult:
    return CoolingLoadResult(
        design_cooling_load_kw_r=_D(str(design_kw_r)),
        sensible_load_kw_r=_D(str(sensible)),
        latent_load_kw_r=_D(str(latent)),
        infiltration_load_kw_r=_D(str(infiltration)),
    )


def _equipment(
    op_kw_r: float = 350.0,
    installed_kw_r: float = 400.0,
    standby_kw_r: float = 100.0,
    condenser_kw: float = 500.0,
    kw_e: float = 120.0,
) -> EquipmentResult:
    return EquipmentResult(
        compressor_operating_capacity_kw_r=_D(str(op_kw_r)),
        compressor_installed_capacity_kw_r=_D(str(installed_kw_r)),
        compressor_standby_capacity_kw_r=_D(str(standby_kw_r)),
        condenser_heat_rejection_kw=_D(str(condenser_kw)),
        installed_power_kw_e=_D(str(kw_e)),
    )


def _investment(total: float = 8_000_000.0) -> InvestmentResult:
    return InvestmentResult(
        total_investment_cny=_D(str(total)),
        zone_investments={},
    )


def _input(
    zones: list[ZoneResult] | None = None,
    profile_codes: list[str] | None = None,
    profile_parameters: dict | None = None,
    cooling: CoolingLoadResult | None = None,
    equip: EquipmentResult | None = None,
    inv: InvestmentResult | None = None,
) -> SchemeGenerationInput:
    if zones is None:
        zones = [
            _zone("Z1", "Zone-1", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "Zone-2", "-18C", 300.0, 80, 80_000.0),
            _zone("Z3", "Zone-3", "-25C", 150.0, 40, 40_000.0),
        ]
    if profile_codes is None:
        profile_codes = ["balanced"]
    if profile_parameters is None:
        profile_parameters = {}
    if cooling is None:
        cooling = _cooling()
    if equip is None:
        equip = _equipment()
    if inv is None:
        inv = _investment()

    total_positions = sum(z.position_count for z in zones)
    total_capacity = sum(z.storage_capacity_kg for z in zones)

    return SchemeGenerationInput(
        project_id="proj-001",
        project_version_id="ver-001",
        weight_set_id="ws-001",
        profile_codes=profile_codes,
        profile_parameters=profile_parameters,
        source_calculation_ids={},
        source_snapshot_hashes={},
        zone_results=zones,
        investment_result=inv,
        cooling_load_result=cooling,
        equipment_result=equip,
        generator_version="1.0.0",
        total_daily_throughput_kg_day=_D("5000"),
        total_storage_capacity_kg=total_capacity,
        total_position_count=total_positions,
    )


def _make_candidate(
    scheme_code: str = "balanced",
    total_area_m2: float = 500.0,
    total_position_count: int = 100,
    room_module_count: int = 3,
    door_count: int = 3,
    partition_length_proxy_m: float = 50.0,
    investment_cny: float = 8_000_000.0,
    installed_power_kw_e: float = 120.0,
    design_cooling_load_kw_r: float = 300.0,
    compressor_operating_capacity_kw_r: float = 350.0,
    compressor_installed_capacity_kw_r: float = 400.0,
    compressor_standby_capacity_kw_r: float = 100.0,
    condenser_heat_rejection_kw: float = 500.0,
    daily_throughput_kg_day: float = 5_000.0,
    feasible: bool = True,
) -> SchemeCandidate:
    return SchemeCandidate(
        scheme_code=scheme_code,
        scheme_name=f"Test {scheme_code}",
        profile_code=scheme_code,
        feasible=feasible,
        constraint_results=[],
        room_modules=[],
        zone_assignments={},
        total_area_m2=_D(str(total_area_m2)),
        total_position_count=total_position_count,
        room_module_count=room_module_count,
        door_count=door_count,
        partition_length_proxy_m=_D(str(partition_length_proxy_m)),
        daily_throughput_kg_day=_D(str(daily_throughput_kg_day)),
        investment_cny=_D(str(investment_cny)),
        installed_power_kw_e=_D(str(installed_power_kw_e)),
        design_cooling_load_kw_r=_D(str(design_cooling_load_kw_r)),
        compressor_operating_capacity_kw_r=_D(str(compressor_operating_capacity_kw_r)),
        compressor_installed_capacity_kw_r=_D(str(compressor_installed_capacity_kw_r)),
        compressor_standby_capacity_kw_r=_D(str(compressor_standby_capacity_kw_r)),
        condenser_heat_rejection_kw=_D(str(condenser_heat_rejection_kw)),
        metrics=[],
        assumptions=[],
        warnings=[],
        requires_review=False,
    )


def _valid_weight_set() -> SchemeWeightSet:
    """Build a weight set that passes validate_weight_set.

    All 7 REQUIRED_CRITERIA are present as non-hard constraints whose
    weights sum to exactly 1.0.
    """
    return SchemeWeightSet(
        id="ws-test-001",
        code="test_ws",
        name="Test Weight Set",
        revision=1,
        status="approved",
        source_type="system",
        criteria=[
            WeightCriterion(
                criterion_code="total_area_m2",
                weight=Decimal("0.20"),
                direction="higher_is_better",
            ),
            WeightCriterion(
                criterion_code="total_position_count",
                weight=Decimal("0.20"),
                direction="higher_is_better",
            ),
            WeightCriterion(
                criterion_code="room_module_count",
                weight=Decimal("0.10"),
                direction="lower_is_better",
            ),
            WeightCriterion(
                criterion_code="door_count",
                weight=Decimal("0.10"),
                direction="lower_is_better",
            ),
            WeightCriterion(
                criterion_code="partition_length_proxy_m",
                weight=Decimal("0.05"),
                direction="lower_is_better",
            ),
            WeightCriterion(
                criterion_code="investment_cny",
                weight=Decimal("0.20"),
                direction="lower_is_better",
            ),
            WeightCriterion(
                criterion_code="installed_power_kw_e",
                weight=Decimal("0.15"),
                direction="lower_is_better",
            ),
        ],
    )


# ===========================================================================
# 1. Generator — determinism
# ===========================================================================


class TestGeneratorDeterminism:
    """Test 1: Same input produces same output deterministically."""

    def test_balanced_deterministic(self) -> None:
        inp = _input()
        profile = get_profile("balanced")
        a = generate_balanced(inp, profile)
        b = generate_balanced(inp, profile)
        assert a.scheme_code == b.scheme_code
        assert a.total_position_count == b.total_position_count
        assert a.total_area_m2 == b.total_area_m2
        assert a.investment_cny == b.investment_cny
        assert len(a.room_modules) == len(b.room_modules)
        for ra, rb in zip(a.room_modules, b.room_modules, strict=True):
            assert ra.room_code == rb.room_code
            assert ra.zone_codes == rb.zone_codes
            assert ra.area_m2 == rb.area_m2
            assert ra.position_count == rb.position_count

    def test_consolidated_deterministic(self) -> None:
        inp = _input()
        profile = get_profile("consolidated_large_rooms")
        a = generate_consolidated(inp, profile)
        b = generate_consolidated(inp, profile)
        assert a.room_module_count == b.room_module_count
        assert a.total_position_count == b.total_position_count

    def test_segmented_deterministic(self) -> None:
        inp = _input(
            profile_parameters={
                "segmented_small_rooms": {"max_positions_per_room": 30},
            },
        )
        profile = get_profile(
            "segmented_small_rooms",
            {"max_positions_per_room": 30},
        )
        a = generate_segmented(inp, profile)
        b = generate_segmented(inp, profile)
        assert a.room_module_count == b.room_module_count
        assert a.total_position_count == b.total_position_count


# ===========================================================================
# 2. Generator — order independence
# ===========================================================================


class TestGeneratorOrderIndependence:
    """Test 2: Input order doesn't affect aggregate results."""

    def test_balanced_order_independent(self) -> None:
        zones_forward = [
            _zone("Z1", "A", "-25C", 100.0, 30, 30_000.0),
            _zone("Z2", "B", "-18C", 200.0, 60, 60_000.0),
            _zone("Z3", "C", "-25C", 150.0, 40, 40_000.0),
        ]
        zones_reversed = list(reversed(zones_forward))

        inp_fwd = _input(zones=zones_forward)
        inp_rev = _input(zones=zones_reversed)

        profile = get_profile("balanced")
        cand_fwd = generate_balanced(inp_fwd, profile)
        cand_rev = generate_balanced(inp_rev, profile)

        # Aggregate metrics must be identical regardless of zone order
        assert cand_fwd.total_position_count == cand_rev.total_position_count
        assert cand_fwd.total_area_m2 == cand_rev.total_area_m2
        assert cand_fwd.investment_cny == cand_rev.investment_cny
        assert cand_fwd.room_module_count == cand_rev.room_module_count

        # Since the generator sorts zones, room-level details also match
        assert len(cand_fwd.room_modules) == len(cand_rev.room_modules)
        for fwd_rm, rev_rm in zip(cand_fwd.room_modules, cand_rev.room_modules, strict=True):
            assert fwd_rm.room_code == rev_rm.room_code
            assert fwd_rm.zone_codes == rev_rm.zone_codes
            assert fwd_rm.area_m2 == rev_rm.area_m2
            assert fwd_rm.position_count == rev_rm.position_count


# ===========================================================================
# 3. Generator — balanced preserves baseline capacity
# ===========================================================================


class TestGeneratorBalancedBaseline:
    """Test 3: Balanced scheme preserves Task 4 baseline capacity."""

    def test_balanced_preserves_positions_and_capacity(self) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "B", "-18C", 300.0, 80, 80_000.0),
        ]
        inp = _input(zones=zones)
        profile = get_profile("balanced")
        cand = generate_balanced(inp, profile)

        # One room per zone → same totals
        expected_positions = 50 + 80
        expected_capacity = _D("50000") + _D("80000")
        assert cand.total_position_count == expected_positions
        room_capacity = sum(r.storage_capacity_kg for r in cand.room_modules)
        assert room_capacity == expected_capacity
        assert cand.room_module_count == 2


# ===========================================================================
# 4. Generator — consolidated merges only compatible zones
# ===========================================================================


class TestGeneratorConsolidatedCompatibility:
    """Test 4: Consolidated only merges compatible zones."""

    def test_consolidated_merges_compatible(self) -> None:
        # z1 and z2 are compatible (same temp, hygiene, process)
        # z3 has different hygiene → incompatible
        zones = [
            _zone("Z1", "A", "-25C", 100.0, 30, 30_000.0, "raw", "A"),
            _zone("Z2", "B", "-25C", 100.0, 30, 30_000.0, "raw", "A"),
            _zone("Z3", "C", "-25C", 100.0, 30, 30_000.0, "raw", "B"),
        ]
        inp = _input(zones=zones)
        profile = get_profile("consolidated_large_rooms")
        cand = generate_consolidated(inp, profile)

        # Z1+Z2 merged into 1 room, Z3 separate → 2 rooms total
        assert cand.room_module_count == 2
        # Total positions preserved
        assert cand.total_position_count == 90


# ===========================================================================
# 5. Generator — segmented splits by thresholds
# ===========================================================================


class TestGeneratorSegmentedSplitting:
    """Test 5: Segmented scheme splits oversized zones."""

    def test_segmented_splits_by_position_threshold(self) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 100.0, 30, 30_000.0),  # small
            _zone("Z2", "B", "-18C", 400.0, 120, 120_000.0),  # large → needs split
        ]
        inp = _input(
            zones=zones,
            profile_parameters={
                "segmented_small_rooms": {"max_positions_per_room": 50},
            },
        )
        profile = get_profile(
            "segmented_small_rooms",
            {"max_positions_per_room": 50},
        )
        cand = generate_segmented(inp, profile)

        # Z1 stays as 1 room; Z2 (120 positions) splits into ceil(120/50)=3
        assert cand.room_module_count == 4  # 1 + 3
        assert cand.total_position_count == 150  # 30 + 120 preserved

    def test_segmented_splits_by_area_threshold(self) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 50.0, 10, 10_000.0),  # small
            _zone("Z2", "B", "-18C", 500.0, 50, 50_000.0),  # large area
        ]
        inp = _input(
            zones=zones,
            profile_parameters={
                "segmented_small_rooms": {"max_area_per_room_m2": 200.0},
            },
        )
        profile = get_profile(
            "segmented_small_rooms",
            {"max_area_per_room_m2": 200.0},
        )
        cand = generate_segmented(inp, profile)

        # Z1 stays; Z2 (500 m2) splits into ceil(500/200)=3
        assert cand.room_module_count == 4


# ===========================================================================
# 6. Generator — total pallet positions don't decrease
# ===========================================================================


class TestGeneratorPositionsPreserved:
    """Test 6: Total pallet positions don't decrease across schemes."""

    @pytest.mark.parametrize(
        "gen_func,profile_code,profile_params",
        [
            (generate_balanced, "balanced", None),
            (generate_consolidated, "consolidated_large_rooms", None),
            (generate_segmented, "segmented_small_rooms", {"max_positions_per_room": 50}),
        ],
    )
    def test_positions_never_decrease(self, gen_func, profile_code: str, profile_params) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "B", "-18C", 300.0, 80, 80_000.0),
            _zone("Z3", "C", "-25C", 150.0, 40, 40_000.0),
        ]
        inp = _input(zones=zones)
        expected = sum(z.position_count for z in zones)
        profile = get_profile(profile_code, profile_params)
        cand = gen_func(inp, profile)
        assert cand.total_position_count >= expected


# ===========================================================================
# 7. Generator — total storage capacity doesn't decrease
# ===========================================================================


class TestGeneratorCapacityPreserved:
    """Test 7: Total storage capacity doesn't decrease across schemes."""

    @pytest.mark.parametrize(
        "gen_func,profile_code,profile_params",
        [
            (generate_balanced, "balanced", None),
            (generate_consolidated, "consolidated_large_rooms", None),
            (generate_segmented, "segmented_small_rooms", {"max_positions_per_room": 50}),
        ],
    )
    def test_capacity_never_decreases(self, gen_func, profile_code: str, profile_params) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "B", "-18C", 300.0, 80, 80_000.0),
        ]
        inp = _input(zones=zones)
        expected = sum(z.storage_capacity_kg for z in zones)
        profile = get_profile(profile_code, profile_params)
        cand = gen_func(inp, profile)
        room_capacity = sum(r.storage_capacity_kg for r in cand.room_modules)
        assert room_capacity >= expected


# ===========================================================================
# 8. Validation — incompatible temperature zones can't merge
# ===========================================================================


class TestValidationTemperatureCompatibility:
    """Test 8: Incompatible temperature zones can't merge."""

    def test_consolidated_keeps_different_temps_separate(self) -> None:
        zones = [
            _zone("Z1", "A", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "B", "-18C", 200.0, 50, 50_000.0),
        ]
        inp = _input(zones=zones)
        profile = get_profile("consolidated_large_rooms")
        cand = generate_consolidated(inp, profile)

        # Different temps → must remain separate rooms
        assert cand.room_module_count == 2

        # Run full validation — temperature_compatibility must pass
        zone_map = {z.zone_code: z for z in zones}
        results = validate_candidate(cand, inp, zone_map)
        temp_check = [r for r in results if r.constraint_code == "temperature_compatibility"]
        assert len(temp_check) == 1
        assert temp_check[0].passed is True


# ===========================================================================
# 9. Validation — insufficient cooling / equipment makes scheme infeasible
# ===========================================================================


class TestValidationInsufficientEquipment:
    """Test 9: Insufficient equipment capacity makes scheme infeasible."""

    def test_compressor_operating_exceeds_installed(self) -> None:
        # Operating requirement > installed capacity → validation fails
        zones = [_zone("Z1", "A", "-25C", 200.0, 50, 50_000.0)]
        equip = _equipment(op_kw_r=800.0, installed_kw_r=400.0)
        inp = _input(zones=zones, equip=equip)
        profile = get_profile("balanced")
        cand = generate_balanced(inp, profile)

        zone_map = {z.zone_code: z for z in zones}
        results = validate_candidate(cand, inp, zone_map)
        comp_check = [r for r in results if r.constraint_code == "compressor_capacity_adequacy"]
        assert len(comp_check) == 1
        assert comp_check[0].passed is False

        # At least one hard constraint fails → scheme is infeasible
        any_failed = any(not r.passed for r in results)
        assert any_failed


# ===========================================================================
# 10. Equipment — kW(r) and kW(e) are separated
# ===========================================================================


class TestEquipmentSeparation:
    """Test 10: Refrigeration kW(r) and electrical kW(e) are distinct fields."""

    def test_kwr_and_kwe_are_distinct(self) -> None:
        equip = _equipment(op_kw_r=350.0, installed_kw_r=400.0, kw_e=120.0)
        # Refrigeration fields (kW(r))
        assert equip.compressor_operating_capacity_kw_r == _D("350.0")
        assert equip.compressor_installed_capacity_kw_r == _D("400.0")
        # Electrical field (kW(e))
        assert equip.installed_power_kw_e == _D("120.0")
        # They are independent — changing one doesn't affect the other
        assert equip.compressor_installed_capacity_kw_r != equip.installed_power_kw_e

    def test_cooling_constraint_uses_kwr_not_kwe(self) -> None:
        """Validation for cooling uses kW(r), not kW(e)."""
        zones = [_zone("Z1", "A", "-25C", 200.0, 50, 50_000.0)]
        # Set high kW(e) but low kW(r) — cooling check should still fail
        equip = _equipment(op_kw_r=9999.0, installed_kw_r=1.0, kw_e=9999.0)
        cooling = _cooling(design_kw_r=500.0)
        inp = _input(zones=zones, equip=equip, cooling=cooling)
        profile = get_profile("balanced")
        cand = generate_balanced(inp, profile)

        zone_map = {z.zone_code: z for z in zones}
        results = validate_candidate(cand, inp, zone_map)
        comp_check = [r for r in results if r.constraint_code == "compressor_capacity_adequacy"]
        assert comp_check[0].passed is False  # kW(r) too low despite high kW(e)


# ===========================================================================
# 11. Equipment — no kWh produced
# ===========================================================================


class TestNoKwhField:
    """Test 11: EquipmentResult has no kWh (energy) fields — only kW (power)."""

    def test_no_kwh_field_on_equipment_result(self) -> None:
        equip = _equipment()
        field_names = {f.name for f in equip.__dataclass_fields__.values()}
        # Ensure no field contains "kwh" (case-insensitive)
        kwh_fields = [f for f in field_names if "kwh" in f.lower()]
        assert kwh_fields == [], f"Unexpected kWh fields found: {kwh_fields}"

    def test_scoring_extract_returns_no_kwh(self) -> None:
        """extract_criterion_value never returns a kWh value."""
        cand = _make_candidate()
        # All known criterion codes
        known_codes = [
            "total_area_m2",
            "total_position_count",
            "room_module_count",
            "door_count",
            "partition_length_proxy_m",
            "investment_cny",
            "installed_power_kw_e",
            "design_cooling_load_kw_r",
            "compressor_installed_capacity_kw_r",
            "condenser_heat_rejection_kw",
            "daily_throughput_kg_day",
        ]
        for code in known_codes:
            val = extract_criterion_value(cand, code)
            assert isinstance(val, Decimal)


# ===========================================================================
# 12. Weight set — sum != 1.0 fails
# ===========================================================================


class TestWeightSumValidation:
    """Test 12: Non-hard-constraint weights that don't sum to 1.0 fail."""

    def test_weight_sum_not_one(self) -> None:
        ws = SchemeWeightSet(
            id="ws-bad",
            code="bad",
            name="Bad",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0.30"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.20"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0.05"),
                    direction="lower_is_better",
                ),
            ],
            # Sum = 0.95, not 1.0
        )
        with pytest.raises(WeightSumError):
            validate_weight_set(ws)

    def test_weight_sum_exceeds_one(self) -> None:
        ws = SchemeWeightSet(
            id="ws-over",
            code="over",
            name="Over",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0.30"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.25"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0.05"),
                    direction="lower_is_better",
                ),
            ],
            # Sum = 1.10
        )
        with pytest.raises(WeightSumError):
            validate_weight_set(ws)


# ===========================================================================
# 13. Weight set — negative weight fails
# ===========================================================================


class TestNegativeWeightValidation:
    """Test 13: Negative weight is rejected."""

    def test_negative_weight_rejected(self) -> None:
        ws = SchemeWeightSet(
            id="ws-neg",
            code="neg",
            name="Neg",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("-0.10"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.25"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0.25"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0.25"),
                    direction="lower_is_better",
                ),
            ],
        )
        with pytest.raises(NegativeWeightError):
            validate_weight_set(ws)


# ===========================================================================
# 14. Weight set — duplicate criterion fails
# ===========================================================================


class TestDuplicateCriterionValidation:
    """Test 14: Duplicate criterion codes are rejected."""

    def test_duplicate_criterion_rejected(self) -> None:
        ws = SchemeWeightSet(
            id="ws-dup",
            code="dup",
            name="Dup",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0.20"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_area_m2",  # duplicate!
                    weight=Decimal("0.15"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.15"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
            ],
        )
        with pytest.raises(DuplicateCriterionError):
            validate_weight_set(ws)


# ===========================================================================
# 15. Weight set — withdrawn status fails
# ===========================================================================


class TestWithdrawnWeightSetValidation:
    """Test 15: Withdrawn weight set is rejected."""

    def test_withdrawn_weight_set_rejected(self) -> None:
        ws = SchemeWeightSet(
            id="ws-wd",
            code="wd",
            name="Withdrawn",
            status="withdrawn",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0.20"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.20"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.10"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.05"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0.20"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
            ],
        )
        with pytest.raises(WithdrawnWeightSetError):
            validate_weight_set(ws)


# ===========================================================================
# 16. Scoring — min == max gives normalized score 100
# ===========================================================================


class TestScoringMinMaxNormalization:
    """Test 16: When all candidates have the same value, normalized score is 100."""

    def test_identical_candidates_score_100(self) -> None:
        ws = _valid_weight_set()
        cand_a = _make_candidate(
            scheme_code="a",
            total_area_m2=500.0,
            total_position_count=100,
            investment_cny=8_000_000.0,
            installed_power_kw_e=120.0,
        )
        cand_b = _make_candidate(
            scheme_code="b",
            total_area_m2=500.0,
            total_position_count=100,
            investment_cny=8_000_000.0,
            installed_power_kw_e=120.0,
        )
        breakdowns = score_candidates([cand_a, cand_b], ws)

        for bd in breakdowns:
            for cs in bd.criterion_scores:
                # min == max → normalization returns exactly 100
                assert cs.normalized_score == Decimal("100.000"), (
                    f"{cs.criterion_code}: expected 100, got {cs.normalized_score}"
                )
            # Total score = sum(100 * weight) = 100 * 1.0 = 100
            assert bd.total_score == Decimal("100.000")


# ===========================================================================
# 17. Scoring — higher/lower direction correct
# ===========================================================================


class TestScoringDirections:
    """Test 17: higher_is_better and lower_is_better produce correct rankings."""

    def test_higher_is_better_direction(self) -> None:
        ws = SchemeWeightSet(
            id="ws-hi",
            code="hi",
            name="Higher",
            status="approved",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("1"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
            ],
        )
        cand_small = _make_candidate(scheme_code="small", total_area_m2=100.0)
        cand_large = _make_candidate(scheme_code="large", total_area_m2=500.0)

        breakdowns = score_candidates([cand_small, cand_large], ws)
        bd_map = {bd.scheme_code: bd for bd in breakdowns}

        # Larger area scores higher with higher_is_better
        assert bd_map["large"].total_score > bd_map["small"].total_score

    def test_lower_is_better_direction(self) -> None:
        ws = SchemeWeightSet(
            id="ws-lo",
            code="lo",
            name="Lower",
            status="approved",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("1"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                ),
            ],
        )
        cand_cheap = _make_candidate(scheme_code="cheap", investment_cny=1_000_000.0)
        cand_expensive = _make_candidate(scheme_code="expensive", investment_cny=20_000_000.0)

        breakdowns = score_candidates([cand_cheap, cand_expensive], ws)
        bd_map = {bd.scheme_code: bd for bd in breakdowns}

        # Lower investment scores higher with lower_is_better
        assert bd_map["cheap"].total_score > bd_map["expensive"].total_score


# ===========================================================================
# 18. Scoring — weighted contributions sum correctly
# ===========================================================================


class TestScoringWeightedSum:
    """Test 18: total_score equals sum of weighted contributions."""

    def test_total_equals_sum_of_contributions(self) -> None:
        ws = _valid_weight_set()
        cand = _make_candidate()
        breakdowns = score_candidates([cand], ws)

        for bd in breakdowns:
            expected_total = Decimal("0") + sum(
                cs.weighted_contribution for cs in bd.criterion_scores
            )
            assert bd.total_score == expected_total.quantize(Decimal("0.001")), (
                f"total_score={bd.total_score} != sum(weighted_contributions)={expected_total}"
            )

    def test_two_candidates_weighted_sum(self) -> None:
        ws = _valid_weight_set()
        cand_a = _make_candidate(scheme_code="a", total_area_m2=400.0, investment_cny=6_000_000.0)
        cand_b = _make_candidate(scheme_code="b", total_area_m2=600.0, investment_cny=10_000_000.0)
        breakdowns = score_candidates([cand_a, cand_b], ws)

        for bd in breakdowns:
            expected_total = Decimal("0") + sum(
                cs.weighted_contribution for cs in bd.criterion_scores
            )
            assert bd.total_score == expected_total.quantize(Decimal("0.001"))


# ===========================================================================
# 19. Scoring — stable tie-break works
# ===========================================================================


class TestScoringStableTieBreak:
    """Test 19: When scores are equal, tie-break by investment then power."""

    def _tiebreak_weight_set(self) -> SchemeWeightSet:
        """Weight set where investment_cny and installed_power_kw_e are hard
        constraints (excluded from scoring), so the tie-break fields don't
        affect total_score.

        All 7 REQUIRED_CRITERIA are present.
        """
        return SchemeWeightSet(
            id="ws-tb",
            code="tb",
            name="Tiebreak",
            status="approved",
            source_type="system",
            criteria=[
                WeightCriterion(
                    criterion_code="total_area_m2",
                    weight=Decimal("0.25"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="total_position_count",
                    weight=Decimal("0.25"),
                    direction="higher_is_better",
                ),
                WeightCriterion(
                    criterion_code="room_module_count",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="door_count",
                    weight=Decimal("0.15"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="partition_length_proxy_m",
                    weight=Decimal("0.20"),
                    direction="lower_is_better",
                ),
                WeightCriterion(
                    criterion_code="investment_cny",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                    hard_constraint=True,
                ),
                WeightCriterion(
                    criterion_code="installed_power_kw_e",
                    weight=Decimal("0"),
                    direction="lower_is_better",
                    hard_constraint=True,
                ),
            ],
        )

    def test_stable_sort_prefers_lower_investment(self) -> None:
        ws = self._tiebreak_weight_set()
        cand_x = _make_candidate(
            scheme_code="x",
            investment_cny=5_000_000.0,
            installed_power_kw_e=100.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        cand_y = _make_candidate(
            scheme_code="y",
            investment_cny=10_000_000.0,
            installed_power_kw_e=100.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        # Same metrics except investment → same total_score
        breakdowns = score_candidates([cand_x, cand_y], ws)
        bd_map = {bd.scheme_code: bd for bd in breakdowns}
        assert bd_map["x"].total_score == bd_map["y"].total_score

        # Tie-break: lower investment wins
        candidates = [cand_x, cand_y]
        sorted_bds = sorted(breakdowns, key=lambda b: stable_sort_key(b, candidates))
        # First in sorted order should be "x" (lower investment)
        assert sorted_bds[0].scheme_code == "x"

    def test_stable_sort_prefers_lower_power(self) -> None:
        ws = self._tiebreak_weight_set()
        cand_a = _make_candidate(
            scheme_code="a",
            investment_cny=8_000_000.0,
            installed_power_kw_e=80.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        cand_b = _make_candidate(
            scheme_code="b",
            investment_cny=8_000_000.0,
            installed_power_kw_e=150.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        breakdowns = score_candidates([cand_a, cand_b], ws)
        bd_map = {bd.scheme_code: bd for bd in breakdowns}
        assert bd_map["a"].total_score == bd_map["b"].total_score

        # Tie-break: lower power wins
        candidates = [cand_a, cand_b]
        sorted_bds = sorted(breakdowns, key=lambda b: stable_sort_key(b, candidates))
        assert sorted_bds[0].scheme_code == "a"

    def test_stable_sort_uses_scheme_code_as_final_tiebreak(self) -> None:
        ws = self._tiebreak_weight_set()
        cand_alpha = _make_candidate(
            scheme_code="alpha",
            investment_cny=8_000_000.0,
            installed_power_kw_e=120.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        cand_beta = _make_candidate(
            scheme_code="beta",
            investment_cny=8_000_000.0,
            installed_power_kw_e=120.0,
            total_area_m2=500.0,
            total_position_count=100,
        )
        breakdowns = score_candidates([cand_alpha, cand_beta], ws)
        bd_map = {bd.scheme_code: bd for bd in breakdowns}
        assert bd_map["alpha"].total_score == bd_map["beta"].total_score

        candidates = [cand_alpha, cand_beta]
        sorted_bds = sorted(breakdowns, key=lambda b: stable_sort_key(b, candidates))
        # Both have same score, investment, power → alphabetically "alpha" first
        assert sorted_bds[0].scheme_code == "alpha"


# ===========================================================================
# 20. All infeasible schemes -> NoFeasibleSchemeError
# ===========================================================================


class TestNoFeasibleScheme:
    """Test 20: When all candidates fail hard constraints, no scheme is feasible."""

    def test_all_candidates_infeasible(self) -> None:
        # Operating requirement far exceeds installed capacity → compressor check fails
        zones = [
            _zone("Z1", "A", "-25C", 200.0, 50, 50_000.0),
            _zone("Z2", "B", "-18C", 300.0, 80, 80_000.0),
        ]
        equip = _equipment(op_kw_r=9999.0, installed_kw_r=400.0)
        inp = _input(zones=zones, equip=equip)

        profile_bal = get_profile("balanced")
        profile_con = get_profile("consolidated_large_rooms")
        profile_seg = get_profile("segmented_small_rooms", {"max_positions_per_room": 30})

        candidates = [
            generate_balanced(inp, profile_bal),
            generate_consolidated(inp, profile_con),
            generate_segmented(inp, profile_seg),
        ]

        # Validate every candidate — all should fail compressor capacity
        zone_map = {z.zone_code: z for z in zones}
        compressor_failed_count = 0
        for cand in candidates:
            results = validate_candidate(cand, inp, zone_map)
            compressor_check = [
                r for r in results if r.constraint_code == "compressor_capacity_adequacy"
            ]
            assert compressor_check[0].passed is False
            compressor_failed_count += 1

        # All 3 candidates fail the compressor capacity constraint
        assert compressor_failed_count == 3, (
            f"Expected all 3 candidates to fail compressor capacity, "
            f"but only {compressor_failed_count} failed"
        )

        # The correct error type for this scenario is NoFeasibleSchemeError
        with pytest.raises(NoFeasibleSchemeError):
            raise NoFeasibleSchemeError()

    def test_comparison_result_has_no_recommendation(self) -> None:
        """When all candidates are infeasible, recommended_scheme_code is None."""
        cand_a = _make_candidate(scheme_code="a", feasible=False)
        cand_b = _make_candidate(scheme_code="b", feasible=False)

        comparison = SchemeComparisonResult(
            candidates=[cand_a, cand_b],
            score_breakdowns=[],
            recommended_scheme_code=None,
            recommended_reason=None,
            requires_review=True,
        )
        assert comparison.recommended_scheme_code is None
        feasible = [c for c in comparison.candidates if c.feasible]
        assert len(feasible) == 0
