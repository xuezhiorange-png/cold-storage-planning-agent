"""Read-only, finite functional sizing preview; no P1/Stage B integration."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, fields
from typing import Any

from cold_storage.modules.layout.application.cabinet_front_review import (
    SOURCE_PATH,
    SOURCE_SHA256,
    bind_front_project,
)
from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.domain.functional_room_sizing_input import (
    VERSION,
    RoomUseConditions,
    SizingSearch,
    search_points,
)
from cold_storage.modules.layout.domain.reverse_sizing_geometry import construct_sizing_geometry
from cold_storage.modules.layout.domain.reverse_sizing_margins import geometry_margins
from cold_storage.modules.layout.domain.reverse_sizing_operation import simulate_sizing_shift

TASK = "V2_2_2_R11_R10_FUNCTIONAL_ROOM_REVERSE_SIZING_R1"


def preview_request(raw: dict[str, Any]) -> tuple[RoomUseConditions, SizingSearch]:
    if not isinstance(raw, dict) or not set(raw) <= {"conditions", "search"}:
        raise ValueError("PREVIEW_ONLY_CONDITIONS_AND_FINITE_SEARCH_REQUIRED")

    def construct(cls: Any, values: Any) -> Any:
        if not isinstance(values, dict) or not set(values) <= {f.name for f in fields(cls)}:
            raise ValueError("UNSUPPORTED_PREVIEW_INPUT_OR_APPROVAL_LABEL")
        if cls is SizingSearch:
            values = {k: tuple(v) if isinstance(v, list) else v for k, v in values.items()}
        return cls(**values)

    c = construct(RoomUseConditions, raw.get("conditions", {}))
    s = construct(SizingSearch, raw.get("search", {}))
    search_points(c, s)
    return c, s


def _area(mm2: int) -> str:
    return f"{mm2 // 1000000}.{mm2 % 1000000:06d}"


def evaluate_sizing_point(
    original: dict[str, Any], demand: dict[str, Any], c: RoomUseConditions, point: dict[str, Any]
) -> dict[str, Any]:
    g = construct_sizing_geometry(original, demand, c, point)
    can_run = (
        g["static_status"] == "STATIC_GEOMETRY_PASS"
        and g["cross_section"]["status"] == "NECESSARY_CONDITIONS_PASS"
    )
    shifts = [simulate_sizing_shift(g, s, None) for s in (1, 2)] if can_run else []
    full = len(shifts) == 2 and all(
        s["status"] == "VERIFIED_UNDER_HYPOTHESES"
        and s["initial_service_occupancy"] == s["completed_users"] == 53
        for s in shifts
    )
    margins = geometry_margins(g, shifts)
    payload = dict(geometry=g, shifts=shifts, margins=margins)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    L, W = point["length_mm"], point["width_mm"]
    worst = margins["minimum_declared_spatial_margin"]
    summary = dict(
        id=f"R10-L{L}-W{W}-M{point['margin_mm']}-{point['profile']}",
        point=point,
        area_mm2=L * W,
        area_m2=_area(L * W),
        added_area_m2=_area(L * W - 26331 * 3250),
        length_delta_mm=L - 26331,
        width_delta_mm=W - 3250,
        source_physical_room_count=1,
        source_records=["P01", "P02"],
        section_status=g["cross_section"]["status"],
        static_status=g["static_status"],
        full_flow_status="CONDITIONAL_FLOW_PASS"
        if full
        else "CONDITIONAL_FLOW_BLOCKED"
        if shifts
        else "NOT_EVALUATED_UPSTREAM_REJECTED",
        completed_users=[s["completed_users"] for s in shifts],
        full_flow_verified=full,
        home_count=g["metrics"]["home_count"],
        rotated_home_count=g["metrics"]["rotated_home_count"],
        minimum_margin_mm=worst["extra_mm"] if worst else None,
        limiting_margin=worst,
        margin_target_met=bool(full and margins["margin_target_met"]),
        north_wall_margin_mm=margins["north_waiting_finished_wall_margin_mm"],
        conditional_flow_conflicts=[s["blocker"] for s in shifts if s["blocker"]],
        static_conflicts=g["waiting_evaluation"]["conflicts"]
        + g["waiting_clearance_conflicts"]
        + g["hierarchy_failures"],
        boundary_mapping=g["room"]["boundary_mapping"],
        actual_engineering_approval="INPUT_REQUIRED",
        witness_sha256=digest,
    )
    return dict(summary=summary, **payload)


def select_designs(rows: list[dict[str, Any]], review_target: int) -> dict[str, Any]:
    eligible = [r for r in rows if r["full_flow_verified"]]

    def area_key(r: dict[str, Any]) -> tuple[Any, ...]:
        return (r["area_mm2"], r["point"]["margin_mm"], r["id"])

    if not eligible:
        return dict(
            A_MIN_VERIFIED_AREA=None,
            B_LARGER_MARGIN=None,
            C_MIN_BOUNDARY_CHANGE=None,
            conclusion="NO_FULLY_VALIDATED_CANDIDATE_IN_TESTED_SET",
        )
    small = min(eligible, key=area_key)
    larger = min(eligible, key=lambda r: (-r["minimum_margin_mm"], r["area_mm2"], r["id"]))
    changes = [r for r in eligible if r["minimum_margin_mm"] >= review_target]
    change = (
        min(
            changes,
            key=lambda r: (
                abs(r["length_delta_mm"]) + abs(r["width_delta_mm"]),
                r["area_mm2"],
                r["id"],
            ),
        )
        if changes
        else None
    )
    return dict(
        A_MIN_VERIFIED_AREA=small["id"],
        B_LARGER_MARGIN=larger["id"],
        C_MIN_BOUNDARY_CHANGE=change["id"] if change else None,
        rules=dict(
            A=(
                "minimum measured area among full two-shift witnesses; "
                "comparison, not recommendation"
            ),
            B="maximum minimum declared planar allowance; smallest area breaks ties",
            C=(
                f"minimum |delta L|+|delta W| with full flow and margin >= {review_target}mm; "
                "hypothetical review target, not a standard"
            ),
        ),
        recommended_for_review=larger["id"]
        if larger["minimum_margin_mm"] > small["minimum_margin_mm"]
        else None,
        conclusion="CONDITIONAL_PREVIEW_ONLY_INPUT_REQUIRED",
    )


def input_contract(catalog: dict[str, Any], c: RoomUseConditions) -> dict[str, Any]:
    source = next(r for r in catalog["groups"] if r["group"] == "G01")
    return dict(
        supported_full_flow_adapter="H5_TWO_SHIFTS_53_FIVE_TIER",
        project_demand=catalog["demands"]["INTERNAL_PARTITION"],
        original_room_and_portals=source["room"],
        variable_boundaries=dict(
            WEST="FIXED", SOUTH="FIXED", EAST="LENGTH_SENSITIVITY", NORTH="WIDTH_SENSITIVITY"
        ),
        turning_envelope=dict(
            model="CONSERVATIVE_CONTINUOUS_FULL_DIAGONAL_SQUARE",
            derived_from_mm=[c.transport_width_mm, c.transport_depth_mm, c.body_height_mm],
            source_label="ENGINEERING_DERIVED_FROM_HYPOTHETICAL_BODY",
        ),
        conditional_padding_rule=(
            "Add targets to installation/unit gaps, standoff, aisle width, "
            "front/waiting-to-aisle and waiting gaps; measure results independently"
        ),
        conditions=asdict(c),
        conditions_approval="INPUT_REQUIRED",
    )


def preview_room_sizing(
    catalog: dict[str, Any],
    r7_source: bytes,
    r8_source: bytes,
    c: RoomUseConditions,
    search: SizingSearch,
    *,
    evidence_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    binding = bind_front_project(catalog, r7_source, r8_source)
    # These design counts already occur in the byte-verified R8 Owner source.
    # Retain the historical arithmetic basis separately; no new approval channel.
    expected_lines = (
        "SHIFT_DESIGN_USERS=53,53",
        "SIMULTANEOUS_ROOM_DESIGN_USERS=53",
        "FIVE_TIER_COLUMNS=22",
        "INDEPENDENT_COMPARTMENT_CAPACITY=110",
    )
    if any(line not in r8_source.decode().splitlines() for line in expected_lines):
        raise ValueError("FROZEN_OWNER_DESIGN_COUNTS_REQUIRED")
    binding["reviewed_design_requirements"] = {
        field: asdict(
            ReviewedProjectDatum(
                field,
                value,
                "count",
                binding["project_scope_id"],
                "OWNER_CONFIRMED",
                f"{SOURCE_PATH}; sha256:{SOURCE_SHA256}; R10 reaffirmed design requirement",
            )
        )
        for field, value in (
            ("USERS_PER_SHIFT", 53),
            ("SHIFT_COUNT", 2),
            ("SIMULTANEOUS_USERS", 53),
            ("CABINET_COLUMNS", 22),
            ("COMPARTMENT_CAPACITY", 110),
        )
    }
    source = next(row for row in catalog["groups"] if row["group"] == "G01")
    points = search_points(c, search)
    rows = []
    for point in points:
        case = evaluate_sizing_point(
            source["room"], catalog["demands"]["INTERNAL_PARTITION"], c, point
        )
        rows.append(case["summary"])
        if evidence_sink:
            evidence_sink(case)
    return dict(
        schema_version=VERSION,
        task=TASK,
        interface="FUNCTIONAL_ROOM_REVERSE_SIZING_PREVIEW_ONLY",
        binding=binding,
        conditions=asdict(c),
        conditions_classification="HYPOTHETICAL_NOT_APPROVED",
        search=asdict(search),
        source_room=source["room"],
        source_records=source["records"],
        source_physical_room_count=1,
        source_area_m2=_area(26331 * 3250),
        input_contract=input_contract(catalog, c),
        input_provenance=dict(
            owner_confirmed=binding["reviewed_project_facts"],
            project_design_basis=binding["design_basis"],
            derived_storage_demand=catalog["demands"]["INTERNAL_PARTITION"],
            historical_geometry="ENGINEERING_DERIVED_ARCHIVED_P01_P02_SAME_ROOM",
            all_conditions="source_type=demo; validity_status=unverified; requires_review=true",
        ),
        candidate_count=len(rows),
        candidates=rows,
        designs=select_designs(rows, search.change_review_target_mm),
        evaluation_order=[
            "section necessary condition",
            "actual static geometry",
            "original complete two-shift functional validation",
            "measured margin review",
            "actual engineering approval remains INPUT_REQUIRED",
        ],
        scope_limits=[
            "finite template/grid exploration, not global minimum or infeasibility proof",
            "boundary/Portal mapping does not validate external Access/Site/Footprint",
            "reach/hygiene/equipment/human motion and all numerical assumptions need review",
            "no P1, Stage B, production solver or Authority writes",
        ],
        original_access_readbacks=source["record_access_readbacks"],
        original_external_routes=source["external_routes"],
        actual_functional_status="INPUT_REQUIRED",
        new_native_solves=0,
        new_main=False,
        new_grant=False,
        new_claim=False,
        full_ci="NOT_REQUESTED",
        inherited_ci_native_tests="SEPARATE_FROM_R10_FUNCTIONAL_EVALUATION",
    )
