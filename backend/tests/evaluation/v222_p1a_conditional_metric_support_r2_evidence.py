"""Direct canonical R2 capture; no Access/Truck/P2D business invocation.

Run with --baseline /tmp/r2_start_baseline_capture.json. That file must come
from the pinned pre-P3 source replay, not a coordinate seed into production.
"""

from __future__ import annotations

import argparse
import inspect
import json
import resource
import time
from collections import Counter
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
from cold_storage.modules.layout.domain import conditional_metric_support as conditional
from cold_storage.modules.layout.domain import metric_interface_reservation as metric
from cold_storage.modules.layout.domain import metric_reservation_consumption as runtime
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

EXPECTED_P2 = "sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677"
CONTROL = "sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47"


def capture(baseline: dict[str, Any], checkpoint: Path) -> dict[str, Any]:
    def sources() -> str:
        return canonical_hash(
            {
                m.__name__: inspect.getsource(m)
                for m in (
                    exact,
                    conditional,
                    runtime,
                    metric,
                )
            }
        )

    source_hash = sources()
    result: dict[str, Any] = {
        "task_id": "V2_2_2_P1A_P3_CONDITIONAL_METRIC_SUPPORT_R2",
        "start_head": "ff4626fce1d88f9860b64cd183af3ce1db21a26a",
        "control_source_head": "112f30115d201dd8ef2daf541f5352b92d2154fe",
        "source_code_hash": source_hash,
        "baseline": baseline,
        "engineering_authority_changed": False,
        "access_truck_p2d_business_validation_executed": False,
    }

    def save(phase: str) -> None:
        result["capture_phase"] = phase
        checkpoint.write_text(canonical_json(result))
        print("R2_CAPTURE_PHASE=" + phase, flush=True)

    contexts = []
    performances = []
    original_builder = app.build_metric_runtime_context
    original_update = conditional.ConditionalMetricSupportQueryV2.update
    timings = {"build_seconds": 0.0, "query_seconds": 0.0, "query_calls": 0}

    def builder(*args: Any, **kwargs: Any) -> runtime.MetricRuntimeContextV1:
        t = time.perf_counter()
        context = original_builder(*args, **kwargs)
        timings["build_seconds"] += time.perf_counter() - t
        contexts.append(context)
        return context

    def update(self: Any, *args: Any, **kwargs: Any) -> Any:
        t = time.perf_counter()
        answer = original_update(self, *args, **kwargs)
        timings["query_seconds"] += time.perf_counter() - t
        timings["query_calls"] += 1
        return answer

    replays = []
    for number in (1, 2):
        timings.update(build_seconds=0.0, query_seconds=0.0, query_calls=0)
        misses = runtime.build_runtime_domain.cache_info().misses
        t = time.perf_counter()
        print(f"R2_CANONICAL_PLACEMENT_BEGIN={number}", flush=True)
        with (
            patch.object(app, "build_metric_runtime_context", builder),
            patch.object(conditional.ConditionalMetricSupportQueryV2, "update", update),
        ):
            actual = app.enumerate_composition_placements(*_context())
        body = json.loads(canonical_json(actual.placements.to_dict()))
        body["candidate_hashes"] = [c.canonical_result_hash for c in actual.placements.candidates]
        assert body["nodes_used"] == sum(a["nodes_visited"] for a in body["search_attempts"])
        assert body["nodes_used"] <= 60000
        for attempt in body["search_attempts"]:
            assert attempt["nodes_visited"] == sum(
                f["candidate_rectangle_attempt_count"] for f in attempt["role_search_funnel"]
            )
            assert (
                attempt["metric_reservation_diagnostics"]["accepted_partial_with_zero_capacity"]
                == 0
            )
            if attempt["complete_layout_found"]:
                certs = attempt["metric_reservation_diagnostics"]["final_consumed"]
                assert len(certs) == 7 and all(
                    c["certificate_source"] == "DIRECT_FINAL" for c in certs
                )
        performances.append(
            {
                **timings,
                "seconds": time.perf_counter() - t,
                "static_domain_cache_misses": runtime.build_runtime_domain.cache_info().misses
                - misses,
            }
        )
        replays.append(body)
        result["replay_1"] = replays[0]
        result["performance"] = performances
        save(f"placement_{number}")
    assert replays[0] == replays[1]
    result["replay_2_hash"] = canonical_hash(replays[1])
    result["full_placement_determinism"] = True

    # Given real START geometry is inspected only as a regression fixture.
    args = _context()
    binding = bind_layout_authority(*args)
    comps = build_structural_compositions(*args)
    candidate = baseline["candidates"][0]
    assert canonical_hash(candidate) == CONTROL
    handoff = next(
        h
        for h in comps.placement_handoffs
        if h.composition_identity == candidate["composition_identity"]
    )
    payload = args[2].to_dict()
    boundary = normalize_polygon(
        payload["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(payload)
    authority = exact._authority_shapes(binding.dimension_authorities, boundary, obstacles)
    shapes = exact._composition_shape_order(
        handoff, {r: exact._canonical_construction_shapes(v) for r, v in authority.items()}, 1
    )
    domains = exact._domain_arrangement(handoff, 1, boundary, binding.dimension_authorities)
    faces = exact._domain_faces(handoff, 1)

    def origins(role: str, shape: Any, placed: Any) -> Any:
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

    query = conditional.ConditionalMetricSupportQueryV2(
        contexts[0].domains,
        exact.process_graph().must_adjacencies,
        lambda p: exact._partial_intent_possible(handoff, p, faces),
        shapes=shapes,
        boundary=boundary,
        obstacles=obstacles,
        origin_provider=origins,
        provenance={
            "handoff_hash": handoff.canonical_result_hash,
            "dimension_authority_hash": canonical_hash(binding.dimension_authorities),
            "site_geometry_hash": handoff.source_site_geometry_hash,
        },
    )
    rooms = {
        z["zone_code"]: PlacedRectangleV1(
            **{
                k: Decimal(v) if k in {"x", "y", "width_m", "depth_m"} else v
                for k, v in z.items()
                if k != "actual_area_m2"
            }
        )
        for z in candidate["zones"]
    }
    placed: dict[str, PlacedRectangleV1] = {}
    parent = ()
    prefixes = []
    for role in (None, *exact._zone_order(handoff)):
        if role is not None:
            room = rooms[role]
            assert exact._candidate_rejection(room, placed, boundary, obstacles) is None
            assert any(
                (s.world_width_mm, s.world_depth_mm)
                == (room.bounds_mm[2] - room.bounds_mm[0], room.bounds_mm[3] - room.bounds_mm[1])
                for s in shapes[role]
            )
            placed[role] = room
            assert exact._partial_intent_possible(handoff, placed, faces)
        parent = query.update(placed, parent)
        counts = Counter(s.status for s in parent)
        assert counts[conditional.ConditionalSupportStatusV2.NONE] == 0
        prefixes.append({"placed_count": len(placed), "statuses": dict(counts)})
    assert query.consumed(placed, parent)
    memberships = []
    for d in contexts[0].domains:
        a, b = (rooms[r].bounds_mm for r in d.summary.roles)
        memberships.append(
            {
                "roles": d.summary.roles,
                "member": any(d.slots[i][:2] == (a, b) for i in d.endpoint_indexes[0].get(a, ())),
            }
        )
    assert sum(m["member"] for m in memberships) == 0
    result["start_control_regression"] = {
        "hard_valid": True,
        "prefixes": prefixes,
        "static_memberships": memberships,
        "direct_final_certificates": [s.certificate.proof() for s in parent],
    }
    save("start_control_13_prefixes")

    print("R2_PUBLIC_P2_REPLAY_BEGIN", flush=True)
    t = time.perf_counter()
    p2 = realize_metric_interface_reservations(*_context())
    raw = json.loads(canonical_json([asdict(v) for v in p2]))
    assert canonical_hash(raw) == EXPECTED_P2
    reference = {r.source_edge_identity: r for r in p2[0].reservations}
    for domain in contexts[0].domains:
        item = reference[domain.source_edge_identity]
        assert domain.summary.valid_count == item.valid_slot_count
        assert domain.summary.slot_set_digest == item.slot_set_digest
    result["public_p2_parity"] = {
        "hash": canonical_hash(raw),
        "realizations": 42,
        "runtime_parity": "7/7",
        "seconds": time.perf_counter() - t,
    }
    result["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert sources() == source_hash, "SOURCE_CHANGED_DURING_CAPTURE"
    save("complete")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    opts = parser.parse_args()
    capture(json.loads(opts.baseline.read_text()), opts.output)
