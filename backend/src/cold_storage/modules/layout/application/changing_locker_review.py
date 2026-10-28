"""R3 source-reviewed project basis and room-scoped, opt-in functional review."""

import copy
import hashlib
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
    bind_project_functional_inputs,
)
from cold_storage.modules.layout.domain.changing_locker_screening import (
    HypotheticalLockerParameters,
    screen_locker_rows,
)
from cold_storage.modules.layout.domain.functional_room_fit import (
    COMMON,
    REQUIRED,
    BasisValue,
    evaluate_functional_room,
)

TASK = "V2_2_2_R11_R3_106_LOCKER_LAYOUT_REVIEW_R1"
PROJECT_SCOPE = (
    "sha256:61b59f8e6bd8e81c8b43751bd58ce52df82d349b82346bbfd6585a891139cddd:"
    "sha256:e1fac31df5458427a882d3669f9e79ae4edfac086db732aaa1345a626482ab85"
)
REVIEWED_SOURCE_SHA256 = "53ffa4e0e3584cabe7166d75214d0569fcaebfc34cc1e71bc35c70abedab7326"


def bind_r3_project(
    review: Mapping[str, Any], owner: bytes, reviewed_source: bytes
) -> dict[str, Any]:
    """Materialize the fact reviewed in this Owner task, not arbitrary JSON approval.

    The digest pins the reviewed source and applicability, and is not a MAIN token.
    No general-purpose import of user-authored labels or statuses is provided.
    """
    if hashlib.sha256(reviewed_source).hexdigest() != REVIEWED_SOURCE_SHA256:
        raise ValueError("REVIEWED_OWNER_PROJECT_SOURCE_CHANGED")
    if bind_project_functional_inputs(review, owner)["project_scope_id"] != PROJECT_SCOPE:
        raise ValueError("REVIEWED_OWNER_PROJECT_SCOPE_MISMATCH")
    datum = ReviewedProjectDatum(
        field_name="PACKAGED_PRODUCT_MASS_KG_PER_DAY",
        value=20000,
        unit="kg/day",
        project_scope_id=PROJECT_SCOPE,
        source_label="OWNER_CONFIRMED",
        reference=(
            f"Owner instruction {TASK} section 1; "
            "docs/tasks/V2_2_2-r11-r3-reviewed-project-fact.txt; "
            f"sha256:{REVIEWED_SOURCE_SHA256}"
        ),
    )
    result = bind_project_functional_inputs(
        review, owner, reviewed_project={datum.field_name: datum}
    )
    result["r3_project_basis_status"] = "CONFIRMED_PROJECT_BASIS"
    result["staffing_interpretation"] = "ENGINEERING_DERIVED_DESIGN_COUNTS_NOT_EMPLOYEE_ROSTER"
    result["historical_input_mutated"] = False
    return result


def evaluate_reviewed_locker_witness(
    room: dict[str, Any],
    binding: Mapping[str, Any],
    *,
    field_refs: Mapping[str, str] | None = None,
    reviewed_basis: Mapping[str, BasisValue] | None = None,
    witness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Use the original R11 oracle; hypothetical parameters cannot enter this port.

    Complete design data still needs application review before BasisValue is built.
    Fixed project design counts override any attempted request-side count change.
    """
    if binding.get("project_scope_id") != PROJECT_SCOPE or not room["scope_id"].startswith(
        PROJECT_SCOPE + ":"
    ):
        raise ValueError("PROJECT_ROOM_SCOPE_MISMATCH")
    refs, basis = dict(field_refs or {}), dict(reviewed_basis or {})
    fields = COMMON | REQUIRED["changing_room"]
    values = {
        "simultaneous_users": binding["workforce"]["simultaneous_changing_users"],
        "shift_locker_counts": binding["workforce"]["separate_personal_lockers"],
        "shift_change_policy": binding["owner_confirmed_policy"]["shift_change_policy"],
        "internal_clothing_separation": binding["owner_confirmed_policy"][
            "locker_internal_separation"
        ],
    }
    for field, value in values.items():
        key = "r3-design-basis:" + field
        refs[field] = key
        basis[key] = BasisValue(
            value=value,
            unit=fields[field],
            source_label="ENGINEERING_DERIVED",
            reference=f"{TASK}; approved mass and unchanged Owner V2 policy",
            scope_id=room["scope_id"],
            field_name=field,
        )
    result = evaluate_functional_room(room, refs, witness, reviewed_basis=basis)
    if result["functional_status"] != "INPUT_REQUIRED" and witness:
        components = witness.get("components", [])
        lockers = [c for c in components if c["role"] == "LOCKER"]
        if len(lockers) != sum(values["shift_locker_counts"]) or any(
            sum(c.get("shift") == i for c in lockers) != required
            for i, required in enumerate(values["shift_locker_counts"], 1)
        ):
            result["conflicts"].append(
                dict(code="R3_EXACT_INDEPENDENT_LOCKER_ALLOCATION_REQUIRED", components=[])
            )
            result["functional_status"] = "CONFIGURATION_NOT_FIT"
    return result


def build_r3_catalog(review: dict[str, Any], owner: bytes, source: bytes) -> dict[str, Any]:
    binding = bind_r3_project(review, owner, source)
    groups: dict[str, dict[str, Any]] = {}
    for row in review["room_evaluations"]:
        if row["room"]["room_code"] != "changing_room":
            continue
        key = row["physical_group"]
        room = row["room"]
        normalized = [(p["id"], p["segment_mm"], p["clear_width_mm"]) for p in room["portals"]]
        if key not in groups:
            groups[key] = dict(
                group=key,
                handoff=row["handoff"],
                records=[],
                room=copy.deepcopy(room),
                original_evaluation=copy.deepcopy(row["evaluation"]),
                project_evaluation=evaluate_reviewed_locker_witness(room, binding),
                aliases=[],
            )
        else:
            prior = groups[key]["room"]
            if (
                prior["local_bounds_mm"] != room["local_bounds_mm"]
                or [(p["id"], p["segment_mm"], p["clear_width_mm"]) for p in prior["portals"]]
                != normalized
            ):
                raise ValueError(
                    "DUPLICATE_RECTANGLE_WITH_DIFFERENT_PORTAL_REQUIRES_SEPARATE_REVIEW"
                )
        groups[key]["records"].append(row["record"])
        groups[key]["aliases"].append(
            dict(
                record=row["record"],
                candidate_hash=room["candidate_hash"],
                candidate_sha256=row["source_candidate_sha256"],
                geometry_reference=room["geometry_reference"],
            )
        )
    if len(groups) != 8 or sum(len(g["records"]) for g in groups.values()) != 9:
        raise ValueError("EXPECTED_NINE_RECORDS_EIGHT_PHYSICAL_GROUPS")
    staff = binding["workforce"]
    design = dict(
        packaged_mass_kg_per_day=binding["project_reviewed_facts"][
            "PACKAGED_PRODUCT_MASS_KG_PER_DAY"
        ]["value"],
        shift_workers=staff["separate_personal_lockers"],
        shift_mass_kg=[r["packaged_product_mass_kg"] for r in staff["per_shift_capacity"]],
        locker_count=sum(staff["separate_personal_lockers"]),
        simultaneous_users=staff["simultaneous_changing_users"],
        packing_tables=staff["required_packing_tables"],
    )
    return dict(
        task=TASK,
        base_head="93d7d1520052daf2fccdf62e6dd7e61468ef007f",
        project_binding=binding,
        design_counts=design,
        groups=list(groups.values()),
        original_record_count=9,
        unique_rectangle_count=8,
        original_history_unchanged=True,
        functional_approval=False,
        native_solves=0,
    )


def hypothetical_review(
    catalog: Mapping[str, Any], group: str, parameters: HypotheticalLockerParameters
) -> dict[str, Any]:
    rows = [r for r in catalog["groups"] if r["group"] == group]
    if len(rows) != 1:
        raise ValueError("KNOWN_PHYSICAL_GROUP_REQUIRED")
    row = rows[0]
    design = catalog["design_counts"]
    screening = screen_locker_rows(
        row["room"], design["locker_count"], design["simultaneous_users"], parameters
    )
    return dict(
        group=group,
        records=row["records"],
        handoff=row["handoff"],
        room=row["room"],
        design_counts=design,
        project_status="INPUT_REQUIRED",
        project_evaluation=row["project_evaluation"],
        screening=screening,
        external_access_status="ARCHIVED_STAGE_B_PASS_NOT_INTERIOR_FUNCTIONAL_APPROVAL",
        external_routes=row.get("external_routes", []),
    )
