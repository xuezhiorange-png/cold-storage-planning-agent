"""Source-bound, read-only H5 counterfactual overlay. Never an acceptance gate."""

import json
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.functional_sizing_handoff import (
    preview_functional_sizing_handoff,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    HISTORICAL,
    HISTORICAL_FILES,
    checked_bytes,
)
from cold_storage.modules.layout.domain.access_routing import derive_building_footprint
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_fit import Rect, area
from cold_storage.modules.layout.domain.functional_site_impact import (
    IDENTITY,
    contact_report,
    expansion_bands,
    orthogonal_tiles,
    polygon_metrics,
    polygon_of,
    rectangular_union_area,
)
from cold_storage.modules.layout.domain.functional_sizing_advisory import area_text
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    normalize_segment,
    polygon_contains_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_share_positive_edge,
    segment_on_polygon_boundary,
)

TASK = "V2_2_2_R11_R12_FUNCTIONAL_ROOM_SITE_IMPACT_REVIEW_R1"
BASE_HEAD = "5a652a05afa438bd43631b7ffdaf4b541899c8ca"
R11_PATH = "docs/previews/v2.2.2/r11-r11-functional-sizing-advisory-r1"
R11_MANIFEST_SHA256 = "466493b55ec70d1d143a05fe60598613348c676ca35bc37ec7d8a0384f7edaac"
RECORDS = ("P01", "P02")


def _polygon(raw: Any) -> PolygonMM:
    return normalize_polygon(raw, allow_numeric_string=True)


def _zone(row: Mapping[str, Any]) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        str(row["zone_code"]),
        Decimal(str(row["x"])),
        Decimal(str(row["y"])),
        Decimal(str(row["width_m"])),
        Decimal(str(row["depth_m"])),
        rotation_deg=row["rotation_deg"],
    )


def _segment(raw: Mapping[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    return normalize_segment(
        {
            end: {axis: Decimal(str(value)) for axis, value in point.items()}
            for end, point in raw.items()
        }
    )


def _object(raw: Any, reference: str, *, footprint: Any = None) -> dict[str, Any]:
    return dict(
        id=reference,
        reference=reference,
        object_hash=canonical_hash(raw),
        polygon_mm=[list(p) for p in _polygon(footprint if footprint is not None else raw)],
        boxes_mm=[list(b) for b in orthogonal_tiles(_polygon(footprint or raw))],
    )


def _scene(candidate: dict[str, Any], site: dict[str, Any], path: str) -> dict[str, Any]:
    ev = candidate["engineering_validation"]
    zones = {r["zone_code"]: _zone(r) for r in ev["zones"]}
    if len(ev["zones"]) != len(ZONE_CODES) or set(zones) != set(ZONE_CODES):
        raise ValueError("SITE_IMPACT_FULL_ROLE_SET_REQUIRED")
    interfaces = candidate["composition_handoff"]["mandatory_hard_interfaces"]
    if (
        len(interfaces) != len(process_graph().must_adjacencies)
        or {frozenset((v["endpoint_a_role"], v["endpoint_b_role"])) for v in interfaces}
        != {frozenset(pair) for pair in process_graph().must_adjacencies}
        or any(v["source_graph_identity"] != process_graph().identity for v in interfaces)
    ):
        raise ValueError("SITE_IMPACT_ORIGINAL_PROCESS_GRAPH_MISMATCH")
    zone_records = [
        dict(
            id=role,
            reference=f"{path}#/engineering_validation/zones/{i}",
            object_hash=canonical_hash(row),
            bounds_mm=list(zones[role].bounds_mm),
            boxes_mm=[list(zones[role].bounds_mm)],
            original_row=deepcopy(row),
        )
        for i, row in enumerate(ev["zones"])
        for role in [row["zone_code"]]
    ]
    corridors: list[dict[str, Any]] | None = [] if isinstance(ev.get("corridors"), list) else None
    if corridors is not None:
        expected = {
            r["requirement_identity"]
            for r in ev["access_results"]
            if r.get("topology") == "CORRIDOR_MEDIATED" and r["flow_kind"] != "TRUCK"
        }
        if {r["requirement_identity"] for r in ev["corridors"]} != expected:
            corridors = None
    if corridors is not None:
        for i, corridor in enumerate(ev["corridors"]):
            requirement = corridor["requirement_identity"]
            matches = [r for r in ev["access_results"] if r["requirement_identity"] == requirement]
            if len(matches) != 1 or any(
                corridor[k] != matches[0][v]
                for k, v in (
                    ("envelope", "corridor_envelope"),
                    ("centerline", "centerline"),
                    ("clear_width_m", "clear_width_m"),
                )
            ):
                raise ValueError("SITE_IMPACT_CORRIDOR_SOURCE_CONTRADICTION")
            for j, envelope in enumerate(corridor["envelope"]):
                obj = _object(
                    envelope, f"{path}#/engineering_validation/corridors/{i}/envelope/{j}"
                )
                obj.update(
                    requirement_identity=requirement,
                    clear_width_m=corridor["clear_width_m"],
                    clear_width_mm=int(Decimal(corridor["clear_width_m"]) * 1000),
                )
                corridors.append(obj)
    return dict(
        zones=zones,
        zone_records=zone_records,
        corridors=corridors,
        site=site,
        access_results=ev["access_results"],
        raw=candidate,
        reference=path,
    )


def _site_impact(bands: list[Rect], expanded: Rect, site: Mapping[str, Any]) -> dict[str, Any]:
    boundaries: dict[str, Any] = {}
    for key in ("site_boundary", "buildable_boundary", "effective_buildable_boundary"):
        raw = site.get("site", {}).get(key)
        boundaries[key] = (
            dict(
                status="WITHIN_ARCHIVED_BOUNDARY"
                if polygon_contains_polygon(_polygon(raw), polygon_of(expanded))
                else "OUTSIDE_ARCHIVED_BOUNDARY_DETECTED",
                polygon_mm=[list(p) for p in _polygon(raw)],
                reference=f"{HISTORICAL}/server-authorities.json#/site/site/{key}",
                object_hash=canonical_hash(raw),
            )
            if raw is not None
            else dict(status="NOT_EVALUATED", reason="ARCHIVED_BOUNDARY_MISSING")
        )
        if raw is not None:
            inside = contact_report(bands, [_object(raw, boundaries[key]["reference"])])
            outside = sum(area(b) for b in bands) - inside["unique_intersection_area_mm2"]
            boundaries[key].update(
                added_outside_area_mm2=outside,
                added_outside_area_m2=area_text(outside),
            )
    obstacles = {}
    for key in (
        "hard_obstacles",
        "no_build_zones",
        "existing_buildings",
        "conditional_removal_footprints",
    ):
        raw = site.get("obstacles", {}).get(key)
        objects = None
        if isinstance(raw, list):
            objects = [
                _object(
                    obj,
                    f"{HISTORICAL}/server-authorities.json#/site/obstacles/{key}/{i}",
                    footprint=obj.get("footprint")
                    if isinstance(obj, dict) and "footprint" in obj
                    else None,
                )
                for i, obj in enumerate(raw)
            ]
        result = contact_report(bands, objects)
        if objects is not None:
            result["archived_objects"] = objects
            result["closed_contact_object_ids"] = [
                obj["id"]
                for obj in objects
                if rectangle_intersects_closed_obstacle(
                    PlacedRectangleV1(
                        "EXPANSION_DIAGNOSTIC",
                        Decimal(expanded[0]) / 1000,
                        Decimal(expanded[1]) / 1000,
                        Decimal(expanded[2] - expanded[0]) / 1000,
                        Decimal(expanded[3] - expanded[1]) / 1000,
                    ),
                    tuple(tuple(p) for p in obj["polygon_mm"]),
                )
            ]
        obstacles[key] = result
    hard_groups = [obstacles[k] for k in ("hard_obstacles", "no_build_zones")]
    unique = (
        rectangular_union_area(
            [
                tuple(box)
                for group in hard_groups
                for contact in group["contacts"]
                for box in contact["intersection_rectangles_mm"]
            ]
        )
        if all(group["status"] != "NOT_EVALUATED" for group in hard_groups)
        else None
    )
    return dict(
        boundaries=boundaries,
        obstacles=obstacles,
        unique_hard_and_no_build_intersection_area_mm2=unique,
        unique_hard_and_no_build_intersection_area_m2=area_text(unique)
        if unique is not None
        else "NOT_EVALUATED",
        engineering_acceptance="NOT_EVALUATED",
    )


def _footprint(scene: dict[str, Any], updated: dict[str, PlacedRectangleV1]) -> dict[str, Any]:
    ev = scene["raw"]["engineering_validation"]
    if scene["corridors"] is None or not isinstance(ev.get("building_footprint"), dict):
        return dict(status="NOT_EVALUATED", reason="FOOTPRINT_OR_CORRIDOR_EVIDENCE_MISSING")
    corridors = tuple(tuple(tuple(p) for p in obj["polygon_mm"]) for obj in scene["corridors"])
    archived = _polygon(ev["building_footprint"]["footprint"])
    derived = derive_building_footprint(scene["zones"], corridors)
    if not (
        polygon_contains_polygon(archived, derived)
        and polygon_contains_polygon(derived, archived)
        and area_text(polygon_metrics(archived)["area_mm2"])
        == format(Decimal(ev["building_footprint"]["gross_area_m2"]), ".6f")
    ):
        raise ValueError("SITE_IMPACT_ARCHIVED_FOOTPRINT_UNION_MISMATCH")
    expanded = derive_building_footprint(updated, corridors)
    before, after = polygon_metrics(archived), polygon_metrics(expanded)
    topology = inspect_rectangular_union(
        [z.bounds_mm for z in updated.values()]
        + [tuple(b) for obj in scene["corridors"] for b in obj["boxes_mm"]]
    )
    delta = {
        k: after[k] - before[k]
        for k in ("area_mm2", "perimeter_mm", "turn_count", "concave_corner_count")
    }
    delta["area_m2"] = area_text(delta["area_mm2"])
    return dict(
        status="EXACT_SUPERPOSITION_ONLY_NOT_ENGINEERING_ACCEPTANCE",
        archived=before,
        hypothetical_union=after,
        delta=delta,
        topology=topology,
        archived_union_reproduced=True,
        overlap_is_not_removed_from_room=True,
        revalidation_required=[
            "BUILDING_FOOTPRINT",
            "SITE",
            "ACCESS",
            "ADJACENT_PROCESS",
            "ENGINEERING_ACCEPTANCE",
        ],
    )


def _access_impact(
    scene: dict[str, Any], expanded: Rect, advisory: dict[str, Any], collisions: dict[str, Any]
) -> list[dict[str, Any]]:
    original = scene["zones"]["changing_room"].bounds_mm
    mappings = {m["original"]["id"]: m for m in advisory["external_impact"]["portal_mappings"]}
    affected = []
    for index, r in enumerate(scene["access_results"]):
        if "changing_room" not in (r["from_ref"], r["to_ref"]):
            continue
        old = r["portal_from"] if r["from_ref"] == "changing_room" else r["portal_to"]
        old_segment = _segment(old["segment"])
        mapping = mappings[old["identity"]]
        original_segment = tuple(
            (original[0] + p[0], original[1] + p[1]) for p in mapping["original"]["segment_mm"]
        )
        if old_segment != tuple(sorted(original_segment)):
            raise ValueError("SITE_IMPACT_ORIGINAL_PORTAL_MAPPING_MISMATCH")
        mapped = mapping["mapped"]
        new_segment = tuple((original[0] + p[0], original[1] + p[1]) for p in mapped["segment_mm"])
        overlap = [
            c
            for c in collisions["contacts"]
            if any(
                o["id"] == c["object_id"] and o["requirement_identity"] == r["requirement_identity"]
                for o in scene["corridors"] or []
            )
        ]
        changed = old_segment != tuple(sorted(new_segment))
        affected.append(
            dict(
                requirement_identity=r["requirement_identity"],
                source_access_hash=r["canonical_hash"],
                reference=scene["reference"] + f"#/engineering_validation/access_results/{index}",
                portal_identity=old["identity"],
                mapped_portal_identity=mapped["id"],
                original_portal_segment_mm=[list(p) for p in old_segment],
                hypothetical_portal_segment_mm=[list(p) for p in new_segment],
                clear_width_mm=int(Decimal(old["clear_width_m"]) * 1000),
                portal_mapped=changed,
                mapped_portal_on_counterfactual_boundary=segment_on_polygon_boundary(
                    new_segment[0], new_segment[1], polygon_of(expanded)
                ),
                archived_portal_still_on_counterfactual_boundary=segment_on_polygon_boundary(
                    old_segment[0], old_segment[1], polygon_of(expanded)
                ),
                corridor_intersection_detected=bool(overlap),
                corridor_redesign_required=changed or bool(overlap),
                status="NOT_EVALUATED_MISSING_CORRIDOR_EVIDENCE"
                if r["topology"] == "CORRIDOR_MEDIATED" and scene["corridors"] is None
                else "ARCHIVED_CORRIDOR_INTERSECTION_DETECTED"
                if overlap
                else "ARCHIVED_PORTAL_MAPPING_REQUIRES_REVALIDATION"
                if changed
                else "ARCHIVED_RELATION_UNCHANGED_IN_CHECKED_INPUTS",
                original_centerline=deepcopy(r["centerline"]),
                original_route_length_m=r["route_length_m"],
                future_route_length_m="NOT_EVALUATED",
                full_access_revalidated=False,
            )
        )
    return affected


def _overlay_status(proposal: dict[str, Any]) -> str:
    reports = [proposal["zone_intersections"], proposal["corridor_intersections"]]
    reports += [proposal["site"]["obstacles"][k] for k in ("hard_obstacles", "no_build_zones")]
    if any(report["contacts"] for report in reports):
        return "POSITIVE_AREA_INTERSECTION_DETECTED"
    boundaries = proposal["site"]["boundaries"].values()
    if any(b["status"] == "OUTSIDE_ARCHIVED_BOUNDARY_DETECTED" for b in boundaries):
        return "OUTSIDE_ARCHIVED_BOUNDARY_DETECTED"
    if any(r["status"] == "NOT_EVALUATED" for r in [*reports, *boundaries]):
        return "NOT_EVALUATED"
    if any(report.get("closed_contact_object_ids") for report in reports):
        return "CLOSED_HARD_OBSTACLE_CONTACT_REQUIRES_REVIEW"
    return "NO_POSITIVE_INTERSECTION_IN_CHECKED_INPUTS"


def _matrix_row(record: str, proposal: dict[str, Any]) -> dict[str, Any]:
    access = next(r for r in proposal["access"] if "main_entrance" in r["requirement_identity"])
    return dict(
        record=record,
        label=proposal["label"],
        advisory_id=proposal["advisory_id"],
        additional_room_area_m2=proposal["additional_room_area_m2"],
        other_zone_overlap_m2=proposal["zone_intersections"].get(
            "unique_intersection_area_m2", "NOT_EVALUATED"
        ),
        corridor_overlap_m2=proposal["corridor_intersections"].get(
            "unique_intersection_area_m2", "NOT_EVALUATED"
        ),
        prohibited_overlap_m2=proposal["site"]["unique_hard_and_no_build_intersection_area_m2"],
        effective_boundary=proposal["site"]["boundaries"]["effective_buildable_boundary"]["status"],
        net_footprint_increase_m2=proposal["footprint"]
        .get("delta", {})
        .get("area_m2", "NOT_EVALUATED"),
        entrance_access=access["status"],
        corridor_redesign_required=access["corridor_redesign_required"],
        preserved_must_edge_count=sum(
            r["positive_shared_edge"] for r in proposal["must_adjacencies"]
        ),
        must_edge_count=len(proposal["must_adjacencies"]),
        truck_envelope="NOT_EVALUATED",
        final_factory_applicability="NOT_EVALUATED",
        checked_geometry_status=proposal["checked_geometry_status"],
    )


def review_functional_site_impact(
    files: Mapping[str, bytes],
    *,
    project_scope_id: str,
    candidate_records: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Only archived H5. No persistence, runtime solver, routing or approval port."""
    if set(candidate_records) != set(RECORDS):
        raise ValueError("SITE_IMPACT_BOTH_ARCHIVED_RECORDS_REQUIRED")
    manifest_name = f"{R11_PATH}/source-manifest.json"
    manifest = json.loads(checked_bytes(files, manifest_name, R11_MANIFEST_SHA256))
    for name, sha in manifest["derived_files"].items():
        checked_bytes(files, f"{R11_PATH}/{name}", sha)
    payloads = json.loads(files[f"{R11_PATH}/advisories.json"])
    preview = preview_functional_sizing_handoff(
        files,
        project_scope_id=project_scope_id,
        layout_candidates=[candidate_records[k] for k in RECORDS],
        advisory_payloads=payloads,
    )
    aliases = {
        a["record"]: a["candidate_hash"]
        for a in preview["advisories"][0]["physical_room"]["aliases"]
    }
    site = json.loads(files[f"{HISTORICAL}/server-authorities.json"])["site"]
    results = []
    for record, source in zip(RECORDS, HISTORICAL_FILES[2:], strict=True):
        candidate = candidate_records[record]
        if candidate["canonical_result_hash"] != aliases[record]:
            raise ValueError("SITE_IMPACT_CANDIDATE_RECORD_MISMATCH")
        path = f"{HISTORICAL}/{source}"
        scene = _scene(candidate, site, path)
        original = scene["zones"]["changing_room"].bounds_mm
        proposals = []
        for advisory in preview["advisories"]:
            room = advisory["advised_room"]
            expanded = (
                original[0],
                original[1],
                original[0] + room["length_mm"],
                original[1] + room["width_mm"],
            )
            bands = expansion_bands(original, expanded)
            boxes = [tuple(b["bounds_mm"]) for b in bands]
            zone_contacts = contact_report(
                boxes, [z for z in scene["zone_records"] if z["id"] != "changing_room"]
            )
            corridor_contacts = contact_report(boxes, scene["corridors"])
            updated = dict(scene["zones"])
            updated["changing_room"] = PlacedRectangleV1(
                "changing_room",
                Decimal(original[0]) / 1000,
                Decimal(original[1]) / 1000,
                Decimal(room["length_mm"]) / 1000,
                Decimal(room["width_mm"]) / 1000,
            )
            must = [
                dict(
                    roles=[v["endpoint_a_role"], v["endpoint_b_role"]],
                    source_edge_identity=v["source_edge_identity"],
                    positive_shared_edge=rectangles_share_positive_edge(
                        updated[v["endpoint_a_role"]], updated[v["endpoint_b_role"]]
                    ),
                )
                for v in candidate["composition_handoff"]["mandatory_hard_interfaces"]
            ]
            proposals.append(
                dict(
                    advisory_id=room["id"],
                    label=room["label"],
                    advisory_hash=advisory["advisory_hash"],
                    witness_sha256=advisory["functional_evidence"]["witness_sha256"],
                    conditions=advisory["conditions"],
                    original_room_bounds_mm=list(original),
                    expanded_room_bounds_mm=list(expanded),
                    expansion_bands=bands,
                    additional_room_area_mm2=advisory["advised_room"]["additional_area_mm2"],
                    additional_room_area_m2=advisory["advised_room"]["additional_area_m2"],
                    zone_intersections=zone_contacts,
                    corridor_intersections=corridor_contacts,
                    site=_site_impact(boxes, expanded, site),
                    footprint=_footprint(scene, updated),
                    access=_access_impact(scene, expanded, advisory, corridor_contacts),
                    must_adjacencies=must,
                    must_definition_changed=False,
                    truck_envelope_impact=dict(
                        status="NOT_EVALUATED",
                        reason="ARCHIVED_TRUCK_ROUTE_NOT_VALIDATED",
                        archived_status=candidate["engineering_validation"]["truck_route_status"],
                        archived_envelope_count=len(
                            candidate["engineering_validation"].get("truck_envelopes", [])
                        ),
                    ),
                    unarchived_occupancy=dict(
                        status="NOT_EVALUATED", reason="NO_INFERENCE_ABOUT_UNRECORDED_OBJECTS"
                    ),
                    whole_factory_acceptance="NOT_EVALUATED",
                    engineering_approval="NOT_EVALUATED",
                    functional_status="INPUT_REQUIRED",
                )
            )
        results.append(
            dict(
                record=record,
                candidate_hash=candidate["canonical_result_hash"],
                source_file=path,
                source_sha256=manifest["source_files"][path],
                zones=scene["zone_records"],
                corridors=scene["corridors"],
                archived_portals=deepcopy(candidate["engineering_validation"]["portals"]),
                portal_geometries=[
                    dict(
                        id=p["identity"],
                        reference=f"{path}#/engineering_validation/portals/{i}",
                        object_hash=canonical_hash(p),
                        segment_mm=[list(v) for v in _segment(p["segment"])],
                        clear_width_mm=int(Decimal(p["clear_width_m"]) * 1000),
                    )
                    for i, p in enumerate(candidate["engineering_validation"]["portals"])
                ],
                proposals=proposals,
                historical_engineering_status="PRESERVED",
            )
        )
    for checked_record in results:
        for proposal in checked_record["proposals"]:
            proposal["checked_geometry_status"] = _overlay_status(proposal)
    return dict(
        identity=IDENTITY,
        task=TASK,
        base_head=BASE_HEAD,
        project_scope_id=project_scope_id,
        physical_room_id=preview["physical_room_id"],
        physical_room_count=1,
        independently_checked_records=2,
        records=results,
        impact_matrix=[_matrix_row(r["record"], p) for r in results for p in r["proposals"]],
        additional_area_counting="ONE_PHYSICAL_ROOM_PER_SCHEME_NOT_SUM_OF_P01_P02",
        owner_confirmed_inputs=deepcopy(preview["owner_confirmed_inputs"]),
        owner_confirmation_checklist=deepcopy(preview["owner_confirmation_checklist"]),
        owner_parameter_template=dict(
            project_scope_id=project_scope_id,
            state="UNREVIEWED_TEMPLATE_NOT_AUTHORITY",
            reviewed_inputs=deepcopy(preview["owner_confirmed_inputs"]),
            dimensions_and_operation={
                key: dict(
                    value=None,
                    unit="mm"
                    if key.endswith("_mm")
                    else "count"
                    if key == "columns_per_unit"
                    else "enum",
                    status="INPUT_REQUIRED",
                )
                for key in preview["advisories"][0]["conditions"]["parameters"]
            },
            checklist=[
                dict(id=row["id"], value=None, status="INPUT_REQUIRED")
                for row in preview["owner_confirmation_checklist"]
            ],
            review_mechanism="EXISTING_PROJECT_REVIEW_REQUIRED_NO_APPROVAL_FROM_JSON_LABELS",
        ),
        source_hashes={
            **manifest["source_files"],
            **{f"{R11_PATH}/{n}": s for n, s in manifest["derived_files"].items()},
            manifest_name: R11_MANIFEST_SHA256,
        },
        calculation_basis=dict(
            version=IDENTITY,
            units="INTEGER_MM_AND_MM2",
            coefficients=[],
            input_reference="records[].zones / corridors / source_file and archived Site hashes",
            assumptions=[
                "Other archived rooms, corridors and Site objects remain fixed "
                "for this overlay only",
                "Counterfactual dimensions retain unapproved R10/R11 conditions",
                "No inference about missing Truck or unarchived occupancy",
            ],
            predicates="EXISTING_EXACT_RECTANGLE_COVERAGE_SITE_CONTAINMENT_AND_FOOTPRINT_UNION",
            formulas=[
                "intersection_mm2=max(0,min(right)-max(left))*max(0,min(top)-max(bottom))",
                "new_room_area=union(disjoint_north_and_east_bands)",
                "footprint_delta=area(archived_rooms_and_corridors_plus_expansion)-archived_footprint_area",
            ],
            review_status="REQUIRES_ENGINEERING_REVIEW",
        ),
        warnings=[
            "OVERLAY_IS_NOT_ENGINEERING_ACCEPTANCE",
            "TRUCK_AND_UNARCHIVED_OCCUPANCY_NOT_EVALUATED",
            "EXTERNAL_ACCESS_NOT_REPLANNED_OR_REVALIDATED",
            "HYPOTHETICAL_FUNCTIONAL_PARAMETERS_REQUIRE_OWNER_REVIEW",
        ],
        final_factory_applicability="NOT_EVALUATED",
        external_routes_replanned=False,
        modifies_authority=False,
        changes_historical_status=False,
        native_solves=0,
        main_executed=False,
    )
