"""R10 R2 projections of current execution receipts; never new solver/quality rules."""

import json
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

UNKNOWN = "NOT_EVALUATED"


def organization_evidence(
    output: Path,
    result: Any,
    lease: Any,
    candidates: list[Any],
    facts: dict[str, Any],
    recovery: dict[str, Any],
    ids: set[str],
) -> dict[str, Any]:
    events = lease.record.get("enumeration_events", [])
    counters = lease.record.get("counters", {})
    labels = counters.get("resource_events")
    copy_work = labels.get("ROUTE_LOCAL_MODEL_COPY", 0) if isinstance(labels, dict) else UNKNOWN
    if isinstance(copy_work, int) and copy_work:
        raise LayoutAuthorityError("R10_R2_FORBIDDEN_LOCAL_COPY_RECORDED")
    # Stream the existing journal; retain only numeric composition endpoints.
    checkpoints = []
    journal = output / "journal.jsonl"
    if journal.is_file():
        with journal.open() as source:
            for line in source:
                row = json.loads(line)
                if row.get("phase") in {
                    "POOL_COMPOSITION_STARTED",
                    "STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED",
                }:
                    raw = row.get("snapshot", {})
                    checkpoints.append(
                        dict(
                            phase=row["phase"],
                            snapshot={
                                k: raw[k]
                                for k in (
                                    "model_work",
                                    "native_host_work",
                                    "solver_wall",
                                    "solver_monotonic_wall",
                                    "checked_solutions",
                                    "resource_events",
                                    "elapsed_seconds",
                                )
                                if k in raw
                            },
                        )
                    )
                    if isinstance(raw.get("attempts"), list):
                        checkpoints[-1]["snapshot"]["native_call_count"] = len(raw["attempts"])
    starts = [i for i, c in enumerate(checkpoints) if c["phase"] == "POOL_COMPOSITION_STARTED"]
    cursor = lease.record.get("cursor")
    complete_prefix = type(cursor) is int and len(starts) == cursor
    snapshots = {r["candidate_hash"]: r for r in facts["all_valid_proposal_facts"]}
    current = []
    for candidate in candidates:
        if not _eligible(candidate, ids):
            raise LayoutAuthorityError("R10_R2_REPORT_REQUIRES_CURRENT_ACCEPTED_CANDIDATE")
        if any(
            candidate.get(key) != lease.decision[bound]
            for key, bound in (
                ("source_zone_plan_hash", "zone_plan_hash"),
                ("source_p1_handoff_hash", "p1_hash"),
                ("source_site_geometry_hash", "site_hash"),
            )
        ):
            raise LayoutAuthorityError("R10_R2_REPORT_AUTHORITY_MISMATCH")
        snap = snapshots[candidate["canonical_result_hash"]]
        native = next(
            r for r in candidate["proposal"]["routes"] if r["from_ref"] == "main_entrance"
        )
        actual = next(
            r
            for r in candidate["engineering_validation"]["access_results"]
            if r["from_ref"] == "main_entrance"
        )
        current.append(
            dict(
                candidate_hash=snap["candidate_hash"],
                composition_hash=snap["composition_hash"],
                geometry_hash=snap["geometry_hash"],
                search_stage=candidate["proposal"].get("search_stage", UNKNOWN),
                v2=snap["functional_diversity"],
                room_dimensions_and_areas=snap["area_efficiency"]["rooms"],
                actual_shapes=snap["construction_facts"]["room_shapes"],
                sorting_changing_positions=[
                    z
                    for z in candidate["proposal"]["zones"]
                    if z["zone_code"] in {"sorting_packaging_room", "changing_room"}
                ],
                cp_sat_personnel_portal_and_route=native,
                independently_validated_application_personnel=actual,
                metrics=snap["metrics"],
                current_execution_only=True,
                historical_r9_p04_formally_compared=False,
            )
        )
    compositions = {c["composition_identity"]: c for c in (result or {}).get("compositions", [])}
    rows = []
    for ordinal, handoff in enumerate(lease.decision["compositions"]):
        h = handoff["composition_hash"]
        he = [e for e in events if e.get("sources", {}).get("composition_hash") == h]
        shares = [e for e in he if e.get("kind") == "HANDOFF_SHARE_STARTED"]
        activations = [e for e in he if e.get("kind") == "BOUNDED_IMPROVEMENT_STARTED"]
        baselines = [b for b in recovery["per_handoff_baselines"] if b["composition_hash"] == h]
        accepted = [c for c in current if c["composition_hash"] == h]
        consumption: Any = UNKNOWN
        if complete_prefix and ordinal < len(starts):
            stop = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(checkpoints)
            ends = [
                c
                for c in checkpoints[starts[ordinal] : stop]
                if c["phase"] == "STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED"
            ]
            if len(ends) == 1:
                before, after = checkpoints[starts[ordinal]]["snapshot"], ends[0]["snapshot"]
                needed = {
                    "model_work",
                    "native_host_work",
                    "solver_wall",
                    "solver_monotonic_wall",
                    "checked_solutions",
                    "native_call_count",
                    "resource_events",
                }
                if needed <= before.keys() and needed <= after.keys():
                    deltas = {
                        k: after["resource_events"].get(k, 0) - before["resource_events"].get(k, 0)
                        for k in set(before["resource_events"]) | set(after["resource_events"])
                    }
                    native_delta = max(after["solver_wall"], after["solver_monotonic_wall"]) - max(
                        before["solver_wall"], before["solver_monotonic_wall"]
                    )
                    work_delta = (
                        after["model_work"]
                        + after["native_host_work"]
                        - before["model_work"]
                        - before["native_host_work"]
                    )
                    checked_delta = after["checked_solutions"] - before["checked_solutions"]
                    call_delta = after["native_call_count"] - before["native_call_count"]
                    if (
                        min([native_delta, work_delta, checked_delta, call_delta, *deltas.values()])
                        < 0
                    ):
                        raise LayoutAuthorityError("R10_R2_REPORT_COUNTER_REGRESSION")
                    consumption = dict(
                        native_seconds=native_delta,
                        observable_work=work_delta,
                        checked_assignments=checked_delta,
                        native_calls=call_delta,
                        model_work_labels=deltas,
                        source="ORIGINAL_DURABLE_COMPOSITION_ENDPOINTS",
                    )
        composition = compositions.get(handoff["identity"], {})
        attempts = [
            a
            for a in (result or {}).get("attempts", [])
            if a.get("composition_identity") == handoff["identity"]
        ]
        last = attempts[-1] if attempts else {}
        error = composition.get("error")
        failure = output / "failure.json"
        if not error and ordinal == lease.record.get("cursor", 0) - 1 and failure.exists():
            error = json.loads(failure.read_text())
        rows.append(
            dict(
                ordinal=ordinal + 1,
                identity=handoff["identity"],
                composition_hash=h,
                first_valid_baseline=baselines[0] if len(baselines) == 1 else UNKNOWN,
                first_stage_valid_count=sum(
                    c["search_stage"] == "FEASIBILITY_FIRST" for c in accepted
                ),
                second_stage_started=bool(activations),
                second_stage_activations=activations,
                second_stage_valid_count=sum(
                    c["search_stage"] == "BOUNDED_QUALITY_IMPROVEMENT" for c in accepted
                ),
                valid_candidate_hashes=[c["candidate_hash"] for c in accepted],
                share=shares[0] if len(shares) == 1 else UNKNOWN,
                consumption=consumption,
                status=composition.get("status", last.get("status", UNKNOWN)),
                last_native_solver_status=last.get("solver_status", UNKNOWN),
                termination_reason=error
                or dict(
                    status=composition.get("status", last.get("status", UNKNOWN)),
                    solver_status=last.get("solver_status", UNKNOWN),
                    codes=last.get("candidate_result", {}).get("proposal", {}).get("codes", []),
                ),
            )
        )
    return dict(
        per_handoff=rows,
        valid_candidates=current,
        h1_h4_valid_candidates={r["identity"]: r["valid_candidate_hashes"] for r in rows[:4]},
        local_model_copy_work=copy_work,
        first_recovery_is_quality_improvement=False,
        historical_r9_p04_used_as_formal_frontier=False,
        original_nine_and_twelve=facts["comparisons"],
        unknown_is_infeasible=False,
        real_layout_quality_improved="NOT_ESTABLISHED_BY_SEARCH_PROXY",
        truck="NOT_VALIDATED_WITHOUT_INDEPENDENT_EVIDENCE",
        p2d_full_pass=False,
    )
