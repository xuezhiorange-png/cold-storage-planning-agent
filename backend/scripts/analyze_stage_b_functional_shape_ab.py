"""Read sealed A/B evidence; write deterministic reports to a separate directory.

No solver, execution store, grant or exporter is imported or called. A null
orthogonal-union hole count is unknown, not zero or an implicit hole rejection.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.construction_branch_diversity import (
    construction_branch_diversity,
)
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import canonical_hash


def dump(path: Path, body: Any) -> None:
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def classify_topology_rejections(events: list[Any]) -> dict[str, Any]:
    """Count independent certificate facts, never infer absent hole counts.

    Categories may overlap: multiple components can also contain holes, and an
    error code is not an exhaustive enumeration of a certificate's geometry.
    Only nonnegative *integers* (not bool/float/string) establish a hole count.
    """
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("kind") != "TOPOLOGY_REJECTED_WITNESS_CUT":
            continue
        raw = event.get("certificate")
        certificate = raw if isinstance(raw, dict) else {}
        anomalies = []
        if not isinstance(raw, dict):
            anomalies.append("CERTIFICATE_NOT_OBJECT")
        holes: Any = certificate.get("hole_count")
        known = type(holes) is int and holes >= 0
        if "hole_count" not in certificate:
            anomalies.append("HOLE_COUNT_MISSING")
        elif holes is not None and not known:
            anomalies.append("HOLE_COUNT_INVALID_TYPE_OR_VALUE")
        error = certificate.get("error")
        if not isinstance(error, str) or not error:
            anomalies.append("REJECTION_ERROR_MISSING_OR_INVALID")
        components: Any = certificate.get("connected_component_count")
        if components is not None and (type(components) is not int or components < 1):
            anomalies.append("COMPONENT_COUNT_INVALID_TYPE_OR_VALUE")
        singular = certificate.get("singular_points_mm")
        if singular is not None and not isinstance(singular, list):
            anomalies.append("SINGULAR_POINTS_INVALID_TYPE")
        categories = []
        if known and holes > 0:
            categories.append("CONFIRMED_HOLE")
        if error == "SINGULAR_POINT_CONTACT" or (isinstance(singular, list) and singular):
            categories.append("SINGULAR_POINT_CONTACT")
        if error == "MULTIPLE_COMPONENTS" or (type(components) is int and components > 1):
            categories.append("MULTIPLE_COMPONENTS")
        if (
            isinstance(error, str)
            and error
            and error not in ("ENCLOSED_HOLE", "SINGULAR_POINT_CONTACT", "MULTIPLE_COMPONENTS")
        ):
            categories.append("OTHER_TOPOLOGY_REJECTION")
        if error == "ENCLOSED_HOLE" and known and holes == 0:
            anomalies.append("ENCLOSED_HOLE_WITH_ZERO_COUNT")
        if anomalies or not categories:
            categories.append("UNCLASSIFIED_CERTIFICATE")
        rows.append(
            {
                "event_index": index,
                "event_hash": event.get("canonical_event_hash"),
                "categories": categories,
                "hole_count": holes if known else None,
                "hole_count_status": "KNOWN" if known else "UNKNOWN",
                "field_anomalies": anomalies,
                "original_certificate": raw,
            }
        )
    category_counts = Counter(c for row in rows for c in row["categories"])
    unknown = sum(row["hole_count_status"] == "UNKNOWN" for row in rows)
    confirmed = sum(row["hole_count"] for row in rows if row["hole_count_status"] == "KNOWN")
    return {
        "rejected_witness_count": len(rows),
        "hole_rejected_witness_count": category_counts["CONFIRMED_HOLE"],
        "confirmed_hole_loop_count": confirmed,
        "total_hole_loop_count": None if unknown else confirmed,
        "total_hole_loop_count_determinable": unknown == 0,
        "singular_contact_witness_count": category_counts["SINGULAR_POINT_CONTACT"],
        "multiple_component_witness_count": category_counts["MULTIPLE_COMPONENTS"],
        "other_rejection_witness_count": category_counts["OTHER_TOPOLOGY_REJECTION"],
        "unclassified_certificate_count": category_counts["UNCLASSIFIED_CERTIFICATE"],
        "unknown_hole_count_witness_count": unknown,
        "certificate_field_anomaly_count": sum(len(row["field_anomalies"]) for row in rows),
        "certificate_anomaly_witness_count": sum(bool(row["field_anomalies"]) for row in rows),
        "categories_are_mutually_exclusive": False,
        "witnesses": rows,
    }


def quality_extractor(repo: Path) -> Any:
    directory = repo / "docs/previews/v2.2.2/stage-b/layout-quality-baseline-01"
    manifest = json.loads((directory / "source_manifest.json").read_bytes())
    source = directory / "analyze.py"
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["files"]["analyze.py"]["sha256"]:
        raise ValueError("EXISTING_QUALITY_EXTRACTOR_CHANGED")
    spec = importlib.util.spec_from_file_location("existing_ab_quality_facts", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def describe(values: list[str]) -> dict[str, Any]:
    ordered = sorted(Fraction(v) for v in values)
    return {
        "count": len(ordered),
        "values_exact": [str(v) for v in ordered],
        "min": str(ordered[0]) if ordered else None,
        "max": str(ordered[-1]) if ordered else None,
        "mean_exact": str(sum(ordered) / len(ordered)) if ordered else None,
    }


def analyze(source: Path, repo: Path, *, output: Path) -> dict[str, Any]:
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("ANALYSIS_OUTPUT_MUST_BE_DISJOINT_FROM_SEALED_INPUT")
    extractor = quality_extractor(repo)
    head = json.loads((source / "source-admission.json").read_text())["head"]
    output.mkdir(parents=True, exist_ok=True)
    comparison: dict[str, Any] = {
        "execution_head": head,
        "arms": {},
        "paired_handoff_scope": "INTENT_MATCH_NOT_IDENTICAL_PHYSICAL_LAYOUT",
    }
    validations = []
    for arm in ("A", "B"):
        folder = source / f"arm-{arm.lower()}"
        if not (folder / "pool.json").exists():
            comparison["arms"][arm] = {"status": "NOT_EXECUTED", "candidates": []}
            continue
        result = json.loads((folder / "pool.json").read_bytes())
        ledger = json.loads((folder / "resource-ledger.json").read_bytes())
        record = ledger["pools"][0]
        events = record.get("enumeration_events", [])
        rows = []
        for path in sorted(
            (source / "previews" / f"arm-{arm.lower()}").glob("candidate-*/candidate.json")
        ):
            original = json.loads(path.read_bytes())
            div = json.loads((path.parent / "diversity.json").read_bytes())
            provenance = json.loads((path.parent / "drawing_provenance.json").read_bytes())
            raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if raw_sha != provenance["candidate_file_sha256"]:
                raise ValueError("SEALED_CANDIDATE_SHA256_MISMATCH")
            v1 = construction_diversity(original["proposal"]["zones"])
            v2 = construction_branch_diversity(
                original["proposal"]["zones"], original["engineering_validation"]["access_results"]
            )
            # JSON round-trips tuple signatures as lists; compare the existing
            # canonical identity, not Python container implementation details.
            if canonical_hash(v1) != canonical_hash(div["v1"]) or canonical_hash(
                v2
            ) != canonical_hash(div["v2"]):
                raise ValueError("SEALED_DIVERSITY_IDENTITY_MISMATCH")
            if (
                div["geometry_hash"] != v1["symmetry_invariant_geometry_hash"]
                or div["major_family_hash"] != v1["major_family_hash"]
                or canonical_hash(original["engineering_validation"])
                != provenance["source_application_hash"]
                or original["canonical_result_hash"] != provenance["candidate_canonical_hash"]
            ):
                raise ValueError("SEALED_APPLICATION_OR_GEOMETRY_IDENTITY_MISMATCH")
            accepted = [
                c for c in result["candidates"] if c["geometry_hash"] == div["geometry_hash"]
            ]
            if bool(accepted) != div["v2_construction_counted"] or len(accepted) > 1:
                raise ValueError("ACCEPTED_CANDIDATE_MEMBERSHIP_MISMATCH")
            if accepted and accepted[0]["candidate_result"] != original:
                raise ValueError("ACCEPTED_CANDIDATE_BYTES_IDENTITY_MISMATCH")
            if accepted and not v2["countable"]:
                raise ValueError("ACCEPTED_CANDIDATE_BRANCH_EVIDENCE_MISMATCH")
            app = original["engineering_validation"]
            for source_key, body_key in (
                ("zone_plan_hash", "source_zone_plan_hash"),
                ("p1_hash", "source_p1_handoff_hash"),
                ("site_hash", "source_site_geometry_hash"),
            ):
                if original[body_key] != result["sources"][source_key] or (
                    app[body_key] != original[body_key]
                ):
                    raise ValueError("CANDIDATE_POOL_AUTHORITY_SOURCE_MISMATCH")
            projection = {
                key: original[key]
                for key in (
                    "engineering_validation",
                    "composition_handoff",
                    "independent_validation",
                    "native_independent_validation",
                    "canonical_result_hash",
                )
            }
            projection["provenance"] = {
                "candidate_id": f"arm-{arm.lower()}/{path.parent.name}",
                "raw_candidate_sha256": raw_sha,
                "source_head": head,
                "geometry_hash": div["geometry_hash"],
                "family_hash": div["major_family_hash"],
                "meaningful_hash": div["v2"].get("meaningful_construction_hash"),
                "v2_counted": div["v2_construction_counted"],
                "archive": "CURRENT_PRIVATE_SOURCE_BOUND_AB_RUN",
            }
            facts = extractor.analyze(projection)
            target = output / "candidate-facts" / f"arm-{arm.lower()}" / path.parent.name
            target.mkdir(parents=True, exist_ok=True)
            dump(target / "quality-facts.json", facts)
            metrics = facts["METRICS"]
            rooms = {
                r["zone"]: r
                for r in metrics["ROOM_DIMENSION_FACTS"]["VALUE"]
                if r["zone"] in ("office", "changing_room", "coating_room")
            }
            semi = {
                r: str(Fraction(v["width_m"]) + Fraction(v["depth_m"])) for r, v in rooms.items()
            }
            row = {
                "candidate_id": projection["provenance"]["candidate_id"],
                "accepted_candidate_id": accepted[0]["candidate_id"] if accepted else None,
                "raw_candidate_sha256": raw_sha,
                "candidate_identity": original["identity"],
                "canonical_result_hash": original["canonical_result_hash"],
                "composition_identity": original["composition_handoff"]["composition_identity"],
                "source_family": original["composition_handoff"]["family"],
                "meaningful_construction_hash": v2.get("meaningful_construction_hash"),
                "source_identities": {
                    k: original[k]
                    for k in (
                        "source_zone_plan_hash",
                        "source_p1_handoff_hash",
                        "source_site_geometry_hash",
                        "source_composition_hash",
                        "source_composition_handoff_hash",
                    )
                },
                "engineering_original_status": {
                    "acceptance_status": original["acceptance_status"],
                    "stage_a_engineering_accepted": original["stage_a_engineering_accepted"],
                    "independent": original["independent_validation"],
                    "native_independent": original["native_independent_validation"],
                    "truck_route_status": app["truck_route_status"],
                    "truck_route_validated": app["truck_route_validated"],
                    "project_layout_validated": app["project_layout_validated"],
                    "p2_complete": app["p2_complete"],
                },
                "geometry_hash": div["geometry_hash"],
                "family_hash": div["major_family_hash"],
                "v2_counted": div["v2_construction_counted"],
                "rooms": rooms,
                "semiperimeter_m_exact": semi,
                "semiperimeter_sum_m_exact": str(sum(Fraction(v) for v in semi.values())),
                "measured_metrics": {
                    k: metrics[k]
                    for k in (
                        "PERSONNEL_ROUTE_LENGTH_M",
                        "PERSONNEL_ROUTE_TURN_COUNT",
                        "BUILDING_AREA_M2",
                        "BUILDING_PERIMETER_M",
                        "EXTERIOR_TURN_COUNT",
                        "EXTERIOR_REFLEX_CORNER_COUNT",
                        "MAJOR_ZONE_GRID_ALIGNMENT_RATE",
                    )
                },
                "unavailable_metrics": {
                    k: v for k, v in metrics.items() if v["STATUS"] == "UNAVAILABLE"
                },
                "coating_process": "PACKAGING_BOX_FILM_SEALING",
                "functional_fit_status": "INPUT_REQUIRED",
                "truck": "BLOCKED_PROJECT_INPUT",
                "p2d_full_pass": False,
                "quality_facts_hash": canonical_hash(facts),
            }
            rows.append(row)
            validations.append(
                {
                    "candidate_id": row["candidate_id"],
                    "independent": original["independent_validation"],
                    "native_independent": original["native_independent_validation"],
                    "footprint": original["engineering_validation"]["building_footprint"],
                }
            )
        counted = [r for r in rows if r["v2_counted"]]
        if (
            len(rows) != result["distinct_physical_geometry_count"]
            or len({r["geometry_hash"] for r in rows}) != len(rows)
            or len(counted) != result["distinct_meaningful_construction_count"]
            or len({r["meaningful_construction_hash"] for r in counted}) != len(counted)
            or len({r["family_hash"] for r in counted}) != result["major_structural_family_count"]
        ):
            raise ValueError("SEALED_POOL_COUNTS_INCONSISTENT")
        topology = classify_topology_rejections(events)
        summary: dict[str, Any] = {
            "status": result["status"],
            "input_sources": result["sources"],
            "candidates": rows,
            "physical_assignments": record["counters"]["checked_solutions"],
            "topology_rejections": topology,
            "engineering_accepted_geometries": len(rows),
            "physical_geometry_count": result["distinct_physical_geometry_count"],
            "meaningful_constructions": result["distinct_meaningful_construction_count"],
            "major_families": result["major_structural_family_count"],
            "resource_counters": record["counters"],
            "native_statuses": dict(
                Counter(a["solver_status"] for a in record["counters"]["attempts"])
            ),
            "handoffs": result["compositions"],
            "room_distributions": room_distributions(rows),
            "metric_distributions": metric_distributions(rows),
        }
        comparison["arms"][arm] = summary
    comparison["same_handoff_groups"] = {}
    for arm, summary in comparison["arms"].items():
        for handoff in summary.get("handoffs", []):
            comparison["same_handoff_groups"].setdefault(
                handoff["composition_identity"], {"A": [], "B": []}
            )
        for row in summary["candidates"]:
            comparison["same_handoff_groups"].setdefault(
                row["composition_identity"], {"A": [], "B": []}
            )[arm].append(row["candidate_id"])
    grouped = {
        identity: {
            arm: {
                "candidate_ids": ids[arm],
                "resource_observation": next(
                    (
                        h
                        for h in comparison["arms"][arm].get("handoffs", [])
                        if h["composition_identity"] == identity
                    ),
                    None,
                ),
                "metric_distributions": metric_distributions(
                    [
                        r
                        for r in comparison["arms"][arm]["candidates"]
                        if r["candidate_id"] in ids[arm]
                    ]
                ),
                "room_distributions": room_distributions(
                    [
                        row
                        for row in comparison["arms"][arm]["candidates"]
                        if row["candidate_id"] in ids[arm]
                    ]
                ),
            }
            for arm in ("A", "B")
        }
        for identity, ids in comparison["same_handoff_groups"].items()
    }
    dump(
        output / "handoff-comparison.json",
        {
            "scope": "SAME_HANDOFF_INTENT_NOT_MATCHED_PHYSICAL_CANDIDATES",
            "one_to_one_causal_comparison_established": False,
            "groups": grouped,
        },
    )
    dump(
        output / "topology-rejection-classification.json",
        {
            arm: value.get("topology_rejections", classify_topology_rejections([]))
            for arm, value in comparison["arms"].items()
        },
    )
    dump(
        output / "engineering-validation.json",
        {
            "candidates": validations,
            "p2d_full_pass_count": 0,
            "scope": "ACTUAL_PER_CANDIDATE_INDEPENDENT_NON_TRUCK_CHECKS",
        },
    )
    dump(output / "candidate-quality-comparison.json", comparison)
    dump(
        output / "ab-conclusion.json",
        {
            "conclusion": "INCONCLUSIVE",
            "reason": "DESCRIPTIVE_EVIDENCE_REQUIRES_REVIEW_NOT_AUTOMATIC_QUALITY_PASS",
            "real_layout_quality_improved": "NOT_ESTABLISHED",
            "real_replay_determinism": "NOT_EVALUATED",
            "b_default_promotion_authorized": False,
            "statistical_significance_claimed": False,
            "formal_quality_ranking": False,
        },
    )
    return comparison


def room_distributions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        role: {
            "width_m": describe([r["rooms"][role]["width_m"] for r in rows]),
            "depth_m": describe([r["rooms"][role]["depth_m"] for r in rows]),
            "aspect_ratio": describe([r["rooms"][role]["aspect_exact"] for r in rows]),
            "semiperimeter_m": describe([r["semiperimeter_m_exact"][role] for r in rows]),
        }
        for role in ("office", "changing_room", "coating_room")
    }


def metric_distributions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    names = (
        "PERSONNEL_ROUTE_LENGTH_M",
        "PERSONNEL_ROUTE_TURN_COUNT",
        "BUILDING_AREA_M2",
        "BUILDING_PERIMETER_M",
        "EXTERIOR_TURN_COUNT",
        "EXTERIOR_REFLEX_CORNER_COUNT",
        "MAJOR_ZONE_GRID_ALIGNMENT_RATE",
    )
    result = {}
    for name in names:
        measured = [r["measured_metrics"][name] for r in rows]
        known = [str(m["VALUE"]) for m in measured if m["STATUS"] in ("MEASURED", "DERIVED")]
        result[name] = {**describe(known), "unavailable_count": len(measured) - len(known)}
    result["AUXILIARY_SEMIPERIMETER_SUM_M"] = describe(
        [r["semiperimeter_sum_m_exact"] for r in rows]
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Sealed evidence, read only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.input, Path(__file__).resolve().parents[2], output=args.output)


if __name__ == "__main__":
    main()
