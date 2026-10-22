"""Read-only analysis of existing pool evidence; never invokes a solver."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.construction_diagnostics import construction_diagnostics


def analyze_evidence(root: Path) -> dict[str, Any]:
    ledger = json.loads((root / "resource_ledger.json").read_text())
    structures = []
    calls = []
    diagnostics = []
    input_hashes = {}
    call_work: dict[tuple[int, int], dict[str, Any]] = {}
    journal = root.parent / "durable-authorization/journal.jsonl"
    if journal.exists():
        input_hashes["../durable-authorization/journal.jsonl"] = hashlib.sha256(
            journal.read_bytes()
        ).hexdigest()
        for line in journal.read_text().splitlines():
            event = json.loads(line)
            snapshot = event["snapshot"]
            if event["phase"] in ("CP_SAT_STARTED", "CP_SAT_RETURNED"):
                ordinal = len(snapshot["attempts"]) + (event["phase"] == "CP_SAT_STARTED")
                edge = "before" if event["phase"] == "CP_SAT_STARTED" else "after"
                call_work.setdefault((event["pool"], ordinal), {})[edge] = {
                    k: snapshot[k] for k in ("model_work", "native_host_work", "elapsed_seconds")
                }
    for name in (
        "resource_ledger.json",
        "main_pool.json",
        "replay_pool.json",
        "source_binding.json",
    ):
        input_hashes[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    for mode, record in zip(("main", "replay"), ledger["pools"], strict=True):
        pool = json.loads((root / f"{mode}_pool.json").read_text())
        native = record["counters"]["attempts"]
        for a in pool["attempts"]:
            before, after = a["resources_before"], a["resources_after"]
            start, end = before["native_call_count"], after["native_call_count"]
            c = a.get("candidate_result", {})
            proposal = c.get("proposal", {})
            topology_cuts = proposal.get("topology_refinement_cuts", [])
            final_feasible = sum(
                call["phase"] == "ALL_ROOMS_ALL_ACCESS"
                and call["solver_status"] in ("FEASIBLE", "OPTIMAL")
                for call in native[start:end]
            )
            structures.append(
                {
                    "pool": mode,
                    "composition": a["composition_identity"],
                    "family_intent": a["source_family_intent"],
                    "pool_status": a["status"],
                    "solver_status": a.get("solver_status"),
                    "error": a.get("error"),
                    "solver_seconds": after["solver_seconds"] - before["solver_seconds"],
                    "model_work": after["model_work"] - before["model_work"],
                    "native_host_work": after["native_host_work"] - before["native_host_work"],
                    "native_calls": end - start,
                    "complete_zone_count": len(c.get("proposal", {}).get("zones", [])),
                    "native_complete_model_feasible_assignments": final_feasible,
                    "model_zone_count": proposal.get("model_zone_count"),
                    "topology_rejected_assignments": topology_cuts,
                    "construction_outcome": "TOPOLOGY_REJECTED_THEN_UNKNOWN"
                    if topology_cuts and a.get("solver_status") == "UNKNOWN"
                    else a["status"],
                    "engineering_accepted": c.get("stage_a_engineering_accepted", False),
                    "native_independent": c.get("native_independent_validation"),
                    "independent": c.get("independent_validation"),
                    "diversity": a.get("diversity"),
                    "dedup_rejection": a["status"]
                    if a["status"]
                    in {"DUPLICATE_GEOMETRY_NOT_COUNTED", "SAME_MAJOR_ORGANIZATION_NOT_COUNTED"}
                    else None,
                }
            )
            for number, call in enumerate(native[start:end], start + 1):
                calls.append(
                    {
                        "pool": mode,
                        "composition": a["composition_identity"],
                        "ordinal": number,
                        "original_work_checkpoints": call_work.get(
                            (1 if mode == "main" else 2, number), "UNAVAILABLE"
                        ),
                        "work_units_are_not_native_branches_or_conflicts": True,
                        **call,
                    }
                )
            if c.get("proposal", {}).get("zones"):
                diagnostics.append(
                    {
                        "pool": mode,
                        "composition": a["composition_identity"],
                        "candidate_result_hash": c["canonical_result_hash"],
                        "diagnostics": construction_diagnostics(
                            c["proposal"]["zones"], c["engineering_validation"]
                        ),
                    }
                )
    assert len(calls) == ledger["totals"]["native_calls"]
    return {
        "identity": "stage-b-existing-evidence-analysis@1.0.0",
        "source_file_sha256": input_hashes,
        "structure_attempt_records": structures,
        "native_call_records": calls,
        "complete_candidate_diagnostics": diagnostics,
        "actual_resource_totals": ledger["totals"],
        "receiving_mapping": "UNAVAILABLE_NOT_INFERRED_FROM_TRUCK_ENTRANCE",
        "real_new_solves": 0,
        "new_owner_quota_consumed": False,
        "real_quality_improvement_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Analysis output must not overwrite historical evidence")
    result = analyze_evidence(args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
