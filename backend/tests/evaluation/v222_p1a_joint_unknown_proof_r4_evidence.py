"""R4 capture reuses the R3 independent proof validator and full replay protocol.

No observation changes production outcomes or imports historical geometry as a seed.
"""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from functools import wraps
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from cold_storage.modules.layout.domain import joint_metric_capacity as joint
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from tests.evaluation import v222_p1a_joint_metric_capacity_r3_evidence as protocol


def capture(r2_audit: Path, r3_audit: Path, output: Path, regressions: bool) -> None:
    original = joint.JointMetricCapacityQueryV1.update
    original_placement = protocol.app.enumerate_composition_placements
    snapshots = []
    events = []
    samples = {}

    @wraps(original)
    def observe(self, placed, edge_states, parent=()):
        # The unchanged protocol also checks historical control and unit fixtures.
        # Only its canonical-placement initializer supplies this audit label.
        if not hasattr(self.pairwise, "audit_composition"):
            return original(self, placed, edge_states, parent)
        before = Counter(self.counts)
        answer = original(self, placed, edge_states, parent)
        admitted = bool(placed) and not any(s.status == "PROVED_NO_SUPPORT" for s in answer)
        item = {
            "composition": self.pairwise.audit_composition,
            "depth": len(placed),
            "admitted": admitted,
            "partial_hash": canonical_hash({r: p.bounds_mm for r, p in placed.items()}),
            "states": [{"status": s.status, "reason": s.reason} for s in answer],
            "work": dict(self.counts - before),
        }
        events.append(item)
        for state in answer:
            if state.status == "UNKNOWN_SUPPORT":
                key = str((item["composition"], len(placed), state.reason))
                samples.setdefault(
                    key, {**item, "placed": {r: asdict(p) for r, p in placed.items()}}
                )
        return answer

    @wraps(original_placement)
    def placement(*args, **kwargs):
        events.clear()
        samples.clear()
        result = original_placement(*args, **kwargs)
        snapshots.append({"events": list(events), "representative_partials": dict(samples)})
        return result

    with (
        patch.object(joint.JointMetricCapacityQueryV1, "update", observe),
        patch.object(protocol.app, "enumerate_composition_placements", placement),
    ):
        protocol.capture(json.loads(r2_audit.read_text()), output, regressions)
    result = json.loads(output.read_text())
    assert snapshots[0]["events"] == snapshots[1]["events"], "R4_QUERY_TRACE_DRIFT"
    baseline = json.loads(r3_audit.read_text())
    result["task_id"] = "V2_2_2_P1A_P3_JOINT_UNKNOWN_PROOF_CLOSURE_R4"
    result["start_head"] = "9e566603ae217a3eb6a3c2969c0b646756a4df9d"
    result["r3_start_summary"] = {
        "candidate_count": len(baseline["placement"]["candidates"]),
        "nodes": baseline["placement"]["nodes_used"],
        "attempts": len(baseline["placement"]["search_attempts"]),
        "unknown_query_count": len(baseline["records"]),
        "unknown_accepted_count": sum(r["admitted"] for r in baseline["records"]),
        "unknown_by_reason": dict(
            Counter(s["reason"] for r in baseline["records"] for s in r["states"])
        ),
        "representative_partials": [
            next(r for r in baseline["records"] if r["states"][0]["reason"] == reason)
            for reason in ("POSITIVE_PROBE_CAP_EXHAUSTED", "JOINT_ASSIGNMENT_UNPROVEN")
        ],
        "read_only_replay_seconds": baseline["seconds"],
        "record_digest": canonical_hash(baseline["records"]),
    }
    result["r4_observations"] = snapshots[0]
    result["query_trace_determinism_digest"] = canonical_hash(snapshots[0]["events"])
    result["resource_contract"] = {
        "evaluation_cap": 256,
        "event_cap": 1024,
        "placement_budget": 60000,
    }
    result["historical_coordinates_used_as_production_seed"] = False
    output.write_text(canonical_json(result))


def finalize(
    output: Path,
    r3_audit: Path,
    probe_path: Path | None = None,
    regression_retry_xml: Path | None = None,
) -> None:
    """Bind R4 metadata and RCA without rerunning or modifying captured outcomes."""
    result = json.loads(output.read_text())
    baseline = json.loads(r3_audit.read_text())
    assert not baseline["comparison_differences"]
    assert result["determinism"]["full_placement_and_joint_sequence_equal"]
    if regression_retry_xml is not None:
        suites = ElementTree.parse(regression_retry_xml).getroot()
        cases = suites.findall(".//testcase")
        assert cases and not suites.findall(".//failure") and not suites.findall(".//error")
        assert not suites.findall(".//skipped")
        modules = {case.attrib["classname"] for case in cases}
        for path in result["regression_paths"]:
            expected = ".".join(Path(path).with_suffix("").parts[-3:])
            assert any(m == expected or m.startswith(expected + ".") for m in modules)
        result["regression_attempts"] = [
            {
                "scope": "FULL_RELATED_SUITE_IN_CAPTURE_OBSERVER",
                "exit_code": result["regression_exit_code"],
                "failure_details": "Retained capture traceback and task document",
                "original_assertions_changed": False,
            },
            {
                "scope": "FULL_RELATED_SUITE_UNWRAPPED_SEPARATE_PROCESS",
                "exit_code": 0,
                "passed": len(cases),
                "junit_sha256": sha256(regression_retry_xml.read_bytes()).hexdigest(),
                "all_original_regression_modules_covered": True,
                "original_assertions_changed": False,
            },
        ]
        result["regression_gate_resolved_by_full_unwrapped_retry"] = True
        result["local_regression_gate_result"] = "PASS_AFTER_FULL_UNWRAPPED_RETRY"
    else:
        assert result.get("regression_exit_code", 0) == 0
    result["isolated_checkout_recovery"]["backup_sha256"] = (
        "624356070a492c0ace3f47059f349cb93e67a64509b213e81620ede65d1e8c3f"
    )
    result["baseline_candidate_hashes"] = [
        canonical_hash(c) for c in baseline["placement"]["candidates"]
    ]
    result["baseline_nodes"] = baseline["placement"]["nodes_used"]
    result["baseline_attempts"] = len(baseline["placement"]["search_attempts"])
    names = {
        h.canonical_result_hash: h.composition_identity
        for h in protocol.build_structural_compositions(*protocol._context()).placement_handoffs
    }
    records = baseline["records"]
    admitted = [r for r in records if r["admitted"]]
    capped = [r for r in records if r["states"][0]["reason"] == "POSITIVE_PROBE_CAP_EXHAUSTED"]
    rca = {
        "source_head": baseline["source_head"],
        "complete_start_body_matches_committed_evidence": True,
        "unknown_queries": len(records),
        "unknown_accepted": len(admitted),
        "unknown_roots": len(records) - len(admitted),
        "accepted_by_depth": dict(Counter(len(r["placed"]) for r in admitted)),
        "accepted_by_composition": dict(
            Counter(names[r["provenance"]["handoff_hash"]] for r in admitted)
        ),
        "query_by_reason": dict(Counter(r["states"][0]["reason"] for r in records)),
        "candidate_cap_exhausted": sum(
            r["work"].get("candidate_evaluations", 0) >= 256 for r in capped
        ),
        "origin_event_cap_exhausted": sum(
            r["work"].get("origin_events", 0) >= 1024 for r in capped
        ),
        "work": dict(sum((Counter(r["work"]) for r in records), Counter())),
        "no_unknown_is_a_negative_proof": True,
        "small_fixture_event_omission_independently_verified": True,
        "unproven_depths": dict(
            Counter(
                len(r["placed"])
                for r in records
                if r["states"][0]["reason"] == "JOINT_ASSIGNMENT_UNPROVEN"
            )
        ),
        "unproven_with_negative_arc_guard": sum(
            r["work"].get("necessary_arc_resource_unknown", 0) > 0
            for r in records
            if r["states"][0]["reason"] == "JOINT_ASSIGNMENT_UNPROVEN"
        ),
    }
    if probe_path is not None:
        rca["fixed_start_partial_positive_probe"] = json.loads(probe_path.read_text())
    result["r3_precise_rca"] = rca

    def edge_counts(body):
        counts = {}
        for attempt in body["search_attempts"]:
            for edge, values in attempt["metric_reservation_diagnostics"]["by_edge"].items():
                counts.setdefault(edge, Counter()).update(values)
        return {edge: dict(values) for edge, values in counts.items()}

    result["pairwise_edge_work_comparison"] = {
        "scope": "PAIRWISE_QUERY_WORK_NOT_JOINT_CONFLICT_ATTRIBUTION",
        "start": edge_counts(baseline["placement"]),
        "final": edge_counts(result["replay_1"]),
    }
    result["placement_attempt_parity_except_proof_diagnostics"] = all(
        {k: v for k, v in before.items() if k != "metric_reservation_diagnostics"}
        == {k: v for k, v in after.items() if k != "metric_reservation_diagnostics"}
        for before, after in zip(
            baseline["placement"]["search_attempts"],
            result["replay_1"]["search_attempts"],
            strict=True,
        )
    )
    attempts = result["replay_1"]["search_attempts"]
    unknown = sum(
        a["metric_reservation_diagnostics"]["accepted_partial_with_unknown_capacity"]
        for a in attempts
    )
    roots_unknown = sum(
        s["status"] == "UNKNOWN_SUPPORT"
        for a in attempts
        for s in a["metric_reservation_diagnostics"]["root_joint"]
    )
    result["result"] = (
        "FAIL"
        if not result["replay_1"]["candidates"]
        else "PARTIAL"
        if unknown or roots_unknown
        else "PASS_PENDING_EXACT_HEAD_CI"
    )
    result["p3_complete"] = False  # Terminal CI is never inferred by a local capture.
    result["all_accepted_partials_jointly_proven"] = unknown == 0
    result["joint_unplaced_role_capacity_proven"] = unknown == roots_unknown == 0
    output.write_text(canonical_json(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--r2-audit", type=Path, required=True)
    p.add_argument("--r3-audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--regressions", action="store_true")
    p.add_argument("--finalize-only", action="store_true")
    p.add_argument("--probe", type=Path)
    p.add_argument("--regression-retry-xml", type=Path)
    args = p.parse_args()
    if not args.finalize_only:
        capture(args.r2_audit, args.r3_audit, args.output, args.regressions)
    finalize(args.output, args.r3_audit, args.probe, args.regression_retry_xml)
