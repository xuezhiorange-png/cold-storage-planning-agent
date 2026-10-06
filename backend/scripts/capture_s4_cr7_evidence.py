"""Bounded diagnostic capture; never a source of production placement seeds.

Run from backend with PYTHONPATH=src:. and --mode search/control/baseline/evidence.
The baseline mode alone reads historical partials to classify the CR6 debt.
Search mode calls the actual production application with canonical authorities.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.access_aware_composition_placement import (
    replay_control_candidate,
    search_access_aware_composition_placements,
)
from cold_storage.modules.layout.domain import composition_placement as domain
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from tests.unit.test_v222_p1a_s4_cr1_access_aware_placement import authorities
from tests.unit.test_v222_p1a_s4_cr3_forward_check import (
    _rectangle_from_bounds,
    context,
)

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/tasks/evidence"
KNOWN = "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"


def known_attempt(result: dict[str, Any]) -> dict[str, Any]:
    return next(
        row
        for row in result["placements"]["search_attempts"]
        if row["composition_identity"] == KNOWN
        and row["peripheral_bank_sign"] == 1
        and row["search_order_lane"] == "S3_COMPATIBILITY_ORDER"
    )


def baseline_profiles() -> dict[str, Any]:
    """Historical TEST/diagnostic partials only, never passed to search API."""
    historical = json.loads(
        (EVIDENCE / "v2_2_2_p1a_s4_cr6/xinzhao_mandatory_chain_successor_capacity.json").read_text()
    )
    # The previous evidence includes complete captures, not runtime seeds.
    run = historical["full_replay"] if "full_replay" in historical else historical["replay_1"]
    attempt = next(
        row
        for row in run["attempts"]
        if row["composition_identity"] == KNOWN
        and row["bank_sign"] == 1
        and row["search_order_lane"] == "S3_COMPATIBILITY_ORDER"
    )
    data = context.__wrapped__()
    handoff = data["handoffs"][KNOWN]
    boundary, obstacles, shapes = data["boundary"], data["obstacles"], data["shapes"]
    shapes = domain._composition_shape_order(handoff, shapes, 1)
    domains = domain._domain_arrangement(handoff, 1, boundary, data["dimension_authorities"])
    faces = domain._domain_faces(handoff, 1)
    fixed = {
        name: _rectangle_from_bounds(name, tuple(bounds))
        for name, bounds in attempt["best_partial_placement_witness"]["zone_bounds_mm"].items()
        if name != "coating_room"
    }
    samples = attempt["composition_propagation"]["accepted_candidate_samples"]
    profiles = []
    for sample in samples:
        if sample["role"] != "coating_room":
            continue
        placed = {
            **fixed,
            "coating_room": _rectangle_from_bounds("coating_room", tuple(sample["bounds_mm"])),
        }
        per_shape = []
        for shape in shapes["finished_goods_room"]:
            role = "finished_goods_room"
            origins = set(
                domain._domain_derived_anchors(
                    role, shape, handoff, domains, 1, placed, boundary, obstacles
                )
            )
            origins.update(
                domain._domain_derived_anchors(
                    role, shape, handoff, domains, 1, placed, boundary, obstacles, data["intent"]
                )
            )
            origins.update(
                domain._generic_fallback_anchors(
                    role, shape, placed, boundary, obstacles, limit=None
                )
            )
            neighbors = tuple(name for name in domain._must_neighbors(role) if name in placed)
            must_origins = set(
                domain._anchors_at_must_faces(role, shape, placed, neighbors, boundary, obstacles)
            )
            origins.update(must_origins)
            finite = domain._feasible_successor_domain(
                role, shape, tuple(origins), placed, handoff, 1
            )
            compatible = tuple(
                point
                for point in finite.origins
                if domain._composition_intent_projection_decision(
                    handoff,
                    {**placed, role: domain._rectangle(role, *point, shape)},
                    boundary,
                    shapes,
                    faces,
                ).status
                != "PROVABLY_INCOMPATIBLE"
            )
            axis, interval = domain._domain_interval(role, handoff, domains)
            box = (
                min(p[0] for p in boundary),
                min(p[1] for p in boundary),
                max(p[0] for p in boundary),
                max(p[1] for p in boundary),
            )
            obstacle_boxes = [
                (
                    min(p[0] for p in poly),
                    min(p[1] for p in poly),
                    max(p[0] for p in poly),
                    max(p[1] for p in poly),
                )
                for poly in obstacles
            ]

            def historical_priority(
                point,
                role=role,
                shape=shape,
                placed=placed,
                axis=axis,
                interval=interval,
                must_origins=must_origins,
                box=box,
                obstacle_boxes=obstacle_boxes,
            ):
                candidate = domain._rectangle(role, *point, shape)
                b = domain._bounds(candidate)
                decision = domain._composition_intent_projection_decision(
                    handoff, {**placed, role: candidate}, boundary, shapes, faces
                )
                projection = domain._center(candidate, axis)
                interval_penalty = (
                    0
                    if interval is None or interval[0] <= projection <= interval[1]
                    else min(abs(projection - interval[0]), abs(projection - interval[1]))
                )

                def intersects(other):
                    return int(
                        b[0] < other[2] and other[0] < b[2] and b[1] < other[3] and other[1] < b[3]
                    )

                flow_violation = max(
                    0, domain._center(placed["coating_room"], "Y") - domain._center(candidate, "Y")
                )
                return (
                    int(point not in must_origins),
                    int(b[0] < box[0] or b[1] < box[1] or b[2] > box[2] or b[3] > box[3]),
                    sum(intersects(domain._bounds(room)) for room in placed.values()),
                    sum(intersects(other) for other in obstacle_boxes),
                    0,
                    -decision.slack,
                    flow_violation,
                    interval_penalty,
                    point[0],
                    point[1],
                )

            _, profile = domain._exact_successor_free_space_domain(
                role,
                shape,
                tuple(sorted(compatible, key=historical_priority)),
                placed,
                boundary,
                obstacles,
                handoff,
                1,
            )
            per_shape.append(dict(profile))
        profiles.append({"coating_bounds_mm": sample["bounds_mm"], "shape_profiles": per_shape})
    stop = attempt["composition_propagation"]["budget_stop_candidate_samples"][0]["bounds_mm"]
    last_rows = [row for shape in profiles[-1]["shape_profiles"] for row in shape["candidates"]]
    stop_index = next(i for i, row in enumerate(last_rows) if row["bounds_mm"] == stop)
    tail = last_rows[stop_index:]
    assert len(tail) == 127, "CR6 finite-order reconstruction must match the measured debt"
    assert Counter(row["exclusive_classification"] for row in tail) == {
        "SITE": 84,
        "OBSTACLE": 36,
        "OVERLAP": 7,
    }
    return {
        "diagnostic_fixture_only": True,
        "runtime_seed_used": False,
        "site_boundary_polygon_mm": boundary,
        "site_boundary_identity": canonical_hash({"polygon_mm": boundary}),
        "historical_coating_profile_count": len(profiles),
        "profiles": profiles,
        "previously_unexpanded_count": len(tail),
        "previously_unexpanded_candidates": tail,
        "previously_unexpanded_classifications": dict(
            Counter(row["exclusive_classification"] for row in tail)
        ),
        "obstacle_identity_map": [
            {"identity": canonical_hash({"polygon_mm": polygon}), "polygon_mm": polygon}
            for polygon in obstacles
        ],
    }


def assemble(directory: Path) -> dict[str, Any]:
    digests = []
    for name in ("run1.json", "run2.json"):
        digest = sha256()
        with (directory / name).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digests.append(digest.hexdigest())
    if digests[0] != digests[1]:
        raise ValueError("FULL_REPLAY_OUTPUT_BYTES_DIVERGED")
    one = json.loads((directory / "run1.json").read_text())
    # Identical full output bytes establish equality of every decoded subtree.
    # Do not simultaneously materialize two 545 MB diagnostic trees on an
    # 8 GB host merely to compare equal scalar records a second time.
    two = one
    baseline = json.loads((directory / "baseline.json").read_text())
    control = json.loads((directory / "control.json").read_text())
    checks = {}
    for label, selector in {
        "attempt_schedule": lambda r: [
            (
                a["composition_identity"],
                a["peripheral_bank_sign"],
                a["search_order_lane"],
                a["nodes_allocated"],
            )
            for a in r["placements"]["search_attempts"]
        ],
        "propagation": lambda r: [
            a["composition_propagation"]["decision_sequence_hash"]
            for a in r["placements"]["search_attempts"]
        ],
        "free_space": lambda r: [
            a["mandatory_chain_successor_capacity"]["exact_successor_free_space"]["sequence_hash"]
            for a in r["placements"]["search_attempts"]
        ],
        "successor_capacity": lambda r: r["placements"]["mandatory_chain_successor_capacity"],
        "forward_check": lambda r: r["placements"]["forward_check_sequence_hashes"],
        "witness": lambda r: r["placements"]["witness_sequence_hashes"],
        "candidate_hashes": lambda r: r["placements"]["candidates"],
        "best_candidate": lambda r: r["best_candidate_hash"],
        "access_results": lambda r: r["candidate_assessments"],
    }.items():
        left = canonical_hash(selector(one))
        checks[label] = {
            "run1_hash": left,
            "run2_hash": left,
            "equal": True,
            "verified_by_full_output_byte_identity": True,
        }
    checks["entire_replay"] = {
        "run1_hash": digests[0],
        "run2_hash": digests[1],
        "equal": True,
        "hash_scope": "UNABRIDGED_OUTPUT_BYTES",
    }
    p = one["placements"]
    known = known_attempt(one)
    nodes = [
        {
            "primary": r["placements"]["primary_search_nodes_used"],
            "forward": r["placements"]["forward_check_nodes_used"],
            "total": r["placements"]["nodes_used"],
            "valid": r["placements"]["node_accounting_sum_valid"]
            and r["placements"]["nodes_used"] <= 60000,
        }
        for r in (one, two)
    ]
    classified = Counter()
    for profile in baseline["profiles"]:
        for shape in profile["shape_profiles"]:
            classified.update(shape["exclusive_counts"])
    # Compare the unabridged replays above, then avoid duplicating millions
    # of origin rows in the checked-in artifact. All seven historical profiles
    # and the 127 debt records remain unabridged. Current production profiles
    # retain every fixed partial, count, blocker map and canonical row digest.
    for replay in (one,):
        for attempt in replay["placements"]["search_attempts"]:
            free_space = attempt["mandatory_chain_successor_capacity"]["exact_successor_free_space"]
            grouped = {}
            for profile in free_space.pop("profiles"):
                key = (profile["role"], profile["partial_geometry_hash"])
                group = grouped.setdefault(
                    key,
                    {
                        "role": profile["role"],
                        "partial_geometry_hash": profile["partial_geometry_hash"],
                        "fixed_zone_bounds_mm": profile["fixed_zone_bounds_mm"],
                        "shape_profile_count": 0,
                        "classified_count": 0,
                        "free_space_count": 0,
                        "unclassified_count": 0,
                        "exclusive_counts": Counter(),
                        "obstacle_identity_counts": Counter(),
                        "overlapping_room_counts": Counter(),
                        "overlapping_group_counts": Counter(),
                        "single_non_must_release_counts": Counter(),
                        "classification_shape_digests": [],
                    },
                )
                group["shape_profile_count"] += 1
                for metric in ("classified_count", "free_space_count", "unclassified_count"):
                    group[metric] += profile[metric]
                for metric in (
                    "exclusive_counts",
                    "obstacle_identity_counts",
                    "overlapping_room_counts",
                    "overlapping_group_counts",
                ):
                    group[metric].update(profile[metric])
                for release in profile["single_non_must_blocker_release"]:
                    group["single_non_must_release_counts"][release["released_role"]] += release[
                        "restored_physical_domain_count"
                    ]
                group["classification_shape_digests"].append(
                    (profile["shape"], profile["candidate_classification_rows_hash"])
                )
            for group in grouped.values():
                group["all_shape_classification_hash"] = canonical_hash(
                    group.pop("classification_shape_digests")
                )
                group["successor_domain_conflict_set"] = {
                    "site_boundary": bool(group["exclusive_counts"]["SITE"]),
                    "obstacle_identities": sorted(group["obstacle_identity_counts"]),
                    "overlapping_room_roles": sorted(group["overlapping_room_counts"]),
                    "overlapping_groups": sorted(group["overlapping_group_counts"]),
                    "minimal_conflict_set_claimed": False,
                    "all_physical_exclusions_attributed": group["unclassified_count"] == 0,
                    "hard_recovery_authority": False,
                }
            free_space["profiles_by_fixed_partial"] = list(grouped.values())
            free_space["raw_output_compacted_only_after_full_byte_identity_check"] = True
    return {
        "task_id": "V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR7",
        "mode": "EXACT_SUCCESSOR_FREE_SPACE_DOMAIN_PROPAGATION_AND_PHYSICAL_BLOCKER_ATTRIBUTION",
        "start_head": "22fa1ff0efc87820d7d6def72449826095e4ff90",
        "runtime_source_sha256": sha256(
            (
                REPO / "backend/src/cold_storage/modules/layout/domain/composition_placement.py"
            ).read_bytes()
        ).hexdigest(),
        "authority_changed": False,
        "budgets": {"placement": 60000, "access": 20000, "truck": 20000},
        "cr8_authorized": False,
        "global_infeasibility_proven": False,
        "architecture_decision_point_required": one["complete_candidates_constructed"] == 0,
        "result": "PASS"
        if one["complete_candidates_constructed"] > 0
        and one["best_non_truck_access_pass_count"] > 7
        else "FAIL",
        "validation_progress_result": "PHYSICAL_BLOCKER_ATTRIBUTION_COMPLETE_NO_COMPLETE_CANDIDATE"
        if one["complete_candidates_constructed"] == 0
        else "COMPLETE_CANDIDATE_REACHED_REVIEW_ACCESS_RESULTS",
        "node_accounting": nodes,
        "attempt_count": p["attempt_count"],
        "baseline_seven_coating_profiles": baseline,
        "baseline_classification_totals": dict(classified),
        "baseline_all_candidates_classified": all(
            shape["unclassified_count"] == 0
            for profile in baseline["profiles"]
            for shape in profile["shape_profiles"]
        ),
        "known_lane": known,
        "full_replay_1": one,
        "full_replay_2": {
            "independent_production_replay_completed": True,
            "unabridged_output_sha256": digests[1],
            "unabridged_output_size_bytes": (directory / "run2.json").stat().st_size,
            "identical_to_unabridged_run1": True,
            "node_accounting": nodes[1],
            "attempt_schedule": [
                {
                    key: attempt[key]
                    for key in (
                        "composition_identity",
                        "peripheral_bank_sign",
                        "search_order_lane",
                        "nodes_allocated",
                        "nodes_visited",
                    )
                }
                for attempt in p["search_attempts"]
            ],
            "sequence_comparison": checks,
            "complete_candidates_constructed": two["complete_candidates_constructed"],
            "best_candidate_hash": two["best_candidate_hash"],
            "best_non_truck_access_pass_count": two["best_non_truck_access_pass_count"],
        },
        "current_code_control_replay": control,
        "determinism": checks,
        "full_determinism_verified": all(row["equal"] for row in checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("search", "control", "baseline", "evidence"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--captures", type=Path)
    args = parser.parse_args()
    if args.mode == "search":
        result = search_access_aware_composition_placements(*authorities.__wrapped__()).to_dict()
    elif args.mode == "control":
        result = dict(replay_control_candidate(*authorities.__wrapped__()))
    elif args.mode == "baseline":
        result = baseline_profiles()
    else:
        if args.captures is None:
            parser.error("--captures required for evidence mode")
        result = assemble(args.captures)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {
                "mode": args.mode,
                "output": str(args.output),
                "canonical_hash": canonical_hash(result),
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
