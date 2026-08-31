"""V1.5 envelope geometry bind: roof=floor, wall=height×4×√A."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.projects.application.demo_zone_thermal_catalog import ROOM_HEIGHT_M
from cold_storage.modules.projects.application.engineering_input_bundle import (
    LINEAGE_PENDING_STATE,
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
    assemble_engineering_input_bundle,
)
from cold_storage.modules.projects.application.preview_lineage_bind import (
    ENVELOPE_GEOMETRY_REQUIRES_REVIEW,
    ENVELOPE_GEOMETRY_SOURCE_TYPE,
    ENVELOPE_GEOMETRY_VALIDITY_STATUS,
    LineageBindFailure,
    bind_cooling_identity_and_plan_area_from_zone,
    square_plan_wall_area_m2,
)
from cold_storage.modules.projects.domain.models import ProjectVersion

_FLOOR_400 = Decimal("400")
_FLOOR_100 = Decimal("100")


def _v09_operator_payload() -> dict[str, object]:
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.1.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
            "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
            "auxiliary_packaging_storage_days": {"value": "12", "unit": "day", "state": "provided"},
        },
    }


def _version() -> ProjectVersion:
    return ProjectVersion(
        project_id="p-v15",
        version_number=1,
        change_summary="v15-envelope",
        id="pv-v15",
    )


def _assemble_snapshot() -> tuple[dict[str, object], dict[str, object]]:
    bundle = assemble_engineering_input_bundle(
        operator_input=_v09_operator_payload(),
        project_id="p-v15",
        version=_version(),
        actor="test-actor",
    )
    return bundle, project_execution_snapshot_from_bundle(bundle)


def _zone_payload_with_area(area: Decimal) -> dict[str, object]:
    zones: list[dict[str, object]] = []
    for zone_code, zone_name, temperature_band in REFRIGERATED_ZONE_REGISTRY:
        zones.append(
            {
                "zone_code": zone_code,
                "zone_name": zone_name,
                "temperature_band": temperature_band,
                "required_area_m2": str(area),
            }
        )
    zones.append(
        {
            "zone_code": "ambient_hall",
            "zone_name": "常温穿堂",
            "temperature_band": "常温",
            "required_area_m2": "9999",
        }
    )
    return {"zones": zones, "total_required_area_m2": str(area)}


def test_v15_square_plan_wall_formula_is_height_times_four_sqrt_floor() -> None:
    demo_height = Decimal("5.0")
    wall = square_plan_wall_area_m2(floor_area_m2=_FLOOR_400, room_height_m=demo_height)
    assert wall == demo_height * Decimal("4") * Decimal("20")


def test_v15_assembler_wall_roof_are_lineage_pending_height_stays_catalog() -> None:
    bundle, _snapshot = _assemble_snapshot()
    zone = bundle["cooling_load_inputs"]["zones"][0]
    assert zone["wall_area"]["state"] == LINEAGE_PENDING_STATE
    assert zone["roof_area"]["state"] == LINEAGE_PENDING_STATE
    assert zone["wall_area"]["value"] is None
    assert zone["roof_area"]["value"] is None
    assert zone["room_height"]["value"] in {"4", "4.0"}
    assert zone["room_height"]["source_type"] == "demo"
    assert zone["room_height"]["validity_status"] == "unverified"
    assert zone["room_height"]["requires_review"] is True


def test_v15_bind_sets_roof_equal_floor_and_square_plan_wall() -> None:
    _bundle, snapshot = _assemble_snapshot()
    cooling = dict(snapshot["cooling_load"])
    cooling["zones"] = [dict(zone) for zone in cooling["zones"]]
    bind_cooling_identity_and_plan_area_from_zone(
        zone_payload=_zone_payload_with_area(_FLOOR_400),
        cooling_inputs=cooling,
    )
    expected_wall = square_plan_wall_area_m2(
        floor_area_m2=_FLOOR_400,
        room_height_m=Decimal(ROOM_HEIGHT_M),
    )
    assert cooling["zones"]
    for zone in cooling["zones"]:
        assert zone["zone_code"] != "ambient_hall"
        assert Decimal(str(zone["floor_area"])) == _FLOOR_400
        assert Decimal(str(zone["zone_area"])) == _FLOOR_400
        assert Decimal(str(zone["roof_area"])) == _FLOOR_400
        assert Decimal(str(zone["wall_area"])) == expected_wall
        assert Decimal(str(zone["wall_area"])) != Decimal("200")
        assert Decimal(str(zone["roof_area"])) != Decimal("100")
        assert zone["envelope_geometry_source_type"] == ENVELOPE_GEOMETRY_SOURCE_TYPE
        assert zone["envelope_geometry_validity_status"] == ENVELOPE_GEOMETRY_VALIDITY_STATUS
        assert zone["envelope_geometry_requires_review"] is ENVELOPE_GEOMETRY_REQUIRES_REVIEW


def test_v15_bind_skips_ambient_zones() -> None:
    _bundle, snapshot = _assemble_snapshot()
    cooling = dict(snapshot["cooling_load"])
    cooling["zones"] = [dict(zone) for zone in cooling["zones"]]
    bind_cooling_identity_and_plan_area_from_zone(
        zone_payload=_zone_payload_with_area(_FLOOR_100),
        cooling_inputs=cooling,
    )
    codes = {zone["zone_code"] for zone in cooling["zones"]}
    assert "ambient_hall" not in codes
    assert "shipping_channel" in codes


def test_v15_bind_missing_room_height_fails_closed() -> None:
    _bundle, snapshot = _assemble_snapshot()
    cooling = dict(snapshot["cooling_load"])
    cooling["zones"] = [dict(zone) for zone in cooling["zones"]]
    for zone in cooling["zones"]:
        zone.pop("room_height", None)
    with pytest.raises(LineageBindFailure) as exc_info:
        bind_cooling_identity_and_plan_area_from_zone(
            zone_payload=_zone_payload_with_area(_FLOOR_400),
            cooling_inputs=cooling,
        )
    assert exc_info.value.field_path == "cooling_load_inputs.zones[].room_height"
    assert exc_info.value.details["reason"] == "missing_room_height"


def test_v15_bind_zero_room_height_fails_closed() -> None:
    _bundle, snapshot = _assemble_snapshot()
    cooling = dict(snapshot["cooling_load"])
    cooling["zones"] = [dict(zone) for zone in cooling["zones"]]
    cooling["zones"][0]["room_height"] = "0"
    with pytest.raises(LineageBindFailure) as exc_info:
        bind_cooling_identity_and_plan_area_from_zone(
            zone_payload=_zone_payload_with_area(_FLOOR_400),
            cooling_inputs=cooling,
        )
    assert exc_info.value.details["reason"] == "non_positive_room_height"
