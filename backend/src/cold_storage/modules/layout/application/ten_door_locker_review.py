"""Existing source-bound Owner selection + independent R14 complete-unit review."""

import copy
import hashlib
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.changing_locker_review import PROJECT_SCOPE
from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.functional_sizing_handoff import _physical_key
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_sizing_input import RoomUseConditions
from cold_storage.modules.layout.domain.ten_door_locker_geometry import (
    closed_door_flow,
    complete_cabinet_geometry,
)
from cold_storage.modules.layout.domain.ten_door_locker_model import (
    VERSION,
    DoorSensitivity,
    actual_door_records,
    complete_inventory,
)
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import check_flow_doors

TASK = "V2_2_2_R11_R14_OWNER_SELECTED_TEN_DOOR_LOCKER_R1"
BASE_HEAD = "9501238d7a815957e8bd46831b3f9f24767ce754"
SOURCE_PATH = "docs/tasks/V2_2_2-r11-r14-owner-selected-locker-scope.txt"
SOURCE_SHA256 = "2efef566238708208f74a17e3b64b69921cb5032d6f9d124d6e04490f8df985b"


def bind_owner_selection(ctx: dict[str, Any], source: bytes) -> dict[str, Any]:
    if not isinstance(source, bytes) or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("R14_OWNER_SELECTION_SOURCE_MISMATCH")
    scope = ctx["source"]["catalog"]["project_scope_id"]
    if (
        scope != PROJECT_SCOPE
        or ctx["overlay"]["project_scope_id"] != scope
        or ctx["room"]["local_bounds_mm"] != [0, 0, 26331, 3250]
        or ctx["overlay"]["physical_room_id"] != _physical_key(ctx["room"], scope)
    ):
        raise ValueError("R14_REVIEWED_PROJECT_AND_FROZEN_H5_REQUIRED")
    values: tuple[tuple[str, str | int, str], ...] = (
        ("SELECTED_CABINET_NOMINAL_WIDTH_MM", 850, "mm"),
        ("SELECTED_CABINET_NOMINAL_DEPTH_MM", 390, "mm"),
        ("SELECTED_CABINET_NOMINAL_HEIGHT_MM", 1800, "mm"),
        ("SELECTED_CABINET_COLUMNS", 2, "count"),
        ("SELECTED_CABINET_TIERS", 5, "count"),
        ("SELECTED_COMPLETE_CABINET_COUNT", 11, "count"),
        ("IMAGE_LABEL_DOOR_NOMINAL_WIDTH_MM", 400, "mm"),
        ("IMAGE_LABEL_DOOR_NOMINAL_DEPTH_MM", 360, "mm"),
        ("IMAGE_LABEL_DOOR_NOMINAL_HEIGHT_MM", 320, "mm"),
        ("IMAGE_REPORTED_CLOTHES_RAIL_COUNT", 0, "count"),
        ("IMAGE_REPORTED_ADDITIONAL_SHELVES", 0, "count"),
    )
    facts = {
        name: asdict(
            ReviewedProjectDatum(
                name,
                value,
                unit,
                scope,
                "OWNER_CONFIRMED",
                f"{TASK}; {SOURCE_PATH}; sha256:{SOURCE_SHA256}; NOMINAL_SELECTION_ONLY",
            )
        )
        for name, value, unit in values
    }
    return dict(
        project_scope_id=scope,
        physical_room_id=ctx["overlay"]["physical_room_id"],
        source_path=SOURCE_PATH,
        source_sha256=SOURCE_SHA256,
        reviewed_selection=facts,
        status="OWNER_SELECTED_NOMINAL_DESIGN_BASIS",
        single_door_image_label_mm=[400, 360, 320],
        single_door_label_is_internal_clear_size=False,
        photo_file=None,
        photo_sha256=None,
        photo_evidence_status="INPUT_REQUIRED",
        supplier_technical_review="NOT_EVALUATED",
        procurement_acceptance="NOT_EVALUATED",
        engineering_approval="NOT_EVALUATED",
    )


def combine_flow(checked: dict[str, Any], doors: dict[str, Any]) -> dict[str, Any]:
    flows = checked["shifts"]
    complete = len(flows) == 2 and all(
        f["status"] == "VERIFIED_UNDER_HYPOTHESES"
        and f["initial_service_occupancy"] == f["completed_users"] == 53
        for f in flows
    )
    okay = complete and doors["status"] == "CONDITIONAL_DOOR_EVENTS_PASS"
    return dict(
        status="CONDITIONAL_COMBINED_FLOW_PASS"
        if okay
        else "CONDITIONAL_CONFIGURATION_NOT_FIT"
        if doors["status"] == "CONFIGURATION_NOT_FIT"
        else "NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW",
        complete=okay,
        closed_door_flow_complete=complete,
        required_open_door_subproof=doors["status"],
        actual_functional_status="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
    )


def evidence_is_current(
    ctx: dict[str, Any], source: bytes, case: dict[str, Any], profile: dict[str, Any]
) -> bool:
    """Integrity and input matching only; never an approval endpoint."""
    try:
        owner = bind_owner_selection(ctx, source)
        payload = profile["payload"]
        closed = dict(
            geometry=case["geometry"],
            shifts=case["closed_door_flows"],
            margins=case["margins"],
            proof_scope=(
                "CLOSED_CABINET_DOOR_GEOMETRY_AND_MOVEMENT_ONLY; "
                "NEVER_A_COMPLETE_DOOR_OR_STORAGE_PASS"
            ),
        )
        return bool(
            canonical_hash(payload) == profile["witness_hash"]
            and payload["owner"] == owner
            and payload["source_hashes"] == ctx["source_hashes"]
            and payload["conditions"] == case["conditions"]
            and payload["spatial_padding_mm"] == case["margin_target_mm"]
            and payload["door_sensitivity"] == profile["hypothesis"]
            and payload["closed_door_evidence_hash"]
            == canonical_hash(closed)
            == case["closed_door_evidence_hash"]
            and payload["open_door_evidence"] == profile["doors"]
            and payload["combined"] == profile["combined"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def review_ten_door_selection(ctx: dict[str, Any], owner_source: bytes) -> dict[str, Any]:
    owner = bind_owner_selection(ctx, owner_source)
    inv = complete_inventory(ctx["demand"], DoorSensitivity("ALL_LEFT"))
    reports = []
    for finish, installation, margin in ((20, 20, 50), (30, 40, 100)):
        c = RoomUseConditions(
            column_width_mm=425,
            column_depth_mm=390,
            cabinet_height_mm=1800,
            cell_height_mm=320,
            finish_mm=finish,
            installation_gap_mm=installation,
            door_kind="NO_PLAN_INTRUSION",
        )
        conditions = asdict(c)
        # The old dataclass signatures are reused internally, but those field
        # names must not present a door label/gap as an actual clear cell/board.
        for old, new in (
            ("cell_height_mm", "door_face_height_sensitivity_mm"),
            ("plinth_mm", "bottom_door_face_sensitivity_mm"),
            ("shelf_mm", "vertical_door_gap_sensitivity_mm"),
        ):
            conditions[new] = conditions.pop(old)
        # The inherited field is CLOSED-DOOR subproof only, never selected hardware.
        conditions["door_kind"] = "CLOSED_DOOR_SUBPROOF_ONLY"
        for label, width in (("C", 3550), ("3850", 3850)):
            g = complete_cabinet_geometry(ctx["room"], ctx["demand"], c, width, margin)
            checked = closed_door_flow(g)
            profiles = []
            for hinge in ("ALL_LEFT", "MIRRORED"):
                hypothesis = DoorSensitivity(hinge)
                doors = check_flow_doors(g, checked["shifts"], hypothesis)
                combined = combine_flow(checked, doors)
                closed_min = checked["margins"]["minimum_declared_spatial_margin"]
                door_min = doors["minimum_door_clearance_lower_bound"]
                combined.update(
                    margin_target_mm=margin,
                    minimum_declared_margin_lower_bound_mm=min(
                        closed_min["extra_mm"], door_min["extra_mm"]
                    )
                    if combined["complete"] and closed_min and door_min
                    else None,
                    door_limiting_location=door_min,
                )
                combined["margin_target_met"] = bool(
                    combined["complete"]
                    and combined["minimum_declared_margin_lower_bound_mm"] is not None
                    and combined["minimum_declared_margin_lower_bound_mm"] >= margin
                )
                payload = dict(
                    version=VERSION,
                    owner=owner,
                    source_hashes=ctx["source_hashes"],
                    conditions=conditions,
                    spatial_padding_mm=margin,
                    physical_cabinet_count=11,
                    door_sensitivity=asdict(hypothesis),
                    closed_door_evidence_hash=canonical_hash(checked),
                    open_door_evidence=doors,
                    combined=combined,
                )
                profiles.append(
                    dict(
                        hypothesis=asdict(hypothesis),
                        doors=doors,
                        combined=combined,
                        witness_hash=canonical_hash(payload),
                        payload=payload,
                    )
                )
            worst = checked["margins"]["minimum_declared_spatial_margin"]
            reports.append(
                dict(
                    id=f"R14-{finish}-{installation}-M{margin}-{label}",
                    label=label,
                    conditions=conditions,
                    margin_target_mm=margin,
                    room_dimensions_mm=[26331, width],
                    area_mm2=26331 * width,
                    geometry=g,
                    closed_door_flows=checked["shifts"],
                    margins=checked["margins"],
                    closed_door_evidence_hash=canonical_hash(checked),
                    home_count=len(g["model"]["homes"]),
                    missing_home_count=53 - len(g["model"]["homes"]),
                    completed_users=[f["completed_users"] for f in checked["shifts"]],
                    minimum_observed_margin_mm=worst["extra_mm"] if worst else None,
                    door_profiles=profiles,
                    site_impact_reference_label=label,
                    actual_functional_status="INPUT_REQUIRED",
                )
            )
    return dict(
        task=TASK,
        version=VERSION,
        base_head=BASE_HEAD,
        owner_selection=owner,
        actual_door_records=actual_door_records(inv),
        inventory=inv,
        reports=reports,
        source_hashes=copy.deepcopy(ctx["source_hashes"]),
        site_impact_reference=copy.deepcopy(ctx["overlay"]),
        physical_room_count=1,
        historical_records=["P01", "P02"],
        occupancy_basis=dict(
            shift_people=[53, 53],
            initial_people_in_room=53,
            exclusive_cells_required=106,
            allocated_cells_per_shift=[55, 55],
            spare_cells=4,
        ),
        difference_from_400_500_reference=dict(
            old_columns=22,
            old_column_pitch_mm=400,
            old_depth_mm=500,
            old_summed_width_mm=8800,
            new_summed_complete_width_mm=9350,
            summed_width_delta_mm=550,
            old_floor_footprint_mm2=4400000,
            new_floor_footprint_mm2=3646500,
            footprint_delta_mm2=-753500,
            note=(
                "NOMINAL_ENVELOPE_ONLY; installed run includes individually reported gaps; "
                "not functional suitability"
            ),
        ),
        storage_function_checks=dict(
            capacity_arithmetic=dict(
                status="SATISFIED_ARITHMETIC_ONLY", required=106, allocated=110, spare=4
            ),
            actual_internal_clear_dimensions=dict(
                status="INPUT_REQUIRED",
                net_width_mm=None,
                net_depth_mm=None,
                net_height_mm=None,
                nominal_400_360_320_is_net=False,
            ),
            work_private_separation=dict(status="INPUT_REQUIRED", automatic_extra_partition=False),
            folded_clothing_storage=dict(
                status="INPUT_REQUIRED",
                clothing_envelope_mm=None,
                volume=None,
                rails_reported=0,
                extra_shelves_reported=0,
            ),
            lowest_highest_tier_retrieval=dict(
                status="INPUT_REQUIRED",
                actual_reach_range_mm=None,
                conditional_door_face_range_mm=[100, 1780],
                conditional_reference_reach_mm=[100, 1800, 600],
            ),
            actual_hinges_opening_and_fixing=dict(
                status="INPUT_REQUIRED",
                angle_degrees=None,
                hinges=None,
                fixing_clearance_mm=None,
                maintenance_clearance_mm=None,
            ),
        ),
        actual_calibration="INPUT_REQUIRED",
        storage_hygiene="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
        missing_inputs=[
            "Original selected photograph bytes; manufacturer/model and reviewed product drawing",
            "Verified net width/depth/height of all five tiers and actual panels/base/frame",
            "Actual hinges, left/right mirroring, opening angle and leaf thickness",
            "Clothing folded dimensions/volume, work/private segregation and hygiene process",
            "Actual lowest/highest tier retrieval reach and human activity envelopes",
            "Fixing/maintenance/installation requirements, finish and construction tolerances",
            "Room door swings, reviewed operating sequence, "
            "external Site/Access and hygiene review",
        ],
        native_solves=0,
        main_executed=False,
        real_grant_claim=False,
    )
