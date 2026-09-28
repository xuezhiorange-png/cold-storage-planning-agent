"""Capture R12 access evidence from the real, unmodified Tool 7 chain.

The wrappers below are process-local observers: every wrapped function delegates
to the original implementation, and none of the instrumentation is persisted in
production or serialized into the Tool 7 response.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.mcp_site_layout import (
    invoke_preview_site_layout_tool,
)
from cold_storage.modules.layout.application import access_routing as access_app
from cold_storage.modules.layout.application import validated_candidate_selection as selector
from cold_storage.modules.layout.domain import access_routing as access_domain
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.main_process_skeleton import (
    MAIN_PROCESS_ZONE_CODES,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
EVIDENCE_DIR = REPOSITORY_ROOT / "docs/tasks/evidence/v2_2_2_p1a"
MAIN_ZONE_CODES = frozenset(MAIN_PROCESS_ZONE_CODES)
TAIL_ZONE_CODES = (
    "changing_room",
    "office",
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
)
TARGET_SKELETONS = {
    "CONTROL": "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953",
    "TARGET_A": "sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c",
    "TARGET_B": "sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3",
}


def _json_write(path: Path, payload: Any) -> None:
    def default(value: Any) -> str:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Not JSON serializable: {type(value).__name__}")

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=default,
        )
        + "\n",
        encoding="utf-8",
    )


def _zone_skeleton_hash(zone_rows: list[dict[str, Any]]) -> str:
    by_code = {str(row["zone_code"]): row for row in zone_rows}
    ordered = [by_code[code] for code in MAIN_PROCESS_ZONE_CODES]
    records = [
        {
            "zone_code": str(row["zone_code"]),
            "x": str(row["x"]),
            "y": str(row["y"]),
            "width_m": str(row["width_m"]),
            "depth_m": str(row["depth_m"]),
            "rotation_deg": row["rotation_deg"],
        }
        for row in ordered
    ]
    return canonical_hash(records)


def _classify_failure(
    requirement: dict[str, Any],
    result: dict[str, Any],
    *,
    counterfactual_status: str | None,
    main_only: bool,
) -> list[str]:
    codes = set(str(code) for code in result.get("codes", []))
    classes: list[str] = []
    if "PORTAL_CLEAR_WIDTH_INSUFFICIENT" in codes:
        classes.append("PORTAL_WIDTH_CONFLICT")
    if "EDGE_ORIENTATION_ALIGNMENT_REQUIRED" in codes:
        classes.append("EDGE_ORIENTATION_CONFLICT")
    if "ROUTE_SEARCH_EXHAUSTED" in codes:
        classes.append("ROUTE_SEARCH_BUDGET_EXHAUSTION")
    if requirement.get("flow_kind") == "TRUCK":
        classes.append("OTHER_EXACT_ACCESS_CONFLICT")
    corridor_codes = {
        "CORRIDOR_INCIDENT_ZONE_CROSSING",
        "CORRIDOR_OUTSIDE_BUILDABLE_BOUNDARY",
        "CORRIDOR_OBSTACLE_INTERSECTION",
        "CORRIDOR_UNRELATED_ZONE_INTERSECTION",
    }
    if codes & corridor_codes:
        classes.append("CORRIDOR_GEOMETRY_CONFLICT")
    refs = {str(requirement.get("from_ref")), str(requirement.get("to_ref"))}
    if requirement.get("flow_kind") == "PEOPLE" or refs & {"office", "changing_room"}:
        classes.append("PERSONNEL_ACCESS_CONFLICT")
    if "packaging_material_storage" in refs:
        classes.append("PACKAGING_ACCESS_CONFLICT")
    if refs <= MAIN_ZONE_CODES or (requirement.get("flow_kind") == "TRUCK" and main_only):
        classes.append(
            "MAIN_SKELETON_ACCESS_GEOMETRY_CONFLICT"
            if main_only and counterfactual_status not in {"PASS", None}
            else "MAIN_FLOW_ACCESS_CONFLICT"
        )
    if counterfactual_status == "PASS":
        classes.append("TAIL_PLACEMENT_ACCESS_OCCLUSION")
    if not classes:
        classes.append("OTHER_EXACT_ACCESS_CONFLICT")
    return list(dict.fromkeys(classes))


def _direct_failure_reason(
    requirement: dict[str, Any],
    result: dict[str, Any],
    zones: dict[str, PlacedRectangleV1],
    relationships: dict[str, dict[str, Any]],
) -> str:
    if requirement.get("flow_kind") == "TRUCK":
        return "NOT_APPLICABLE_TRUCK_MANEUVER_AUTHORITY"
    if requirement.get("from_ref") in {"main_entrance", "truck_entrance"}:
        return "DIRECT_NOT_APPLICABLE_BOUNDARY_ENDPOINT"
    if requirement.get("direct_allowed") is not True:
        return "DIRECT_NOT_ALLOWED"
    from_ref = str(requirement.get("from_ref"))
    to_ref = str(requirement.get("to_ref"))
    first = zones.get(from_ref)
    second = zones.get(to_ref)
    if first is None or second is None:
        return "DIRECT_ENDPOINT_NOT_PLACED"
    shared = access_domain._shared_edge_segment(first, second)
    if shared is None:
        return "NO_SHARED_EDGE"
    relationship = access_domain._relation_for(requirement, relationships)
    expected_from = (
        access_domain._edge_class(relationship.get("from_edge_class")) if relationship else None
    )
    expected_to = (
        access_domain._edge_class(relationship.get("to_edge_class")) if relationship else None
    )
    actual_from, actual_to = access_domain._edge_match_for_shared(first, second, shared)
    aligned = (expected_from is None or expected_from == actual_from) and (
        expected_to is None or expected_to == actual_to
    )
    if not aligned:
        return "EDGE_ORIENTATION_ALIGNMENT_REQUIRED"
    profile = access_domain.resolve_access_profile(str(requirement["profile_identity"]))
    portal_width = access_domain._mm(profile.portal_clear_width_m, field="portal_clear_width_m")
    if requirement.get("cold_room_refs"):
        portal_width = max(
            portal_width,
            access_domain._mm(
                access_domain.resolve_access_profile(access_domain.COLD_ROOM).portal_clear_width_m,
                field="cold_room_portal_clear_width_m",
            ),
        )
    if access_domain._segment_length_mm(shared) < portal_width:
        return "PORTAL_CLEAR_WIDTH_INSUFFICIENT"
    if result.get("topology") == "DIRECT_SHARED_EDGE":
        return "DIRECT_SHARED_EDGE_SELECTED"
    return "DIRECT_EDGE_AVAILABLE_BUT_NOT_SELECTED"


def _portal_pair_descriptors(
    requirement: dict[str, Any],
    *,
    relationships: dict[str, dict[str, Any]],
    zones: dict[str, PlacedRectangleV1],
    boundary: Any,
    entrances: dict[str, Any],
) -> list[dict[str, Any]]:
    if requirement.get("flow_kind") == "TRUCK":
        return []
    from_ref = str(requirement.get("from_ref"))
    to_ref = str(requirement.get("to_ref"))
    relation = access_domain._relation_for(requirement, relationships)
    expected_from = access_domain._edge_class(relation.get("from_edge_class")) if relation else None
    expected_to = access_domain._edge_class(relation.get("to_edge_class")) if relation else None
    profile = access_domain.resolve_access_profile(str(requirement["profile_identity"]))
    portal_width = access_domain._mm(profile.portal_clear_width_m, field="portal_clear_width_m")
    corridor_width = access_domain._mm(
        profile.corridor_clear_width_m, field="corridor_clear_width_m"
    )
    if requirement.get("cold_room_refs"):
        portal_width = max(
            portal_width,
            access_domain._mm(
                access_domain.resolve_access_profile(access_domain.COLD_ROOM).portal_clear_width_m,
                field="cold_room_portal_clear_width_m",
            ),
        )
    from_options = access_domain._edge_options(
        zones.get(from_ref),
        required_class=expected_from,
        clear_width_mm=portal_width,
        boundary_segment=entrances.get(from_ref),
    )
    to_options = access_domain._edge_options(
        zones.get(to_ref),
        required_class=expected_to,
        clear_width_mm=portal_width,
    )
    output: list[dict[str, Any]] = []
    for index, (from_option, to_option) in enumerate(product(from_options, to_options), start=1):
        start = access_domain._portal_center(from_option["segment_mm"])
        end = access_domain._portal_center(to_option["segment_mm"])
        if from_ref in entrances:
            start = access_domain._boundary_interior_point(
                start,
                entrances[from_ref],
                boundary,
                corridor_width // 2,
            )
        output.append(
            {
                "portal_pair_index": index,
                "from_portal_segment_mm": from_option["segment_mm"],
                "to_portal_segment_mm": to_option["segment_mm"],
                "from_portal_edge_class": from_option["edge_class"],
                "to_portal_edge_class": to_option["edge_class"],
                "from_portal_clear_width_m": from_option["clear_width_m"],
                "to_portal_clear_width_m": to_option["clear_width_m"],
                "route_start_mm": start,
                "route_end_mm": end,
            }
        )
    return output


def _access_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = {
        str(row.get("identity")): row for row in candidate["p2d"].get("access_requirements", [])
    }
    results = {
        str(row.get("requirement_identity")): row
        for row in candidate["p2d"].get("access_results", [])
    }
    output: list[dict[str, Any]] = []
    for identity in sorted(requirements):
        requirement = requirements[identity]
        result = results.get(identity, {})
        portal_from = result.get("portal_from")
        portal_to = result.get("portal_to")
        output.append(
            {
                "requirement_identity": identity,
                "from_ref": requirement.get("from_ref"),
                "to_ref": requirement.get("to_ref"),
                "flow_kind": requirement.get("flow_kind"),
                "access_class": requirement.get("access_class"),
                "profile_identity": requirement.get("profile_identity"),
                "portal_required": requirement.get("portal_required"),
                "direct_allowed": requirement.get("direct_allowed"),
                "corridor_allowed": requirement.get("corridor_allowed"),
                "edge_orientation_requirement": requirement.get("edge_orientation_requirement"),
                "route_shape_constraint": requirement.get("route_shape_constraint"),
                "status": result.get("status", "MISSING_RESULT"),
                "codes": list(result.get("codes", [])),
                "selected_topology": result.get("topology"),
                "portal_from": portal_from,
                "portal_to": portal_to,
                "portal_clear_width_m": (
                    portal_from.get("clear_width_m") if isinstance(portal_from, dict) else None
                ),
                "corridor_clear_width_m": result.get("clear_width_m")
                if result.get("topology") == "CORRIDOR_MEDIATED"
                else None,
                "route_shape": result.get("route_shape"),
                "turn_count": result.get("turn_count"),
                "route_length_m": result.get("route_length_m"),
                "centerline": result.get("centerline", []),
            }
        )
    return output


def _instrumented_capture() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state: dict[str, Any] = {
        "candidates": [],
        "attempts": [],
        "active_candidate": None,
        "active_requirement": None,
        "active_attempt": None,
        "selection_internal": None,
        "authority_context": None,
    }
    original_route_site = selector.route_site_placement
    original_route_requirement = access_app.route_access_requirement
    original_find_route = access_domain._find_route
    original_route_safe = access_domain._route_is_safe
    original_select = site_layout_preview.select_validated_placement

    def route_requirement_observer(requirement: dict[str, Any], **kwargs: Any) -> Any:
        previous = state["active_requirement"]
        state["active_requirement"] = str(requirement.get("identity"))
        try:
            return original_route_requirement(requirement, **kwargs)
        finally:
            state["active_requirement"] = previous

    def route_safe_observer(*args: Any, **kwargs: Any) -> Any:
        result = original_route_safe(*args, **kwargs)
        active_attempt = state.get("active_attempt")
        if active_attempt is not None and result[0] is False and result[1] is not None:
            reasons = active_attempt.setdefault("route_safety_rejections", {})
            reasons[str(result[1])] = reasons.get(str(result[1]), 0) + 1
        return result

    def find_route_observer(start: Any, end: Any, **kwargs: Any) -> Any:
        candidate = state.get("active_candidate") or {}
        attempt = {
            "candidate_hash": candidate.get("candidate_hash"),
            "skeleton_hash": candidate.get("skeleton_hash"),
            "requirement_identity": state.get("active_requirement"),
            "route_start_mm": start,
            "route_end_mm": end,
            "route_safety_rejections": {},
        }
        state["attempts"].append(attempt)
        previous = state["active_attempt"]
        state["active_attempt"] = attempt
        try:
            path, reason, envelopes = original_find_route(start, end, **kwargs)
            attempt["outcome"] = "PASS" if path is not None else "FAIL"
            attempt["failure_reason"] = reason or None
            attempt["route_points_mm"] = path or []
            attempt["turn_count"] = access_domain._turn_count(path) if path else None
            attempt["route_length_mm"] = access_domain._path_length_mm(path) if path else None
            attempt["corridor_envelope_count"] = len(envelopes)
            return path, reason, envelopes
        finally:
            state["active_attempt"] = previous

    def route_site_observer(
        canonical_zone_plan: Any,
        p1_handoff: Any,
        site_geometry: Any,
        placement: Any,
        truck_binding: Any = None,
        **kwargs: Any,
    ) -> Any:
        body = placement.to_dict()
        zone_rows = body.get("zones", [])
        skeleton_hash = _zone_skeleton_hash(zone_rows)
        candidate = {
            "candidate_hash": body.get("canonical_candidate_hash"),
            "candidate_result_hash": body.get("canonical_result_hash"),
            "skeleton_hash": skeleton_hash,
            "zones": zone_rows,
            "shipping_loading_face_segment": body.get("shipping_loading_face_segment"),
            "search_provenance": body.get("search_provenance"),
            "route_node_budget": kwargs.get("route_node_budget"),
            "truck_node_budget": kwargs.get("truck_node_budget"),
        }
        previous_candidate = state["active_candidate"]
        state["active_candidate"] = candidate
        result = original_route_site(
            canonical_zone_plan,
            p1_handoff,
            site_geometry,
            placement,
            truck_binding,
            **kwargs,
        )
        candidate["p2d"] = result.to_dict()
        candidate["authority_context_index"] = 0
        state["authority_context"] = (
            canonical_zone_plan,
            p1_handoff,
            site_geometry,
            truck_binding,
        )
        state["candidates"].append(candidate)
        state["active_candidate"] = previous_candidate
        return result

    def select_observer(*args: Any, **kwargs: Any) -> Any:
        result = original_select(*args, **kwargs)
        state["selection_internal"] = result.internal_evaluation
        return result

    selector.route_site_placement = route_site_observer
    access_app.route_access_requirement = route_requirement_observer
    access_domain._find_route = find_route_observer
    access_domain._route_is_safe = route_safe_observer
    site_layout_preview.select_validated_placement = select_observer
    try:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        tool_result = invoke_preview_site_layout_tool(payload)
    finally:
        selector.route_site_placement = original_route_site
        access_app.route_access_requirement = original_route_requirement
        access_domain._find_route = original_find_route
        access_domain._route_is_safe = original_route_safe
        site_layout_preview.select_validated_placement = original_select
    state["tool_result"] = tool_result
    return state, state["candidates"]


def _topology_metadata(
    selection_internal: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    diagnostics = selection_internal.get("r6_topology_diagnostics", {})
    if isinstance(diagnostics, dict):
        registry = diagnostics.get("geometry_evaluation_registry", [])
        rows.extend(row for row in registry if isinstance(row, dict))
    rows.extend(
        row for row in selection_internal.get("skeleton_survival", []) if isinstance(row, dict)
    )
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        skeleton_hash = row.get("skeleton_hash")
        if isinstance(skeleton_hash, str):
            mapping.setdefault(skeleton_hash, {}).update(row)
    return mapping


def _context_for_counterfactual(
    candidate: dict[str, Any],
    authority_context: tuple[Any, Any, Any, Any],
) -> dict[str, Any]:
    zone_plan, handoff, site_geometry, _ = authority_context
    _, _, _, requirements, spatial_relationships = access_app._validate_p1_authority(
        zone_plan, handoff, site_geometry
    )
    geometry_body = site_geometry.to_dict()
    site_body = geometry_body["site"]
    obstacle_body = geometry_body["obstacles"]
    boundary = normalize_polygon(
        site_body["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(row["footprint"], allow_numeric_string=True)
        for row in obstacle_body.get("hard_obstacles", [])
    )
    entrances = {
        name: access_domain._segment_from_mapping(geometry_body["entrances"][name], field=name)
        for name in ("main_entrance", "truck_entrance")
    }
    relationships = {
        str(row["identity"]): dict(row)
        for row in spatial_relationships
        if isinstance(row, dict) and isinstance(row.get("identity"), str)
    }
    zones = {
        str(row["zone_code"]): access_app._rectangle_from_row(row) for row in candidate["zones"]
    }
    return {
        "requirements": list(requirements),
        "relationships": relationships,
        "zones": zones,
        "boundary": boundary,
        "obstacles": obstacles,
        "entrances": entrances,
        "site_geometry_hash": site_geometry.canonical_result_hash,
        "truck_binding": authority_context[3],
    }


def _run_counterfactual(
    requirement: dict[str, Any],
    context: dict[str, Any],
    *,
    candidate: dict[str, Any],
    authority_context: tuple[Any, Any, Any, Any],
    route_node_budget: int,
) -> dict[str, Any]:
    refs = {str(requirement.get("from_ref")), str(requirement.get("to_ref"))}
    keep = set(MAIN_ZONE_CODES) | (refs & set(TAIL_ZONE_CODES))
    subset = {code: rectangle for code, rectangle in context["zones"].items() if code in keep}
    if requirement.get("flow_kind") == "TRUCK":
        shipping_face = access_domain._segment_from_mapping(
            candidate["shipping_loading_face_segment"],
            field="shipping_loading_face_segment",
        )
        truck_result = access_domain.validate_truck_maneuver_chain(
            context["truck_binding"],
            truck_entrance=context["entrances"]["truck_entrance"],
            shipping_loading_face=shipping_face,
            boundary=context["boundary"],
            obstacles=context["obstacles"],
            zones=subset,
            node_budget=int(candidate["truck_node_budget"] or 5_000),
        )
        search = truck_result.get("search_provenance", {})
        return {
            "preserved_zone_codes": sorted(subset),
            "removed_unrelated_tail_zone_codes": sorted(set(TAIL_ZONE_CODES) - set(subset)),
            "status": truck_result.get("status"),
            "truck_route_validated": truck_result.get("truck_route_validated"),
            "codes": truck_result.get("codes", []),
            "maneuver_chain": truck_result.get("maneuver_chain", []),
            "search_provenance": search,
            "exact_no_route_within_enumerated_authority": (
                search.get("search_tree_exhausted") is True
                and search.get("node_budget_exhausted") is False
                and truck_result.get("truck_route_validated") is not True
            ),
        }
    result, _ = access_domain.route_access_requirement(
        requirement,
        relationships=context["relationships"],
        zones=subset,
        boundary=context["boundary"],
        obstacles=context["obstacles"],
        entrances=context["entrances"],
        route_node_budget=route_node_budget,
    )
    return {
        "preserved_zone_codes": sorted(subset),
        "removed_unrelated_tail_zone_codes": sorted(set(TAIL_ZONE_CODES) - set(subset)),
        "status": result.get("status"),
        "codes": result.get("codes", []),
        "topology": result.get("topology"),
        "portal_from": result.get("portal_from"),
        "portal_to": result.get("portal_to"),
        "route_shape": result.get("route_shape"),
        "turn_count": result.get("turn_count"),
        "route_length_m": result.get("route_length_m"),
    }


def _evidence_payloads() -> dict[str, Any]:
    state, candidates = _instrumented_capture()
    if state["tool_result"].get("ok") is not True:
        raise AssertionError(f"Real Tool 7 replay failed: {state['tool_result']}")
    metadata = _topology_metadata(state["selection_internal"] or {})
    for candidate in candidates:
        row = metadata.get(candidate["skeleton_hash"], {})
        candidate["discovery_topology"] = row.get("discovery_topology")
        candidate["canonical_topology_owner"] = row.get("canonical_topology_owner")
        candidate["canonical_family"] = row.get("canonical_family") or row.get("family")
        candidate["access_rows"] = _access_rows(candidate)
        candidate["access_pass_count"] = sum(
            row["status"] == "PASS" for row in candidate["access_rows"]
        )
        candidate["access_fail_count"] = sum(
            row["status"] == "FAIL" for row in candidate["access_rows"]
        )
        candidate["access_blocked_count"] = sum(
            row["status"] == "BLOCKED" for row in candidate["access_rows"]
        )
        candidate["failed_requirement_ids"] = [
            row["requirement_identity"]
            for row in candidate["access_rows"]
            if row["status"] != "PASS"
        ]

    target_candidates = {
        label: [row for row in candidates if row["skeleton_hash"] == skeleton_hash]
        for label, skeleton_hash in TARGET_SKELETONS.items()
    }
    context_cache: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        context_cache[candidate["candidate_hash"]] = _context_for_counterfactual(
            candidate, state["authority_context"]
        )

    counterfactual_rows: list[dict[str, Any]] = []
    route_budget = int(candidates[0]["route_node_budget"] or 5_000)
    failed_rows_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        requirement_by_id = {
            str(row["identity"]): row for row in candidate["p2d"].get("access_requirements", [])
        }
        p2d_results = {
            str(row["requirement_identity"]): row
            for row in candidate["p2d"].get("access_results", [])
        }
        failures: list[dict[str, Any]] = []
        for identity in candidate["failed_requirement_ids"]:
            requirement = requirement_by_id[identity]
            p2d_result = p2d_results[identity]
            counterfactual = _run_counterfactual(
                requirement,
                context_cache[candidate["candidate_hash"]],
                candidate=candidate,
                authority_context=state["authority_context"],
                route_node_budget=route_budget,
            )
            main_only = set(
                (requirement.get("from_ref"), requirement.get("to_ref"))
            ) <= MAIN_ZONE_CODES or (
                requirement.get("flow_kind") == "TRUCK"
                and requirement.get("to_ref") == "shipping_channel"
            )
            direct_reason = _direct_failure_reason(
                requirement,
                p2d_result,
                context_cache[candidate["candidate_hash"]]["zones"],
                context_cache[candidate["candidate_hash"]]["relationships"],
            )
            failure_classes = _classify_failure(
                requirement,
                p2d_result,
                counterfactual_status=counterfactual["status"],
                main_only=main_only,
            )
            detail = {
                "requirement_identity": identity,
                "from_ref": requirement.get("from_ref"),
                "to_ref": requirement.get("to_ref"),
                "flow_kind": requirement.get("flow_kind"),
                "status": p2d_result.get("status"),
                "codes": p2d_result.get("codes", []),
                "failure_classes": failure_classes,
                "direct_failure_reason": direct_reason,
                "counterfactual": counterfactual,
                "failure_present_with_main_skeleton_only": (
                    counterfactual.get("truck_route_validated") is not True
                    if requirement.get("flow_kind") == "TRUCK" and main_only
                    else counterfactual["status"] != "PASS"
                    if main_only
                    else None
                ),
                "failure_disappears_when_unrelated_tail_removed": (
                    counterfactual.get("truck_route_validated") is True
                    if requirement.get("flow_kind") == "TRUCK"
                    else counterfactual["status"] == "PASS"
                ),
            }
            failures.append(detail)
            counterfactual_rows.append(
                {
                    "candidate_hash": candidate["candidate_hash"],
                    "skeleton_hash": candidate["skeleton_hash"],
                    "requirement": identity,
                    "endpoints_are_main_process_zones": set(
                        (requirement.get("from_ref"), requirement.get("to_ref"))
                    )
                    <= MAIN_ZONE_CODES,
                    "main_process_skeleton_access_tested": main_only,
                    **detail,
                }
            )
        failed_rows_by_candidate[candidate["candidate_hash"]] = failures

    matrix_candidates: list[dict[str, Any]] = []
    failed_matrix: list[dict[str, Any]] = []
    for candidate in candidates:
        row = {
            key: candidate.get(key)
            for key in (
                "candidate_hash",
                "candidate_result_hash",
                "skeleton_hash",
                "discovery_topology",
                "canonical_topology_owner",
                "canonical_family",
                "route_node_budget",
                "zones",
                "access_pass_count",
                "access_fail_count",
                "access_blocked_count",
                "failed_requirement_ids",
                "p2d",
                "access_rows",
            )
        }
        row["access_requirement_count"] = len(candidate["access_rows"])
        matrix_candidates.append(row)
        for access_row in candidate["access_rows"]:
            failed_matrix.append(
                {
                    "candidate_hash": candidate["candidate_hash"],
                    "skeleton_hash": candidate["skeleton_hash"],
                    "requirement_identity": access_row["requirement_identity"],
                    "status": access_row["status"],
                    "codes": access_row["codes"],
                }
            )

    topology_trace = []
    for candidate in candidates:
        matching_attempts = [
            attempt
            for attempt in state["attempts"]
            if attempt.get("candidate_hash") == candidate["candidate_hash"]
        ]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for attempt in matching_attempts:
            grouped[str(attempt.get("requirement_identity"))].append(attempt)
        context = context_cache[candidate["candidate_hash"]]
        requirements = {
            str(row["identity"]): row for row in candidate["p2d"].get("access_requirements", [])
        }
        for row in candidate["access_rows"]:
            identity = row["requirement_identity"]
            requirement = requirements[identity]
            descriptors = _portal_pair_descriptors(
                requirement,
                relationships=context["relationships"],
                zones=context["zones"],
                boundary=context["boundary"],
                entrances=context["entrances"],
            )
            actual_attempts = grouped.get(identity, [])
            pair_rows = []
            outcome_counts: Counter[str] = Counter()
            rejection_counts: Counter[str] = Counter()
            for index, attempt in enumerate(actual_attempts):
                descriptor = descriptors[index] if index < len(descriptors) else {}
                outcome = str(attempt.get("outcome", "UNKNOWN"))
                outcome_counts[outcome] += 1
                for reason, count in attempt.get("route_safety_rejections", {}).items():
                    rejection_counts[str(reason)] += int(count)
                pair_rows.append(
                    {
                        **descriptor,
                        "attempt_index": index + 1,
                        "outcome": outcome,
                        "failure_reason": attempt.get("failure_reason"),
                        "route_safety_rejections": attempt.get("route_safety_rejections", {}),
                        "route_points_mm": attempt.get("route_points_mm", []),
                        "turn_count": attempt.get("turn_count"),
                        "route_length_mm": attempt.get("route_length_mm"),
                    }
                )
            topology_trace.append(
                {
                    "candidate_hash": candidate["candidate_hash"],
                    "skeleton_hash": candidate["skeleton_hash"],
                    "requirement_identity": identity,
                    "requirement_status": row["status"],
                    "direct_failure_reason": _direct_failure_reason(
                        requirement,
                        next(
                            result
                            for result in candidate["p2d"]["access_results"]
                            if result.get("requirement_identity") == identity
                        ),
                        context["zones"],
                        context["relationships"],
                    ),
                    "portal_pair_count": len(pair_rows),
                    "portal_pair_pass_count": outcome_counts.get("PASS", 0),
                    "portal_pair_failure_counts": dict(sorted(outcome_counts.items())),
                    "route_safety_rejection_counts": dict(sorted(rejection_counts.items())),
                    "portal_pairs": pair_rows,
                }
            )

    variant_rows: list[dict[str, Any]] = []
    for label, rows in target_candidates.items():
        variants = sorted(rows, key=lambda row: str(row["candidate_hash"]))
        variant_access = [
            {
                "candidate_hash": row["candidate_hash"],
                "access_pass_count": row["access_pass_count"],
                "access_fail_count": row["access_fail_count"],
                "failed_requirement_ids": row["failed_requirement_ids"],
                "failed_requirement_codes": {
                    access_row["requirement_identity"]: access_row["codes"]
                    for access_row in row["access_rows"]
                    if access_row["status"] != "PASS"
                },
            }
            for row in variants
        ]
        changed_tail: list[str] = []
        if len(variants) >= 2:
            zones_by_variant = [
                {str(zone["zone_code"]): zone for zone in variant["zones"]}
                for variant in variants[:2]
            ]
            changed_tail = [
                code
                for code in TAIL_ZONE_CODES
                if zones_by_variant[0].get(code) != zones_by_variant[1].get(code)
            ]
        failed_sets = [set(row["failed_requirement_ids"]) for row in variants]
        common_failed = sorted(set.intersection(*failed_sets)) if failed_sets else []
        variant_rows.append(
            {
                "label": label,
                "skeleton_hash": TARGET_SKELETONS[label],
                "variant_count": len(variants),
                "variants": variant_access,
                "changed_tail_zone_codes": changed_tail,
                "two_variants_fail_same_requirement": bool(common_failed),
                "common_failed_requirement_ids": common_failed,
                "all_variants_have_same_failed_requirement_set": (
                    len({tuple(sorted(values)) for values in failed_sets}) <= 1
                    if failed_sets
                    else False
                ),
            }
        )

    target_root_causes: list[dict[str, Any]] = []
    for label in ("TARGET_A", "TARGET_B"):
        variants = target_candidates[label]
        failures = [
            failure
            for variant in variants
            for failure in failed_rows_by_candidate.get(variant["candidate_hash"], [])
        ]
        target_fail_ids = [set(row["failed_requirement_ids"]) for row in variants]
        common_failed = sorted(set.intersection(*target_fail_ids)) if target_fail_ids else []
        by_req: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for failure in failures:
            by_req[str(failure["requirement_identity"])].append(failure)
        invariant_ids = [
            identity
            for identity in common_failed
            if len(by_req[identity]) >= len(variants)
            and len({tuple(sorted(row["codes"])) for row in by_req[identity]}) == 1
        ]
        main_infeasible_ids = [
            identity
            for identity in invariant_ids
            if all(
                row["failure_present_with_main_skeleton_only"] is True
                and (
                    row["counterfactual"].get("exact_no_route_within_enumerated_authority") is True
                    or (
                        row["counterfactual"].get("status") != "BLOCKED"
                        and "ROUTE_SEARCH_BUDGET_EXHAUSTION" not in row["failure_classes"]
                    )
                )
                for row in by_req[identity]
            )
        ]
        target_root_causes.append(
            {
                "label": label,
                "skeleton_hash": TARGET_SKELETONS[label],
                "variant_count": len(variants),
                "common_failed_requirement_ids": common_failed,
                "failure_invariant_across_tail_variants": bool(invariant_ids),
                "invariant_requirement_ids": invariant_ids,
                "main_skeleton_access_infeasibility_proven": bool(main_infeasible_ids),
                "main_skeleton_infeasibility_requirement_ids": main_infeasible_ids,
                "tail_access_witness_existence_unresolved": any(
                    "ROUTE_SEARCH_BUDGET_EXHAUSTION" in row["failure_classes"] for row in failures
                ),
                "failure_details": failures,
            }
        )

    route_exhaustions = [
        row
        for candidate in candidates
        for row in candidate["access_rows"]
        if "ROUTE_SEARCH_EXHAUSTED" in row["codes"]
    ]
    route_sensitivity: dict[str, Any] = {
        "executed": False,
        "reason": "NO_ROUTE_SEARCH_EXHAUSTED_FAILURE",
        "production_route_node_budget": route_budget,
        "candidate_requirement_runs": [],
        "route_budget_causal": False,
    }
    if route_exhaustions:
        route_sensitivity["executed"] = True
        route_sensitivity["reason"] = "ROUTE_SEARCH_EXHAUSTED_PRESENT"
        route_sensitivity["candidate_requirement_runs"] = []
        route_sensitivity["route_budget_causal"] = False
        for candidate in candidates:
            context = context_cache[candidate["candidate_hash"]]
            requirements = {
                str(row["identity"]): row for row in candidate["p2d"].get("access_requirements", [])
            }
            for access_row in candidate["access_rows"]:
                if "ROUTE_SEARCH_EXHAUSTED" not in access_row["codes"]:
                    continue
                requirement = requirements[access_row["requirement_identity"]]
                if requirement.get("flow_kind") == "TRUCK":
                    continue
                measurements = []
                for budget in (route_budget, route_budget * 2, route_budget * 4):
                    routed, _ = access_domain.route_access_requirement(
                        requirement,
                        relationships=context["relationships"],
                        zones=context["zones"],
                        boundary=context["boundary"],
                        obstacles=context["obstacles"],
                        entrances=context["entrances"],
                        route_node_budget=budget,
                    )
                    measurements.append(
                        {
                            "route_node_budget": budget,
                            "status": routed.get("status"),
                            "codes": routed.get("codes", []),
                        }
                    )
                causal = any(item["status"] == "PASS" for item in measurements[1:])
                route_sensitivity["route_budget_causal"] = (
                    route_sensitivity["route_budget_causal"] or causal
                )
                route_sensitivity["candidate_requirement_runs"].append(
                    {
                        "candidate_hash": candidate["candidate_hash"],
                        "skeleton_hash": candidate["skeleton_hash"],
                        "requirement_identity": access_row["requirement_identity"],
                        "measurements": measurements,
                        "route_budget_causal": causal,
                    }
                )

    selected_layout = state["tool_result"].get("layout", {})
    p2d_target_counts = {
        label: {
            "candidate_count": len(rows),
            "pass_counts": [row["access_pass_count"] for row in rows],
            "fail_counts": [row["access_fail_count"] for row in rows],
            "blocked_counts": [row["access_blocked_count"] for row in rows],
        }
        for label, rows in target_candidates.items()
    }
    root_cause_categories = sorted(
        {
            category
            for row in target_root_causes
            for failure in row["failure_details"]
            for category in failure["failure_classes"]
        }
    )
    any_main_infeasible = any(
        row["main_skeleton_access_infeasibility_proven"] for row in target_root_causes
    )
    any_tail_occlusion = any(
        failure["failure_disappears_when_unrelated_tail_removed"]
        for row in target_root_causes
        for failure in row["failure_details"]
    )
    if route_sensitivity["route_budget_causal"]:
        next_path = "ACCESS_ROUTE_SEARCH_COVERAGE_REVIEW"
    elif any_main_infeasible:
        next_path = "MAIN_SKELETON_ACCESS_NECESSARY_PREFLIGHT"
    elif any_tail_occlusion or root_cause_categories:
        next_path = "ACCESS_AWARE_TAIL_SEARCH"
    else:
        next_path = "MIXED"

    replay_summary = {
        "tool7_ok": state["tool_result"].get("ok"),
        "project_layout_validated": selected_layout.get("project_layout_validated"),
        "p2_complete": selected_layout.get("p2_complete"),
        "selected_layout_canonical_result_hash": selected_layout.get("canonical_result_hash"),
        "selected_svg_sha256": state["tool_result"].get("drawing", {}).get("svg_sha256"),
        "complete_p2c_capture_count": len(candidates),
        "target_skeleton_counts": p2d_target_counts,
        "access_requirement_count_each": sorted({len(row["access_rows"]) for row in candidates}),
        "route_node_budget": route_budget,
    }
    candidate_access = {
        "identity": "v222-p1a-r12-real-tool7-candidate-access-matrix@1.0.0",
        "source": (
            "real canonical Xinzhao Tool 7 replay; process-local observers "
            "delegate to original P2C/P2D functions"
        ),
        "fixture_path": "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json",
        "replay": replay_summary,
        "candidates": matrix_candidates,
    }
    failed_requirements = {
        "identity": "v222-p1a-r12-failed-requirement-matrix@1.0.0",
        "matrix_dimensions": ["candidate", "requirement", "status", "failure_codes"],
        "rows": failed_matrix,
        "failed_rows": [row for row in failed_matrix if row["status"] != "PASS"],
    }
    portal_trace = {
        "identity": "v222-p1a-r12-portal-route-failure-trace@1.0.0",
        "route_node_budget": route_budget,
        "portal_pair_count": sum(row["portal_pair_count"] for row in topology_trace),
        "portal_pair_pass_count": sum(row["portal_pair_pass_count"] for row in topology_trace),
        "portal_pair_failure_counts": dict(
            sorted(
                sum(
                    (Counter(row["portal_pair_failure_counts"]) for row in topology_trace),
                    Counter(),
                ).items()
            )
        ),
        "requirements": topology_trace,
    }
    variant_comparison = {
        "identity": "v222-p1a-r12-tail-variant-access-comparison@1.0.0",
        "tail_zone_codes_compared": list(TAIL_ZONE_CODES),
        "skeletons": variant_rows,
    }
    counterfactual = {
        "identity": "v222-p1a-r12-main-skeleton-access-counterfactual@1.0.0",
        "method": (
            "real planar route_access_requirement or truck "
            "validate_truck_maneuver_chain on captured candidate geometry; "
            "preserve all seven main zones and any tail endpoint zone, "
            "omit other tail zones"
        ),
        "rows": counterfactual_rows,
    }
    root_cause = {
        "identity": "v222-p1a-r12-access-root-cause@1.0.0",
        "targets": target_root_causes,
        "failure_categories_observed": root_cause_categories,
        "packaging_access_failure_present": any(
            "packaging_material_storage" in {row.get("from_ref"), row.get("to_ref")}
            for target in target_root_causes
            for row in target["failure_details"]
        ),
        "personnel_access_failure_present": "PERSONNEL_ACCESS_CONFLICT" in root_cause_categories,
        "main_flow_access_failure_present": "MAIN_FLOW_ACCESS_CONFLICT" in root_cause_categories,
        "portal_width_failure_present": "PORTAL_WIDTH_CONFLICT" in root_cause_categories,
        "edge_orientation_failure_present": "EDGE_ORIENTATION_CONFLICT" in root_cause_categories,
        "corridor_geometry_failure_present": "CORRIDOR_GEOMETRY_CONFLICT" in root_cause_categories,
        "route_search_exhaustion_present": bool(route_exhaustions),
        "route_budget_sensitivity": route_sensitivity,
        "route_budget_causal": route_sensitivity["route_budget_causal"],
        "next_implementation_path": next_path,
        "diagnostic_only": True,
        "runtime_changed": False,
    }
    return {
        "xinzhao_p1a_r12_candidate_access_matrix.json": candidate_access,
        "xinzhao_p1a_r12_failed_requirement_matrix.json": failed_requirements,
        "xinzhao_p1a_r12_portal_route_failure_trace.json": portal_trace,
        "xinzhao_p1a_r12_tail_variant_access_comparison.json": variant_comparison,
        "xinzhao_p1a_r12_main_skeleton_access_counterfactual.json": counterfactual,
        "xinzhao_p1a_r12_access_root_cause.json": root_cause,
    }


def write_r12_evidence() -> dict[str, Any]:
    payloads = _evidence_payloads()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        _json_write(EVIDENCE_DIR / name, payload)
    return payloads


if __name__ == "__main__":
    written = write_r12_evidence()
    print(json.dumps({"written": sorted(written)}, ensure_ascii=False))
