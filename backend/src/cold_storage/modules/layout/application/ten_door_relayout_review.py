"""R15 source supplement and finite review; no approval or planning writes."""

import copy
import hashlib
from typing import Any

from cold_storage.modules.layout.application.ten_door_locker_review import (
    bind_owner_selection,
    combine_flow,
    evidence_is_current,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.ten_door_local_relayout import (
    MAX_CANDIDATES,
    VERSION,
    finite_organizations,
    home_coordinate_diff,
    rearrange_homes,
)
from cold_storage.modules.layout.domain.ten_door_locker_geometry import closed_door_flow
from cold_storage.modules.layout.domain.ten_door_locker_model import DoorSensitivity
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import check_flow_doors
from cold_storage.modules.layout.domain.ten_door_sweep_clearance import trace_archived_minimum

TASK = "V2_2_2_R11_R15_TEN_DOOR_LOCKER_LOCAL_RELAYOUT_R1"
BASE_HEAD = "784e87e1e1307b6379214903da6b2fcc393a244d"
SOURCE_PATH = "docs/tasks/V2_2_2-r11-r15-owner-photo-supplement.txt"
SOURCE_SHA256 = "6c4026e6c40a084ca1eff339cf199e7c46f662935b4bd8dc1f08a6b1959f59af"
PHOTO_FILENAME = "IMG_0875.jpeg"
PHOTO_OWNER_REPORTED_SHA256 = "833c674259d29129d75703c37c6eb532b360d09647f3e221f6cce3951b41ccaa"


def verify_private_photo(data: bytes, expected_sha256: str) -> str:
    """Checks raw bytes only. No file publication, product audit or approval."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("NONEMPTY_ORIGINAL_PHOTO_BYTES_REQUIRED")
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("EXPLICIT_SHA256_REQUIRED")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ValueError("ORIGINAL_PHOTO_SHA256_MISMATCH")
    return digest


def photo_source_supplement(
    ctx: dict[str, Any],
    owner_source: bytes,
    supplement_source: bytes,
    photo_bytes: bytes | None = None,
) -> dict[str, Any]:
    owner = bind_owner_selection(ctx, owner_source)
    if (
        not isinstance(supplement_source, bytes)
        or hashlib.sha256(supplement_source).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("R15_OWNER_PHOTO_SUPPLEMENT_SOURCE_MISMATCH")
    digest = (
        verify_private_photo(photo_bytes, PHOTO_OWNER_REPORTED_SHA256)
        if photo_bytes is not None
        else None
    )
    return dict(
        version=VERSION,
        task=TASK,
        project_scope_id=owner["project_scope_id"],
        physical_room_id=owner["physical_room_id"],
        r14_selection_source_path=owner["source_path"],
        r14_selection_source_sha256=owner["source_sha256"],
        supplement_source_path=SOURCE_PATH,
        supplement_source_sha256=SOURCE_SHA256,
        owner_reported_filename=PHOTO_FILENAME,
        owner_reported_sha256=PHOTO_OWNER_REPORTED_SHA256,
        actual_photo_sha256=digest,
        photo_file_evidence="RAW_BYTES_SHA256_VERIFIED_PRIVATE"
        if digest
        else "INPUT_REQUIRED_ORIGINAL_PHOTO_FILE_MISSING",
        photo_publication_authorized=False,
        photo_embedded_or_copied=False,
        nominal_label_basis=(
            "OWNER_REPORTED_850x390x1800_AND_400x360x320; NOT_NET_COMPARTMENT_DIMENSIONS"
        ),
        actual_net_compartment_dimensions="INPUT_REQUIRED",
        actual_hardware="INPUT_REQUIRED",
        supplier_technical_review="NOT_EVALUATED",
        procurement_acceptance="NOT_EVALUATED",
        r14_history_overwritten=False,
    )


def review_local_relayout(
    ctx: dict[str, Any],
    archived: dict[str, Any],
    owner_source: bytes,
    supplement_source: bytes,
    photo_bytes: bytes | None = None,
) -> dict[str, Any]:
    supplement = photo_source_supplement(ctx, owner_source, supplement_source, photo_bytes)
    if archived["owner_selection"] != bind_owner_selection(ctx, owner_source):
        raise ValueError("R14_ARCHIVE_PROJECT_SELECTION_MISMATCH")
    cases = archived["reports"]
    if len(cases) != 4 or not all(
        evidence_is_current(ctx, owner_source, case, p)
        for case in cases
        for p in case["door_profiles"]
    ):
        raise ValueError("R14_ARCHIVE_WITNESS_SOURCE_OR_GEOMETRY_MISMATCH")
    base = next(c for c in cases if c["id"] == "R14-30-40-M100-3850")
    if base["home_count"] != 52 or base["closed_door_flows"]:
        raise ValueError("PRESERVED_R14_52_HOME_FAILURE_REQUIRED")
    traces = [
        trace_archived_minimum(c, p)
        for c in cases
        if c["closed_door_flows"]
        for p in c["door_profiles"]
    ]
    reports = []
    for org in finite_organizations():
        g = rearrange_homes(base["geometry"], org)
        checked = closed_door_flow(g)
        profiles = []
        for hinge in ("ALL_LEFT", "MIRRORED"):
            p = DoorSensitivity(hinge)
            doors = check_flow_doors(g, checked["shifts"], p)
            combined = combine_flow(checked, doors)
            cm, dm = (
                checked["margins"]["minimum_declared_spatial_margin"],
                doors["minimum_door_clearance_lower_bound"],
            )
            lower = (
                min(cm["extra_mm"], dm["extra_mm"]) if combined["complete"] and cm and dm else None
            )
            combined.update(
                margin_target_mm=100,
                minimum_declared_margin_lower_bound_mm=lower,
                margin_target_met=lower is not None and lower >= 100,
            )
            profiles.append(dict(hinges=hinge, doors=doors, combined=combined))
        payload = dict(
            version=VERSION,
            supplement=supplement,
            source_hashes=ctx["source_hashes"],
            archived_base_evidence_hash=base["closed_door_evidence_hash"],
            checked=checked,
            profiles=profiles,
        )
        reports.append(
            dict(
                id=org["id"],
                organization=org,
                geometry=g,
                closed_door_flows=checked["shifts"],
                margins=checked["margins"],
                home_count=len(g["model"]["homes"]),
                profiles=profiles,
                coordinate_diff=home_coordinate_diff(base["geometry"], g),
                witness_hash=canonical_hash(payload),
                payload=payload,
            )
        )
    complete = [c for c in reports if all(p["combined"]["complete"] for p in c["profiles"])]
    selected = (
        min(complete, key=lambda c: (len(c["coordinate_diff"]["changed_homes"]), c["id"]))
        if complete
        else None
    )
    return dict(
        task=TASK,
        base_head=BASE_HEAD,
        version=VERSION,
        photo_source_supplement=supplement,
        historical_r14_summary=[
            dict(
                id=c["id"],
                homes=c["home_count"],
                completed_users=c["completed_users"],
                profile_status=[p["combined"]["status"] for p in c["door_profiles"]],
            )
            for c in cases
        ],
        archived_baseline=copy.deepcopy(base),
        clearance_traces=traces,
        new_clearance_traces=[
            trace_archived_minimum(selected, dict(p, hypothesis=dict(hinges=p["hinges"])))
            for p in selected["profiles"]
        ]
        if selected
        else [],
        reports=reports,
        candidate_limit=MAX_CANDIDATES,
        actual_candidates=len(reports),
        complete_candidate_ids=[c["id"] for c in complete],
        selected_candidate_id=selected["id"] if selected else None,
        all_margin_100_target_candidate_ids=[
            c["id"]
            for c in complete
            if all(p["combined"]["margin_target_met"] for p in c["profiles"])
        ],
        selection_scope="CONDITIONAL_REVIEW_ONLY; COMPLETE_FLOW_AND_100MM_MARGIN_ARE_SEPARATE",
        source_hashes=copy.deepcopy(ctx["source_hashes"]),
        actual_calibration="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
        native_solves=0,
        main_executed=False,
        real_grant_claim=False,
        missing_inputs=[
            "Original IMG_0875.jpeg bytes if unavailable",
            "Actual net compartment dimensions and clothing volume/separation/hygiene",
            "Reviewed hinges, mirroring, door thickness and opening angle",
            "Reviewed human activity/reach and simultaneous-opening sequence",
            "Actual fixing/maintenance/installation, finish and construction tolerances",
            "External Site/Access and room door hardware",
        ],
    )
