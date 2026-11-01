"""Current P1 requirements reused by opt-in process generation and admission.

No new area Authority: the original calculator's grid and minimum are both
retained, with their original source zone hash. Storage-day changes cannot use
the previous experiment's capacity or a lower minimum in place of the grid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_hash

STORAGE_ROLES = (
    "packaging_material_storage",
    "finished_goods_room",
    "raw_fruit_buffer",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
)


def current_storage_requirements(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    zones = {z["zone_code"]: z for z in plan["result"]["zones"]}
    result = {}
    for code in STORAGE_ROLES:
        z = zones[code]
        grid = int(z["position_count"])
        minimum = int(z.get("n_need", grid))
        result[code] = {
            "p1_grid_positions": grid,
            "minimum_positions": minimum,
            "required_positions": max(grid, minimum),
            "source_zone_hash": canonical_hash(z),
            "source": "CURRENT_CALCULATOR_P1_GRID_UNMODIFIED",
            "formula": "max(current position_count, current n_need)",
            "unit": "pallet_addresses",
            "new_authority": False,
        }
    return result


def current_equipment_counts(project: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, int]:
    zones = {z["zone_code"]: z for z in plan["result"]["zones"]}
    specs = project["equipment_specs"]
    return {
        "packing_line": int(specs["packing_line"]["quantity"]),
        "case_erector": int(specs["case_erector"]["quantity"]),
        "ten_door_locker": int(specs["locker"]["quantity"]),
        "PRI_pallet": int(zones["primary_precooling_room"]["position_count"]),
        "SEC_pallet": int(zones["secondary_precooling_room"]["position_count"]),
        "case_film_component": len(specs["case_film_line"]["components"]),
    }


def current_passage_requirements(
    requirements: Sequence[Mapping[str, Any]], roles: Sequence[str]
) -> dict[str, list[dict[str, str]]]:
    """Only connection identities, never inherited paths or PASS evidence."""
    incident: dict[str, list[Mapping[str, Any]]] = {}
    storage = []
    for req in requirements:
        if req["flow_kind"] == "TRUCK":
            continue
        for side in ("from_ref", "to_ref"):
            code = req[side]
            if code not in roles:
                continue
            incident.setdefault(code, []).append(req)
            if code in STORAGE_ROLES and req["flow_kind"] != "PEOPLE":
                storage.append({"room": code, "requirement_identity": req["identity"]})
    interior = []
    for code, rows in sorted(incident.items()):
        for r in rows[1:]:
            interior.append(
                {"room": code, "from_access": rows[0]["identity"], "to_access": r["identity"]}
            )
    return {"equipment_aware_interior_paths": interior, "storage_portal_interfaces": storage}
