"""Default / unit alignment matrix for V0.7 P1 data integrity proof."""

from __future__ import annotations

from dataclasses import MISSING, fields
from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
    DemoZoneCoefficient,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    project_execution_snapshot_from_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs" / "audit" / "data-integrity-matrix.md"

KEY_ZONE_FIELDS: tuple[str, ...] = (
    "daily_inbound_mass_kg",
    "working_time_h_per_day",
    "finished_storage_days",
    "packaging_storage_days",
    "precooling_required_ratio",
)

KNOWN_CONFLICT_LEAVES: dict[str, str] = {
    "frozen_fruit_ratio": "E1",
    "frozen_storage_days": "E2",
    "storage_position_capacity_kg": "E3",
    "packaging_storage_days": "E4",
    "precooling_required_ratio": "E5",
    "raw_holding_hours": "E8",
}

LEGACY_FALLBACK_DEFAULTS: dict[str, float] = {
    "packaging_storage_days": 7.0,
    "precooling_required_ratio": 0.8,
}


def _matrix_text() -> str:
    return MATRIX_PATH.read_text(encoding="utf-8")


def _dataclass_defaults() -> dict[str, float]:
    defaults: dict[str, float] = {}
    for field in fields(ColdRoomZonePlanInput):
        if field.default is not MISSING:
            defaults[field.name] = float(field.default)
    return defaults


def _demo_coefficient_values() -> dict[str, DemoZoneCoefficient]:
    planner = ColdRoomZonePlanner()
    return dict(planner._coefficients)


def _minimal_bundle() -> dict:
    from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

    return build_valid_engineering_input_bundle(
        project_id="p-matrix",
        project_version_id="pv-matrix",
        version_number=1,
    )


def test_matrix_file_documents_consumer_or_non_consumer_columns() -> None:
    text = _matrix_text()
    assert "consumer" in text
    assert "non_consumer" in text
    assert "known_conflict" in text
    assert "requires_review" in text


def test_bundle_key_zone_fields_project_to_execution_snapshot() -> None:
    bundle = _minimal_bundle()
    snapshot = project_execution_snapshot_from_bundle(bundle)
    zone = snapshot["zone"]
    for field_name in KEY_ZONE_FIELDS:
        assert field_name in zone, f"execution snapshot missing KEY field {field_name!r}"
        bundle_leaf = bundle["zone_planning_inputs"][field_name]
        assert str(zone[field_name]) == str(bundle_leaf["value"])


def test_execution_snapshot_key_fields_match_dataclass_when_only_keys_provided() -> None:
    bundle = _minimal_bundle()
    zone_snapshot = project_execution_snapshot_from_bundle(bundle)["zone"]
    defaults = _dataclass_defaults()
    for field_name, default_value in defaults.items():
        if field_name in KEY_ZONE_FIELDS:
            continue
        # Extended fields not in KEY set must come from dataclass defaults at adapter boundary.
        assert field_name not in zone_snapshot or str(zone_snapshot[field_name]) == str(
            default_value
        )


def test_known_conflict_leaves_are_registered_in_matrix() -> None:
    text = _matrix_text()
    for leaf_id, expert_id in KNOWN_CONFLICT_LEAVES.items():
        assert leaf_id in text, f"Matrix missing leaf {leaf_id!r}"
        assert expert_id in text, f"Matrix missing expert id {expert_id!r}"


def test_e1_e3_demo_metadata_differs_from_input_defaults_without_p1_resolution() -> None:
    defaults = _dataclass_defaults()
    demo = _demo_coefficient_values()
    conflicts = {
        "frozen_fruit_ratio": "E1",
        "frozen_storage_days": "E2",
        "storage_position_capacity_kg": "E3",
    }
    for leaf_id, expert_id in conflicts.items():
        assert defaults[leaf_id] != demo[leaf_id].value, (
            f"{expert_id}: expected KNOWN_CONFLICT between Input default and DemoZoneCoefficient"
        )


def test_e8_raw_holding_hours_is_non_consumer_in_formula_body() -> None:
    source = Path(
        REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"
    ).read_text(encoding="utf-8")
    assert "data.raw_holding_hours" not in source
    assert "E8" in _matrix_text()


def test_legacy_fallback_defaults_documented_as_known_conflicts() -> None:
    text = _matrix_text()
    for leaf_id, fallback in LEGACY_FALLBACK_DEFAULTS.items():
        assert leaf_id in text
        assert str(int(fallback)) in text or str(fallback) in text
