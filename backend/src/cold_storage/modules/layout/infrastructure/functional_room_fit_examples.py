"""Explicit synthetic plans, never project inputs or equipment recommendations."""

from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import (
    COMMON,
    REQUIRED,
    STATES,
    BasisValue,
)


def scenario(
    kind: str = "SINGLE_SIDE",
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], dict[str, BasisValue]]:
    zone = (
        "changing_room"
        if kind in {"SINGLE_SIDE", "DOUBLE_SIDE", "NARROW"}
        else "office"
        if kind == "OFFICE"
        else "coating_room"
    )
    scope = "SYNTHETIC:" + kind
    w, h = (
        (5000, 8000)
        if kind == "DOUBLE_SIDE"
        else (10000, 8000)
        if kind == "COATING"
        else (40000, 1000)
        if kind == "NARROW"
        else (8000, 5000)
    )
    py = (
        4000
        if kind == "DOUBLE_SIDE"
        else 1600
        if kind == "COATING"
        else 1700
        if kind == "OFFICE"
        else 2200
    )
    portals = [
        dict(
            id="entry",
            segment_mm=[[0, py - 750], [0, py + 750]],
            clear_width_mm=1500,
            source_label="ENGINEERING_DERIVED",
            reference=scope,
        )
    ]
    if kind == "COATING":
        portals.append(
            dict(
                id="exit",
                segment_mm=[[w, py - 750], [w, py + 750]],
                clear_width_mm=1500,
                source_label="ENGINEERING_DERIVED",
                reference=scope,
            )
        )
    room = dict(
        room_code=zone,
        scope_id=scope,
        local_bounds_mm=[0, 0, w, h],
        p1_required_area_mm2=40000000 if zone == "changing_room" else 20000000,
        portals=portals,
        original_engineering_status="SYNTHETIC_NOT_ORIGINAL_ENGINEERING_ACCEPTANCE",
    )
    if kind == "NARROW":
        portals[0]["segment_mm"] = [[1250, 0], [2750, 0]]
    values = dict(
        finished_clear_bounds_mm=[0, 0, w, h],
        clear_height_mm=4000,
        aisle_width_mm=1200,
        door_operation="SLIDING",
        cleaning_maintenance_basis=(
            "Synthetic explicit envelopes in all four states; no hygiene approval"
        ),
    )
    components = []

    def add(identifier: str, role: str, rect: list[int], **extra: Any) -> None:
        components.append(
            dict(
                id=identifier,
                role=role,
                bounds_mm=rect,
                states=list(STATES),
                source_label="ENGINEERING_DERIVED",
                reference=scope,
                **extra,
            )
        )

    add("door-pocket", "DOOR_OPERATION", [0, py + 750, 100, py + 2250], portal_id="entry")
    if zone == "changing_room":
        double = kind == "DOUBLE_SIDE"
        values.update(
            simultaneous_users=8,
            shift_change_policy="NON_OVERLAPPING",
            locker_model="SYNTHETIC_LOCKER_NOT_PROJECT_SELECTION",
            locker_internal_separation_available=True,
            shift_locker_counts=[8, 8],
            locker_dimensions_mm=[400, 500, 1800],
            locker_arrangement="DOUBLE_SIDE" if double else "SINGLE_SIDE",
            locker_front_clearance_mm=600,
            person_space_mm=[400, 600],
            bench_count=0 if double else 1,
            bench_dimensions_mm="NOT_APPLICABLE" if double else [800, 400, 450],
            bench_operation_mm="NOT_APPLICABLE" if double else 500,
            internal_clothing_separation=True,
            clean_separation="NOT_REQUIRED",
        )
        for i in range(16):
            x = 500 + (i % 8 if double else i) * 400
            top = double and i >= 8
            y = 7000 if top else 500
            add(
                f"locker-{i + 1}",
                "LOCKER",
                [x, y, x + 400, y + 500],
                shift=1 if i < 8 else 2,
                front="S" if top else "N",
            )
            add(
                f"person-{i + 1}",
                "PERSON",
                [x, 6400 if top else 1000, x + 400, 7000 if top else 1600],
            )
        if double:
            add("front-low", "AISLE", [500, 1600, 5000, 2800])
            add("front-high", "AISLE", [500, 5200, 5000, 6400])
            add("aisle-link", "AISLE", [3800, 1600, 5000, 6400])
            add("entry-aisle", "AISLE", [0, 3400, 5000, 4600])
        else:
            add("front", "AISLE", [0, 1600, 8000, 2800])
            add("bench-link", "AISLE", [6800, 1600, 8000, 3000])
            add("bench", "BENCH", [7000, 3500, 7800, 3900], front="S")
    elif zone == "office":
        values.update(
            staff_count=1,
            desk_dimensions_mm=[1200, 600, 750],
            chair_movement_mm=[1200, 1200],
            storage_count=0,
            storage_dimensions_mm="NOT_APPLICABLE",
            necessary_functions="Synthetic single desk; explicit no storage",
        )
        add("desk", "DESK", [2000, 3500, 3200, 4100])
        add("chair", "CHAIR", [2000, 2300, 3200, 3500], serves="desk")
        add("entry-aisle", "AISLE", [0, 1100, 8000, 2300])
    else:
        values.update(
            process_type="PACKAGING_BOX_FILM_SEALING",
            equipment_model="SYNTHETIC_NOT_SELECTED_DEVICE",
            equipment_count=1,
            equipment_dimensions_mm=[2000, 1000, 1800],
            operating_clearances_mm=[0, 0, 800, 800],
            maintenance_clearances_mm=[0, 0, 800, 800],
            infeed_space_mm=[1000, 1000],
            outfeed_space_mm=[800, 1000],
            buffer_space_mm=[1000, 800],
            effective_capacity_basis="Synthetic geometry only; no capacity approval",
            logistics_direction_basis="Explicit west-in east-out synthetic plan",
            process_portal_roles=dict(INFEED="entry", OUTFEED="exit"),
            equipment_flow_faces=dict(INFEED="W", OUTFEED="E"),
        )
        add("equipment", "EQUIPMENT", [4000, 3000, 6000, 4000])
        add("infeed", "INFEED", [3000, 3000, 4000, 4000], serves="equipment")
        add("outfeed", "OUTFEED", [6000, 3000, 6800, 4000], serves="equipment")
        add("buffer", "BUFFER", [2000, 2200, 3000, 3000])
        add("main", "AISLE", [0, 1000, 10000, 2200])
        add("left", "AISLE", [1800, 1000, 3000, 6000])
        add("right", "AISLE", [6800, 1000, 8000, 6000])
        add("upper", "AISLE", [1800, 4800, 8000, 6000])
        add("exit-pocket", "DOOR_OPERATION", [9900, 2350, 10000, 3850], portal_id="exit")
    routes = [
        dict(
            id="portal-route",
            points_mm=[[0, py], [w if kind == "COATING" else w - 600, py]],
            width_mm=1200,
            states=list(STATES),
        )
    ]
    if kind == "NARROW":
        components[0]["bounds_mm"] = [2750, 0, 4250, 100]
        routes[0]["points_mm"] = [[2000, 0], [2000, 800]]
    values["door_operation_envelopes_mm"] = {
        p["id"]: [
            c["bounds_mm"]
            for c in components
            if c["role"] == "DOOR_OPERATION" and c.get("portal_id") == p["id"]
        ]
        for p in portals
    }
    units = COMMON | REQUIRED[zone]
    basis = {
        k: BasisValue(
            v,
            units[k],
            "ENGINEERING_DERIVED",
            "infrastructure/functional_room_fit_examples.py#" + kind + ":" + k,
            scope,
            k,
        )
        for k, v in values.items()
    }
    return room, {k: k for k in basis}, dict(components=components, routes=routes), basis
