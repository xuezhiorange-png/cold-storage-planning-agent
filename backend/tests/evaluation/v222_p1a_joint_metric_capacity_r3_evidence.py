"""Actual R3 production captures; no standalone Access/Truck/P2D invocation."""

from __future__ import annotations

import argparse
import inspect
import json
import resource
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cold_storage.modules.layout.application import composition_placement as app
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.metric_interface_reservation import (
    realize_metric_interface_reservations,
)
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain import conditional_metric_support as pairwise
from cold_storage.modules.layout.domain import joint_metric_capacity as joint
from cold_storage.modules.layout.domain import metric_reservation_consumption as runtime
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
)
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

ROOT = Path(__file__).resolve().parents[3]
P2_HASH = "sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677"
R2_EVIDENCE = (
    ROOT
    / "docs/tasks/evidence/v2_2_2_p1a_p3_conditional_metric_support_r2"
    / "xinzhao_conditional_metric_support.json"
)


def public_p2_snapshot() -> tuple[list[dict[str, Any]], float, int]:
    """Independent public invocation, parallel to placement, with no shared runtime cache."""
    started = time.perf_counter()
    result = [asdict(r) for r in realize_metric_interface_reservations(*_context())]
    return (
        result,
        time.perf_counter() - started,
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )


def independent_verify(engine: Any, cert: Any, placed: Any) -> bool:
    q = engine.pairwise
    combined = dict(placed)
    for role, bounds, shape in cert.assignment:
        if shape not in q.shapes[role] or role in placed and placed[role].bounds_mm != bounds:
            return False
        combined[role] = q.rectangle(role, bounds, shape)
    rooms = tuple(combined.values())
    return (
        all(rectangle_inside_polygon(p, q.boundary) for p in rooms)
        and not any(rectangle_intersects_closed_obstacle(p, o) for p in rooms for o in q.obstacles)
        and not any(rectangles_overlap(a, b) for i, a in enumerate(rooms) for b in rooms[i + 1 :])
        and all(
            rectangles_share_positive_edge(combined[a], combined[b])
            for a, b in q.must_edges
            if a in combined and b in combined
        )
        and q.intent_possible(combined)
        and engine.verify(cert, placed)
    )


def capture(baseline_audit: dict[str, Any], output: Path, regressions: bool) -> None:
    args = _context()
    compositions = build_structural_compositions(*args)
    handoff_names = {
        h.canonical_result_hash: h.composition_identity for h in compositions.placement_handoffs
    }
    historical = json.loads(R2_EVIDENCE.read_text())
    # The actual unchanged-R2 replay must reproduce the committed production body.
    expected = historical["replay_1"]
    actual_start = baseline_audit["placement"]
    assert all(expected[k] == actual_start[k] for k in actual_start), "R2_BASELINE_DRIFT"
    p2_pool = ProcessPoolExecutor(max_workers=1)
    p2_future = p2_pool.submit(public_p2_snapshot)
    baseline_summary = {
        k: v for k, v in baseline_audit.items() if k not in {"records", "placement"}
    }
    baseline_summary["unknown_by_composition"] = dict(
        Counter(handoff_names[r["composition"]] for r in baseline_audit["records"])
    )
    baseline_summary["orthogonal_flags"] = {
        key: sum(bool(r[key]) for r in baseline_audit["records"])
        for key in ("static_domain_not_covered", "fixed_endpoint_multi_neighbor_constraint")
    }
    baseline_summary["record_digest"] = canonical_hash(baseline_audit["records"])
    baseline_summary["joint_causes_not_assessed_by_r2"] = [
        "SHARED_UNPLACED_ROLE_INCONSISTENCY",
        "JOINT_ASSIGNMENT_UNPROVEN",
    ]
    result: dict[str, Any] = {
        "task_id": "V2_2_2_P1A_P3_JOINT_METRIC_CAPACITY_PROOF_R3",
        "start_head": "8c921b0f654d5d00e8664cf19650a278d558a7a0",
        "isolated_checkout_recovery": {
            "path": str(ROOT),
            "non_shallow": True,
            "shared_git_metadata": False,
            "original_worktree_untouched": True,
            "original_index_lock_untouched": True,
            "backup_sha256": "aa0283b7459b29c3bb762082f2a23b9729bc500005e2e59e859bb07694c4d04e",
        },
        "r2_unknown_attribution": baseline_summary,
        "baseline_candidate_hashes": expected["candidate_hashes"],
        "baseline_nodes": actual_start["nodes_used"],
        "baseline_attempts": len(actual_start["search_attempts"]),
        "standalone_access_truck_p2d_executed": False,
        "engineering_authority_changed": False,
        "joint_proof_scope": "PER_CONNECTED_HARD_COMPONENT",
        "whole_building_feasibility_proven": False,
    }
    fingerprint = canonical_hash(
        {m.__name__: inspect.getsource(m) for m in (exact, pairwise, joint, runtime)}
    )
    result["production_source_fingerprint"] = fingerprint

    def save(phase: str) -> None:
        result["capture_phase"] = phase
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(canonical_json(result))
        print("R3_CAPTURE_PHASE=" + phase, flush=True)

    original_init = pairwise.ConditionalMetricSupportQueryV2.__init__
    original_joint = joint.JointMetricCapacityQueryV1.update
    original_build = app.build_metric_runtime_context
    contexts = []
    records: list[dict[str, Any]] = []
    samples: dict[str, Any] = {}
    timings = Counter()
    verified = Counter()

    def init(self: Any, *a: Any, **kw: Any) -> None:
        original_init(self, *a, **kw)
        self.audit_composition = handoff_names[kw["provenance"]["handoff_hash"]]

    def builder(*a: Any, **kw: Any) -> Any:
        t = time.perf_counter()
        context = original_build(*a, **kw)
        timings["build_seconds"] += time.perf_counter() - t
        contexts.append(context)
        return context

    def update(self: Any, placed: Any, edge_states: Any, parent: Any = ()) -> Any:
        t = time.perf_counter()
        answer = original_joint(self, placed, edge_states, parent)
        timings["joint_query_seconds"] += time.perf_counter() - t
        composition = self.pairwise.audit_composition
        for s in answer:
            if s.certificate:
                assert independent_verify(self, s.certificate, placed), "FALSE_POSITIVE_JOINT_PROOF"
                verified["positive_certificates_independently_rechecked"] += 1
                samples.setdefault(composition, s.certificate.proof())
            if s.negative_certificate:
                self.verify_negative(s, placed)
                verified["negative_certificates_rechecked"] += 1
        admitted = bool(placed) and not any(
            s.status == pairwise.ConditionalSupportStatusV2.NONE for s in answer
        )
        records.append(
            {
                "composition": composition,
                "depth": len(placed),
                "admitted": admitted,
                "components": [
                    {
                        "roles": s.roles,
                        "status": s.status,
                        "reason": s.reason,
                        "edges": s.source_reservation_identities,
                        "proof_digest": s.certificate.proof()["certificate_identity"]
                        if s.certificate
                        else None,
                    }
                    for s in answer
                ],
                "pairwise_unknown_edges": [
                    s.source_edge_identity
                    for s in edge_states
                    if s.status == pairwise.ConditionalSupportStatusV2.UNKNOWN
                ],
            }
        )
        return answer

    replays = []
    for number in (1, 2):
        records.clear()
        samples.clear()
        timings.clear()
        verified.clear()
        misses = runtime.build_runtime_domain.cache_info().misses
        t = time.perf_counter()
        print(f"R3_CANONICAL_BEGIN={number}", flush=True)
        with (
            patch.object(pairwise.ConditionalMetricSupportQueryV2, "__init__", init),
            patch.object(joint.JointMetricCapacityQueryV1, "update", update),
            patch.object(app, "build_metric_runtime_context", builder),
        ):
            actual = app.enumerate_composition_placements(*args)
        body = json.loads(canonical_json(actual.placements.to_dict()))
        body["candidate_hashes"] = [c.canonical_result_hash for c in actual.placements.candidates]
        assert body["nodes_used"] == sum(a["nodes_visited"] for a in body["search_attempts"])
        assert body["nodes_used"] <= 60000
        for a in body["search_attempts"]:
            assert a["nodes_visited"] == sum(
                f["candidate_rectangle_attempt_count"] for f in a["role_search_funnel"]
            )
            assert a["metric_reservation_diagnostics"]["accepted_partial_with_zero_capacity"] == 0
            if a["complete_layout_found"]:
                certs = a["metric_reservation_diagnostics"]["final_consumed"]
                assert len(certs) == 7 and all(
                    c["certificate_source"] == "DIRECT_FINAL" for c in certs
                )
                assert a["metric_reservation_diagnostics"]["final_joint_certificates"]
        summary = {
            "joint_unknown_by_composition": dict(
                Counter(
                    r["composition"]
                    for r in records
                    if r["admitted"]
                    and any(
                        s["status"] == pairwise.ConditionalSupportStatusV2.UNKNOWN
                        for s in r["components"]
                    )
                )
            ),
            "joint_unknown_by_depth": dict(
                Counter(
                    r["depth"]
                    for r in records
                    if r["admitted"]
                    and any(
                        s["status"] == pairwise.ConditionalSupportStatusV2.UNKNOWN
                        for s in r["components"]
                    )
                )
            ),
            "joint_unknown_by_reason": dict(
                Counter(
                    s["reason"]
                    for r in records
                    for s in r["components"]
                    if s["status"] == pairwise.ConditionalSupportStatusV2.UNKNOWN
                )
            ),
            "joint_negative_by_reason": dict(
                Counter(
                    s["reason"]
                    for r in records
                    for s in r["components"]
                    if s["status"] == pairwise.ConditionalSupportStatusV2.NONE
                )
            ),
            "pairwise_unknown_resolved_by_joint_by_edge": dict(
                Counter(
                    e
                    for r in records
                    if all(
                        s["status"] == pairwise.ConditionalSupportStatusV2.SUPPORTED
                        for s in r["components"]
                    )
                    for e in r["pairwise_unknown_edges"]
                )
            ),
            "verified": dict(verified),
            "query_sequence_digest": canonical_hash(records),
        }
        replays.append((body, summary))
        result.setdefault("performance", []).append(
            {
                **dict(timings),
                "whole_replay_seconds": time.perf_counter() - t,
                "runtime_domain_build_count": runtime.build_runtime_domain.cache_info().misses
                - misses,
                "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        )
        if number == 1:
            result["replay_1"] = body
            result["joint_assessment"] = summary
            result["representative_joint_certificates"] = dict(samples)
        save(f"placement_{number}")
    assert replays[0] == replays[1], "R3_FULL_DETERMINISM_FAILED"
    result["determinism"] = {
        "full_placement_and_joint_sequence_equal": True,
        "second_result_digest": canonical_hash(replays[1]),
    }

    # Real historical control is a regression input, never a runtime layout seed.
    binding = bind_layout_authority(*args)
    control = historical["baseline"]["candidates"][0]
    handoff = next(
        h
        for h in compositions.placement_handoffs
        if h.composition_identity == control["composition_identity"]
    )
    payload = args[2].to_dict()
    boundary = normalize_polygon(
        payload["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(payload)
    shapes = exact._composition_shape_order(
        handoff,
        {
            r: exact._canonical_construction_shapes(v)
            for r, v in exact._authority_shapes(
                binding.dimension_authorities, boundary, obstacles
            ).items()
        },
        1,
    )
    domains = exact._domain_arrangement(handoff, 1, boundary, binding.dimension_authorities)
    faces = exact._domain_faces(handoff, 1)

    def origins(role: Any, shape: Any, placed: Any) -> Any:
        return tuple(
            dict.fromkeys(
                (
                    *exact._domain_derived_anchors(
                        role, shape, handoff, domains, 1, placed, boundary, obstacles
                    ),
                    *exact._generic_fallback_anchors(role, shape, placed, boundary, obstacles),
                )
            )
        )

    q = pairwise.ConditionalMetricSupportQueryV2(
        contexts[0].domains,
        exact.process_graph().must_adjacencies,
        lambda p: exact._partial_intent_possible(handoff, p, faces),
        shapes=shapes,
        boundary=boundary,
        obstacles=obstacles,
        origin_provider=origins,
        provenance={
            "handoff_hash": handoff.canonical_result_hash,
            "site_geometry_hash": handoff.source_site_geometry_hash,
            "dimension_authority_hash": canonical_hash(binding.dimension_authorities),
        },
    )
    engine = joint.JointMetricCapacityQueryV1(q, graph_identity=exact.process_graph().identity)
    rooms = {
        z["zone_code"]: PlacedRectangleV1(
            **{
                k: Decimal(v) if k in {"x", "y", "width_m", "depth_m"} else v
                for k, v in z.items()
                if k != "actual_area_m2"
            }
        )
        for z in control["zones"]
    }
    placed: dict[str, PlacedRectangleV1] = {}
    parent: Any = ()
    joint_parent: Any = ()
    prefixes = []
    for role in (None, *exact._zone_order(handoff)):
        if role is not None:
            assert exact._candidate_rejection(rooms[role], placed, boundary, obstacles) is None
            placed[role] = rooms[role]
            assert exact._partial_intent_possible(handoff, placed, faces)
        parent = q.update(placed, parent)
        joint_parent = engine.update(placed, parent, joint_parent)
        assert not any(
            s.status == pairwise.ConditionalSupportStatusV2.NONE for s in (*parent, *joint_parent)
        )
        prefixes.append(
            {
                "depth": len(placed),
                "pairwise": dict(Counter(s.status for s in parent)),
                "joint": dict(Counter(s.status for s in joint_parent)),
            }
        )
    assert q.consumed(placed, parent) and exact._intent_preserved(handoff, placed, faces)
    assert all(
        s.certificate and independent_verify(engine, s.certificate, placed) for s in joint_parent
    )
    result["start_control"] = {
        "hard_valid": True,
        "direct_final_certificates": 7,
        "prefixes": prefixes,
        "joint_final_certificates": [s.certificate.proof() for s in joint_parent],
    }
    save("control_prefixes")
    print("R3_PUBLIC_P2_JOIN", flush=True)
    p2, p2_seconds, p2_rss = p2_future.result()
    p2_pool.shutdown(wait=True)
    assert canonical_hash(p2) == P2_HASH
    assert len(p2) == 6 and sum(len(r["reservations"]) for r in p2) == 42
    result["p2_public_performance"] = {"seconds": p2_seconds, "peak_rss_bytes": p2_rss}
    reference = {r["source_edge_identity"]: r for r in p2[0]["reservations"]}
    result["p2_runtime_parity"] = [
        {
            "edge": d.source_edge_identity,
            "runtime_count": d.summary.valid_count,
            "p2_count": reference[d.source_edge_identity]["valid_slot_count"],
            "runtime_digest": d.summary.slot_set_digest,
            "p2_digest": reference[d.source_edge_identity]["slot_set_digest"],
        }
        for d in contexts[0].domains
    ]
    assert all(
        r["runtime_count"] == r["p2_count"] and r["runtime_digest"] == r["p2_digest"]
        for r in result["p2_runtime_parity"]
    )
    result["p2_public_result_hash"] = P2_HASH
    result["runtime_total_valid_slots"] = sum(d.summary.valid_count for d in contexts[0].domains)
    save("public_p2")
    if regressions:
        import pytest

        print("R3_REGRESSIONS_BEGIN", flush=True)
        paths = [
            str(p)
            for p in (ROOT / "backend/tests/unit").glob("test_v222_p1a_*.py")
            if p.name != "test_v222_p1a_composition_candidate_validation.py"
            and any(
                w in p.name
                for w in (
                    "composition",
                    "structural_hard",
                    "structural_interface",
                    "mandatory",
                    "metric",
                    "hard_obstacle",
                )
            )
        ]
        paths += [str(p) for p in (ROOT / "backend/tests/architecture").glob("test_v222_p1a_*.py")]
        result["regression_paths"] = paths
        result["regression_exit_code"] = pytest.main(["-q", *paths])
    assert (
        canonical_hash(
            {m.__name__: inspect.getsource(m) for m in (exact, pairwise, joint, runtime)}
        )
        == fingerprint
    )
    result["result"] = (
        "FAIL"
        if not result["replay_1"]["candidates"]
        else "PARTIAL"
        if sum(
            a["metric_reservation_diagnostics"]["accepted_partial_with_unknown_capacity"]
            for a in result["replay_1"]["search_attempts"]
        )
        else "PASS_PENDING_TESTS_AND_CI"
    )
    save("complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regressions", action="store_true")
    opts = parser.parse_args()
    capture(json.loads(opts.baseline_audit.read_text()), opts.output, opts.regressions)
