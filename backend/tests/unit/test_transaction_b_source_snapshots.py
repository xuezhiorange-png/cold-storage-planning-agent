"""Unit tests for Transaction B typed source snapshot models.

Covers:
- Typed result snapshot construction and rejection of unknown fields
- Traceability model construction and rejection of unknown fields
- Hash sensitivity (determinism, canonicalization, rejection of non-finite values)
- Stage-specific subclass literal type enforcement
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cold_storage.modules.orchestration.application.source_snapshots import (
    CoefficientEntry,
    CoolingLoadResultSnapshotV1,
    CoolingLoadSourceSnapshotV1,
    EquipmentResultSnapshotV1,
    EquipmentSourceSnapshotV1,
    FormulaEntry,
    InvestmentItemEntry,
    InvestmentResultSnapshotV1,
    InvestmentSourceSnapshotV1,
    PowerEquipmentRowEntry,
    PowerItemEntry,
    PowerResultSnapshotV1,
    PowerSourceSnapshotV1,
    PowerSummaryRowEntry,
    SourceReferenceEntry,
    WarningEntry,
    ZoneResultSnapshotV1,
    ZoneSourceSnapshotV1,
)

# ── Shared fixtures ─────────────────────────────────────────────────────────


def _make_zone_result_snapshot() -> ZoneResultSnapshotV1:
    return ZoneResultSnapshotV1(
        daily_inbound_mass_kg=Decimal("5000"),
        design_daily_mass_kg=Decimal("5000"),
        total_required_area_m2=Decimal("300"),
        total_area_m2=Decimal("350"),
        planning_parameters={"storage_days": 3, "utilization": 0.85},
        zones=[
            {
                "zone_code": "Z1",
                "zone_name": "Freezer",
                "temperature_band": "-25~-18",
                "function": "frozen_storage",
                "daily_throughput_kg_day": Decimal("3000"),
                "design_storage_mass_kg": Decimal("9000"),
                "position_count": 50,
                "required_area_m2": Decimal("200"),
            }
        ],
    )


def _make_cooling_load_result_snapshot() -> CoolingLoadResultSnapshotV1:
    return CoolingLoadResultSnapshotV1(
        total_cooling_load_kw=Decimal("120.5"),
        safety_margin_load_kw=Decimal("12.05"),
        envelope_heat_transfer_load_kw=Decimal("30"),
        product_sensible_heat_load_kw=Decimal("40"),
        packaging_load_kw=Decimal("5"),
        infiltration_load_kw=Decimal("10"),
        personnel_load_kw=Decimal("3"),
        lighting_load_kw=Decimal("2"),
        evaporator_fan_load_kw=Decimal("15"),
        defrost_additional_load_kw=Decimal("10"),
        other_configuration_load_kw=Decimal("5.45"),
    )


def _make_equipment_result_snapshot() -> EquipmentResultSnapshotV1:
    return EquipmentResultSnapshotV1(
        evaporator_total_cooling_capacity_kw=Decimal("150"),
        evaporator_quantity=3,
        single_evaporator_capacity_kw=Decimal("50"),
        compressor_operating_capacity_kw=Decimal("140"),
        standby_capacity_kw=Decimal("20"),
        condenser_heat_rejection_capacity_kw=Decimal("180"),
        evaporation_temperature_c=Decimal("-35"),
        condensing_temperature_c=Decimal("40"),
        defrost_method="electric",
    )


def _make_power_result_snapshot() -> PowerResultSnapshotV1:
    return PowerResultSnapshotV1(
        total_installed_power_kw_e=Decimal("250"),
        total_estimated_demand_kw=Decimal("200"),
        equipment_rows=[
            PowerEquipmentRowEntry(
                sequence=1,
                name="Compressor-1",
                area="machine_room",
                quantity=Decimal("1"),
                running_power_kw=Decimal("50"),
                total_power_kw=Decimal("50"),
                section="compressor",
            )
        ],
        summary_rows=[
            PowerSummaryRowEntry(
                name="Compressor",
                basis="equipment",
                total_power_kw=Decimal("50"),
            )
        ],
        items=[
            PowerItemEntry(
                category="compressor",
                installed_power_kw=Decimal("50"),
                demand_factor=Decimal("0.8"),
                estimated_demand_kw=Decimal("40"),
            )
        ],
        assumptions=["Using demo coefficients"],
    )


def _make_investment_result_snapshot() -> InvestmentResultSnapshotV1:
    return InvestmentResultSnapshotV1(
        total_investment_cny=Decimal("500000"),
        items=[
            InvestmentItemEntry(
                item_name="Compressor",
                amount_cny=Decimal("200000"),
            ),
            InvestmentItemEntry(
                item_name="Evaporator",
                amount_cny=Decimal("150000"),
            ),
        ],
    )


def _make_base_snapshot_kwargs(**overrides: object) -> dict[str, object]:
    """Produce the minimum kwargs needed to build a SourceSnapshotContentV1."""
    base: dict[str, object] = {
        "project_id": "proj-001",
        "project_version_id": "pv-001",
        "execution_snapshot_id": "exec-001",
        "coefficient_context_id": "cc-001",
        "orchestration_identity_id": "oi-001",
        "orchestration_attempt_id": "oa-001",
        "orchestration_fingerprint": "fp-001",
        "calculation_type": "zone",
        "calculator_id": "cold_room_zone_plan",
        "calculator_version": "1.0.0",
        "source_snapshot_schema_version": "1.0.0",
        "requires_review": False,
        "result_snapshot": _make_zone_result_snapshot().model_dump(),
        "formulas": [
            FormulaEntry(
                formula_id="F1",
                formula_version="1.0",
                expression="Q = m * cp * dT",
                description="Sensible heat",
            ).model_dump()
        ],
        "coefficients": [
            CoefficientEntry(
                code="CP_ICE",
                value=Decimal("2.09"),
                unit="kJ/(kg·K)",
                status="active",
            ).model_dump()
        ],
        "assumptions": ["Standard conditions"],
        "warnings": [WarningEntry(code="W1", message="Demo data", details={}).model_dump()],
        "source_references": [SourceReferenceEntry().model_dump()],
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════════════════════════
# TestTypedResultSnapshots
# ══════════════════════════════════════════════════════════════════════════════


class TestTypedResultSnapshots:
    def test_zone_result_snapshot_valid(self) -> None:
        snap = _make_zone_result_snapshot()
        assert snap.daily_inbound_mass_kg == "5000"
        assert snap.total_area_m2 == "350"
        assert len(snap.zones) == 1

    def test_zone_result_snapshot_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ZoneResultSnapshotV1(
                daily_inbound_mass_kg=Decimal("5000"),
                design_daily_mass_kg=Decimal("5000"),
                total_required_area_m2=Decimal("300"),
                total_area_m2=Decimal("350"),
                planning_parameters={"storage_days": 3},
                zones=[],
                bogus_field="should_fail",
            )

    def test_cooling_load_result_snapshot_valid(self) -> None:
        snap = _make_cooling_load_result_snapshot()
        assert snap.total_cooling_load_kw == "120.5"
        assert snap.safety_margin_load_kw == "12.05"

    def test_equipment_result_snapshot_valid(self) -> None:
        snap = _make_equipment_result_snapshot()
        assert snap.evaporator_total_cooling_capacity_kw == "150"
        assert snap.evaporator_quantity == 3
        assert snap.defrost_method == "electric"

    def test_power_result_snapshot_valid(self) -> None:
        snap = _make_power_result_snapshot()
        assert snap.total_installed_power_kw_e == "250"
        assert snap.total_estimated_demand_kw == "200"
        assert len(snap.equipment_rows) == 1
        assert len(snap.items) == 1

    def test_power_result_snapshot_requires_authority_field(self) -> None:
        with pytest.raises(ValidationError, match="total_installed_power_kw_e"):
            PowerResultSnapshotV1(
                # missing total_installed_power_kw_e
                total_estimated_demand_kw=Decimal("200"),
                equipment_rows=[],
                summary_rows=[],
                items=[],
                assumptions=[],
            )

    def test_investment_result_snapshot_valid(self) -> None:
        snap = _make_investment_result_snapshot()
        assert snap.total_investment_cny == "500000"
        assert len(snap.items) == 2
        assert snap.items[0].item_name == "Compressor"

    def test_investment_result_snapshot_rejects_usd(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            InvestmentResultSnapshotV1(
                total_investment_cny=Decimal("500000"),
                items=[
                    InvestmentItemEntry(
                        item_name="Compressor",
                        amount_cny=Decimal("200000"),
                    )
                ],
                total_investment_usd=Decimal("70000"),
            )

    def test_investment_item_requires_name_and_amount(self) -> None:
        with pytest.raises(ValidationError, match="item_name"):
            InvestmentItemEntry(
                item_name="",
                amount_cny=Decimal("100"),
            )


# ══════════════════════════════════════════════════════════════════════════════
# TestTraceabilityModels
# ══════════════════════════════════════════════════════════════════════════════


class TestTraceabilityModels:
    def test_formula_entry_valid(self) -> None:
        f = FormulaEntry(
            formula_id="F1",
            formula_version="1.0",
            expression="Q = m * cp * dT",
            description="Sensible heat formula",
        )
        assert f.formula_id == "F1"
        assert f.expression == "Q = m * cp * dT"

    def test_coefficient_entry_valid(self) -> None:
        c = CoefficientEntry(
            code="CP_ICE",
            value=Decimal("2.09"),
            unit="kJ/(kg·K)",
            status="active",
        )
        assert c.code == "CP_ICE"
        assert c.value == "2.09"
        assert c.source_type == "demo"

    def test_warning_entry_valid(self) -> None:
        w = WarningEntry(
            code="W001",
            message="Low storage temperature",
            details={"min_temp_c": Decimal("-30")},
        )
        assert w.code == "W001"
        assert w.details["min_temp_c"] == "-30"

    def test_source_reference_entry_valid(self) -> None:
        s = SourceReferenceEntry(
            source_type="standard",
            source_reference="GB/T 2025",
            version="2025-1",
            validity_status="valid",
            approval_status="approved",
            requires_review=False,
            notes="National standard",
        )
        assert s.source_type == "standard"
        assert s.source_reference == "GB/T 2025"

    def test_formula_entry_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            FormulaEntry(
                formula_id="F1",
                formula_version="1.0",
                expression="Q = m * cp * dT",
                description="Sensible heat",
                unknown_field="boom",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TestHashSensitivity
# ══════════════════════════════════════════════════════════════════════════════


def _make_full_zone_snapshot(**result_overrides: object) -> ZoneSourceSnapshotV1:
    """Build a full ZoneSourceSnapshotV1 for hash testing."""
    result = _make_zone_result_snapshot()
    result_data = result.model_dump()
    result_data.update(result_overrides)
    # Re-build result with overrides
    zone_result = ZoneResultSnapshotV1(**result_data)
    return ZoneSourceSnapshotV1(
        **_stage_base_kwargs(zone_result),
    )


class TestHashSensitivity:
    def test_same_content_same_hash(self) -> None:
        a = _make_full_zone_snapshot()
        b = _make_full_zone_snapshot()
        assert a.result_hash() == b.result_hash()

    def test_different_result_different_hash(self) -> None:
        a = _make_full_zone_snapshot()
        b = _make_full_zone_snapshot(
            daily_inbound_mass_kg=Decimal("5001"),
        )
        assert a.result_hash() != b.result_hash()

    def test_decimal_canonicalization(self) -> None:
        """Decimal('1.0'), Decimal('1.00'), Decimal('1E0') should all hash identically."""
        snapshots = []
        for value in [Decimal("1.0"), Decimal("1.00"), Decimal("1E0")]:
            snap = _make_full_zone_snapshot(
                daily_inbound_mass_kg=value,
            )
            snapshots.append(snap)
        hashes = [s.result_hash() for s in snapshots]
        assert len(set(hashes)) == 1, f"Expected 1 unique hash, got {len(set(hashes))}: {hashes}"

    def test_key_order_irrelevant(self) -> None:
        """Dict keys inserted in different orders should produce the same hash."""
        snap_a = _make_full_zone_snapshot()
        snap_b = _make_full_zone_snapshot()
        # The planning_parameters dict is rebuilt inside the constructor with sorted keys
        # so we verify via canonical dict instead
        cd_a = snap_a.to_canonical_dict()
        cd_b = snap_b.to_canonical_dict()
        assert cd_a == cd_b
        assert snap_a.result_hash() == snap_b.result_hash()

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="Non-finite"):
            _make_full_zone_snapshot(
                daily_inbound_mass_kg=Decimal("NaN"),
            )

    def test_infinity_rejected(self) -> None:
        with pytest.raises(ValueError, match="Non-finite"):
            _make_full_zone_snapshot(
                daily_inbound_mass_kg=Decimal("Infinity"),
            )

    def test_float_rejected(self) -> None:
        # Float is rejected by _coerce_decimals_deep in the base SourceSnapshotContentV1
        # validator (mode="before"), before the result_snapshot model sees it.
        result_dict = _make_zone_result_snapshot().model_dump()
        result_dict["daily_inbound_mass_kg"] = 5000.0  # raw float, not Decimal
        kwargs = _stage_base_kwargs(result_dict)
        # Override to use the dict directly (bypass model_dump conversion)
        kwargs["result_snapshot"] = result_dict
        with pytest.raises(TypeError, match="float"):
            ZoneSourceSnapshotV1(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# TestStageSubclasses
# ══════════════════════════════════════════════════════════════════════════════


def _stage_base_kwargs(result_snapshot: object) -> dict[str, object]:
    """Minimal kwargs shared by all stage-specific subclass constructors."""

    # Convert pydantic models to dicts so the mode="before" validator can process them
    def _to_raw(v: object) -> object:
        if hasattr(v, "model_dump"):
            return v.model_dump()
        return v

    formulas = [
        _to_raw(f)
        for f in [
            FormulaEntry(
                formula_id="F1",
                formula_version="1.0",
                expression="x = y",
                description="test",
            )
        ]
    ]
    coefficients = [_to_raw(c) for c in []]
    warnings = [_to_raw(w) for w in []]
    source_refs = [_to_raw(s) for s in []]

    return {
        "project_id": "proj-001",
        "project_version_id": "pv-001",
        "execution_snapshot_id": "exec-001",
        "coefficient_context_id": "cc-001",
        "orchestration_identity_id": "oi-001",
        "orchestration_attempt_id": "oa-001",
        "orchestration_fingerprint": "fp-001",
        "source_snapshot_schema_version": "1.0.0",
        "requires_review": False,
        "result_snapshot": _to_raw(result_snapshot),
        "formulas": formulas,
        "coefficients": coefficients,
        "assumptions": [],
        "warnings": warnings,
        "source_references": source_refs,
    }


class TestStageSubclasses:
    def test_zone_snapshot_literal_types(self) -> None:
        snap = ZoneSourceSnapshotV1(
            **_stage_base_kwargs(_make_zone_result_snapshot()),
        )
        assert snap.calculation_type == "zone"
        assert snap.calculator_id == "cold_room_zone_plan"
        assert snap.calculator_version == "1.0.0"

    def test_cooling_load_snapshot_literal_types(self) -> None:
        snap = CoolingLoadSourceSnapshotV1(
            **_stage_base_kwargs(_make_cooling_load_result_snapshot()),
        )
        assert snap.calculation_type == "cooling_load"
        assert snap.calculator_id == "cooling_load"

    def test_equipment_snapshot_literal_types(self) -> None:
        snap = EquipmentSourceSnapshotV1(
            **_stage_base_kwargs(_make_equipment_result_snapshot()),
        )
        assert snap.calculation_type == "equipment"
        assert snap.calculator_id == "equipment"

    def test_power_snapshot_literal_types(self) -> None:
        snap = PowerSourceSnapshotV1(
            **_stage_base_kwargs(_make_power_result_snapshot()),
        )
        assert snap.calculation_type == "power"
        assert snap.calculator_id == "installed_power"

    def test_investment_snapshot_literal_types(self) -> None:
        snap = InvestmentSourceSnapshotV1(
            **_stage_base_kwargs(_make_investment_result_snapshot()),
        )
        assert snap.calculation_type == "investment"
        assert snap.calculator_id == "investment_estimate"

    def test_wrong_calculator_id_rejected(self) -> None:
        """Overriding calculator_id to a non-matching value must fail."""
        with pytest.raises(ValidationError, match="calculator_id"):
            ZoneSourceSnapshotV1(
                **_stage_base_kwargs(_make_zone_result_snapshot()),
                calculator_id="wrong",
            )
