"""Read-only R15 R4 conditional review. No project approval, solve or planning write."""

import copy
from typing import Any

from cold_storage.modules.layout.application.ten_door_locker_review import combine_flow
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.ten_door_local_clearance import (
    VERSION,
    analytic_opening_distances,
    construct_local_adjustment,
    finite_adjustments,
    local_section,
    require_frozen_basis,
)
from cold_storage.modules.layout.domain.ten_door_local_relayout import home_coordinate_diff
from cold_storage.modules.layout.domain.ten_door_locker_geometry import closed_door_flow
from cold_storage.modules.layout.domain.ten_door_locker_model import DoorSensitivity
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import check_flow_doors

TASK = "V2_2_2_R11_R15_R4_LOCAL_CLEARANCE_IMPROVEMENT"
BASE_HEAD = "b8e6e19f83a44b0bbba76ced2538372a8cb23763"
SOURCE_WITNESS = "sha256:447943b97e4d77d13f9d5fb8cc774a6d85a49347852df7d3365984caac8596cf"


def source_case(archive: dict[str, Any]) -> dict[str, Any]:
    selected = [c for c in archive["reports"] if c["id"] == "R15-03"]
    if len(selected) != 1:
        raise ValueError("UNIQUE_R15_03_SOURCE_REQUIRED")
    case: dict[str, Any] = selected[0]
    if (
        case["witness_hash"] != SOURCE_WITNESS
        or canonical_hash(case["payload"]) != SOURCE_WITNESS
        or case["geometry"] != case["payload"]["checked"]["geometry"]
        or case["closed_door_flows"] != case["payload"]["checked"]["shifts"]
        or not all(p["combined"]["complete"] for p in case["profiles"])
    ):
        raise ValueError("PINNED_R15_03_SOURCE_OR_WITNESS_MISMATCH")
    require_frozen_basis(case["geometry"])
    return case


def review_adjustment(base: dict[str, Any], choice: dict[str, Any]) -> dict[str, Any]:
    section = local_section(base["geometry"], choice)
    if choice["scope"] == "SECTION_ONLY":
        # Necessary 100mm section condition already fails. No fabricated layout,
        # route or full-flow status for the independently moved-person diagnostic.
        return dict(
            id=choice["id"],
            choice=choice,
            section=section,
            geometry=None,
            static_status="LOCAL_SECTION_TARGET_REJECTED_NOT_A_FULL_LAYOUT",
            full_flow_status="NOT_EVALUATED_SECTION_NEGATIVE_CONTROL",
            closed_door_flows=[],
            profiles=[],
            all_100_met=False,
            geometry_or_flow_witness_created=False,
        )
    geometry = construct_local_adjustment(base["geometry"], choice)
    checked = closed_door_flow(geometry)
    profiles: list[dict[str, Any]] = []
    for hinge in ("ALL_LEFT", "MIRRORED"):
        doors = check_flow_doors(geometry, checked["shifts"], DoorSensitivity(hinge))
        distances = analytic_opening_distances(geometry, checked["shifts"], doors)
        combined = combine_flow(checked, doors)
        closed = checked["margins"]["minimum_declared_spatial_margin"]
        exact = distances["minimum"]
        exact_100 = exact is not None and exact["distance"]["model_distance_lower_um"] >= 100000
        combined.update(
            margin_target_mm=100,
            exact_door_100_met=exact_100,
            all_declared_100_met=bool(
                combined["complete"] and closed and closed["extra_mm"] >= 100 and exact_100
            ),
        )
        profiles.append(
            dict(hinges=hinge, doors=doors, analytic_distances=distances, combined=combined)
        )
    payload = dict(
        version=VERSION,
        source_witness=SOURCE_WITNESS,
        choice=choice,
        checked=checked,
        profiles=profiles,
    )
    return dict(
        id=choice["id"],
        choice=choice,
        section=section,
        geometry=geometry,
        static_status=geometry["static_status"],
        closed_door_flows=checked["shifts"],
        margins=checked["margins"],
        profiles=profiles,
        payload=payload,
        full_flow_status="CONDITIONAL_FULL_FLOW_COMPLETE"
        if all(p["combined"]["complete"] for p in profiles)
        else "BLOCKED",
        all_100_met=all(p["combined"]["all_declared_100_met"] for p in profiles),
        coordinate_diff=home_coordinate_diff(base["geometry"], geometry),
        geometry_or_flow_witness_created=True,
        witness_hash=canonical_hash(payload),
    )


def review_local_clearance(archive: dict[str, Any]) -> dict[str, Any]:
    base = source_case(archive)
    reports = [review_adjustment(base, c) for c in finite_adjustments()]
    valid = [r for r in reports if r["all_100_met"]]
    selected = (
        min(
            valid,
            key=lambda r: (
                r["choice"]["operator_delta_mm"],
                len(r["coordinate_diff"]["changed_homes"]),
                r["id"],
            ),
        )
        if valid
        else None
    )
    return dict(
        task=TASK,
        version=VERSION,
        base_head=BASE_HEAD,
        source_witness=SOURCE_WITNESS,
        source_geometry=copy.deepcopy(base["geometry"]),
        reports=reports,
        declared_candidate_limit=6,
        declared_candidates=len(reports),
        full_geometry_candidates=sum(r["geometry"] is not None for r in reports),
        selected_candidate_id=selected["id"] if selected else None,
        selection_scope="LEAST_OPERATOR_DISPLACEMENT_IN_SIX_DECLARED_CHECKS_ONLY_NOT_GLOBAL_OPTIMUM",
        actual_calibration="INPUT_REQUIRED",
        actual_operation_clearance="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
        photo_r2="PAUSED_NOT_EVALUATED",
        native_solves=0,
        main_executed=False,
        real_grant_claim=False,
    )
