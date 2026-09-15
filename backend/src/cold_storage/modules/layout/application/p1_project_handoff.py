"""P1 version closure plus separate, fail-closed project truck completeness."""

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application.access_handoff import build_access_handoff
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.domain.access_authority import TRUCK
from cold_storage.modules.layout.domain.dimensioning import canonical_json
from cold_storage.modules.layout.domain.project_truck_input import (
    IDENTITY as TRUCK_INPUT_IDENTITY,
)
from cold_storage.modules.layout.domain.project_truck_input import validate_project_truck_input

IDENTITY = "p1-project-access-handoff@1.0.0"


def build_p1_project_handoff(
    zone_plan: Mapping[str, Any] | None,
    truck_input: Mapping[str, Any] | None = None,
) -> ZoneDimensioningResultV1:
    """New current entrypoint; the full P1E historical payload/hash stays immutable.

    truck_input is the truck_access member of SiteLayoutProjectInputV1. Site
    validation and placement are not implemented here. Omission cannot pick a car.
    """
    legacy = build_access_handoff(zone_plan)
    body = legacy.to_dict()
    old = body["authority_status"]
    complete = all(
        old[key]
        for key in (
            "dimension_authority_complete",
            "personnel_access_authority_complete",
            "material_access_authority_complete",
            "truck_access_contract_complete",
        )
    )
    return ZoneDimensioningResultV1(
        canonical_json(
            {
                "identity": IDENTITY,
                "schema_version": "1.0.0",
                "source_authority": "Charles:V2_2_P1F_PROJECT_TRUCK_INPUT_AND_P1_CLOSURE_R1",
                "p1e_historical_handoff": body,
                "p1e_historical_handoff_hash": legacy.canonical_result_hash,
                "authority_status": {
                    "dimension_authority_complete": old["dimension_authority_complete"],
                    "personnel_access_authority_complete": old[
                        "personnel_access_authority_complete"
                    ],
                    "material_access_authority_complete": old["material_access_authority_complete"],
                    "truck_access_contract_complete": True,
                    "truck_project_input_contract_complete": True,
                    "truck_version_level_engineering_values_required": False,
                    "p1_complete": complete,
                },
                "p1_closure_blockers": [] if complete else ["DIMENSION_AUTHORITY_REQUIRED"],
                "truck_input_binding": {
                    "access_profile_identity": TRUCK,
                    "project_input_contract_identity": TRUCK_INPUT_IDENTITY,
                    "value_source": "PROJECT_INPUT",
                    "version_defaults_allowed": False,
                    "outdoor_only": True,
                    "inside_building_allowed": False,
                    "from_ref": "truck_entrance",
                    "to_ref": "shipping_channel",
                    "to_edge_class": "LONG_EDGE_LOADING_FACE",
                },
                "project_status": validate_project_truck_input(truck_input),
                "p2_implemented": False,
                "p2_authorized": False,
                "requires_review": True,
            }
        )
    )
