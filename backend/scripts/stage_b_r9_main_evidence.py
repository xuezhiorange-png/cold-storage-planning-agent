"""Read-only R9 MAIN projections of original durable receipts and actual geometry.

No solve, engineering acceptance, counter mutation or new quality definition.
Missing/ambiguous checkpoints stay NOT_EVALUATED, never fabricated as zero.
"""

import json
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    compare_area_efficient_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    compare_balanced_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import POOL_ELAPSED_TARGET


def route_resource_evidence(
    output: Path, result: Any, lease: Any, candidates: list[Any], facts: dict[str, Any]
) -> dict[str, Any]:
    events = lease.record.get("enumeration_events", [])
    journal = output / "journal.jsonl"
    checkpoints = (
        [json.loads(s) for s in journal.read_text().splitlines()] if journal.exists() else []
    )
    starts = [i for i, c in enumerate(checkpoints) if c.get("phase") == "POOL_COMPOSITION_STARTED"]
    rows = []
    compositions = {c["composition_identity"]: c for c in (result or {}).get("compositions", [])}
    for ordinal, h in enumerate(lease.decision["compositions"]):
        current = [
            e
            for e in events
            if e.get("sources", {}).get("composition_hash") == h["composition_hash"]
        ]
        shares = [e for e in current if e.get("kind") == "HANDOFF_SHARE_STARTED"]
        route = [e for e in current if e.get("kind") == "SAME_PROXY_ROUTE_REFINEMENT"]
        admitted = [e for e in route if e.get("status") == "LOCAL_PREPARATION_ADMITTED"]
        completed = [e for e in route if e.get("status") == "LOCAL_PREPARATION_COMPLETE"]
        discarded = [e for e in route if e.get("status") == "LOCAL_SCOPE_DISCARDED"]
        comp = compositions.get(h["identity"], {})
        error = comp.get("error", {})
        failure_path = output / "failure.json"
        if not error and ordinal == lease.record.get("cursor", 0) - 1 and failure_path.exists():
            error = json.loads(failure_path.read_text())
        active_failure = bool(admitted and len(discarded) < len(admitted) and error)
        attempts = [
            dict(
                status="SKIPPED"
                if e["status"] == "LOCAL_REFINEMENT_SKIPPED"
                else "RESOURCE_FAILED"
                if active_failure and any(s in str(error) for s in ("RESOURCE", "LIMIT"))
                else "ADMITTED",
                reason=e.get("reason"),
                sequence=e.get("sequence"),
                remaining_at_preflight=e.get("available", "NOT_EVALUATED"),
                estimate=e.get("estimate"),
                original_error=error if active_failure else None,
            )
            for e in route
            if e.get("status") in {"LOCAL_PREPARATION_ADMITTED", "LOCAL_REFINEMENT_SKIPPED"}
        ]
        remaining: Any = "NOT_EVALUATED_MISSING_OR_AMBIGUOUS_CHECKPOINT"
        if len(shares) == 1 and ordinal < len(starts):
            share = shares[0]
            end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(checkpoints)
            ends = [
                c
                for c in checkpoints[starts[ordinal] : end]
                if c.get("phase") == "STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED"
            ]
            audit = [
                c
                for c in checkpoints
                if c.get("phase") == "STAGE_B_ENUMERATION_AUDIT_RECORDED"
                and c.get("snapshot", {})
                .get("resource_events", {})
                .get("STAGE_B_ENUMERATION_AUDIT_RECORD")
                == share.get("sequence")
            ]
            if len(ends) == len(audit) == 1:
                before, after = audit[0]["snapshot"], ends[0]["snapshot"]
                # Invert the unchanged FairNativeSolver's allocation formulas.
                # Native/check counts cannot change before HANDOFF_SHARE_STARTED.
                count = 6 - ordinal
                work_origin = round(600000 - share["work_share"] * count)
                elapsed_origin = POOL_ELAPSED_TARGET - share["elapsed_share"] * count
                remaining = dict(
                    work=share["work_share"]
                    - (after["model_work"] + after["native_host_work"] - work_origin),
                    native=share["native_share"]
                    - (
                        max(after["solver_wall"], after["solver_monotonic_wall"])
                        - max(before["solver_wall"], before["solver_monotonic_wall"])
                    ),
                    elapsed=share["elapsed_share"] - (after["elapsed_seconds"] - elapsed_origin),
                    checked=share["checked_share"]
                    - (after["checked_solutions"] - before["checked_solutions"]),
                    source="ORIGINAL_FAIR_SHARE_FORMULAS_AND_DURABLE_SNAPSHOTS_NOT_REFILLED",
                )
        rows.append(
            dict(
                identity=h["identity"],
                composition_hash=h["composition_hash"],
                allocation=shares[0] if len(shares) == 1 else "NOT_EVALUATED_NOT_STARTED",
                remaining_at_end=remaining,
                local_attempts=attempts,
                actual_completed_copies=len(completed)
                if not admitted or completed
                else "NOT_EVALUATED_INTERRUPTED_COPY",
                copy_receipts=completed,
                error=error or None,
                status=comp.get("status", "NOT_STARTED" if not current else "SEE_RAW_RECEIPTS"),
            )
        )
    snapshots = {s["candidate_hash"]: s for s in facts["all_valid_proposal_facts"]}
    pairs = []
    for i, candidate in enumerate(candidates):
        rr = candidate.get("proposal", {}).get("route_refinement")
        if not rr:
            continue
        before = next(
            (
                c
                for c in reversed(candidates[:i])
                if c["source_composition_hash"] == candidate["source_composition_hash"]
                and c["proposal"]["zones"] == candidate["proposal"]["zones"]
                and any(
                    canonical_hash(r) == canonical_hash(rr["baseline_route"])
                    for r in c["proposal"].get("routes", [])
                )
            ),
            None,
        )
        after = snapshots[candidate["canonical_result_hash"]]
        pair: dict[str, Any] = dict(
            candidate_hash=candidate["canonical_result_hash"],
            same_room_geometry=True,
            area_proxy=rr["area_proxy"],
            hint_preserved=rr["hint_preserved"],
            route_receipt=rr,
        )
        if before is None:
            pair.update(comparison="NOT_EVALUATED_UNPAIRED_CURRENT_ROUTE", baseline=None)
        else:
            b = snapshots[before["canonical_result_hash"]]
            pair.update(
                baseline=b["candidate_hash"],
                original_nine=compare_balanced_quality(b, after),
                twelve=compare_area_efficient_quality(b, after),
                same_v2=b["functional_diversity"]["meaningful_construction_hash"]
                == after["functional_diversity"]["meaningful_construction_hash"],
                route_before_m=b["metrics"]["personnel_route_m"],
                route_after_m=after["metrics"]["personnel_route_m"],
            )
        if rr["cp_length_mm"] != rr["native_route"]["length_mm"]:
            raise LayoutAuthorityError("R9_EXPORTED_ROUTE_LENGTH_MISMATCH")
        pairs.append(pair)
    return dict(
        per_handoff=rows,
        raw_route_events=[e for e in events if e.get("kind", "").startswith("SAME_PROXY_ROUTE")],
        same_room_route_comparisons=pairs,
        engineering_accepted_route_witness_count=len(pairs),
        route_witnesses_are_new_room_geometries=False,
        baseline_recovery_is_route_improvement=False,
        route_improvement_is_formal_pareto=False,
        truck="NOT_PASSED_WITHOUT_INDEPENDENT_EVIDENCE",
        p2d_full_pass=False,
    )
