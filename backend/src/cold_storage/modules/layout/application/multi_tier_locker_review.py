"""Opt-in R4 project interpretation; no mutation of R3's archived conclusions."""

import copy
import hashlib
from typing import Any

from cold_storage.modules.layout.application.changing_locker_review import PROJECT_SCOPE
from cold_storage.modules.layout.domain.multi_tier_locker_layout import assess_template
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    SCENARIOS,
    MultiTierHypothesis,
    storage_demand,
)

TASK = "V2_2_2_R11_R4_MULTI_TIER_LOCKER_MODEL_R1"
SOURCE_SHA256 = "275ff176226358835912b5e827104028c73388b7840ef78d1e4c1eaad2a807da"
MISSING = (
    "selected_cabinet_model_and_column_grouping",
    "cabinet_column_and_compartment_clear_dimensions",
    "shelves_plinth_structure_and_finished_clear_height",
    "compartment_door_sweep_and_simultaneous_operation_rules",
    "cabinet_front_concurrent_users_and_staggered_service_plan",
    "53_person_changing_spaces_and_transition_paths",
    "approved_reach_and_operating_clearance_for_all_five_tiers",
    "internal_divider_or_two_compartment_hygiene_approval",
    "finished_room_dimensions_and_internal_aisle_width",
    "actual_room_door_leaf_motion_and_landing_clearance",
    "benches_dimensions_quantity_and_operation_spaces",
    "clean_unclean_separation_and_cleaning_maintenance_plan",
    "both_shift_complete_reviewed_four_state_witnesses",
)


def bind_multi_tier_review(r3: dict[str, Any], owner_source: bytes) -> dict[str, Any]:
    if hashlib.sha256(owner_source).hexdigest() != SOURCE_SHA256:
        raise ValueError("REVIEWED_R4_LOCKER_FORM_SOURCE_MISMATCH")
    binding = r3["project_binding"]
    if (
        binding["project_scope_id"] != PROJECT_SCOPE
        or binding.get("r3_project_basis_status") != "CONFIRMED_PROJECT_BASIS"
    ):
        raise ValueError("R4_REQUIRES_ORIGINAL_REVIEWED_PROJECT_SCOPE")
    design = r3["design_counts"]
    if (
        design["packaged_mass_kg_per_day"] != 20000
        or design["shift_workers"] != [53, 53]
        or design["simultaneous_users"] != 53
    ):
        raise ValueError("FROZEN_PROJECT_DESIGN_COUNTS_CHANGED")
    if binding["owner_confirmed_policy"]["locker_internal_separation"] is not True:
        raise ValueError("ORIGINAL_WORK_PRIVATE_SEPARATION_REQUIRED")
    demands = {
        mode: storage_demand(design["shift_workers"], design["simultaneous_users"], mode)
        for mode in SCENARIOS
    }
    groups = []
    for row in r3["groups"]:
        if not row["room"]["scope_id"].startswith(PROJECT_SCOPE + ":"):
            raise ValueError("HISTORICAL_ROOM_SCOPE_MISMATCH")
        groups.append(
            {
                k: copy.deepcopy(row[k])
                for k in (
                    "group",
                    "records",
                    "handoff",
                    "room",
                    "aliases",
                    "record_access_readbacks",
                    "external_routes",
                )
            }
        )
    return dict(
        task=TASK,
        base_head="aedcbcbe5114f4624a89f61e3fa9305a49a12197",
        project_scope_id=PROJECT_SCOPE,
        project_facts=dict(
            packaged_mass_kg_per_day=20000,
            cabinet_structure="FIVE_TIER_FIVE_DOOR",
            tiers_per_column=5,
            storage_assignment="ONE_INDEPENDENT_COMPARTMENT_PER_PERSON_BASE_SCENARIO",
            source_label="OWNER_CONFIRMED",
            source_sha256=SOURCE_SHA256,
            reference="docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt",
        ),
        design_basis=dict(
            shift_design_users=[53, 53],
            total_design_users=106,
            simultaneous_room_users=53,
            source_label="ENGINEERING_DERIVED",
            personnel_identity="DESIGN_SLOTS_NOT_EMPLOYEE_ROSTER",
        ),
        reference_dimensions=dict(
            compartment_height_mm=300,
            approximate=True,
            status="REFERENCE_ONLY_NOT_APPROVED_DIMENSION",
        ),
        demands=demands,
        groups=groups,
        original_record_count=9,
        physical_group_count=8,
        cabinet_front_concurrent_users="INPUT_REQUIRED",
        physical_cabinet_unit_count="INPUT_REQUIRED",
        project_functional_status="INPUT_REQUIRED",
        missing_inputs=list(MISSING),
        old_r3_floor_locker_results_applicable=False,
        engineering_approval=False,
        historical_status_changed=False,
        native_solves=0,
    )


def review_multi_tier_template(
    catalog: dict[str, Any],
    group: str,
    scenario: str,
    p: MultiTierHypothesis,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError("KNOWN_SEPARATION_SCENARIO_REQUIRED")
    rows = [r for r in catalog["groups"] if r["group"] == group]
    if len(rows) != 1:
        raise ValueError("KNOWN_HISTORICAL_ROOM_GROUP_REQUIRED")
    row = rows[0]
    result = assess_template(row["room"], catalog["demands"][scenario], p)
    result.update(
        group=group,
        records=row["records"],
        handoff=row["handoff"],
        original_access_readbacks=row["record_access_readbacks"],
        actual_missing_inputs=catalog["missing_inputs"],
    )
    return result
