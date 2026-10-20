"""Read-only actual A/B exports using the existing quality-fact extractor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

from run_stage_b_owner_pool import dump

from cold_storage.modules.layout.domain.dimensioning import canonical_hash


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


def analyze(output: Path, repo: Path) -> dict[str, Any]:
    extractor = quality_extractor(repo)
    head = json.loads((output / "source-admission.json").read_text())["head"]
    comparison: dict[str, Any] = {
        "execution_head": head,
        "arms": {},
        "paired_handoff_scope": "INTENT_MATCH_NOT_IDENTICAL_PHYSICAL_LAYOUT",
    }
    validations = []
    for arm in ("A", "B"):
        folder = output / f"arm-{arm.lower()}"
        if not (folder / "pool.json").exists():
            comparison["arms"][arm] = {"status": "NOT_EXECUTED", "candidates": []}
            continue
        result = json.loads((folder / "pool.json").read_bytes())
        ledger = json.loads((folder / "resource-ledger.json").read_bytes())
        record = ledger["pools"][0]
        events = record.get("enumeration_events", [])
        rows = []
        for path in sorted(
            (output / "previews" / f"arm-{arm.lower()}").glob("candidate-*/candidate.json")
        ):
            original = json.loads(path.read_bytes())
            div = json.loads((path.parent / "diversity.json").read_bytes())
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
                "raw_candidate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_head": head,
                "geometry_hash": div["geometry_hash"],
                "family_hash": div["major_family_hash"],
                "meaningful_hash": div["v2"].get("meaningful_construction_hash"),
                "v2_counted": div["v2_construction_counted"],
                "archive": "CURRENT_PRIVATE_SOURCE_BOUND_AB_RUN",
            }
            facts = extractor.analyze(projection)
            dump(path.parent / "quality-facts.json", facts)
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
                "composition_identity": original["composition_handoff"]["composition_identity"],
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
                    if k in metrics
                },
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
        summary: dict[str, Any] = {
            "status": result["status"],
            "candidates": rows,
            "physical_assignments": record["counters"]["checked_solutions"],
            "hole_rejections": sum(
                e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT" and e["certificate"]["hole_count"] > 0
                for e in events
            ),
            "engineering_accepted_geometries": len(rows),
            "physical_geometry_count": result["distinct_physical_geometry_count"],
            "meaningful_constructions": result["distinct_meaningful_construction_count"],
            "major_families": result["major_structural_family_count"],
            "resource_counters": record["counters"],
            "native_statuses": dict(
                Counter(a["solver_status"] for a in record["counters"]["attempts"])
            ),
            "handoffs": result["compositions"],
            "room_distributions": {
                role: {
                    "width_m": describe([r["rooms"][role]["width_m"] for r in rows]),
                    "depth_m": describe([r["rooms"][role]["depth_m"] for r in rows]),
                    "aspect_ratio": describe([r["rooms"][role]["aspect_exact"] for r in rows]),
                    "semiperimeter_m": describe([r["semiperimeter_m_exact"][role] for r in rows]),
                }
                for role in ("office", "changing_room", "coating_room")
            },
        }
        comparison["arms"][arm] = summary
    comparison["same_handoff_groups"] = {}
    for arm, summary in comparison["arms"].items():
        for row in summary["candidates"]:
            comparison["same_handoff_groups"].setdefault(
                row["composition_identity"], {"A": [], "B": []}
            )[arm].append(row["candidate_id"])
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
            "statistical_significance_claimed": False,
            "formal_quality_ranking": False,
        },
    )
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.output, Path(__file__).resolve().parents[2])


if __name__ == "__main__":
    main()
