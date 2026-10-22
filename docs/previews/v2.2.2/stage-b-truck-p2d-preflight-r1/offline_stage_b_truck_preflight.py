"""Read sealed Stage B facts and existing Truck contracts. Never search or approve.

R13 has no public input-only entry: its preview entry performs a native search.
This sidecar calls only its existing pure document/body predicates, plus original
P1F/P2B1/P2D loading-face predicates. It is a necessary-input preflight, NOT a
second Truck validator or an approval service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from cold_storage.modules.layout.application.access_routing import (
    SiteAccessRoutingResultV1,
    _rectangle_from_row,
    _validate_loading_face,
    _validate_selected_loading_face,
)
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain import truck_parameter_input as r13
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.project_truck_input import (
    LENGTH_FIELDS,
    REFERENCE_FIELDS,
    validate_project_truck_input,
)
from cold_storage.modules.layout.domain.site_geometry import normalize_polygon
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_REVERSE,
    validate_truck_maneuver_project_binding,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASELINE = HERE.parent / "stage-b/layout-quality-baseline-01"
REFERENCE_HEAD = "64537de0c8fe146277bbb28d9b995dfc27ab3ba3"
IDENTITY = "StageBTruckP2DPreflightV1"
VERSION = "stage-b-truck-p2d-preflight@1.0.0"
CATALOG_SHA = "5e616effe7d7f484987dc30f9112cc6a3194533b06569438868e7a7c452d4cc2"
BASELINE_MANIFEST_SHA = "b0432814a870e824fca7d91df580e50bf33fae83da5471ec4c386c3f887b6e24"
RAW_GROUPS = {
    "multi-solution-validation-01": "stage-b-real-multi-solution-validation-01",
    "guided-fair-validation-02": "stage-b-real-guided-fair-validation-02",
}


def encode(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    ).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LayoutAuthorityError(code)


def read(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw)
    require(isinstance(value, dict), "PREFLIGHT_OBJECT_REQUIRED")
    return cast(dict[str, Any], value)


def load_sealed(artifact_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fixed Git-pinned catalogue; explicit raw files only, not archive/Grant scanning."""
    raw = (BASELINE / "source_manifest.json").read_bytes()
    require(sha(raw) == BASELINE_MANIFEST_SHA, "BASELINE_MANIFEST_CHANGED")
    for relative, item in read(raw)["files"].items():
        require(
            sha((BASELINE / relative).read_bytes()) == item["sha256"],
            "SEALED_BASELINE_FILE_CHANGED:" + relative,
        )
    catalog_raw = (BASELINE / "sources.json").read_bytes()
    require(sha(catalog_raw) == CATALOG_SHA, "TRUSTED_CANDIDATE_CATALOG_CHANGED")
    catalog = read(catalog_raw)
    authorities_raw = (BASELINE / "inputs/server_authorities.json").read_bytes()
    require(sha(authorities_raw) == catalog["authority_sha256"], ("FROZEN_AUTHORITY_BYTES_CHANGED"))
    rows = []
    for item in catalog["candidates"]:
        projection_raw = (BASELINE / item["input"]).read_bytes()
        require(
            sha(projection_raw) == item["projection_sha256"], ("CANDIDATE_PROJECTION_HASH_MISMATCH")
        )
        projection = read(projection_raw)
        group, candidate = item["candidate_id"].split("/")
        original_path = (
            artifact_root / RAW_GROUPS[group] / "real-execution/main" / candidate / "candidate.json"
        )
        original_raw = original_path.read_bytes()
        require(
            sha(original_raw) == item[("raw_candidate_sha256")], ("RAW_CANDIDATE_HASH_MISMATCH")
        )
        original = read(original_raw)
        for key in (
            "engineering_validation",
            "composition_handoff",
            "independent_validation",
            "native_independent_validation",
            "canonical_result_hash",
        ):
            require(original[key] == projection[key], ("RAW_CANDIDATE_PROJECTION_SUBTREE_MISMATCH"))
        require(
            canonical_hash({k: v for k, v in original.items() if k != ("canonical_result_hash")})
            == original["canonical_result_hash"],
            "RAW_CANDIDATE_CANONICAL_HASH_MISMATCH",
        )
        require(
            sha((REPO / item["svg_path"]).read_bytes()) == item["svg_sha256"],
            "HISTORICAL_SVG_HASH_MISMATCH",
        )
        rows.append(
            {
                "catalog": item,
                "projection": projection,
                "raw": original,
                "raw_path_reference": "PROJECT_ARTIFACTS/"
                + RAW_GROUPS[group]
                + "/real-execution/main/"
                + candidate
                + "/candidate.json",
            }
        )
    require(
        len(rows) == 8 and len({x["catalog"]["candidate_id"] for x in rows}) == 8,
        "EXACT_EIGHT_CANDIDATES_REQUIRED",
    )
    return read(authorities_raw), rows


def frozen_p1f(p1: dict[str, Any]) -> dict[str, Any]:
    """Decode only the canonical P1F snapshot, as original binding decoder does."""
    source = json.loads(p1["project_status"]["validated_input_canonical_json"])
    for field in LENGTH_FIELDS:
        if isinstance(source.get(field), str):
            source[field] = Decimal(source[field])
    validated = validate_project_truck_input(source)
    require(validated["status"] == "COMPLETE", "FROZEN_P1F_SNAPSHOT_INVALID")
    require(
        validated["validated_input_canonical_json"]
        == p1["project_status"]["validated_input_canonical_json"],
        "FROZEN_P1F_CANONICAL_MISMATCH",
    )
    return cast(dict[str, Any], source)


def entrance_facts(site: dict[str, Any]) -> dict[str, Any]:
    segment = site["entrances"]["truck_entrance"]
    a, b = routing._segment_from_mapping(segment, field="typed_site.truck_entrance")
    axis_aligned = a[0] == b[0] or a[1] == b[1]
    # Manhattan equals exact length only for these axis-aligned segments.
    length = routing._segment_length_mm((a, b)) if axis_aligned else None
    return {
        "SITE_TRUCK_ENTRANCE_SEGMENT": segment,
        "LENGTH_MM": length,
        "LENGTH_M": str(Decimal(length) / 1000) if length is not None else None,
        "AXIS_ALIGNED": axis_aligned,
        "RUNTIME_SEMANTICS": "ENTRY_REFERENCE_POINT_SEARCH_LOCUS",
        "PHYSICAL_GATE_SEMANTICS": "UNCONFIRMED_UPSTREAM_INPUT_NOT_MEASURED_OPENING_PROOF",
        "MEASURED_GATE_CLEAR_OPENING": None,
        "MEASURED_GATE_STATUS": "UNAVAILABLE",
        "R13_CLEAR_OPENING_SEGMENT": None,
        "AUTOMATIC_SEGMENT_ENLARGEMENT_ALLOWED": False,
    }


def historical_truck_state(engineering: dict[str, Any]) -> str:
    if engineering.get("p2_complete") is True:
        return "HISTORICAL_P2D_COMPLETE_CLAIM_REQUIRES_FULL_SOURCE_REVIEW"
    if engineering.get("truck_route_status") == "REQUIRES_ENGINEERING_REVIEW" or engineering.get(
        ("personnel_truck_evaluation"), {}
    ).get("status") == ("REQUIRES_ENGINEERING_REVIEW"):
        return "TRUCK_ROUTE_ENGINEERING_REVIEW_REQUIRED"
    if engineering.get("truck_route_validated") is True:
        return "TRUCK_ROUTE_VALIDATED_NOT_P2D_FULL_PASS"
    provenance = engineering.get("truck_search_provenance", {})
    if (
        engineering.get("source_truck_maneuver_binding_hash") is None
        and provenance.get("visited_nodes") == 0
    ):
        return "PROJECT_INPUT_BLOCKED"
    if provenance.get("visited_nodes", 0) > 0:
        return "TRUCK_SEARCH_EXECUTED_WITHOUT_VALIDATED_ROUTE_NOT_GLOBAL_INFEASIBILITY"
    return "TRUCK_STATUS_UNDETERMINED"


def loading_face(engineering: dict[str, Any]) -> dict[str, Any]:
    row = next(z for z in engineering["zones"] if z["zone_code"] == "shipping_channel")
    rectangle = _rectangle_from_row(row)
    segment = routing._segment_from_mapping(
        engineering["shipping_loading_face_segment"], field="loading_face"
    )
    _validate_loading_face(rectangle, segment)
    _validate_selected_loading_face(rectangle, engineering[("shipping_loading_face_side")], segment)
    r13_full = segment in tuple(
        s for _, kind, s in routing._edge_segments(rectangle) if kind == "LONG_EDGE"
    )
    return {
        "SHIPPING": row,
        "LOADING_FACE": engineering["shipping_loading_face_segment"],
        "LOADING_FACE_SIDE": engineering["shipping_loading_face_side"],
        "FACE_HASH": canonical_hash(
            (
                engineering["shipping_loading_face_side"],
                engineering["shipping_loading_face_segment"],
            )
        ),
        "P2D_SELECTED_LONG_EDGE_BINDING": "VALID_HISTORICAL_GEOMETRY_ONLY",
        "R13_FULL_LONG_EDGE_MATCH": r13_full,
        "PROJECT_DOCK_APPROVAL": "UNAVAILABLE",
    }


def audit_candidate(
    projection: dict[str, Any], expected: dict[str, Any], authorities: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "candidate_id": expected["candidate_id"],
        "CANDIDATE_PREFLIGHT_STATUS": "BLOCKED_SOURCE_OR_PROJECT_INPUT",
        "TRUCK_SEARCH_READY": False,
        "P2D_FULL_PASS": False,
        "REASON_CODES": [],
    }
    try:
        require(
            sha(encode(projection)) == expected["projection_sha256"],
            "CANDIDATE_PROJECTION_HASH_MISMATCH",
        )
        provenance = projection["provenance"]
        require(
            provenance["candidate_id"] == expected["candidate_id"]
            and provenance["raw_candidate_sha256"] == expected["raw_candidate_sha256"],
            "CANDIDATE_SOURCE_IDENTITY_MISMATCH",
        )
        engine = projection["engineering_validation"]
        # Original immutable result reader verifies serialization only, does not route.
        SiteAccessRoutingResultV1.from_mapping(engine)
        require(
            engine[("source_zone_plan_hash")] == canonical_hash(authorities["canonical_zone_plan"]),
            "CANDIDATE_PLAN_HASH_MISMATCH",
        )
        require(
            engine["source_p1_handoff_hash"] == canonical_hash(authorities["p1_handoff"]),
            "CANDIDATE_P1_HASH_MISMATCH",
        )
        require(
            engine["source_site_geometry_hash"] == canonical_hash(authorities["typed_site"]),
            "CANDIDATE_SITE_HASH_MISMATCH",
        )
        diversity = construction_diversity(engine["zones"])
        require(
            diversity["symmetry_invariant_geometry_hash"] == provenance["geometry_hash"],
            "CANDIDATE_PHYSICAL_GEOMETRY_IDENTITY_MISMATCH",
        )
        requirements = authorities["p1_handoff"][("p1e_historical_handoff")]["access_requirements"]
        expected_nontruck = {r["identity"] for r in requirements if r["flow_kind"] != "TRUCK"}
        nontruck = [r for r in engine["access_results"] if r["flow_kind"] != "TRUCK"]
        require(
            len(nontruck) == 11
            and {r["requirement_identity"] for r in nontruck} == expected_nontruck,
            "NON_TRUCK_REQUIREMENT_IDENTITIES_MISMATCH",
        )
        require(all(r["status"] == "PASS" for r in nontruck), ("HISTORICAL_NON_TRUCK_NOT_ALL_PASS"))
        independent = projection["independent_validation"]
        native = projection["native_independent_validation"]
        require(
            engine["zone_count"] == len(engine["zones"]) == independent["zone_count"] == 12,
            "HISTORICAL_ZONE_COUNT_MISMATCH",
        )
        require(
            independent["must_pass_count"] == 7
            and independent["pass"] is True
            and native["pass_count"] == 11
            and native["pass"] is True,
            "HISTORICAL_ENGINEERING_FACTS_INCONSISTENT",
        )
        face = loading_face(engine)
        context_hash = canonical_hash(
            {
                k: engine[k]
                for k in (
                    "zones",
                    "portals",
                    "corridors",
                    "building_footprint",
                    "shipping_loading_face_segment",
                    "shipping_loading_face_side",
                    "source_site_geometry_hash",
                )
            }
        )
        result.update(
            geometry_hash=provenance["geometry_hash"],
            source_application_hash=engine["canonical_result_hash"],
            candidate_canonical_hash=projection["canonical_result_hash"],
            source_candidate_sha256=expected["raw_candidate_sha256"],
            zone_count=12,
            must_pass_count=7,
            non_truck_access_pass_count=len(nontruck),
            NON_TRUCK_EVIDENCE_MODE="SEALED_RESULT_READBACK_NOT_REROUTED",
            non_truck_access_results=[
                {
                    "requirement_identity": r["requirement_identity"],
                    "status": r["status"],
                    "canonical_hash": r["canonical_hash"],
                }
                for r in nontruck
            ],
            truck_route_status=engine["truck_route_status"],
            truck_route_codes=engine["truck_route_codes"],
            source_truck_maneuver_binding_hash=engine["source_truck_maneuver_binding_hash"],
            truck_search_provenance=engine["truck_search_provenance"],
            p2_complete=engine["p2_complete"],
            HISTORICAL_TRUCK_STATE=historical_truck_state(engine),
            LOADING_FACE_BINDING_STATUS=face["P2D_SELECTED_LONG_EDGE_BINDING"],
            LOADING_FACE_FACTS=face,
            TRUCK_ENTRANCE_SEMANTICS=entrance_facts(authorities["typed_site"]),
            CANDIDATE_TRUCK_CONTEXT_HASH=context_hash,
            source_site_geometry_hash=engine["source_site_geometry_hash"],
            source_p1_handoff_hash=engine["source_p1_handoff_hash"],
            CANDIDATE_PREFLIGHT_STATUS=(
                ("PROJECT_INPUT_BLOCKED")
                if historical_truck_state(engine) == ("PROJECT_INPUT_BLOCKED")
                else ("ENGINEERING_REVIEW_REQUIRED")
            ),
            TRUCK_BINDING_STATUS=(
                ("NO_ADMITTED_MANEUVER_BINDING")
                if engine[("source_truck_maneuver_binding_hash")] is None
                else ("HISTORICAL_BINDING_HASH_REQUIRES_SOURCE_REVALIDATION")
            ),
            MISSING_PROJECT_INPUTS=[
                "Actual project vehicle/model and source bytes",
                "Measured gate opening and clearance basis",
                "Project-bound required maneuver geometry and source/revision records",
                "Dock approval and personnel/truck engineering review",
            ],
            REASON_CODES=[
                *engine["truck_route_codes"],
                "P1F_REFERENCE_COMPLETENESS_NOT_SOURCE_VERIFICATION",
                "MEASURED_TRUCK_GATE_OPENING_UNAVAILABLE",
                "PROJECT_MANEUVER_SOURCE_BYTES_AND_APPROVAL_UNAVAILABLE",
                "CANDIDATE_SPECIFIC_TRUCK_VALIDATION_NOT_EXECUTED",
            ],
        )
    except (LayoutAuthorityError, KeyError, TypeError, ValueError) as exc:
        result["REASON_CODES"].append(getattr(exc, "code", str(exc)))
    return result


def check_input_contract(
    payload: dict[str, Any] | None,
    candidate_engineering: dict[str, Any] | None = None,
    typed_site: dict[str, Any] | None = None,
    expected_p1f: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Necessary input-only predicates; NEVER invokes R13 preview/native search.

    Documentary approval verification is inseparable from R13's search entry.
    Therefore it remains NOT_EVALUATED here, not replaced by a new approver.
    Complete bytes can only reach INPUT_VALIDATED_NOT_ROUTE_PASS, never ready.
    """
    result: dict[str, Any] = {
        "STATUS": "UNAVAILABLE",
        "TRUCK_SEARCH_READY": False,
        "PROJECT_TRUCK_INPUT_ADMISSION": "BLOCKED",
        "P2D_FULL_PASS": False,
        "APPROVAL_STATUS": "PROJECT_APPROVAL_REQUIRED_NOT_EVALUATED",
        "REAL_PROJECT_APPROVED": False,
        "DOCUMENT_REVISION_STATUS": "PROJECT_APPLICABILITY_REVIEW_REQUIRED",
        "VALIDATION_SCOPE": "NECESSARY_STATIC_SUBSET_NOT_FULL_R13_OR_P2D_VALIDATION",
        "REASON_CODES": [],
        "SOURCE_DOCUMENTS": {},
    }
    if payload is None:
        result["REASON_CODES"] = ["PROJECT_INPUT_REQUIRED"]
        return result
    try:
        require(set(payload) == set(r13.FIELDS), "INVALID_TRUCK_PREVIEW_INPUT")
        require(
            payload["schema_version"] == "1.0.0"
            and payload["mode"] in ("SYNTHETIC_TEST", "OWNER_PROJECT"),
            "INVALID_TRUCK_PREVIEW_INPUT",
        )
        require(
            isinstance(payload["vehicle_type"], str) and bool(payload["vehicle_type"].strip()),
            "VEHICLE_MODEL_OR_TYPE_REQUIRED",
        )
        p1f = validate_project_truck_input(payload["truck_access"])
        require(p1f["status"] == "COMPLETE", p1f["status"])
        if expected_p1f is not None:
            require(
                canonical_hash(payload["truck_access"]) == canonical_hash(expected_p1f),
                "P1F_PROJECT_VEHICLE_BINDING_MISMATCH",
            )
        binding = validate_truck_maneuver_project_binding(
            payload["truck_access"], payload["truck_maneuver"]
        )
        project = binding.maneuver_project_input.require_complete()
        result[("REQUIRED_MANEUVER_CLASSES")] = list(project.requirement.required_maneuver_classes)
        result["BINDING_HASH"] = binding.canonical_result_hash
        require(
            DOCK_REVERSE in project.requirement.required_maneuver_classes,
            "P2D_DOCK_REVERSE_REQUIRED",
        )
        references: dict[str, str] = {}

        def add_reference(reference: str, digest: str) -> None:
            require(
                reference not in references or references[reference] == digest,
                "TRUCK_SOURCE_CONTENT_HASH_MISMATCH",
            )
            references[reference] = digest

        for key in REFERENCE_FIELDS:
            source = payload["truck_access"][key]
            add_reference(source["reference"], source["content_sha256"])
        for template in project.template_set.templates:
            add_reference(template.reference, template.content_sha256)
        entrance = payload["entrance"]
        require(
            isinstance(entrance, dict)
            and set(entrance)
            == {
                "locator_segment",
                "clear_opening_segment",
                "clear_width_m",
                "measurement_reference",
                "clearance_reference",
            },
            "INVALID_TRUCK_ENTRANCE_GEOMETRY",
        )
        for name in (
            payload["vehicle_source_reference"],
            payload["loading_face_reference"],
            payload["approval_reference"],
            entrance["measurement_reference"],
            entrance["clearance_reference"],
        ):
            require(isinstance(name, str) and bool(name.strip()), "PROJECT_INPUT_REQUIRED")
            references.setdefault(name, "")
        verified = r13._evidence(payload, references)
        result["SOURCE_DOCUMENTS"] = {
            key: {"sha256": value["sha256"], "bytes": value["bytes"]}
            for key, value in verified.items()
        }
        result["SOURCE_BYTE_STATUS"] = "SOURCE_BYTES_VERIFIED_NOT_APPROVAL"
        width = routing._mm(payload["truck_access"]["vehicle_width_m"], field="vehicle_width_m")
        length = routing._mm(payload["truck_access"]["vehicle_length_m"], field="vehicle_length_m")
        body = r13._vehicle_body(payload, width, length)
        r13._verify_body_envelopes(binding, body)
        locator = routing._segment_from_mapping(entrance["locator_segment"], field="locator")
        opening = routing._segment_from_mapping(
            entrance[("clear_opening_segment")], field="opening"
        )
        clear = routing._mm(entrance["clear_width_m"], field="clear_width_m")
        require(
            opening[0][0] == opening[1][0] or opening[0][1] == opening[1][1],
            "INVALID_TRUCK_ENTRANCE_GEOMETRY",
        )
        require(
            clear == routing._segment_length_mm(opening) and clear >= width,
            "TRUCK_ENTRANCE_CLEAR_WIDTH_INSUFFICIENT",
        )
        require(
            all(routing._on_segment(p, *opening) for p in locator),
            "TRUCK_ENTRANCE_LOCATOR_OUTSIDE_OPENING",
        )
        context = payload["site_geometry"]
        require(
            set(context)
            == {("effective_buildable_boundary"), "hard_obstacles", "zones", "personnel_corridors"},
            "INVALID_TRUCK_SITE_CONTEXT",
        )
        boundary = normalize_polygon(
            context["effective_buildable_boundary"], allow_numeric_string=True
        )
        require(
            any(
                all(routing._on_segment(p, a, b) for p in opening)
                for a, b in zip(boundary, (*boundary[1:], boundary[0]), strict=True)
            ),
            "TRUCK_ENTRANCE_NOT_ON_SITE_BOUNDARY",
        )
        zones = {z["zone_code"]: _rectangle_from_row(z) for z in context["zones"]}
        require(len(zones) == len(context["zones"]), "DUPLICATE_TRUCK_CONTEXT_ZONE")
        face = routing._segment_from_mapping(payload["shipping_loading_face"], field="face")
        require(
            face
            in tuple(
                s
                for _, kind, s in routing._edge_segments(zones["shipping_channel"])
                if kind == "LONG_EDGE"
            ),
            "INVALID_SHIPPING_LOADING_FACE",
        )
        if typed_site is not None:
            expected_obstacles = [v["footprint"] for v in typed_site["obstacles"]["hard_obstacles"]]
            require(
                canonical_hash(context["effective_buildable_boundary"])
                == canonical_hash(typed_site["site"]["effective_buildable_boundary"])
                and canonical_hash(context["hard_obstacles"]) == canonical_hash(expected_obstacles),
                "TRUCK_TYPED_SITE_CONTEXT_MISMATCH",
            )
            require(
                locator
                == routing._segment_from_mapping(
                    typed_site["entrances"]["truck_entrance"], field="site_locator"
                ),
                "TRUCK_TYPED_SITE_LOCATOR_MISMATCH",
            )
        if candidate_engineering is not None:
            fields = ("zone_code", "x", "y", "width_m", "depth_m", "rotation_deg")
            expected_zones = [{k: z[k] for k in fields} for z in candidate_engineering["zones"]]
            require(
                canonical_hash(sorted(context["zones"], key=lambda z: z["zone_code"]))
                == canonical_hash(sorted(expected_zones, key=lambda z: z["zone_code"])),
                "CANDIDATE_TRUCK_CONTEXT_MISMATCH",
            )
            require(
                face
                == routing._segment_from_mapping(
                    candidate_engineering[("shipping_loading_face_segment")], field="candidate_face"
                ),
                "CANDIDATE_LOADING_FACE_MISMATCH",
            )
            people_ids = {
                v["requirement_identity"]
                for v in candidate_engineering["access_results"]
                if v["flow_kind"] == "PEOPLE"
            }
            people = [
                polygon
                for corridor in candidate_engineering["corridors"]
                if corridor["requirement_identity"] in people_ids
                for polygon in corridor["envelope"]
            ]
            require(
                canonical_hash(context["personnel_corridors"]) == canonical_hash(people),
                "CANDIDATE_PERSONNEL_CORRIDORS_MISMATCH",
            )
        result.update(
            STATUS="INPUT_VALIDATED_NOT_ROUTE_PASS",
            SYNTHETIC_TEST_ONLY=payload["mode"] == "SYNTHETIC_TEST",
            PROJECT_APPLICABILITY_STATUS="REFERENCE_ONLY"
            if payload["mode"] == "SYNTHETIC_TEST"
            else "PROJECT_APPLICABILITY_REVIEW_REQUIRED",
            REASON_CODES=[
                "FORMAL_PROJECT_APPROVAL_NOT_VERIFIED_BY_PREFLIGHT",
                "FULL_R13_P2D_VALIDATION_NOT_EXECUTED",
            ],
        )
    except (LayoutAuthorityError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
        result.update(STATUS="BLOCKED", REASON_CODES=[getattr(exc, "code", str(exc))])
    return result


def batch(artifact_root: Path) -> dict[str, Any]:
    authorities, rows = load_sealed(artifact_root)
    candidates = [audit_candidate(row["projection"], row["catalog"], authorities) for row in rows]
    return {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "REFERENCE_HEAD": REFERENCE_HEAD,
        "CANDIDATES_AUDITED": len(candidates),
        "CANDIDATE_HASH_VERIFICATION": (
            "RAW_BYTES_PROJECTION_SVG_AND_ORIGINAL_CANONICAL_HASHES_VERIFIED"
        ),
        "PROJECT_TRUCK_INPUT_ADMISSION": "BLOCKED",
        "CANDIDATES": candidates,
        "TRUCK_SEARCH_READY_COUNT": sum(v["TRUCK_SEARCH_READY"] for v in candidates),
        "P2D_FULL_PASS_COUNT": 0,
        "REAL_TRUCK_SEARCHES": 0,
        "REAL_FACTORY_SOLVES": 0,
        "NATIVE_SOLVER_CALLS": 0,
        "NEW_OWNER_GRANT": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "FRESH_OUTPUT_FILE_REQUIRED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(batch(args.artifact_root)))


if __name__ == "__main__":
    main()
