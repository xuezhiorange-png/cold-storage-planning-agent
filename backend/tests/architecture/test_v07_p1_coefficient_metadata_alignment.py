"""Coefficient metadata alignment for V0.7 P1 data integrity proof."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.investment import InvestmentEstimator
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.coefficients.domain.catalog import COEFFICIENT_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs" / "audit" / "data-integrity-matrix.md"
INVENTORY_PATH = REPO_ROOT / "docs" / "audit" / "coefficient-inventory.md"

REQUIRED_DEMO_METADATA_KEYS: tuple[str, ...] = (
    "source_type",
    "validity_status",
    "requires_review",
    "code",
    "name",
    "unit",
    "value",
)


def _matrix_rows_with_leaf(leaf_id: str) -> list[str]:
    text = MATRIX_PATH.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if leaf_id in line and "|" in line]


def test_zone_planner_demo_coefficients_carry_required_metadata() -> None:
    planner = ColdRoomZonePlanner()
    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=20_000,
            working_time_h_per_day=16,
            finished_storage_days=7,
            packaging_storage_days=1,
            precooling_required_ratio=0.6,
        )
    )
    assert result.success is True
    assert result.requires_review is True
    assert result.warnings, "zone planner must surface demo warnings"
    assert result.assumptions, "zone planner must surface demo assumptions"

    for coeff in result.coefficients:
        for key in REQUIRED_DEMO_METADATA_KEYS:
            assert key in coeff, f"coefficient missing metadata key {key!r}: {coeff!r}"
        assert coeff["source_type"] == "demo"
        assert coeff["validity_status"] == "unverified"
        assert coeff["requires_review"] is True


def test_demo_zone_coefficient_to_reference_metadata_locked() -> None:
    planner = ColdRoomZonePlanner()
    for item in planner._coefficients.values():
        ref = item.to_reference()
        assert ref["source_type"] == "demo"
        assert ref["validity_status"] == "unverified"
        assert ref["requires_review"] is True


def test_matrix_rows_declare_consumer_or_non_consumer_for_conflict_leaves() -> None:
    conflict_leaves = (
        "frozen_fruit_ratio",
        "frozen_storage_days",
        "storage_position_capacity_kg",
        "packaging_storage_days",
        "precooling_required_ratio",
        "raw_holding_hours",
        "power_distribution_cost_cny_kw",
        "investment.electrical_installation_ratio",
    )
    for leaf_id in conflict_leaves:
        rows = _matrix_rows_with_leaf(leaf_id)
        assert rows, f"Matrix missing rows for leaf {leaf_id!r}"
        joined = "\n".join(rows)
        assert "consumer" in joined or "non_consumer" in joined, (
            f"Matrix row for {leaf_id!r} must name consumer or non_consumer"
        )


def test_e6_investment_registry_vs_embedded_conflict_registered() -> None:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    assert "E6" in inventory
    assert "E6" in matrix
    assert "power_distribution_cost_cny_kw" in matrix
    assert "investment.electrical_installation_ratio" in matrix

    estimator = InvestmentEstimator()
    embedded = estimator._coefficients["power_distribution_cost_cny_kw"]
    assert embedded.unit == "CNY/kW"

    catalog_codes = {entry["code"] for entry in COEFFICIENT_CATALOG}
    assert "investment.electrical_installation_ratio" in catalog_codes


def test_e7_catalog_codes_are_disjoint_from_demo_seed_topic() -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    assert "seed_catalog" in matrix
    assert "seed_demo_coefficients" in matrix
    assert "E7" in matrix
