"""Located clearances from actual rectangles and full movement/door witnesses.

The declared margin families have explicit definitions; they are not building
standards or a replacement for ergonomic, hygiene or external Access review.
"""

from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import covered, rectangle


def rectangle_gap(a: list[int], b: list[int]) -> int:
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    if dx or dy:
        return max(dx, dy)  # conservative L-infinity lower bound to Euclidean gap
    return -min(min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1]))


def inside_margin(a: list[int], clear: list[int]) -> int:
    return min(a[0] - clear[0], a[1] - clear[1], clear[2] - a[2], clear[3] - a[3])


def geometry_margins(g: dict[str, Any], shifts: list[dict[str, Any]]) -> dict[str, Any]:
    p = g["parameters"]
    c = g["conditions"]
    clear = g["model"]["clear"]
    minimum: dict[str, Any] = {}
    counts: dict[str, int] = {}

    def offer(
        family: str,
        actual: int,
        required: int,
        where: str,
        bounds: list[int] | None = None,
        definition: str = "distance",
    ) -> None:
        counts[family] = counts.get(family, 0) + 1
        row = dict(
            family=family,
            actual_mm=actual,
            required_mm=required,
            extra_mm=actual - required,
            location=where,
            bounds_mm=bounds,
            definition=definition,
            source_label="ENGINEERING_DERIVED_FROM_HYPOTHETICAL_GEOMETRY",
        )
        if family not in minimum or (row["extra_mm"], where) < (
            minimum[family]["extra_mm"],
            minimum[family]["location"],
        ):
            minimum[family] = row

    units = sorted(g["inventory"]["cabinet_units"], key=lambda u: u["bounds_mm"][0])
    for unit in units:
        offer(
            "cabinet_wall_installation",
            inside_margin(unit["bounds_mm"], clear),
            c["installation_gap_mm"],
            unit["id"],
            unit["bounds_mm"],
            "actual cabinet-to-finished-wall distance minus installation hypothesis",
        )
    for a, b in zip(units, units[1:], strict=False):
        offer(
            "cabinet_unit_installation",
            rectangle_gap(a["bounds_mm"], b["bounds_mm"]),
            c["unit_gap_mm"],
            a["id"] + " / " + b["id"],
            b["bounds_mm"],
            "between separate floor units; shared manufactured column joints excluded",
        )
    base = g["waiting_snapshots"]["1"]
    for i, h in enumerate(g["model"]["homes"]):
        box = h["bounds_mm"]
        offer("waiting_finished_boundary", inside_margin(box, clear), 0, f"HOME-{i + 1:02}", box)
        for j, aisle in enumerate(base["aisles"]):
            offer(
                "waiting_to_reserved_aisle",
                rectangle_gap(box, aisle),
                0,
                f"HOME-{i + 1:02} / AISLE-{j}",
                box,
            )
        for j, other in enumerate(g["model"]["homes"][i + 1 :], i + 2):
            offer(
                "waiting_position_gap",
                rectangle_gap(box, other["bounds_mm"]),
                c["waiting_gap_mm"],
                f"HOME-{i + 1:02} / HOME-{j:02}",
                box,
                "axis gap minus the explicitly hypothetical waiting gap",
            )
    offer(
        "continuous_aisle_width",
        p["aisle_mm"],
        c["aisle_required_mm"],
        "all exported centerline envelopes",
        definition="net width surplus, not per-side buffer",
    )
    for portal in g["room"]["portals"]:
        offer(
            "portal_to_reserved_aisle",
            portal["clear_width_mm"],
            p["aisle_mm"],
            portal["id"],
            definition=(
                "total Portal width minus reserved aisle width; each jamb buffer is half this value"
            ),
        )
    for s in g["snapshots"]:
        for a in s["front_activity_evaluation"]["activity_volumes"]:
            for j, aisle in enumerate(s["aisles"]):
                offer(
                    "front_activity_to_aisle",
                    rectangle_gap(a["bounds_mm"], aisle),
                    0,
                    f"{s['id']} / {a['id']} / AISLE-{j}",
                    a["bounds_mm"],
                )
            for u in units:
                offer(
                    "front_activity_to_cabinet",
                    rectangle_gap(a["bounds_mm"], u["bounds_mm"]),
                    0,
                    f"{s['id']} / {a['id']} / {u['id']}",
                    a["bounds_mm"],
                )
        for d in s["doors"]:
            if d["kind"] == "NO_PLAN_INTRUSION":
                continue
            hx, hy = d["hinge_mm"]
            sx, sy = d["direction"]
            rad = d["radius_mm"] + d["thickness_mm"]
            box = [
                min(hx, hx + sx * rad),
                min(hy, hy + sy * rad),
                max(hx, hx + sx * rad),
                max(hy, hy + sy * rad),
            ]
            for person in s["people"]:
                if any(
                    max(v[2], d["z_interval_mm"][0]) < min(v[5], d["z_interval_mm"][1])
                    for v in person["volumes_mm"]
                ):
                    offer(
                        "door_sweep_to_people_lower_bound",
                        rectangle_gap(box, person["bounds_mm"]),
                        0,
                        f"{s['id']} / {d['id']} / {person['id']}",
                        box,
                        (
                            "enclosing-box lower bound; original quarter-disk "
                            "3D validator independently retained"
                        ),
                    )
    turns = []
    for flow in shifts:
        for e in flow["events"]:
            proof = e["proof"]
            if proof["status"] != "VERIFIED_UNDER_HYPOTHESES":
                continue
            key = proof.get("person_id")
            others = [o for o in proof.get("people_before", []) if o["id"] != key]
            if key:
                for v in proof.get("swept_volumes_mm", []):
                    box = [v[0], v[1], v[3], v[4]]
                    for o in [*others, *units]:
                        if any(max(v[2], w[2]) < min(v[5], w[5]) for w in o["volumes_mm"]):
                            offer(
                                "moving_body_to_other_objects",
                                rectangle_gap(box, o["bounds_mm"]),
                                0,
                                f"S{flow['shift']} E{e['index']} / {key} / {o['id']}",
                                box,
                                (
                                    "moving body versus remaining people/cabinets; "
                                    "intentional Portal wall crossing excluded"
                                ),
                            )
            for leg in proof.get("legs", []):
                if leg["operation"] != "YAW_90_IN_EXISTING_AISLE":
                    continue
                v = leg["swept_volumes_mm"][0]
                box = [v[0], v[1], v[3], v[4]]
                # Largest uniform expansion covered by the actual reserved aisle union.
                lo, hi = 0, 1500
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    expanded = [box[0] - mid, box[1] - mid, box[2] + mid, box[3] + mid]
                    if min(expanded) >= 0 and covered(
                        rectangle(expanded), [rectangle(a) for a in base["aisles"]]
                    ):
                        lo = mid
                    else:
                        hi = mid - 1
                offer(
                    "yaw_swept_square_to_aisle_edge",
                    lo,
                    0,
                    f"S{flow['shift']} E{e['index']} / {key}",
                    box,
                    "uniform expansion of the actual continuous yaw square inside the aisle union",
                )
                turns.append(leg["bounding_square_side_mm"])
    rows = list(minimum.values())
    worst = min(rows, key=lambda x: (x["extra_mm"], x["family"])) if rows else None
    # Cross-section values are read from actual placements, never total room area.
    north_edge = base["branch_y"] + p["aisle_mm"] - p["aisle_mm"] // 2
    north_homes = [h for h in g["model"]["homes"] if h["region"].startswith("NORTH")]
    north_spare = min((clear[3] - h["bounds_mm"][3] for h in north_homes), default=None)
    return dict(
        families=minimum,
        observations_checked=counts,
        minimum_declared_spatial_margin=worst,
        margin_target_mm=g["point"]["margin_mm"],
        margin_target_met=bool(worst is not None and worst["extra_mm"] >= g["point"]["margin_mm"]),
        north_waiting_finished_wall_margin_mm=north_spare,
        continuous_yaw_square_mm=max(turns, default=None),
        section_chain_mm=[
            dict(label="finished south", mm=p["finish_mm"]),
            dict(label="installation", mm=p["installation_gap_mm"]),
            dict(label="cabinet", mm=p["column_depth_mm"]),
            dict(label="operator standoff", mm=p["operator_standoff_mm"]),
            dict(label="body depth", mm=p["person_depth_mm"]),
            dict(label="front-to-aisle gap", mm=g["spatial_padding_mm"]),
            dict(label="aisle", mm=p["aisle_mm"]),
            dict(label="north free strip", mm=clear[3] - north_edge),
            dict(label="finished north", mm=p["finish_mm"]),
        ],
        other_unapproved_limits=dict(
            horizontal_reach_reserve_mm=p["reach_horizontal_mm"] - p["operator_standoff_mm"],
            vertical_reach_reference="Original layer checks retained; not ergonomic approval",
            portal_jamb_buffer_mm=(1500 - p["aisle_mm"]) / 2,
        ),
        scope="DECLARED_PLAN_MARGIN_FAMILIES; NOT_A_UNIFORM_BODY_BUFFER_OR_APPROVED_CODE_MINIMUM",
        units="integer mm except centered Portal jamb buffer",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
    )
