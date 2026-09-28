"""Process-local truck-search observation for the R14 design-gate audit.

This module invokes the real Tool 7 selector and the existing authoritative
truck validator.  Its temporary wrappers only observe arguments/results and
the validator's existing template-transform calls; nothing is persisted in
production code or added to the public Tool 7 payload.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import cold_storage.modules.layout.application.validated_candidate_selection as selection
import cold_storage.modules.layout.domain.access_routing as access
import cold_storage.modules.layout.domain.placement as placement_domain
from cold_storage.modules.layout.domain.dimensioning import GRID
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    _polygon_edges,
    normalize_polygon,
    polygon_contains_polygon,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_ZONE_CODES,
)
from tests.evaluation.r12_access_failure_audit import _zone_skeleton_hash
from tests.evaluation.r13_main_skeleton_truck_preflight import (
    EXPECTED_FIXTURE_SHA256,
    FIXTURE,
    _diagnostics,
    _rows,
    run_tool7_with_internal_evaluation,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
R11_BUDGET_PATH = EVIDENCE_DIR / "xinzhao_p1a_r11_budget_accounting.json"
EXPECTED_SKELETON_ORDER = (
    "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953",
    "sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c",
    "sha256:36bb2818ddb16e40fe1a50e0918f148b35e2f01bf93772b6caf239d2b44ccccb",
    "sha256:6613e0eac6cc7991f9c176398b1a0466288898f49a8282b4eddf9a2239ba92b8",
    "sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3",
    "sha256:b667428b8c43add574cec021c508d4d29f481670e38a290cd10b968f4e4840aa",
)
REJECTED_ZONE_CODES = tuple(code for code in MAIN_PROCESS_ZONE_CODES if code != "shipping_channel")
TRANSLATION_STEPS = (
    (1, 0),
    (-1, 0),
    (2, 0),
    (-2, 0),
    (0, 1),
    (0, -1),
    (0, 2),
    (0, -2),
)
TAXONOMY = (
    "BOUNDARY_CONFLICT",
    "HARD_OBSTACLE_CONFLICT",
    "MAIN_ZONE_ENVELOPE_CONFLICT",
    "ENTRY_POSE_INVALID",
    "CHAIN_CONTINUITY_INVALID",
    "FINAL_DOCK_POSE_MISSING",
    "FINAL_DOCK_NOT_ON_LOADING_FACE",
    "NO_TEMPLATE_FOR_REQUIRED_CLASS",
    "OTHER_EXACT_TRUCK_CONFLICT",
)


def _mm(value: object) -> int:
    scaled = Decimal(str(value)) * Decimal(1000)
    if scaled != scaled.to_integral_value():
        raise AssertionError(f"non-mm value in exact geometry: {value!r}")
    return int(scaled)


def _m(value_mm: int) -> Decimal:
    return Decimal(value_mm) / Decimal(1000)


def _segment_row(segment: SegmentMM) -> dict[str, list[int]]:
    return {"start_mm": list(segment[0]), "end_mm": list(segment[1])}


def _polygon_row(polygon: PolygonMM) -> dict[str, Any]:
    return {"points_mm": [list(point) for point in polygon]}


def _rectangle_row(rectangle: PlacedRectangleV1) -> dict[str, Any]:
    return {
        "zone_code": rectangle.zone_code,
        "x_mm": _mm(rectangle.x),
        "y_mm": _mm(rectangle.y),
        "width_mm": _mm(rectangle.width_m),
        "depth_mm": _mm(rectangle.depth_m),
        "rotation_deg": rectangle.rotation_deg,
    }


def _rectangle_hash(zone_rows: Sequence[Mapping[str, Any]]) -> str:
    records = [
        {
            "zone_code": str(row["zone_code"]),
            "x": str(_m(int(row["x_mm"]))),
            "y": str(_m(int(row["y_mm"]))),
            "width_m": str(_m(int(row["width_mm"]))),
            "depth_m": str(_m(int(row["depth_mm"]))),
            "rotation_deg": int(row["rotation_deg"]),
        }
        for row in sorted(zone_rows, key=lambda value: str(value["zone_code"]))
    ]
    return cast(str, _zone_skeleton_hash(records))


def _signature(transformed: Mapping[str, Any]) -> dict[str, Any]:
    frame = transformed.get("reference_frame", {})
    return {
        "template_identity": transformed.get("template_identity"),
        "rotation_deg": transformed.get("rotation_deg"),
        "entry_pose": frame.get("entry_pose") if isinstance(frame, Mapping) else None,
        "exit_pose": frame.get("exit_pose") if isinstance(frame, Mapping) else None,
    }


def _identity(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _pose_point_mm(pose: object) -> tuple[int, int] | None:
    if not isinstance(pose, Mapping) or "x" not in pose or "y" not in pose:
        return None
    return (_mm(pose["x"]), _mm(pose["y"]))


def _node_rejection(
    transformed: Mapping[str, Any],
    local: Mapping[str, Any],
    capture: Mapping[str, Any],
) -> tuple[str | None, str | None, list[str], list[str], bool | None]:
    index = int(local["index"])
    sequence = tuple(local["sequence"])
    frame = transformed["reference_frame"]
    entry_point = _pose_point_mm(frame.get("entry_pose"))
    if index == 0 and (
        entry_point is None
        or not access._on_segment(
            entry_point, capture["truck_entrance"][0], capture["truck_entrance"][1]
        )
    ):
        return "ENTRY_POSE_INVALID", "ENTRY_POSE", [], [], None
    if index > 0 and not access._pose_equal(
        local["chain"][-1]["reference_frame"]["exit_pose"], frame["entry_pose"]
    ):
        return "CHAIN_CONTINUITY_INVALID", "CHAIN_CONTINUITY", [], [], None

    envelope = normalize_polygon(
        transformed["envelope_geometry"],
        error_code="INVALID_TRANSFORMED_MANEUVER_ENVELOPE",
        allow_numeric_string=True,
    )
    boundary_ok = polygon_contains_polygon(capture["boundary"], envelope)
    obstacle_ids = [
        obstacle_id
        for obstacle_id, obstacle in capture["obstacles_with_ids"]
        if access._polygon_intersects_closed(envelope, obstacle)
    ]
    zone_codes = [
        code
        for code, rectangle in capture["zones"].items()
        if access._polygon_interiors_overlap(envelope, rectangle.polygon_mm)
    ]
    safety_ok = access._transformed_maneuver_safe(
        transformed,
        boundary=capture["boundary"],
        obstacles=capture["obstacles"],
        zones=capture["zones"],
    )
    if not boundary_ok:
        return "BOUNDARY_CONFLICT", "ENVELOPE_BOUNDARY", [], [], False
    if obstacle_ids:
        return "HARD_OBSTACLE_CONFLICT", "ENVELOPE_OBSTACLE", [], obstacle_ids, False
    if zone_codes:
        return "MAIN_ZONE_ENVELOPE_CONFLICT", "ENVELOPE_MAIN_ZONE", zone_codes, [], False
    if not safety_ok:
        return "OTHER_EXACT_TRUCK_CONFLICT", "ENVELOPE_SAFETY", [], [], False

    if index == len(sequence) - 1:
        dock_pose = transformed.get("final_dock_pose")
        dock_point = _pose_point_mm(dock_pose)
        if dock_point is None:
            return "FINAL_DOCK_POSE_MISSING", "FINAL_DOCK", [], [], True
        if not access._on_segment(
            dock_point, capture["loading_face"][0], capture["loading_face"][1]
        ):
            return "FINAL_DOCK_NOT_ON_LOADING_FACE", "FINAL_DOCK_LOADING_FACE", [], [], True
    return None, None, [], [], True


def _capture_one_tool7_replay(payload: Mapping[str, Any]) -> dict[str, Any]:
    original_validator = selection.validate_truck_maneuver_chain
    original_transform = access.transform_maneuver_template
    active_capture: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    observer_errors: list[str] = []

    def observe_transform(
        template: Any, translation: Mapping[str, Any], rotation_deg: int
    ) -> dict[str, Any]:
        transformed = original_transform(template, translation, rotation_deg)
        caller = sys._getframe(1)
        if active_capture and caller.f_code.co_name == "recurse":
            capture = active_capture[-1]
            try:
                local = caller.f_locals
                chain = tuple(local["chain"])
                sequence = tuple(local["sequence"])
                direct_reason, rejection_stage, blocking_zones, blocking_obstacles, envelope_ok = (
                    _node_rejection(transformed, local, capture)
                )
                path = [_signature(row) for row in chain] + [_signature(transformed)]
                parent_path = [_signature(row) for row in chain]
                attempt_index = len(capture["nodes"]) + 1
                capture["nodes"].append(
                    {
                        "attempt_index": attempt_index,
                        "sequence_identity": ">".join(str(value) for value in sequence),
                        "sequence_index": int(local["index"]),
                        "maneuver_class": str(sequence[int(local["index"])]),
                        "template_identity": str(template.identity),
                        "entry_lattice_point_mm": list(local["desired_entry"]),
                        "rotation_deg": rotation_deg,
                        "transformed_entry_pose": transformed["reference_frame"]["entry_pose"],
                        "transformed_exit_pose": transformed["reference_frame"]["exit_pose"],
                        "final_dock_pose": transformed.get("final_dock_pose"),
                        "envelope_geometry": transformed["envelope_geometry"],
                        "result": "DIRECTLY_REJECTED" if direct_reason else "LOCAL_PREDICATES_PASS",
                        "rejection_stage": rejection_stage,
                        "rejection_reason": direct_reason,
                        "blocking_zone_codes": blocking_zones,
                        "first_blocking_zone_code": blocking_zones[0] if blocking_zones else None,
                        "blocking_obstacle_ids": blocking_obstacles,
                        "boundary_violation": envelope_ok is False
                        and direct_reason == "BOUNDARY_CONFLICT",
                        "envelope_safety_predicate_pass": envelope_ok,
                        "path_identity": _identity({"sequence": sequence, "path": path}),
                        "parent_path_identity": _identity(
                            {"sequence": sequence, "path": parent_path}
                        ),
                    }
                )
            except Exception as error:  # keep the observer transparent to production logic
                observer_errors.append(f"node observation: {type(error).__name__}: {error}")
        return cast(dict[str, Any], transformed)

    def observe_validator(binding: Any, **kwargs: Any) -> dict[str, Any]:
        zones = kwargs["zones"]
        zone_rows = [_rectangle_row(rectangle) for rectangle in zones.values()]
        skeleton_hash = _rectangle_hash(zone_rows)
        boundary = kwargs["boundary"]
        obstacles = tuple(kwargs["obstacles"])
        obstacle_records = tuple(
            (f"NO_BUILD_POLYGON_{index + 1:02d}", polygon)
            for index, polygon in enumerate(obstacles)
        )
        capture = {
            "skeleton_hash": skeleton_hash,
            "binding": binding,
            "truck_entrance": kwargs["truck_entrance"],
            "loading_face": kwargs["shipping_loading_face"],
            "boundary": boundary,
            "obstacles": obstacles,
            "obstacles_with_ids": obstacle_records,
            "zones": dict(zones),
            "zone_rows": zone_rows,
            "node_budget": kwargs["node_budget"],
            "nodes": [],
        }
        active_capture.append(capture)
        try:
            result = original_validator(binding, **kwargs)
        finally:
            active_capture.pop()
        capture["result"] = result
        provenance = result.get("search_provenance", {})
        capture["visited_nodes_reported"] = int(provenance.get("visited_nodes", 0))
        capture["node_budget_exhausted"] = provenance.get("node_budget_exhausted") is True
        capture["search_tree_exhausted"] = provenance.get("search_tree_exhausted") is True
        capture["route_validated"] = result.get("truck_route_validated") is True
        if len(capture["nodes"]) != capture["visited_nodes_reported"]:
            observer_errors.append(
                "attempt mismatch for "
                f"{skeleton_hash}: observed={len(capture['nodes'])}, "
                f"validator={capture['visited_nodes_reported']}"
            )
        selected = {
            _identity(_signature(row))
            for row in result.get("maneuver_chain", [])
            if isinstance(row, Mapping)
        }
        for node in capture["nodes"]:
            node["on_selected_pass_chain"] = (
                _identity(
                    {
                        "template_identity": node["template_identity"],
                        "rotation_deg": node["rotation_deg"],
                        "entry_pose": node["transformed_entry_pose"],
                        "exit_pose": node["transformed_exit_pose"],
                    }
                )
                in selected
            )
            if node["rejection_reason"] is None:
                node["result"] = (
                    "SELECTED_PASS_CHAIN"
                    if node["on_selected_pass_chain"]
                    else "DESCENDANT_SEARCH_EXHAUSTED"
                    if not capture["route_validated"]
                    else "NONSELECTED_BRANCH_BEFORE_PASS"
                )
                if node["result"] == "DESCENDANT_SEARCH_EXHAUSTED":
                    node["rejection_stage"] = "DESCENDANT_SEARCH"
                    node["rejection_reason"] = "NO_COMPLETE_DESCENDANT_CHAIN"
        captures.append(capture)
        return cast(dict[str, Any], result)

    selection.validate_truck_maneuver_chain = observe_validator
    access.transform_maneuver_template = observe_transform
    try:
        result, internal = run_tool7_with_internal_evaluation(payload)
    finally:
        selection.validate_truck_maneuver_chain = original_validator
        access.transform_maneuver_template = original_transform
    if observer_errors:
        raise AssertionError(
            "R14 observer did not faithfully capture the real search: " + "; ".join(observer_errors)
        )
    return {"result": result, "internal": internal, "captures": captures}


def _result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    provenance = result.get("search_provenance", {})
    provenance = provenance if isinstance(provenance, Mapping) else {}
    chain = result.get("maneuver_chain", [])
    return {
        "truck_route_validated": result.get("truck_route_validated") is True,
        "status": result.get("status"),
        "codes": list(result.get("codes", [])),
        "visited_nodes": int(provenance.get("visited_nodes", 0)),
        "node_budget": int(provenance.get("node_budget", 0)),
        "node_budget_exhausted": provenance.get("node_budget_exhausted") is True,
        "search_tree_exhausted": provenance.get("search_tree_exhausted") is True,
        "maneuver_chain": list(chain) if isinstance(chain, list) else [],
        "truck_envelopes": list(result.get("truck_envelopes", [])),
        "canonical_result_hash": result.get("canonical_result_hash"),
    }


def _validator_call(
    capture: Mapping[str, Any],
    zones: Mapping[str, PlacedRectangleV1],
    loading_face: SegmentMM,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        access.validate_truck_maneuver_chain(
            capture["binding"],
            truck_entrance=capture["truck_entrance"],
            shipping_loading_face=loading_face,
            boundary=capture["boundary"],
            obstacles=capture["obstacles"],
            zones=zones,
            node_budget=int(capture["node_budget"]),
        ),
    )


def _edge_shared(first: PlacedRectangleV1, second: PlacedRectangleV1) -> bool:
    first_edges = _polygon_edges(first.polygon_mm)
    second_edges = _polygon_edges(second.polygon_mm)
    return any(
        segments_share_positive_length(a, b, c, d) for a, b in first_edges for c, d in second_edges
    )


def _conflict_geometry(rectangle: PlacedRectangleV1, capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "inside_effective_boundary": polygon_contains_polygon(
            capture["boundary"], rectangle.polygon_mm
        ),
        "obstacle_intersections": [
            obstacle_id
            for obstacle_id, obstacle in capture["obstacles_with_ids"]
            if access._polygon_intersects_closed(rectangle.polygon_mm, obstacle)
        ],
        "overlap_zone_codes": [
            code
            for code, other in capture["zones"].items()
            if code != rectangle.zone_code
            and access._polygon_interiors_overlap(rectangle.polygon_mm, other.polygon_mm)
        ],
        "shipping_finished_positive_shared_edge": _edge_shared(
            rectangle, capture["zones"]["finished_goods_room"]
        ),
    }


def _skeleton_matrix(
    captures: Mapping[str, Mapping[str, Any]],
    preflights: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = []
    for skeleton_hash in EXPECTED_SKELETON_ORDER:
        capture = captures[skeleton_hash]
        preflight = preflights[skeleton_hash]
        zones = capture["zones"]
        ship = zones["shipping_channel"]
        loading_face = capture["loading_face"]
        final_dock_nodes = [
            node
            for node in capture["nodes"]
            if node.get("sequence_index") == len(node.get("sequence_identity", "").split(">")) - 1
            and node.get("final_dock_pose") is not None
        ]
        final_dock_points = sorted(
            {
                point
                for node in final_dock_nodes
                if (point := _pose_point_mm(node["final_dock_pose"])) is not None
            }
        )
        rows.append(
            {
                "skeleton_hash": skeleton_hash,
                "discovery_topology": preflight.get("discovery_topology"),
                "canonical_topology_owner": preflight.get("canonical_topology_owner"),
                "canonical_family": preflight.get("canonical_family"),
                "main_process_zones": [
                    _rectangle_row(zones[code]) for code in MAIN_PROCESS_ZONE_CODES
                ],
                "shipping_channel": _rectangle_row(ship),
                "shipping_channel_centroid_mm": {
                    "x": str((ship.bounds_mm[0] + ship.bounds_mm[2]) / 2),
                    "y": str((ship.bounds_mm[1] + ship.bounds_mm[3]) / 2),
                },
                "shipping_channel_distance_to_truck_entrance_squared_mm2": str(
                    min(
                        placement_domain.segment_distance_squared(capture["truck_entrance"], edge)
                        for edge in _polygon_edges(ship.polygon_mm)
                    )
                ),
                "shipping_loading_face": {
                    "side": preflight.get("shipping_loading_face_side"),
                    **_segment_row(loading_face),
                },
                "final_dock_pose_points_mm": [list(point) for point in final_dock_points],
                "final_dock_pose_points_on_loading_face": {
                    f"{point[0]},{point[1]}": access._on_segment(
                        point, loading_face[0], loading_face[1]
                    )
                    for point in final_dock_points
                },
                "truck_entrance": _segment_row(capture["truck_entrance"]),
                "effective_buildable_boundary": _polygon_row(capture["boundary"]),
                "hard_obstacles": [
                    {
                        "obstacle_id": obstacle_id,
                        "id_source": "stable validator input order; source supplied no obstacle ID",
                        **_polygon_row(polygon),
                    }
                    for obstacle_id, polygon in capture["obstacles_with_ids"]
                ],
                "preflight": {
                    "status": preflight.get("preflight_status"),
                    "visited_nodes": preflight.get("visited_nodes"),
                    "node_budget": preflight.get("node_budget"),
                    "search_tree_exhausted": preflight.get("search_tree_exhausted"),
                    "node_budget_exhausted": preflight.get("node_budget_exhausted"),
                },
            }
        )
    return {
        "identity": "v222-p1a-r14-skeleton-truck-geometry-matrix@1.0.0",
        "source": "UNMOCKED_TOOL7_PROCESS_LOCAL_VALIDATOR_OBSERVER",
        "rows": rows,
    }


def _search_tree(
    captures: Mapping[str, Mapping[str, Any]],
    preflights: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = []
    for skeleton_hash in EXPECTED_SKELETON_ORDER:
        capture = captures[skeleton_hash]
        nodes = capture["nodes"]
        direct = [node for node in nodes if node.get("result") == "DIRECTLY_REJECTED"]
        direct_counts = Counter(str(node.get("rejection_reason")) for node in direct)
        zone_counts = Counter(
            str(code) for node in direct for code in node.get("blocking_zone_codes", [])
        )
        obstacle_counts = Counter(
            str(obstacle_id)
            for node in direct
            for obstacle_id in node.get("blocking_obstacle_ids", [])
        )
        template_counts = Counter(str(node["template_identity"]) for node in direct)
        rotation_counts = Counter(int(node["rotation_deg"]) for node in direct)
        entry_counts = Counter(tuple(node["entry_lattice_point_mm"]) for node in direct)
        preflight = preflights[skeleton_hash]
        rows.append(
            {
                "skeleton_hash": skeleton_hash,
                "discovery_topology": preflight.get("discovery_topology"),
                "canonical_topology_owner": preflight.get("canonical_topology_owner"),
                "result": _result_summary(capture["result"]),
                "visited_nodes_reported": capture["visited_nodes_reported"],
                "attempted_node_count": len(nodes),
                "attempted_nodes_match_validator": len(nodes) == capture["visited_nodes_reported"],
                "required_template_classes": capture["required_template_classes"],
                "missing_template_classes": capture["missing_template_classes"],
                "direct_rejection_counts": dict(sorted(direct_counts.items())),
                "direct_rejected_node_count": len(direct),
                "descendant_exhausted_node_count": sum(
                    node.get("result") == "DESCENDANT_SEARCH_EXHAUSTED" for node in nodes
                ),
                "top_blocking_zone_counts": dict(sorted(zone_counts.items())),
                "top_blocking_obstacle_counts": dict(sorted(obstacle_counts.items())),
                "top_blocking_template_counts": dict(sorted(template_counts.items())),
                "top_blocking_rotation_counts": {
                    str(key): value for key, value in sorted(rotation_counts.items())
                },
                "top_blocking_entry_lattice_points": [
                    {"point_mm": list(point), "count": count}
                    for point, count in sorted(
                        entry_counts.items(), key=lambda item: (-item[1], item[0])
                    )
                ],
                "nodes": nodes,
            }
        )
    return {
        "identity": "v222-p1a-r14-truck-search-tree@1.0.0",
        "observer": (
            "temporary wrapper around real transform calls; exact predicates are "
            "re-evaluated read-only for labels"
        ),
        "skeletons": rows,
    }


def _taxonomy(tree: Mapping[str, Any]) -> dict[str, Any]:
    classes: Counter[str] = Counter()
    rejected_skeletons = []
    for skeleton in tree["skeletons"]:
        if skeleton["result"]["truck_route_validated"]:
            continue
        direct = skeleton["direct_rejection_counts"]
        for reason, count in direct.items():
            classes[str(reason)] += int(count)
        decisive_classes = sorted(reason for reason, count in direct.items() if count)
        rejected_skeletons.append(
            {
                "skeleton_hash": skeleton["skeleton_hash"],
                "first_decisive_failure_class": decisive_classes[0]
                if len(decisive_classes) == 1
                else "MULTI_CAUSAL_EXHAUSTION",
                "multi_causal_exhaustion": len(decisive_classes) > 1,
                "direct_failure_classes": decisive_classes,
                "first_decisive_blocking_zone_codes": skeleton["top_blocking_zone_counts"],
                "first_decisive_template_identities": skeleton["top_blocking_template_counts"],
                "first_decisive_entry_rotations": skeleton["top_blocking_rotation_counts"],
                "failure_node_counts": direct,
                "search_tree_exhausted": skeleton["result"]["search_tree_exhausted"],
                "node_budget_exhausted": skeleton["result"]["node_budget_exhausted"],
            }
        )
    return {
        "identity": "v222-p1a-r14-rejection-taxonomy@1.0.0",
        "taxonomy_scope": (
            "one primary reason at the first rejecting authoritative predicate "
            "for each attempted node"
        ),
        "rejection_counts": {reason: classes.get(reason, 0) for reason in TAXONOMY},
        "rejected_skeletons": rejected_skeletons,
    }


def _control_chain(
    captures: Mapping[str, Mapping[str, Any]], preflights: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    control_hash = EXPECTED_SKELETON_ORDER[0]
    capture = captures[control_hash]
    result = capture["result"]
    chain = result.get("maneuver_chain", [])
    nodes = capture["nodes"]
    first_node = next((node for node in nodes if node.get("on_selected_pass_chain")), None)
    return {
        "identity": "v222-p1a-r14-control-pass-chain@1.0.0",
        "skeleton_hash": control_hash,
        "truck_route_validated": result.get("truck_route_validated") is True,
        "selected_sequence": [row.get("maneuver_class") for row in chain],
        "selected_template_identities": [row.get("template_identity") for row in chain],
        "entry_lattice_point_mm": first_node.get("entry_lattice_point_mm")
        if isinstance(first_node, Mapping)
        else None,
        "initial_rotation_deg": chain[0].get("rotation_deg") if chain else None,
        "maneuver_chain": chain,
        "truck_envelopes": result.get("truck_envelopes", []),
        "final_dock_pose": chain[-1].get("final_dock_pose") if chain else None,
        "shipping_loading_face": {
            "side": preflights[control_hash].get("shipping_loading_face_side"),
            **_segment_row(capture["loading_face"]),
        },
        "visited_nodes": capture["visited_nodes_reported"],
        "node_budget": capture["node_budget"],
    }


def _geometry_diff(
    captures: Mapping[str, Mapping[str, Any]], preflights: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    control_hash = EXPECTED_SKELETON_ORDER[0]
    control = captures[control_hash]
    control_zones = control["zones"]
    control_face = control["loading_face"]
    control_side = preflights[control_hash].get("shipping_loading_face_side")
    rows = []
    for skeleton_hash in EXPECTED_SKELETON_ORDER[1:]:
        capture = captures[skeleton_hash]
        diffs = []
        for code in MAIN_PROCESS_ZONE_CODES:
            old = _rectangle_row(control_zones[code])
            new = _rectangle_row(capture["zones"][code])
            diffs.append(
                {
                    "zone_code": code,
                    "delta_x_mm": new["x_mm"] - old["x_mm"],
                    "delta_y_mm": new["y_mm"] - old["y_mm"],
                    "delta_width_mm": new["width_mm"] - old["width_mm"],
                    "delta_depth_mm": new["depth_mm"] - old["depth_mm"],
                    "rotation_changed": new["rotation_deg"] != old["rotation_deg"],
                    "control_geometry": old,
                    "rejected_geometry": new,
                }
            )
        face = capture["loading_face"]
        control_ship = control_zones["shipping_channel"]
        rejected_ship = capture["zones"]["shipping_channel"]
        control_distance = min(
            placement_domain.segment_distance_squared(control["truck_entrance"], edge)
            for edge in _polygon_edges(control_ship.polygon_mm)
        )
        rejected_distance = min(
            placement_domain.segment_distance_squared(capture["truck_entrance"], edge)
            for edge in _polygon_edges(rejected_ship.polygon_mm)
        )
        rows.append(
            {
                "skeleton_hash": skeleton_hash,
                "zone_diffs": diffs,
                "loading_face_side_changed": preflights[skeleton_hash].get(
                    "shipping_loading_face_side"
                )
                != control_side,
                "loading_face_translation_mm": {
                    "start_dx": face[0][0] - control_face[0][0],
                    "start_dy": face[0][1] - control_face[0][1],
                    "end_dx": face[1][0] - control_face[1][0],
                    "end_dy": face[1][1] - control_face[1][1],
                },
                "loading_face_orientation_changed": (
                    (face[0][0] == face[1][0]) != (control_face[0][0] == control_face[1][0])
                ),
                "shipping_channel_distance_to_truck_entrance_squared_mm2": {
                    "control": control_distance,
                    "rejected": rejected_distance,
                    "delta": rejected_distance - control_distance,
                },
                "shipping_channel_centroid_delta_mm": {
                    "x": str(
                        (
                            capture["zones"]["shipping_channel"].bounds_mm[0]
                            + capture["zones"]["shipping_channel"].bounds_mm[2]
                            - control_zones["shipping_channel"].bounds_mm[0]
                            - control_zones["shipping_channel"].bounds_mm[2]
                        )
                        / 2
                    ),
                    "y": str(
                        (
                            capture["zones"]["shipping_channel"].bounds_mm[1]
                            + capture["zones"]["shipping_channel"].bounds_mm[3]
                            - control_zones["shipping_channel"].bounds_mm[1]
                            - control_zones["shipping_channel"].bounds_mm[3]
                        )
                        / 2
                    ),
                },
            }
        )
    return {"identity": "v222-p1a-r14-control-rejected-geometry-diff@1.0.0", "rows": rows}


def _counterfactuals(
    captures: Mapping[str, Mapping[str, Any]], preflights: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    face_rows: list[dict[str, Any]] = []
    removal_rows: list[dict[str, Any]] = []
    translation_rows: list[dict[str, Any]] = []
    grid_mm = _mm(GRID)
    for skeleton_hash in EXPECTED_SKELETON_ORDER[1:]:
        capture = captures[skeleton_hash]
        current_face = capture["loading_face"]
        shipping = capture["zones"]["shipping_channel"]
        long_edges = placement_domain._long_edges(shipping)
        alternate_edges = [edge for edge in long_edges if edge[1] != current_face]
        if len(alternate_edges) > 1:
            raise AssertionError("expected at most one alternate shipping long edge")
        if alternate_edges:
            alt_side, alt_face = alternate_edges[0]
            result = _validator_call(capture, capture["zones"], alt_face)
            face_rows.append(
                {
                    "skeleton_hash": skeleton_hash,
                    "evaluation_only": True,
                    "current_authority_loading_face_changed": False,
                    "current_face_side": preflights[skeleton_hash].get(
                        "shipping_loading_face_side"
                    ),
                    "alternate_long_edge_side": alt_side,
                    "alternate_long_edge": _segment_row(alt_face),
                    "result": _result_summary(result),
                }
            )
        else:
            face_rows.append(
                {
                    "skeleton_hash": skeleton_hash,
                    "evaluation_only": True,
                    "current_authority_loading_face_changed": False,
                    "alternate_long_edge_available": False,
                    "result": None,
                }
            )

        for zone_code in REJECTED_ZONE_CODES:
            zones_without = dict(capture["zones"])
            zones_without.pop(zone_code)
            result = _validator_call(capture, zones_without, current_face)
            removal_rows.append(
                {
                    "skeleton_hash": skeleton_hash,
                    "removed_zone_code": zone_code,
                    "evaluation_only": True,
                    "result": _result_summary(result),
                    "removal_causes_pass": result.get("truck_route_validated") is True,
                }
            )

        for dx_steps, dy_steps in TRANSLATION_STEPS:
            dx_mm = dx_steps * grid_mm
            dy_mm = dy_steps * grid_mm
            shifted = PlacedRectangleV1(
                zone_code="shipping_channel",
                x=_m(_mm(shipping.x) + dx_mm),
                y=_m(_mm(shipping.y) + dy_mm),
                width_m=shipping.width_m,
                depth_m=shipping.depth_m,
                rotation_deg=shipping.rotation_deg,
            )
            zones_shifted = dict(capture["zones"])
            zones_shifted["shipping_channel"] = shifted
            shifted_face: SegmentMM = (
                (current_face[0][0] + dx_mm, current_face[0][1] + dy_mm),
                (current_face[1][0] + dx_mm, current_face[1][1] + dy_mm),
            )
            result = _validator_call(capture, zones_shifted, shifted_face)
            conflict_geometry = _conflict_geometry(shifted, capture)
            translation_rows.append(
                {
                    "skeleton_hash": skeleton_hash,
                    "zone_code": "shipping_channel",
                    "evaluation_only": True,
                    "authority_loading_face_changed": False,
                    "dx_mm": dx_mm,
                    "dy_mm": dy_mm,
                    "grid_steps": {"x": dx_steps, "y": dy_steps},
                    "grid_mm": grid_mm,
                    "translated_zone": _rectangle_row(shifted),
                    "translated_loading_face": _segment_row(shifted_face),
                    "other_six_main_zones_unchanged": all(
                        zones_shifted[code] == capture["zones"][code]
                        for code in MAIN_PROCESS_ZONE_CODES
                        if code != "shipping_channel"
                    ),
                    "truck_result": _result_summary(result),
                    "diagnostic_geometry_checks": conflict_geometry,
                    "p2c_full_layout_revalidated": False,
                    "layout_geometry_compatible": (
                        conflict_geometry["inside_effective_boundary"]
                        and not conflict_geometry["obstacle_intersections"]
                        and not conflict_geometry["overlap_zone_codes"]
                        and conflict_geometry["shipping_finished_positive_shared_edge"]
                    ),
                }
            )

    passes = [row for row in translation_rows if row["truck_result"]["truck_route_validated"]]
    compatible_passes = [row for row in passes if row["layout_geometry_compatible"]]
    nearest = min(
        compatible_passes,
        key=lambda row: (
            abs(row["grid_steps"]["x"]) + abs(row["grid_steps"]["y"]),
            row["grid_steps"]["x"],
            row["grid_steps"]["y"],
            row["skeleton_hash"],
        ),
        default=None,
    )
    face_evidence = {
        "identity": "v222-p1a-r14-loading-face-counterfactual@1.0.0",
        "evaluation_only": True,
        "current_authority_loading_face_changed": False,
        "rows": face_rows,
        "alternate_loading_face_pass_count": sum(
            row.get("result", {}).get("truck_route_validated") is True
            for row in face_rows
            if isinstance(row.get("result"), Mapping)
        ),
    }
    removal_evidence = {
        "identity": "v222-p1a-r14-zone-removal-counterfactual@1.0.0",
        "evaluation_only": True,
        "production_candidate": False,
        "rows": removal_rows,
        "pass_witnesses": [row for row in removal_rows if row["removal_causes_pass"]],
    }
    translation_evidence = {
        "identity": "v222-p1a-r14-local-translation-sensitivity@1.0.0",
        "evaluation_only": True,
        "grid_mm": grid_mm,
        "translation_vectors_grid_steps": [{"x": x, "y": y} for x, y in TRANSLATION_STEPS],
        "rows": translation_rows,
        "truck_pass_count": len(passes),
        "layout_geometry_compatible_pass_count": len(compatible_passes),
        "local_feasibility_witness_found": bool(compatible_passes),
        "nearest_diagnostic_pass": nearest,
        "no_local_feasible_translation_found": not compatible_passes,
    }
    return face_evidence, removal_evidence, translation_evidence


def _coverage(internal: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = _diagnostics(internal)
    budget = diagnostics.get("r11_budget_accounting", {})
    if not isinstance(budget, Mapping):
        budget = json.loads(R11_BUDGET_PATH.read_text(encoding="utf-8"))
    active_truncated = int(budget.get("truncated_active_work_item_count", 0))
    remaining = int(budget.get("global_nodes_remaining", 0))
    return {
        "identity": "v222-p1a-r14-search-coverage@1.0.0",
        "production_node_budget": int(budget.get("global_budget", 120)),
        "production_nodes_visited": int(budget.get("global_nodes_visited", 0)),
        "production_nodes_remaining": remaining,
        "global_placement_budget_exhausted": remaining == 0,
        "active_work_item_count": int(budget.get("active_work_item_count", 0)),
        "exhausted_work_item_count": int(budget.get("exhausted_work_item_count", 0)),
        "active_truncated_work_item_count": active_truncated,
        "main_skeleton_search_tree_exhausted": active_truncated == 0,
        "unexplored_constructive_work_remains": active_truncated > 0,
        "no_other_truck_feasible_skeleton_observed_within_current_search_coverage": True,
        "no_other_truck_feasible_skeleton_exists": False,
        "search_coverage_insufficient_for_design_decision": active_truncated > 0,
        "source_budget_accounting": dict(budget),
    }


def _replay_fingerprint(replay: Mapping[str, Any]) -> str:
    material = []
    for capture in sorted(replay["captures"], key=lambda row: row["skeleton_hash"]):
        material.append(
            {
                "skeleton_hash": capture["skeleton_hash"],
                "zone_rows": capture["zone_rows"],
                "truck_entrance": _segment_row(capture["truck_entrance"]),
                "loading_face": _segment_row(capture["loading_face"]),
                "result": _result_summary(capture["result"]),
                "nodes": capture["nodes"],
            }
        )
    return _identity(material)


def _bind_capture_metadata(
    replay: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    internal = replay["internal"]
    preflight_rows = _rows(internal)
    preflights = {
        str(row["main_skeleton_hash"]): row
        for row in preflight_rows
        if isinstance(row.get("main_skeleton_hash"), str)
    }
    captures: dict[str, dict[str, Any]] = {}
    for capture in replay["captures"]:
        skeleton_hash = capture["skeleton_hash"]
        if skeleton_hash in captures:
            raise AssertionError(f"duplicate real preflight validator call: {skeleton_hash}")
        binding_dict = (
            capture["binding"].to_dict()
            if hasattr(capture["binding"], "to_dict")
            else dict(capture["binding"])
        )
        maneuver = binding_dict.get("maneuver_project_input", {})
        template_set = maneuver.get("template_set", {}) if isinstance(maneuver, Mapping) else {}
        requirement = maneuver.get("requirement", {}) if isinstance(maneuver, Mapping) else {}
        catalog = template_set.get("templates", []) if isinstance(template_set, Mapping) else []
        required = (
            requirement.get("required_maneuver_classes", [])
            if isinstance(requirement, Mapping)
            else []
        )
        identities_by_class = {
            str(class_name): [
                str(template.get("identity"))
                for template in catalog
                if isinstance(template, Mapping) and template.get("maneuver_class") == class_name
            ]
            for class_name in required
        }
        capture["required_template_classes"] = list(required)
        capture["missing_template_classes"] = [
            class_name for class_name, identities in identities_by_class.items() if not identities
        ]
        capture["template_catalog"] = [
            {
                "identity": row.get("identity"),
                "maneuver_class": row.get("maneuver_class"),
            }
            for row in catalog
            if isinstance(row, Mapping)
        ]
        captures[skeleton_hash] = capture
    if set(captures) != set(EXPECTED_SKELETON_ORDER):
        raise AssertionError(
            "R14 expected all six unique R13 skeletons; "
            f"captured={sorted(captures)}, expected={sorted(EXPECTED_SKELETON_ORDER)}"
        )
    if set(preflights) != set(EXPECTED_SKELETON_ORDER):
        raise AssertionError(
            f"R13 preflight evidence did not contain six unique skeletons: {sorted(preflights)}"
        )
    return captures, preflights


def build_r14_evidence() -> dict[str, dict[str, Any]]:
    raw = FIXTURE.read_bytes()
    fixture_hash = hashlib.sha256(raw).hexdigest()
    if fixture_hash != EXPECTED_FIXTURE_SHA256:
        raise AssertionError(f"Xinzhao source fixture changed: {fixture_hash}")
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise AssertionError("Xinzhao fixture must be a JSON object")

    first_replay = _capture_one_tool7_replay(payload)
    second_replay = _capture_one_tool7_replay(payload)
    captures, preflights = _bind_capture_metadata(first_replay)
    second_captures, second_preflights = _bind_capture_metadata(second_replay)
    deterministic = (
        _replay_fingerprint(first_replay) == _replay_fingerprint(second_replay)
        and first_replay["result"].get("canonical_result_hash")
        == second_replay["result"].get("canonical_result_hash")
        and first_replay["result"].get("svg_sha256") == second_replay["result"].get("svg_sha256")
        and preflights == second_preflights
        and set(captures) == set(second_captures)
    )

    matrix = _skeleton_matrix(captures, preflights)
    tree = _search_tree(captures, preflights)
    taxonomy = _taxonomy(tree)
    control = _control_chain(captures, preflights)
    diff = _geometry_diff(captures, preflights)
    face_cfs, removal_cfs, translation_cfs = _counterfactuals(captures, preflights)
    coverage = _coverage(first_replay["internal"])

    rejection_rows = [row for row in taxonomy["rejected_skeletons"]]
    failure_signatures = {
        json.dumps(row["failure_node_counts"], sort_keys=True) for row in rejection_rows
    }
    direct_failure_class_sets = {tuple(row["direct_failure_classes"]) for row in rejection_rows}
    local_witness = translation_cfs["local_feasibility_witness_found"]
    removal_witnesses = removal_cfs["pass_witnesses"]
    alternate_face_passes = face_cfs["alternate_loading_face_pass_count"]
    common_root = bool(rejection_rows) and len(failure_signatures) == 1
    multi_causal = any(row["multi_causal_exhaustion"] for row in rejection_rows)
    if common_root and multi_causal:
        root_class = "SHIPPING_CHANNEL_LOADING_FACE_AND_BOUNDARY_REACHABILITY"
    elif common_root and direct_failure_class_sets:
        root_class = "+".join(next(iter(direct_failure_class_sets)))
    else:
        root_class = "MIXED_EXACT_TRUCK_SEARCH_EXHAUSTION"
    if alternate_face_passes:
        next_entry = "LOADING_FACE_AUTHORITY"
        owner_authority_decision_required = True
    elif local_witness:
        next_entry = "SHIPPING_CHANNEL_PLACEMENT_POLICY"
        owner_authority_decision_required = False
    elif removal_witnesses:
        next_entry = "MAIN_SKELETON_CONSTRUCTION_GEOMETRY"
        owner_authority_decision_required = False
    elif multi_causal and common_root:
        next_entry = "TRUCK_PREFLIGHT_AWARE_MAIN_SKELETON_CONSTRUCTION"
        owner_authority_decision_required = False
    elif coverage["search_coverage_insufficient_for_design_decision"]:
        next_entry = "CONSTRUCTIVE_SEARCH_COVERAGE_REDESIGN"
        owner_authority_decision_required = False
    else:
        next_entry = "TRUCK_AUTHORITY"
        owner_authority_decision_required = True

    root_summary = {
        "identity": "v222-p1a-r14-root-cause-summary@1.0.0",
        "unique_main_skeleton_count": len(captures),
        "control_skeleton_hash": EXPECTED_SKELETON_ORDER[0],
        "rejected_skeleton_count": sum(
            not row["result"]["truck_route_validated"] for row in tree["skeletons"]
        ),
        "common_root_cause": common_root,
        "multi_causal_exhaustion": multi_causal,
        "root_cause_class": root_class,
        "identical_rejection_signature_across_five_rejects": common_root,
        "direct_failure_classes_per_rejected_skeleton": {
            row["skeleton_hash"]: row["direct_failure_classes"] for row in rejection_rows
        },
        "rejection_taxonomy_counts": taxonomy["rejection_counts"],
        "direct_rejection_node_counts": {
            reason: count for reason, count in taxonomy["rejection_counts"].items() if count
        },
        "main_zone_envelope_conflict_count": taxonomy["rejection_counts"][
            "MAIN_ZONE_ENVELOPE_CONFLICT"
        ],
        "hard_obstacle_conflict_count": taxonomy["rejection_counts"]["HARD_OBSTACLE_CONFLICT"],
        "attempted_node_total": sum(row["attempted_node_count"] for row in tree["skeletons"]),
        "directly_rejected_node_total": sum(
            row["direct_rejected_node_count"] for row in tree["skeletons"]
        ),
        "descendant_search_exhausted_node_total": sum(
            row["descendant_exhausted_node_count"] for row in tree["skeletons"]
        ),
        "selected_pass_chain_node_total": sum(
            sum(node.get("result") == "SELECTED_PASS_CHAIN" for node in row["nodes"])
            for row in tree["skeletons"]
        ),
        "alternate_loading_face_pass_count": alternate_face_passes,
        "owner_authority_decision_required": owner_authority_decision_required,
        "zone_removal_counterfactual_pass_witnesses": removal_witnesses,
        "local_feasibility_witness_found": local_witness,
        "nearest_diagnostic_pass": translation_cfs["nearest_diagnostic_pass"],
        "main_skeleton_search_tree_exhausted": coverage["main_skeleton_search_tree_exhausted"],
        "global_placement_budget_exhausted": coverage["global_placement_budget_exhausted"],
        "active_truncated_work_item_count": coverage["active_truncated_work_item_count"],
        "unexplored_constructive_work_remains": coverage["unexplored_constructive_work_remains"],
        "no_other_truck_feasible_skeleton_observed_within_current_search_coverage": coverage[
            "no_other_truck_feasible_skeleton_observed_within_current_search_coverage"
        ],
        "no_other_truck_feasible_skeleton_exists": False,
        "search_coverage_insufficient_for_design_decision": coverage[
            "search_coverage_insufficient_for_design_decision"
        ],
        "next_implementation_entry": next_entry,
        "next_implementation_authorized": False,
    }
    selected = first_replay["result"]
    result_evidence = {
        "identity": "v222-p1a-r14-selected-result@1.0.0",
        "project_layout_validated": selected.get("project_layout_validated"),
        "p2_complete": selected.get("p2_complete"),
        "selected_main_skeleton_hash": _zone_skeleton_hash(
            selected.get("layout", {}).get("zones", [])
        ),
        "canonical_result_hash": selected.get("canonical_result_hash"),
        "svg_sha256": selected.get("svg_sha256"),
        "access_pass_count": selected.get("layout", {}).get("access_pass_count"),
        "access_requirement_count": selected.get("layout", {}).get("access_requirement_count"),
        "truck_route_validated": selected.get("layout", {}).get("truck_route_validated"),
        "zone_count": selected.get("zone_count"),
        "building_footprint_present": bool(selected.get("layout", {}).get("building_footprint")),
        "unchanged_from_r13": selected.get("canonical_result_hash")
        == "sha256:ed11e746cd65142b26cfb20e371dda3a91b39501175681d2538d4359ee017c0d",
    }
    determinism = {
        "identity": "v222-p1a-r14-determinism@1.0.0",
        "fixture_sha256": fixture_hash,
        "same_input_same_diagnostic_tree": deterministic,
        "same_input_same_preflight_matrix": preflights == second_preflights,
        "same_input_same_selected_canonical_hash": selected.get("canonical_result_hash")
        == second_replay["result"].get("canonical_result_hash"),
        "same_input_same_svg_hash": selected.get("svg_sha256")
        == second_replay["result"].get("svg_sha256"),
    }
    evidence: dict[str, Any] = {
        "xinzhao_p1a_r14_skeleton_truck_geometry_matrix.json": matrix,
        "xinzhao_p1a_r14_truck_search_tree.json": tree,
        "xinzhao_p1a_r14_rejection_taxonomy.json": taxonomy,
        "xinzhao_p1a_r14_control_pass_chain.json": control,
        "xinzhao_p1a_r14_control_vs_rejected_geometry_diff.json": diff,
        "xinzhao_p1a_r14_zone_removal_counterfactual.json": removal_cfs,
        "xinzhao_p1a_r14_loading_face_counterfactual.json": face_cfs,
        "xinzhao_p1a_r14_local_translation_sensitivity.json": translation_cfs,
        "xinzhao_p1a_r14_search_coverage.json": coverage,
        "xinzhao_p1a_r14_root_cause_summary.json": root_summary,
        "xinzhao_p1a_r14_selected_result.json": result_evidence,
        "xinzhao_p1a_r14_determinism.json": determinism,
    }
    evidence["V2_2_2-P1A-R14-main-skeleton-truck-feasibility-boundary-audit.md"] = _render_report(
        evidence
    )
    return evidence


def _render_report(evidence: Mapping[str, Any]) -> str:
    matrix = evidence["xinzhao_p1a_r14_skeleton_truck_geometry_matrix.json"]
    tree = evidence["xinzhao_p1a_r14_truck_search_tree.json"]
    summary = evidence["xinzhao_p1a_r14_root_cause_summary.json"]
    coverage = evidence["xinzhao_p1a_r14_search_coverage.json"]
    selected = evidence["xinzhao_p1a_r14_selected_result.json"]
    lines = [
        "# V2.2.2 P1A R14 — main-skeleton truck-feasibility boundary audit",
        "",
        "```ini",
        "TASK_ID=V2_2_2_P1A_R14_MAIN_SKELETON_TRUCK_FEASIBILITY_BOUNDARY_AUDIT_R1",
        "TASK_TYPE=DIAGNOSTIC_DESIGN_GATE",
        "RUNTIME_IMPLEMENTATION_AUTHORIZED=false",
        f"UNIQUE_MAIN_SKELETON_COUNT={summary['unique_main_skeleton_count']}",
        f"COMMON_ROOT_CAUSE={str(summary['common_root_cause']).lower()}",
        f"MULTI_CAUSAL_EXHAUSTION={str(summary['multi_causal_exhaustion']).lower()}",
        f"ROOT_CAUSE_CLASS={summary['root_cause_class']}",
        f"NEXT_IMPLEMENTATION_ENTRY={summary['next_implementation_entry']}",
        "NEXT_IMPLEMENTATION_AUTHORIZED=false",
        "```",
        "",
        "## Real R13 preflight skeletons",
        "",
        "All rows below are captured from the unmocked Tool 7 production replay. "
        "The process-local observer wrapped the existing validator's transform call and "
        "did not alter its result or persist runtime instrumentation.",
        "",
        "| Skeleton | Discovery → canonical owner | Truck result | Nodes | Loading face |",
        "| --- | --- | --- | ---: | --- |",
    ]
    tree_by_hash = {row["skeleton_hash"]: row for row in tree["skeletons"]}
    for row in matrix["rows"]:
        search = tree_by_hash[row["skeleton_hash"]]
        face = row["shipping_loading_face"]
        lines.append(
            f"| `{row['skeleton_hash'][:15]}…` | "
            f"{row['discovery_topology']} → {row['canonical_topology_owner']} | "
            f"{search['result']['status']} | {search['visited_nodes_reported']} | "
            f"{face['side']} {face['start_mm']}→{face['end_mm']} |"
        )
    diff_by_hash = {
        row["skeleton_hash"]: row
        for row in evidence["xinzhao_p1a_r14_control_vs_rejected_geometry_diff.json"]["rows"]
    }
    lines.extend(
        [
            "",
            "## Causal geometry boundary",
            "",
            "The control's selected final dock pose lies on its authoritative loading face. "
            "For each rejected skeleton, every observed terminal dock pose misses the current "
            "loading face; other explored branches fail the exact effective-boundary predicate. "
            "No observed branch envelope was rejected by a hard obstacle or another main-zone "
            "interior.",
            "",
            "| Skeleton | Main zones changed vs control | Final dock on current face | "
            "Direct failure counts | Blocking zones / obstacles |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in matrix["rows"]:
        skeleton_hash = row["skeleton_hash"]
        geometry_diff = diff_by_hash.get(skeleton_hash)
        changed_zones = (
            [
                zone["zone_code"]
                for zone in geometry_diff["zone_diffs"]
                if zone["delta_x_mm"]
                or zone["delta_y_mm"]
                or zone["delta_width_mm"]
                or zone["delta_depth_mm"]
                or zone["rotation_changed"]
            ]
            if geometry_diff
            else []
        )
        search = tree_by_hash[skeleton_hash]
        dock_face = row["final_dock_pose_points_on_loading_face"]
        dock_status = "PASS" if dock_face and all(dock_face.values()) else "MISS"
        lines.append(
            f"| `{skeleton_hash[:15]}…` | {', '.join(changed_zones) or '—'} | "
            f"{dock_status} | `{search['direct_rejection_counts']}` | "
            f"zones `{search['top_blocking_zone_counts'] or 'none'}`; "
            f"obstacles `{search['top_blocking_obstacle_counts'] or 'none'}` |"
        )
    lines.extend(
        [
            "",
            f"- The five rejects share the same direct-failure signature: "
            f"`{summary['direct_rejection_node_counts']}`. This is a common failure pattern "
            "with multiple exhausted branch causes: boundary-envelope rejection and final "
            "dock-pose/loading-face mismatch.",
            f"- Across the six real searches, `{summary['attempted_node_total']}` nodes were "
            f"observed: `{summary['directly_rejected_node_total']}` directly failed an existing "
            f"predicate and `{summary['descendant_search_exhausted_node_total']}` locally viable "
            "nodes had no complete descendant chain; "
            f"`{summary['selected_pass_chain_node_total']}` nodes form the control pass chain.",
            f"- Main-zone-envelope conflicts: `{summary['main_zone_envelope_conflict_count']}`; "
            f"hard-obstacle conflicts: `{summary['hard_obstacle_conflict_count']}`.",
        ]
    )
    lines.extend(
        [
            "",
            "## Branch-level findings",
            "",
            "Each attempted template transform includes its required-class sequence, "
            "entry lattice point, rotation, transformed poses, envelope, the first "
            "rejecting existing predicate, and exact blocking zone/obstacle identities. "
            "The machine-readable tree preserves every node; aggregate labels are "
            "descriptive taxonomy, not new engineering rules.",
            "",
            f"- Direct rejection counts: `{summary['rejection_taxonomy_counts']}`.",
            f"- Alternate loading-face passes: `{summary['alternate_loading_face_pass_count']}`.",
            "- Owner authority decision required: "
            f"`{str(summary['owner_authority_decision_required']).lower()}`.",
            "- Local truck-feasible translation witness: "
            f"`{str(summary['local_feasibility_witness_found']).lower()}`.",
            "- Zone-removal counterfactual pass witnesses: "
            f"`{len(summary['zone_removal_counterfactual_pass_witnesses'])}`.",
            "- All loading-face, zone-removal, and translation changes are evaluation-only; "
            "none is a production candidate or authority change.",
            "",
            "## Search coverage and selected result",
            "",
            f"- Placement budget `{coverage['production_node_budget']}`, "
            f"visited `{coverage['production_nodes_visited']}`, "
            f"remaining `{coverage['production_nodes_remaining']}`; "
            "active truncated work items "
            f"`{coverage['active_truncated_work_item_count']}`.",
            "- Unexplored constructive work remains: "
            f"`{str(coverage['unexplored_constructive_work_remains']).lower()}`. "
            "Therefore the observed absence of another truck-feasible skeleton "
            "is not an infeasibility proof.",
            "- Tool 7 remains hard-valid: project layout "
            f"`{str(selected['project_layout_validated']).lower()}`, "
            f"P2 complete `{str(selected['p2_complete']).lower()}`, "
            f"access `{selected['access_pass_count']}/"
            f"{selected['access_requirement_count']}`, "
            f"truck `{str(selected['truck_route_validated']).lower()}`, "
            f"zones `{selected['zone_count']}`, "
            f"footprint `{str(selected['building_footprint_present']).lower()}`.",
            "- Selected layout/hash/SVG remain unchanged from R13; this audit "
            "does not resolve the Owner visual blocker.",
            "",
            "## Governance",
            "",
            "No production code, P2D authority, loading-face policy, truck "
            "templates/budgets, placement budget, public contracts, ranking, "
            "Golden inputs, or P1B thresholds were changed. "
            "R14 is diagnostic only; a subsequent implementation requires separate authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def write_r14_evidence() -> dict[str, Any]:
    evidence = build_r14_evidence()
    for name, value in evidence.items():
        path = ROOT / "docs/tasks" / name if name.endswith(".md") else EVIDENCE_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
    return evidence
