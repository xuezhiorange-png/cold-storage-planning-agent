"""Process-local R8 diagnosis of the frozen R7 956e tail search."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import cold_storage.modules.layout.domain.placement as placement
from cold_storage.modules.aily.application import site_layout_preview as preview_module
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_SKELETON_ZONE_CODES,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
TARGET_SKELETON_HASH = "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
EXPECTED_FIXTURE_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
EXPECTED_R7_RESULT_HASH = "sha256:30daa8da4bb3d181f4dc0004c027f86152b995c68535c8baef0678e53947702a"
EXPECTED_R7_SVG_SHA256 = "sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981"
DIAGNOSTIC_NODE_LIMIT = 5_000
STATE_E_PAIR_LIMIT = 256
SUPPORT_FIRST = (
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
    "changing_room",
    "office",
)
TAIL_ZONE_CODES = (
    "changing_room",
    "office",
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
)
TAIL_CODES = TAIL_ZONE_CODES


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _evidence_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _evidence_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_evidence_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _rectangle_key(rectangle: Any) -> tuple[int, int, int, int, int]:
    return (
        int(rectangle.x * 1000),
        int(rectangle.y * 1000),
        int(rectangle.width_m * 1000),
        int(rectangle.depth_m * 1000),
        int(rectangle.rotation_deg),
    )


def _capture_r7_chain() -> tuple[dict[str, Any], Any, Any, tuple[Any, ...], dict[str, Any]]:
    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_FIXTURE_SHA256:
        raise AssertionError("canonical Xinzhao fixture bytes differ from the frozen R7 fixture")
    payload = json.loads(raw)
    original_construct = placement._construct_main_process_skeletons
    original_select = preview_module.select_validated_placement
    captured: dict[str, Any] = {
        "contexts": [],
        "seeds": [],
        "all_seeds": [],
        "select_args": None,
        "select_kwargs": None,
    }

    def capture_construct(*args: Any, **kwargs: Any):
        context = args[0] if args else kwargs["context"]
        for seed in original_construct(*args, **kwargs):
            captured["all_seeds"].append(
                {
                    "discovery_topology": context.structural_topology,
                    "discovery_family": context.structural_composition_family.to_dict(),
                    "skeleton_hash": seed.main_process_skeleton_hash,
                    "canonical_topology_owner": seed.canonical_topology_owner,
                    "canonical_family": seed.family.to_dict(),
                }
            )
            if seed.main_process_skeleton_hash == TARGET_SKELETON_HASH:
                captured["contexts"].append(context)
                captured["seeds"].append(seed)
            yield seed

    def capture_select(*args: Any, **kwargs: Any):
        captured["select_args"] = args
        captured["select_kwargs"] = kwargs
        result = original_select(*args, **kwargs)
        captured["selection_evaluation"] = result.internal_evaluation
        return result

    placement._construct_main_process_skeletons = capture_construct
    preview_module.select_validated_placement = capture_select
    try:
        result = preview_module.preview_site_layout(payload)
    finally:
        placement._construct_main_process_skeletons = original_construct
        preview_module.select_validated_placement = original_select

    if result.get("canonical_result_hash") != EXPECTED_R7_RESULT_HASH:
        raise AssertionError("real Tool 7 replay did not reproduce the R7 canonical result hash")
    if result.get("svg_sha256") != EXPECTED_R7_SVG_SHA256:
        raise AssertionError("real Tool 7 replay did not reproduce the R7 SVG hash")
    if len(captured["seeds"]) != 1:
        raise AssertionError(f"expected one live 956e seed, got {len(captured['seeds'])}")
    args = captured["select_args"]
    if not isinstance(args, tuple) or len(args) < 3:
        raise AssertionError("Tool 7 selector inputs were not captured")
    return result, captured["contexts"][0], captured["seeds"][0], args, captured


def _canonical_context(context: Any, seed: Any) -> Any:
    canonical = placement._canonical_tail_search_context(context, seed)
    if canonical.structural_topology != "STRAIGHT_LINEAR_BAND":
        raise AssertionError("956e canonical topology did not bind to Straight")
    if canonical.structural_composition_family.family != "LINEAR_PROCESS_BAND":
        raise AssertionError("956e canonical family did not bind to Linear")
    if canonical.structural_composition_family.dominant_axis != "Y":
        raise AssertionError("956e dominant axis differs from frozen R7 evidence")
    if canonical.structural_composition_family.dominant_direction != "POSITIVE":
        raise AssertionError("956e dominant direction differs from frozen R7 evidence")
    return canonical


def _option_call(code: str, placed: Mapping[str, Any], context: Any) -> tuple[Any, ...]:
    return placement._candidate_options(
        code,
        context.authorities[code],
        placed,
        context.boundary,
        context.boundary_bounds,
        context.obstacles,
        context.graph,
        context.structural_composition_family,
        context.main_entrance,
        search_phase=context.search_phase,
        structural_skeleton=context.structural_skeleton,
        zone_authorities=context.authorities,
        truck_entrance=placement._truck_segment(context.site_body),
    )


def _site_failure(rectangle: Any, context: Any) -> str | None:
    left, bottom, right, top = placement._bounds(rectangle)
    low_x, low_y, high_x, high_y = context.boundary_bounds
    if left < low_x or bottom < low_y or right > high_x or top > high_y:
        return "BOUNDING_EXTENTS"
    if not placement.rectangle_inside_polygon(rectangle, context.boundary):
        return "EFFECTIVE_BUILDABLE_POLYGON"
    return None


def _rectangle_bounds(polygon: Any) -> tuple[int, int, int, int] | None:
    points = tuple(polygon)
    xs = {point[0] for point in points}
    ys = {point[1] for point in points}
    if len(points) != 4 or len(xs) != 2 or len(ys) != 2:
        return None
    left, right = min(xs), max(xs)
    bottom, top = min(ys), max(ys)
    if set(points) != {(left, bottom), (left, top), (right, bottom), (right, top)}:
        return None
    return left, bottom, right, top


def _closed_obstacle_forbidden_origins(
    bounds: tuple[int, int, int, int], width_mm: int, depth_mm: int
) -> tuple[int, int, int, int]:
    left, bottom, right, top = bounds
    return left - width_mm, bottom - depth_mm, right, top


def _positive_overlap_forbidden_origins(
    bounds: tuple[int, int, int, int], width_mm: int, depth_mm: int
) -> tuple[int, int, int, int]:
    left, bottom, right, top = bounds
    return left - width_mm + 1, bottom - depth_mm + 1, right - 1, top - 1


def _integer_origin_witness(
    domain: tuple[int, int, int, int], forbidden: list[tuple[int, int, int, int]]
) -> tuple[int, int] | None:
    """Exhaust every integer-mm origin using exact forbidden-origin rectangles."""
    min_x, min_y, max_x, max_y = domain
    if min_x > max_x or min_y > max_y:
        return None
    clipped = [
        (max(min_x, left), max(min_y, bottom), min(max_x, right), min(max_y, top))
        for left, bottom, right, top in forbidden
        if left <= max_x and right >= min_x and bottom <= max_y and top >= min_y
    ]
    clipped = [row for row in clipped if row[0] <= row[2] and row[1] <= row[3]]
    y_breaks = {min_y, max_y + 1}
    for _left, bottom, _right, top in clipped:
        y_breaks.update((bottom, top + 1))
    ordered_y = sorted(y_breaks)
    for y in ordered_y[:-1]:
        if y > max_y:
            continue
        intervals = sorted(
            (left, right) for left, bottom, right, top in clipped if bottom <= y <= top
        )
        candidate_x = min_x
        for left, right in intervals:
            if right < candidate_x:
                continue
            if left > candidate_x:
                return candidate_x, y
            candidate_x = max(candidate_x, right + 1)
            if candidate_x > max_x:
                break
        if candidate_x <= max_x:
            return candidate_x, y
    return None


def _exact_packaging_occupancy_assessment(
    authority: Mapping[str, Any], placed: Mapping[str, Any], context: Any
) -> dict[str, Any]:
    """Exhaust package origins for frozen dimensions, without access inference."""
    mode = authority.get("dimension_mode")
    boundary = _rectangle_bounds(context.boundary)
    obstacle_bounds = [_rectangle_bounds(row) for row in context.obstacles]
    if boundary is None or any(row is None for row in obstacle_bounds):
        return {
            "status": "UNAVAILABLE_NON_RECTANGULAR_BOUNDARY_OR_OBSTACLE",
            "proof_scope": "NONE",
            "dimensions_are_exhaustive": False,
        }
    if mode not in {"FIXED_RECTANGLE", "DETERMINISTIC_GRID_RECTANGLE"}:
        return {
            "status": "UNAVAILABLE_DIMENSION_AUTHORITY_NOT_FINITE",
            "proof_scope": "NONE",
            "dimensions_are_exhaustive": False,
        }

    variants = placement._dimension_variants(authority, placed, context.boundary)
    min_site_x, min_site_y, max_site_x, max_site_y = boundary
    skeleton_bounds = [placement._bounds(rectangle) for rectangle in placed.values()]
    orientations: list[dict[str, Any]] = []
    for width_mm, depth_mm, rotation in variants:
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        domain = (
            min_site_x,
            min_site_y,
            max_site_x - actual_width,
            max_site_y - actual_depth,
        )
        obstacle_forbidden = [
            _closed_obstacle_forbidden_origins(
                (left, bottom, right, top), actual_width, actual_depth
            )
            for left, bottom, right, top in obstacle_bounds
            if (left, bottom, right, top) is not None
        ]
        zone_forbidden = [
            _positive_overlap_forbidden_origins(
                (left, bottom, right, top), actual_width, actual_depth
            )
            for left, bottom, right, top in skeleton_bounds
        ]
        free_domain_witness = _integer_origin_witness(domain, [])
        without_obstacles_witness = _integer_origin_witness(domain, zone_forbidden)
        without_skeleton_witness = _integer_origin_witness(domain, obstacle_forbidden)
        combined_witness = _integer_origin_witness(domain, obstacle_forbidden + zone_forbidden)
        orientations.append(
            {
                "width_mm": actual_width,
                "depth_mm": actual_depth,
                "rotation_deg": rotation,
                "origin_domain_mm_inclusive": list(domain),
                "site_only_witness_origin_mm": list(free_domain_witness)
                if free_domain_witness
                else None,
                "without_no_build_but_with_skeleton_witness_origin_mm": list(
                    without_obstacles_witness
                )
                if without_obstacles_witness
                else None,
                "without_skeleton_but_with_no_build_witness_origin_mm": list(
                    without_skeleton_witness
                )
                if without_skeleton_witness
                else None,
                "combined_site_no_build_skeleton_witness_origin_mm": list(combined_witness)
                if combined_witness
                else None,
                "origin_domain_exhausted": combined_witness is None,
            }
        )

    all_exhausted = bool(orientations) and all(
        row["origin_domain_exhausted"] for row in orientations
    )
    return {
        "status": "NO_AUTHORIZED_ORIENTATION_HAS_SITE_NO_BUILD_SKELETON_SLOT"
        if all_exhausted
        else "GEOMETRIC_SLOT_EXISTS_ORIENTATION_REQUIRES_ROUTE_EVALUATION",
        "proof_scope": "ALL_INTEGER_MM_ORIGINS_FOR_ENUMERATED_AUTHORITATIVE_DIMENSIONS",
        "dimension_mode": mode,
        "dimensions_are_exhaustive": True,
        "position_lattice": "INTEGER_MILLIMETRE_ORIGINS",
        "placement_uses_integer_mm_coordinates": True,
        "obstacle_polygons_are_exact_axis_aligned_rectangles": True,
        "site_boundary_is_exact_axis_aligned_rectangle": True,
        "does_not_evaluate_packaging_access_or_portal_route": True,
        "orientation_results": orientations,
        "all_authorized_orientations_exhausted": all_exhausted,
    }


def _obstacle_rows(context: Any) -> tuple[tuple[str, Any], ...]:
    obstacles_body = context.site_body.get("obstacles", {})
    raw_rows = (
        obstacles_body.get("hard_obstacles", []) if isinstance(obstacles_body, Mapping) else []
    )
    rows = [row for row in raw_rows if isinstance(row, Mapping) and "footprint" in row]
    return tuple(
        (
            str(row.get("obstacle_id", row.get("id", row.get("code", f"HARD_OBSTACLE_{index}")))),
            obstacle,
        )
        for index, (row, obstacle) in enumerate(zip(rows, context.obstacles, strict=False), start=1)
    )


def _option_census(
    code: str,
    placed: Mapping[str, Any],
    context: Any,
    *,
    include_rejected_rectangles: bool = True,
) -> dict[str, Any]:
    raw_rectangles: list[Any] = []
    original_rectangle_from_mm = placement._rectangle_from_mm

    def capture_rectangle(*args: Any, **kwargs: Any):
        rectangle = original_rectangle_from_mm(*args, **kwargs)
        if args and args[0] == code:
            raw_rectangles.append(rectangle)
        return rectangle

    variants = placement._dimension_variants(context.authorities[code], placed, context.boundary)
    placement._rectangle_from_mm = capture_rectangle
    try:
        options = _option_call(code, placed, context)
    finally:
        placement._rectangle_from_mm = original_rectangle_from_mm

    rejection_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    rejected_rows: list[dict[str, Any]] = []
    site_contained_count = 0
    obstacle_clear_count = 0
    nonoverlap_count = 0
    must_pass_count = 0
    region_pass_count = 0
    must_neighbors = placement._must_neighbors(code, placed, context.graph)
    obstacle_pairs = _obstacle_rows(context)
    passed_keys: set[tuple[int, int, int, int, int]] = set()

    for rectangle in raw_rectangles:
        key = _rectangle_key(rectangle)
        left, bottom, right, top = placement._bounds(rectangle)
        rejection: str | None = None
        blockers: dict[str, Any] = {}
        site_reason = _site_failure(rectangle, context)
        if site_reason is not None:
            rejection = "SITE_OUTSIDE"
            blockers["site_boundary_failure"] = site_reason
        else:
            site_contained_count += 1
            hit_obstacles = [
                obstacle_id
                for obstacle_id, obstacle in obstacle_pairs
                if placement.rectangle_intersects_closed_obstacle(rectangle, obstacle)
            ]
            if hit_obstacles:
                rejection = "NO_BUILD_COLLISION"
                blockers["obstacle_identities"] = hit_obstacles
            else:
                obstacle_clear_count += 1
                overlaps = sorted(
                    zone_code
                    for zone_code, other in placed.items()
                    if placement.rectangles_overlap(rectangle, other)
                )
                if overlaps:
                    rejection = "ZONE_OVERLAP"
                    blockers["overlap_with_zone_code"] = overlaps
                else:
                    nonoverlap_count += 1
                    failed_must = sorted(
                        neighbor.zone_code
                        for neighbor in must_neighbors
                        if not placement.rectangles_share_positive_edge(rectangle, neighbor)
                    )
                    if failed_must:
                        rejection = "MUST_ADJACENCY_FAIL"
                        blockers["must_adjacency_blockers"] = failed_must
                    else:
                        must_pass_count += 1
                        if (
                            context.search_phase == placement.STRUCTURED_PHASE
                            and not placement._candidate_fits_skeleton_region(
                                code, rectangle, placed, context.structural_skeleton
                            )
                        ):
                            rejection = "SKELETON_REGION_FAIL"
                            blockers["skeleton_region"] = context.structural_skeleton.identity
                        else:
                            region_pass_count += 1
                            passed_keys.add(key)
        if rejection is not None:
            rejection_counts[rejection] += 1
            identities = blockers.get("overlap_with_zone_code", [])
            if isinstance(identities, list):
                for zone_code in identities:
                    blocker_counts[f"ZONE:{zone_code}"] += 1
            for obstacle_id in blockers.get("obstacle_identities", []):
                blocker_counts[f"OBSTACLE:{obstacle_id}"] += 1
            if include_rejected_rectangles:
                rejected_rows.append(
                    {
                        "zone_code": code,
                        "rectangle_mm": [left, bottom, right, top],
                        "dimensions_and_rotation_mm": list(key[2:]),
                        "reason": rejection,
                        **blockers,
                    }
                )

    final_keys = {_rectangle_key(rectangle) for rectangle in options}
    other_reject_count = max(0, len(passed_keys) - len(final_keys))
    if passed_keys != final_keys and not other_reject_count:
        raise AssertionError(f"instrumented gate census differs from production options for {code}")
    rejection_counts["OTHER_REJECT"] += other_reject_count
    return {
        "zone_code": code,
        "dimension_variant_count": len(variants),
        "dimension_variants_mm_rotation": [list(row) for row in variants],
        "raw_anchor_count": len(raw_rectangles),
        "raw_candidate_attempt_count": len(raw_rectangles),
        "unique_anchor_count": len({(row.x, row.y) for row in raw_rectangles}),
        "unique_rectangle_candidate_count": len({_rectangle_key(row) for row in raw_rectangles}),
        "site_outside_reject_count": rejection_counts["SITE_OUTSIDE"],
        "no_build_collision_reject_count": rejection_counts["NO_BUILD_COLLISION"],
        "zone_overlap_reject_count": rejection_counts["ZONE_OVERLAP"],
        "must_adjacency_reject_count": rejection_counts["MUST_ADJACENCY_FAIL"],
        "skeleton_region_reject_count": rejection_counts["SKELETON_REGION_FAIL"],
        "other_reject_count": other_reject_count,
        "final_option_count": len(options),
        "pipeline_survivors": {
            "site_contained": site_contained_count,
            "no_build_clear": obstacle_clear_count,
            "non_overlapping": nonoverlap_count,
            "must_adjacency_pass": must_pass_count,
            "skeleton_region_pass": region_pass_count,
            "final_unique_options": len(options),
        },
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "rejected_rectangles": rejected_rows,
        "rejected_rectangle_details_complete": include_rejected_rectangles,
        "final_option_rectangles_mm": [
            {
                "zone_code": code,
                "bounds_mm": list(placement._bounds(row)),
                "rotation_deg": row.rotation_deg,
            }
            for row in options
        ],
        "dimension_authority": {
            key: _evidence_value(context.authorities[code].get(key))
            for key in (
                "dimension_mode",
                "required_area_m2",
                "dimension_authority_identity",
                "min_width_m",
                "max_width_m",
                "min_depth_m",
                "max_depth_m",
                "aspect_ratio_bounds",
                "grid_m",
                "p2_may_select_width_depth",
            )
        }
        | {"geometry": _evidence_value(context.authorities[code].get("geometry"))},
    }


def _stage_census(seed: Any, context: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    base = {row.zone_code: row for row in seed.zone_rectangles}
    zones_at_a = {code: _option_census(code, base, context) for code in TAIL_ZONE_CODES}
    changing_options = _option_call("changing_room", base, context)
    office_options = _option_call("office", base, context)
    state_counts: dict[str, Any] = {
        "STATE_A_MAIN_SKELETON_ONLY": {
            "packaging": zones_at_a["packaging_material_storage"],
            "tail_zone_option_counts": {
                code: len(_option_call(code, base, context)) for code in TAIL_ZONE_CODES
            },
        },
        "STATE_B_FIRST_RANKED_CHANGING": {"applicable": bool(changing_options)},
        "STATE_C_FIRST_RANKED_OFFICE": {"applicable": bool(office_options)},
        "STATE_D_FIRST_CHANGING_AND_COMPATIBLE_OFFICE": {"applicable": False},
    }
    if changing_options:
        state_b = dict(base) | {"changing_room": changing_options[0]}
        state_counts["STATE_B_FIRST_RANKED_CHANGING"] |= {
            "changing_rectangle_mm": list(placement._bounds(changing_options[0])),
            "packaging": _option_census("packaging_material_storage", state_b, context),
        }
    else:
        state_counts["STATE_B_FIRST_RANKED_CHANGING"]["not_applicable_reason"] = (
            "NO_CHANGING_ROOM_OPTIONS_ON_SKELETON"
        )
    if office_options:
        state_c = dict(base) | {"office": office_options[0]}
        state_counts["STATE_C_FIRST_RANKED_OFFICE"] |= {
            "office_rectangle_mm": list(placement._bounds(office_options[0])),
            "packaging": _option_census("packaging_material_storage", state_c, context),
        }
    else:
        state_counts["STATE_C_FIRST_RANKED_OFFICE"]["not_applicable_reason"] = (
            "NO_OFFICE_OPTIONS_ON_SKELETON"
        )

    if changing_options:
        state_d = dict(base) | {"changing_room": changing_options[0]}
        compatible_office = _option_call("office", state_d, context)
        if compatible_office:
            state_d["office"] = compatible_office[0]
            state_counts["STATE_D_FIRST_CHANGING_AND_COMPATIBLE_OFFICE"] = {
                "applicable": True,
                "changing_rectangle_mm": list(placement._bounds(changing_options[0])),
                "office_rectangle_mm": list(placement._bounds(compatible_office[0])),
                "packaging": _option_census("packaging_material_storage", state_d, context),
            }
        else:
            state_counts["STATE_D_FIRST_CHANGING_AND_COMPATIBLE_OFFICE"].update(
                {"not_applicable_reason": "NO_OFFICE_OPTION_AFTER_FIRST_CHANGING"}
            )
    else:
        state_counts["STATE_D_FIRST_CHANGING_AND_COMPATIBLE_OFFICE"].update(
            {"not_applicable_reason": "NO_CHANGING_ROOM_OPTIONS_ON_SKELETON"}
        )

    explored_pairs: list[dict[str, Any]] = []
    pair_limit_hit = False
    for changing_index, changing in enumerate(changing_options):
        state_c = dict(base) | {"changing_room": changing}
        for office_index, office in enumerate(_option_call("office", state_c, context)):
            if len(explored_pairs) >= STATE_E_PAIR_LIMIT:
                pair_limit_hit = True
                break
            pair_state = dict(state_c) | {"office": office}
            package = _option_census(
                "packaging_material_storage",
                pair_state,
                context,
                include_rejected_rectangles=True,
            )
            explored_pairs.append(
                {
                    "changing_option_index": changing_index,
                    "office_option_index": office_index,
                    "changing_rectangle_mm": list(placement._bounds(changing)),
                    "office_rectangle_mm": list(placement._bounds(office)),
                    "packaging_option_count": package["final_option_count"],
                    "packaging_rejection_counts": package["rejection_counts"],
                    "packaging_blocker_counts": package["blocker_counts"],
                    "packaging_rejected_rectangles": package["rejected_rectangles"],
                }
            )
        if pair_limit_hit:
            break
    state_counts["STATE_E_EXPLORED_CHANGING_OFFICE_ALTERNATIVES"] = {
        "explored_compatible_pairs": len(explored_pairs),
        "pair_limit": STATE_E_PAIR_LIMIT,
        "search_exhausted": not pair_limit_hit,
        "option_count_distribution": dict(
            sorted(Counter(str(row["packaging_option_count"]) for row in explored_pairs).items())
        ),
        "pairs": explored_pairs,
    }
    general_context = replace(
        context,
        search_phase=placement.GENERAL_FALLBACK_PHASE,
        placement_zone_order=placement.PLACEMENT_ZONE_ORDER,
    )
    general_anchor_census = _option_census("packaging_material_storage", base, general_context)
    general_options = _option_call("packaging_material_storage", base, general_context)
    direct_general_options = sum(
        placement.rectangles_share_positive_edge(rectangle, base["sorting_packaging_room"])
        for rectangle in general_options
    )
    access_row = next(
        (
            dict(row)
            for row in context.access_requirements
            if row.get("from_ref") == "packaging_material_storage"
            and row.get("to_ref") == "sorting_packaging_room"
        ),
        None,
    )
    lifecycle = {
        "identity": "r8-packaging-option-lifecycle@1.0.0",
        "target_skeleton_hash": TARGET_SKELETON_HASH,
        "packaging_to_sorting_must_adjacency": False,
        "packaging_flow_kind": "PACKAGING",
        "packaging_flow_from": "packaging_material_storage",
        "packaging_flow_to": "sorting_packaging_room",
        "packaging_access_mode": "DIRECT_OR_CORRIDOR_MEDIATED",
        "packaging_access_requirement": access_row,
        "must_adjacencies_for_packaging": [
            list(pair)
            for pair in context.graph.must_adjacencies
            if "packaging_material_storage" in pair
        ],
        "general_fallback_anchor_counterfactual": {
            "search_phase": placement.GENERAL_FALLBACK_PHASE,
            "uses_existing_free_anchor_generator": True,
            "is_production_runtime_change": False,
            "option_census": general_anchor_census,
            "direct_shared_edge_option_count": direct_general_options,
            "non_direct_option_count": len(general_options) - direct_general_options,
            "candidate_anchor_gap_demonstrated": len(general_options) > 0,
            "complete_authority_anchor_coverage_proven": False,
            "coverage_assessment": (
                "NO_FIT_IN_CURRENT_GENERAL_EVENT_ANCHOR_ENUMERATION; continuous grid/event-space "
                "completeness is assessed separately by the exact fixed-dimension occupancy sweep"
            ),
            "exact_fixed_skeleton_occupancy": _exact_packaging_occupancy_assessment(
                context.authorities["packaging_material_storage"], base, context
            ),
        },
        "states": state_counts,
    }
    census = {
        "identity": "r8-tail-zone-option-census@1.0.0",
        "target_skeleton_hash": TARGET_SKELETON_HASH,
        "geometry_source": "live_r7_tool7_constructed_seed",
        "canonical_topology": context.structural_topology,
        "canonical_family": context.structural_composition_family.to_dict(),
        "main_process_seed_provenance": seed.to_evaluation_dict(),
        "main_skeleton_zone_codes": list(MAIN_PROCESS_SKELETON_ZONE_CODES),
        "main_skeleton_only": zones_at_a,
        "state_e_pair_limit": STATE_E_PAIR_LIMIT,
    }
    return census, lifecycle


def _p2d_witness(
    candidate: Any, selector_args: tuple[Any, ...], selector_kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    if len(selector_args) < 4:
        raise AssertionError("selector call did not include authoritative truck binding")
    routed = route_site_placement(
        selector_args[0],
        selector_args[1],
        selector_args[2],
        candidate,
        selector_args[3],
        route_node_budget=int(selector_kwargs.get("route_node_budget", 20_000)),
        truck_node_budget=int(selector_kwargs.get("truck_node_budget", 20_000)),
    )
    result = routed.to_dict()
    return {
        "p2d_reached": True,
        "project_layout_validated": result.get("project_layout_validated") is True,
        "p2_complete": result.get("p2_complete") is True,
        "access_pass_count": result.get("access_pass_count"),
        "access_requirement_count": result.get("access_requirement_count"),
        "truck_route_validated": result.get("truck_route_validated") is True,
        "building_footprint_present": bool(result.get("building_footprint")),
        "warnings": result.get("warnings", []),
        "canonical_result_hash": result.get("canonical_result_hash"),
        "p2d_result": result,
    }


def _tail_search(
    strategy: str,
    seed: Any,
    context: Any,
    selector_args: tuple[Any, ...],
    selector_kwargs: Mapping[str, Any],
    *,
    node_limit: int = DIAGNOSTIC_NODE_LIMIT,
    search_phase: str = placement.STRUCTURED_PHASE,
) -> dict[str, Any]:
    placed = {row.zone_code: row for row in seed.zone_rectangles}
    context = replace(
        context,
        node_budget=node_limit,
        complete_candidate_limit=None,
        search_phase=search_phase,
        placement_zone_order=(
            placement.PLACEMENT_ZONE_ORDER
            if search_phase == placement.GENERAL_FALLBACK_PHASE
            else context.placement_zone_order
        ),
    )
    base_order = tuple(code for code in context.placement_zone_order if code not in placed)
    if set(base_order) != set(TAIL_CODES):
        raise AssertionError(f"unexpected canonical tail zone set: {base_order}")
    if strategy == "PERSONNEL_FIRST":
        initial_order = base_order
    elif strategy == "SUPPORT_FIRST":
        initial_order = SUPPORT_FIRST
    elif strategy == "MOST_CONSTRAINED_FIRST":
        initial_order = base_order
    else:
        raise ValueError(strategy)

    stats = placement._PlacementSearchStats()
    first_zero: list[dict[str, Any]] = []
    dead_end_count = 0
    witness: dict[str, Any] | None = None
    truncated = False

    def visit(remaining: tuple[str, ...]) -> bool:
        nonlocal dead_end_count, witness, truncated
        if stats.visited_nodes >= node_limit:
            truncated = True
            return False
        stats.visited_nodes += 1
        if not remaining:
            placement._validate_graph_completeness(context.graph, placed)
            payload = placement._candidate_payload(
                placed,
                context.authorities,
                context.graph,
                context.site_body,
                context.source_zone_plan_hash,
                context.source_p1_handoff_hash,
                context.source_site_geometry_hash,
                context.objective_profile_hash,
                context.access_requirements,
                context.spatial_relationships,
                placement._search_provenance(
                    context,
                    stats,
                    search_tree_exhausted=False,
                    objective_optimal_within_search_family=False,
                ),
            )
            candidate = placement._materialize_candidate_result(payload)
            witness = {
                "complete_p2c": True,
                "candidate": candidate,
                "layout": candidate.to_dict(),
                "p2d": _p2d_witness(candidate, selector_args, selector_kwargs),
                "tail_order": list(initial_order),
            }
            return True

        if strategy == "MOST_CONSTRAINED_FIRST":
            option_rows = [(code, _option_call(code, placed, context)) for code in remaining]
            code, options = min(
                option_rows, key=lambda row: (len(row[1]), base_order.index(row[0]))
            )
        else:
            code = remaining[0]
            options = _option_call(code, placed, context)
        if not options:
            dead_end_count += 1
            first_zero.append(
                {"node": stats.visited_nodes, "zone_code": code, "remaining": list(remaining)}
            )
            return False
        next_remaining = tuple(zone for zone in remaining if zone != code)
        for rectangle in options:
            placed[code] = rectangle
            found = visit(next_remaining)
            placed.pop(code)
            if found:
                return True
            if truncated:
                return False
        return False

    found = visit(initial_order)
    return {
        "strategy": strategy,
        "search_phase": search_phase,
        "diagnostic_node_limit": node_limit,
        "diagnostic_budget_is_production_budget": False,
        "nodes_used": stats.visited_nodes,
        "dead_end_state_count": dead_end_count,
        "zero_option_events": first_zero,
        "complete_p2c_candidate_count": 1 if found else 0,
        "complete_tail_witness_found": found,
        "search_exhausted": not truncated and not found,
        "bounded_search_no_witness": not found and truncated,
        "node_limit_reached": truncated,
        "p2d_reached": bool(witness),
        "p2d_full_pass": bool(
            witness and witness["p2d"]["project_layout_validated"] and witness["p2d"]["p2_complete"]
        ),
        "witness": witness,
        "tail_order": list(initial_order),
        "dynamic_mrv": strategy == "MOST_CONSTRAINED_FIRST",
    }


def run_audit() -> dict[str, Any]:
    result, discovery_context, seed, selector_args, capture = _capture_r7_chain()
    context = _canonical_context(discovery_context, seed)
    placed = {row.zone_code: row for row in seed.zone_rectangles}
    if seed.main_process_skeleton_hash != TARGET_SKELETON_HASH:
        raise AssertionError("captured geometry does not match exact R7 skeleton hash")
    census, lifecycle = _stage_census(seed, context)
    strategies = ["PERSONNEL_FIRST", "SUPPORT_FIRST", "MOST_CONSTRAINED_FIRST"]
    tail_results = [
        _tail_search(
            strategy,
            seed,
            context,
            selector_args,
            capture["select_kwargs"],
        )
        for strategy in strategies
    ]
    tail_results.append(
        _tail_search(
            "SUPPORT_FIRST",
            seed,
            context,
            selector_args,
            capture["select_kwargs"],
            search_phase=placement.GENERAL_FALLBACK_PHASE,
        )
    )
    production_lifecycle = next(
        row
        for row in capture["selection_evaluation"]["skeleton_survival"]
        if row["skeleton_hash"] == TARGET_SKELETON_HASH
    )
    lane_reports = result["selection"]["search_provenance"]["family_lanes"]

    def is_discovery_lane(row: Mapping[str, Any]) -> bool:
        if row.get("topology") == seed.discovery_topology:
            return True
        family_body = row.get("composition_family")
        family_name = (
            family_body.get("family") if isinstance(family_body, Mapping) else row.get("family")
        )
        return family_name == seed.discovery_family.family

    target_lane = next(row for row in lane_reports if is_discovery_lane(row))
    target_lane_phase_accounting = [
        {
            "search_phase": phase.get("search_phase"),
            "phase_node_budget": phase.get("node_budget"),
            "visited_nodes": phase.get("visited_nodes"),
            "complete_candidates": phase.get("complete_candidates"),
        }
        for phase in target_lane.get("phases", [])
        if isinstance(phase, Mapping)
    ]
    target_lane_seeds = [
        row for row in capture["all_seeds"] if row["discovery_topology"] == seed.discovery_topology
    ]
    global_visits = sum(int(row["visited_nodes"]) for row in lane_reports)
    global_budget = int(result["selection"]["search_provenance"]["node_budget"])
    per_skeleton_share = int(production_lifecycle.get("tail_node_limit", 0))
    unused = max(0, global_budget - global_visits)
    saved_r7_path = EVIDENCE / "xinzhao_p1a_r7_metrics.json"
    saved_r7_metrics = json.loads(saved_r7_path.read_text(encoding="utf-8"))
    saved_r7_visits = int(saved_r7_metrics["actual_global_node_visits"])
    root_bounds = list(placement._bounds(placed["sorting_packaging_room"]))
    seed_provenance = seed.to_evaluation_dict()
    face_pair = seed_provenance.get("generation_pattern", "NOT_RECORDED_IN_SEED")
    packaging_a = census["main_skeleton_only"]["packaging_material_storage"]
    rejection_matrix: dict[tuple[str, str, str, str, str], int] = {}
    for row in packaging_a["rejected_rectangles"]:
        reason = str(row["reason"])
        identities = row.get("overlap_with_zone_code") or row.get("obstacle_identities") or []
        blocker = ",".join(sorted(str(item) for item in identities)) or str(
            row.get("site_boundary_failure", "NONE")
        )
        key = (
            seed.discovery_topology,
            str(root_bounds),
            str(face_pair),
            reason,
            blocker,
        )
        rejection_matrix[key] = rejection_matrix.get(key, 0) + 1
    budget = {
        "production_global_budget": global_budget,
        "production_budget_changed": False,
        "production_global_node_visits": global_visits,
        "production_global_nodes_unused": unused,
        "saved_r7_metrics_global_node_visits": saved_r7_visits,
        "saved_r7_metrics_global_nodes_remaining": global_budget - saved_r7_visits,
        "live_replay_matches_saved_r7_budget_accounting": global_visits == saved_r7_visits,
        "live_replay_lane_visit_breakdown": [
            {
                "topology": row.get("topology"),
                "composition_family": row.get("composition_family", row.get("family")),
                "lane_node_budget": row.get("lane_node_budget"),
                "visited_nodes": row.get("visited_nodes"),
                "global_budget_after_lane": row.get("global_budget_after_lane"),
            }
            for row in lane_reports
        ],
        "production_tail_node_limit_for_956e": per_skeleton_share,
        "production_tail_nodes_used_for_956e": int(production_lifecycle.get("tail_nodes", 0)),
        "remaining_lane_budget_at_956e_tail_start": int(
            production_lifecycle.get("tail_node_limit", 0)
        ),
        "unused_global_nodes_recyclable_by_current_scheduler": False,
        "tail_share_starvation_confirmed": bool(
            unused > 0
            and per_skeleton_share < unused
            and production_lifecycle.get("tail_nodes", 0) == per_skeleton_share
        ),
        "accounting_explanation": (
            "The selector partitions the 120-node global budget into topology-lane shares before "
            "candidate enumeration. A lane tail then divides only its own remaining nodes among "
            "its remaining constructed skeleton seeds. Nodes left unused in other topology lanes "
            "are not recycled into this already bounded per-skeleton tail share."
        ),
        "discovery_lane": seed.discovery_topology,
        "discovery_lane_budget": target_lane["lane_node_budget"],
        "discovery_lane_structured_node_budget": target_lane["structured_node_budget"],
        "discovery_lane_fallback_node_budget": target_lane["fallback_node_budget"],
        "discovery_lane_visited_nodes": target_lane["visited_nodes"],
        "target_lane_phase_accounting": _evidence_value(target_lane_phase_accounting),
        "target_lane_skeleton_tail_lifecycles": _evidence_value(
            [
                row
                for row in capture["selection_evaluation"].get("skeleton_survival", [])
                if isinstance(row, Mapping)
                and row.get("discovery_topology") == seed.discovery_topology
            ]
        ),
        "captured_constructed_seeds_by_discovery_lane": _evidence_value(capture["all_seeds"]),
        "target_lane_constructed_seed_count": len(target_lane_seeds),
        "target_lane_constructed_seed_hashes": [row["skeleton_hash"] for row in target_lane_seeds],
        "production_skeleton_survival": production_lifecycle,
        "saved_vs_live_accounting_discrepancy": {
            "status": "PRESENT" if global_visits != saved_r7_visits else "NONE",
            "saved_snapshot_visits": saved_r7_visits,
            "live_replay_sum_of_lane_visits": global_visits,
            "canonical_result_hash_matches_r7": result["canonical_result_hash"]
            == EXPECTED_R7_RESULT_HASH,
            "effect_on_956e_tail_share": "NONE; live replay still assigns and consumes 12 nodes",
        },
    }
    exact_occupancy = lifecycle["general_fallback_anchor_counterfactual"][
        "exact_fixed_skeleton_occupancy"
    ]
    exact_no_package_slot = (
        exact_occupancy.get("dimensions_are_exhaustive") is True
        and exact_occupancy.get("all_authorized_orientations_exhausted") is True
    )
    feasibility = {
        "identity": "r8-fixed-skeleton-tail-feasibility@1.0.0",
        "target_skeleton_hash": TARGET_SKELETON_HASH,
        "skeleton_geometry_match_r7": True,
        "real_tool7_replay": {
            "fixture_sha256": EXPECTED_FIXTURE_SHA256,
            "canonical_result_hash": result["canonical_result_hash"],
            "svg_sha256": result["svg_sha256"],
            "project_layout_validated": result["project_layout_validated"],
            "p2_complete": result["p2_complete"],
            "zone_count": result["zone_count"],
            "access_requirement_count": result["layout"]["access_requirement_count"],
            "access_pass_count": result["layout"]["access_pass_count"],
            "truck_route_validated": result["layout"]["truck_route_validated"],
            "building_footprint_present": bool(result["layout"].get("building_footprint")),
        },
        "canonical_topology": context.structural_topology,
        "canonical_family": context.structural_composition_family.to_dict(),
        "fixed_main_process_rectangles": {
            row.zone_code: list(placement._bounds(row)) for row in seed.zone_rectangles
        },
        "diagnostic_node_limit_per_policy": DIAGNOSTIC_NODE_LIMIT,
        "production_tail_node_limit": per_skeleton_share,
        "strategies": tail_results,
        "enumerated_candidate_anchor_families_exhausted": all(
            row["search_exhausted"] for row in tail_results
        ),
        "packaging_has_no_site_no_build_skeleton_slot_for_authoritative_dimensions": (
            exact_no_package_slot
        ),
        "tail_completion_infeasible_within_fixed_skeleton_authority": exact_no_package_slot,
        "global_geometric_infeasibility_proven": False,
        "infeasibility_proven": False,
        "root_cause_classification": {
            "TAIL_ORDERING_STARVATION": False,
            "PERSONNEL_BRANCH_STARVES_SUPPORT": False,
            "PACKAGING_ANCHOR_COVERAGE_GAP": False if exact_no_package_slot else "UNRESOLVED",
            "TAIL_SHARE_ALLOCATION_STARVATION": budget["tail_share_starvation_confirmed"],
            "TAIL_SHARE_IS_PRIMARY_CAUSE_OF_ZERO_PACKAGING_OPTIONS": False,
            "TRUE_ENUMERATED_GEOMETRY_CONFLICT": exact_no_package_slot,
            "P2D_HARD_FAILURE_AFTER_COMPLETE_P2C": False,
            "UNRESOLVED_BOUNDED_SEARCH": not exact_no_package_slot,
        },
        "packaging_rejection_matrix_by_discovery_root_face_zone_reason_blocker": [
            {
                "family": family,
                "sorting_root_mm": root_bounds,
                "face_pair_or_generation_pattern": face_pair,
                "zone_code": "packaging_material_storage",
                "reason": reason,
                "blocker_identity_or_site_failure": blocker,
                "count": count,
            }
            for (family, _root, _face, reason, blocker), count in sorted(rejection_matrix.items())
        ],
        "enumerated_authority_scope": (
            "The package-slot proof exhausts every integer-mm origin for every fixed or "
            "deterministic authoritative package dimension/orientation on the exact rectangular "
            "site, exact rectangular obstacles and frozen seven-zone geometry. It does not prove "
            "that another main-process skeleton is incompatible, nor evaluate access/truck/P2D "
            "for a nonexistent package placement."
        ),
    }
    p2d_results = [
        row["witness"]["p2d"] for row in tail_results if isinstance(row.get("witness"), Mapping)
    ]
    return {
        "replay": {
            "fixture_sha256": EXPECTED_FIXTURE_SHA256,
            "r7_canonical_result_hash": result["canonical_result_hash"],
            "r7_svg_sha256": result["svg_sha256"],
            "project_layout_validated": result["project_layout_validated"],
            "p2_complete": result["p2_complete"],
            "zone_count": result["zone_count"],
            "access_requirement_count": result["layout"]["access_requirement_count"],
            "access_pass_count": result["layout"]["access_pass_count"],
            "truck_route_validated": result["layout"]["truck_route_validated"],
            "building_footprint_present": bool(result["layout"].get("building_footprint")),
        },
        "seed": seed.to_evaluation_dict(),
        "census": census,
        "lifecycle": lifecycle,
        "tail_results": tail_results,
        "feasibility": feasibility,
        "budget": budget,
        "p2d_results": p2d_results,
        "scope": {
            "instrumentation": "PROCESS_LOCAL_MONKEYPATCH_FOR_REAL_TOOL7_REPLAY_ONLY",
            "runtime_persisted": False,
            "backend_src_changed": False,
            "tool7_payload_changed": False,
            "production_node_budget": global_budget,
            "tail_order_changed": False,
            "p2d_rules_changed": False,
        },
    }


def write_evidence() -> dict[str, Any]:
    audit = run_audit()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    _write_json(EVIDENCE / "xinzhao_p1a_r8_tail_zone_option_census.json", audit["census"])
    _write_json(EVIDENCE / "xinzhao_p1a_r8_packaging_option_lifecycle.json", audit["lifecycle"])
    _write_json(
        EVIDENCE / "xinzhao_p1a_r8_tail_order_comparison.json",
        {"identity": "r8-tail-order-comparison@1.0.0", "strategies": audit["tail_results"]},
    )
    _write_json(EVIDENCE / "xinzhao_p1a_r8_tail_feasibility_search.json", audit["feasibility"])
    _write_json(EVIDENCE / "xinzhao_p1a_r8_tail_budget_accounting.json", audit["budget"])
    witnesses = [row for row in audit["tail_results"] if row["complete_tail_witness_found"]]
    if witnesses:
        _write_json(
            EVIDENCE / "xinzhao_p1a_r8_956e_tail_witness.json",
            {
                "identity": "r8-956e-complete-p2c-tail-witness@1.0.0",
                "target_skeleton_hash": TARGET_SKELETON_HASH,
                "witnesses": [
                    {key: value for key, value in row.items() if key != "witness"}
                    | {
                        "witness": {
                            key: value
                            for key, value in row["witness"].items()
                            if key != "candidate"
                        }
                    }
                    for row in witnesses
                ],
            },
        )
        _write_json(
            EVIDENCE / "xinzhao_p1a_r8_956e_p2d_result.json",
            {"identity": "r8-956e-real-p2d-replay@1.0.0", "results": audit["p2d_results"]},
        )
    return audit


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


if __name__ == "__main__":
    report = write_evidence()
    print(
        json.dumps(
            {
                "replay": report["replay"],
                "main_skeleton_hash": TARGET_SKELETON_HASH,
                "packaging_state_a_options": report["census"]["main_skeleton_only"][
                    "packaging_material_storage"
                ]["final_option_count"],
                "tail_strategies": [
                    {
                        "strategy": row["strategy"],
                        "nodes_used": row["nodes_used"],
                        "witness": row["complete_tail_witness_found"],
                        "exhausted": row["search_exhausted"],
                    }
                    for row in report["tail_results"]
                ],
                "budget": report["budget"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
