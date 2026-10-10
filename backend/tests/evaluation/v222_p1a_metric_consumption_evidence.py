"""Bounded direct production capture; no Access/Truck/P2D or artifact injection.

Print compact counts/digests/consumed proofs, never the full runtime slot set.
"""

from __future__ import annotations

import argparse
import inspect
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from cold_storage.modules.layout.application.metric_interface_reservation import (
    realize_metric_interface_reservations,
)
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain import metric_interface_reservation as metric
from cold_storage.modules.layout.domain import metric_reservation_consumption as runtime
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

ROOT = Path(__file__).resolve().parents[3]
P2_EVIDENCE = (
    ROOT
    / "docs/tasks/evidence/v2_2_2_p1a_metric_interface_reservation_p2"
    / "xinzhao_metric_interface_reservation_realization.json"
)


def placement_capture() -> dict[str, Any]:
    result = enumerate_composition_placements(*_context())
    body = result.placements.to_dict()
    for attempt in body["search_attempts"]:
        attempt["construction_domains_hash"] = canonical_hash(attempt.pop("construction_domains"))
    body["candidate_hashes"] = [c.canonical_result_hash for c in result.placements.candidates]
    body["application_result_hash"] = result.canonical_result_hash
    body["candidate_count"] = len(result.placements.candidates)
    assert body["nodes_used"] == sum(a["nodes_visited"] for a in body["search_attempts"])
    assert all(
        a["nodes_visited"]
        == sum(r["candidate_rectangle_attempt_count"] for r in a["role_search_funnel"])
        for a in body["search_attempts"]
    )
    for attempt in body["search_attempts"]:
        stats = attempt["metric_reservation_diagnostics"]
        assert stats["accepted_partial_with_zero_capacity"] == 0
        # R2: UNKNOWN is honest incomplete proof, not positive capacity and not
        # permission to prune. Capture it instead of asserting it away.
        assert stats["accepted_partial_with_unknown_capacity"] >= 0
        if attempt["complete_layout_found"]:
            proof = stats["final_consumed"]
            assert len(proof) == len(body["metric_runtime_diagnostics"]["domains"])
            candidate = next(
                c
                for c in result.placements.candidates
                if c.composition_identity == attempt["composition_identity"]
            )
            rooms = {r.zone_code: r.bounds_mm for r in candidate.zones}
            assert all(
                tuple(rooms[r] for r in p["roles"]) == tuple(p["endpoint_bounds_mm"]) for p in proof
            )
    return json.loads(canonical_json(body))


def metric_capture() -> dict[str, Any]:
    actual = realize_metric_interface_reservations(*_context())
    raw = json.loads(canonical_json([asdict(r) for r in actual]))
    expected = json.loads(P2_EVIDENCE.read_text())
    assert raw == expected["compositions"]
    return {
        "public_result_hash": canonical_hash(raw),
        "full_serialized_artifacts_equal": True,
        "compositions": [
            {
                "identity": r.composition_identity,
                "gate": asdict(r.gate),
                "interfaces": [
                    {
                        "edge": i.source_edge_identity,
                        "count": i.valid_slot_count,
                        "digest": i.slot_set_digest,
                        "complete": i.finite_domain_complete,
                    }
                    for i in r.reservations
                ],
            }
            for r in actual
        ],
    }


def capture() -> dict[str, Any]:
    source_hash = canonical_hash(
        {m.__name__: inspect.getsource(m) for m in (exact, metric, runtime)}
    )
    print("P3 complete production placement replay 1", flush=True)
    first = placement_capture()
    print("P3_PLACEMENT_CAPTURE_1=" + canonical_json(first), flush=True)
    print("P3 complete production placement replay 2", flush=True)
    second = placement_capture()
    print("P3_PLACEMENT_CAPTURE_2=" + canonical_json(second), flush=True)
    assert first == second
    print("P3 independent P2 public replay 1", flush=True)
    metric_first = metric_capture()
    print("P3_METRIC_CAPTURE_1=" + canonical_json(metric_first), flush=True)
    print("P3 independent P2 public replay 2", flush=True)
    metric_second = metric_capture()
    print("P3_METRIC_CAPTURE_2=" + canonical_json(metric_second), flush=True)
    assert metric_first == metric_second
    metric_by_edge = {i["edge"]: i for i in metric_first["compositions"][0]["interfaces"]}
    for d in first["metric_runtime_diagnostics"]["domains"]:
        p2 = metric_by_edge[d["source_edge_identity"]]
        assert d["valid_slot_count"] == p2["count"] and d["slot_set_digest"] == p2["digest"]
        assert d["finite_domain_complete"] == p2["complete"]
    assert source_hash == canonical_hash(
        {m.__name__: inspect.getsource(m) for m in (exact, metric, runtime)}
    )
    return {
        "source_code_hash": source_hash,
        "final_placement": first,
        "second_placement_hash": canonical_hash(second),
        "full_exact_placement_determinism": True,
        "p2_public_replay": metric_first,
        "second_metric_hash": canonical_hash(metric_second),
        "p2_determinism": True,
        "runtime_p2_full_domain_parity": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "placement", "metric"), default="all")
    phase = parser.parse_args().phase
    if phase == "all":
        print("P3_FINAL_CAPTURE=" + canonical_json(capture()), flush=True)
    else:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        sources = canonical_hash(
            {m.__name__: inspect.getsource(m) for m in (exact, metric, runtime)}
        )
        result = placement_capture() if phase == "placement" else metric_capture()
        assert (
            head
            == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        )
        assert sources == canonical_hash(
            {m.__name__: inspect.getsource(m) for m in (exact, metric, runtime)}
        )
        print(
            "P3_PHASE_CAPTURE="
            + canonical_json(
                {"phase": phase, "head": head, "source_code_hash": sources, "result": result}
            ),
            flush=True,
        )
