"""Bounded multi-structure collection on the unchanged stage-A validation chain.

This internal entry requires a separately approved durable pool authorization,
covering every composition in one shared
ledger. The old stage-A replay grants are explicitly insufficient. No UUID,
family label, output directory or remaining numerical allowance admits a pool.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from cold_storage.modules.layout.application.global_composition_solver import (
    ExecutionAuthorization,
    GlobalCompositionSolver,
    StageALedger,
    generate_global_composition_candidate,
    zone_geometry_hash,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash

IDENTITY = "controlled-multi-structural-construction@1.0.0"
RESOURCE_POLICY = "STAGE_B_SEPARATELY_APPROVED_SHARED_POOL_REQUIRED"


class PoolExecutionAuthorization(ExecutionAuthorization, Protocol):
    """Trusted durable admission port, NOT an Owner authorization implementation.

    validate_pool must verify a separate Owner instruction/source binding and
    atomically reserve the entire ordered plan, not refill per family. Inherited
    begin/checkpoint/validate retain NEW/RESUME, interruption and shared counters.
    The lease must reject unplanned/repeated calls and incomplete history.
    Trusted bootstrap alone supplies a separately pinned Owner pool grant.
    """

    def validate_pool(
        self, ledger: StageALedger, sources: Mapping[str, str], plan: tuple[str, ...]
    ) -> Mapping[str, str]: ...


def _resources(ledger: StageALedger) -> dict[str, Any]:
    return {
        "solver_seconds": ledger.solver_wall,
        "model_work": ledger.model_work,
        "native_host_work": ledger.native_host_work,
        "checked_solutions": ledger.checked_solutions,
        "native_call_count": len(ledger.attempts),
    }


def _eligible(result: Mapping[str, Any], identities: set[str]) -> bool:
    application = result.get("engineering_validation", {})
    rows = [r for r in application.get("access_results", []) if r.get("flow_kind") != "TRUCK"]
    return bool(
        result.get("stage_a_engineering_accepted") is True
        and result.get("independent_validation", {}).get("pass") is True
        and result.get("native_independent_validation", {}).get("pass") is True
        and result.get("native_independent_validation", {}).get("coexistence") is True
        and len(rows) == len(identities) == 11
        and {r.get("requirement_identity") for r in rows} == identities
        and all(r.get("status") == "PASS" for r in rows)
        and application.get("building_footprint")
    )


def generate_global_composition_pool(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    solver: GlobalCompositionSolver,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    """One finite server-derived schedule; every attempt shares ONE ledger.

    Only current server handoffs are searched. Their source family labels are
    scheduling intent, never achieved structural coverage. Each attempt calls
    the complete existing generator/oracles; no prior candidate PASS is reused.
    Model INFEASIBLE means bounded-model UNSAT, never project infeasibility.
    """
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    handoffs = build_structural_compositions(
        canonical_zone_plan, p1_handoff, site_geometry
    ).placement_handoffs
    # Round-robin orientations across families instead of exhausting one family.
    buckets: dict[str, list[Any]] = {}
    for h in sorted(handoffs, key=lambda h: h.composition_identity):
        buckets.setdefault(h.family.value, []).append(h)
    ordered = [
        buckets[f][i]
        for i in range(max(map(len, buckets.values())))
        for f in sorted(buckets)
        if i < len(buckets[f])
    ]
    plan = tuple(h.composition_identity for h in ordered)
    sources = {
        "zone_plan_hash": binding.canonical_zone_plan_hash,
        "p1_hash": binding.p1_handoff_hash,
        "site_hash": binding.site_geometry_hash,
        "schedule_hash": canonical_hash([h.to_dict() for h in ordered]),
    }
    result: dict[str, Any] = {
        "identity": IDENTITY,
        "sources": sources,
        "schedule": list(plan),
        "resource_policy": RESOURCE_POLICY,
        "construction_target": 5,
        "major_family_target": 3,
        "candidates": [],
        "attempts": [],
        "p2d_full_pass_count": 0,
        "p3_complete": False,
        "p2_complete": False,
        "server_replay_accepted": False,
        "project_infeasible_proven": False,
    }
    ledger = execution_ledger
    authorization = ledger.execution_authorization if ledger is not None else None
    admit = getattr(authorization, "validate_pool", None)
    if ledger is None or admit is None:
        result["status"] = "OWNER_POOL_EXECUTION_QUOTA_REQUIRED"
        result["resource_ledger"] = None
    else:
        # Admission happens before any solver call and is never manufactured here.
        result["execution_authorization_receipt"] = dict(admit(ledger, sources, plan))
        ledger.remaining_solver_seconds()
        requirements = {
            r["identity"] for r in binding.access_requirements if r["flow_kind"] != "TRUCK"
        }
        geometries: set[str] = set()
        organizations: set[str] = set()
        major_families: set[str] = set()
        result["status"] = "BOUNDED_SCHEDULE_COMPLETE_TARGET_NOT_MET"
        for h in ordered:
            before = _resources(ledger)
            record: dict[str, Any] = {
                "composition_identity": h.composition_identity,
                "source_family_intent": h.family.value,
                "resources_before": before,
            }
            result["attempts"].append(record)
            try:
                ledger.guard()
                ledger.remaining_solver_seconds()
                candidate = deepcopy(
                    generate_global_composition_candidate(
                        canonical_zone_plan,
                        p1_handoff,
                        site_geometry,
                        solver=solver,
                        composition_identity=h.composition_identity,
                        execution_ledger=ledger,
                    )
                )
                record["candidate_result_hash"] = candidate["canonical_result_hash"]
                record["solver_status"] = candidate["proposal"].get("solver_status")
                record["search_outcome"] = {
                    "UNKNOWN": "SEARCH_UNKNOWN_NOT_ACCEPTED",
                    "INFEASIBLE": "BOUNDED_MODEL_UNSAT_NOT_PROJECT_INFEASIBLE",
                }.get(record["solver_status"], "SEE_SOLVER_STATUS_AND_ENGINEERING_VALIDATION")
                record["candidate_result"] = candidate
                ledger.guard()
                if (
                    candidate.get("source_zone_plan_hash") != sources["zone_plan_hash"]
                    or candidate.get("source_p1_handoff_hash") != sources["p1_hash"]
                    or candidate.get("source_site_geometry_hash") != sources["site_hash"]
                    or candidate.get("source_composition_handoff_hash")
                    != canonical_hash(h.to_dict())
                    or candidate["canonical_result_hash"]
                    != canonical_hash(
                        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
                    )
                ):
                    raise LayoutAuthorityError("STAGE_B_CANDIDATE_SOURCE_OR_HASH_MISMATCH")
                if not _eligible(candidate, requirements):
                    record["status"] = "ENGINEERING_INCOMPLETE_NOT_COUNTED"
                    continue
                zones = candidate["proposal"]["zones"]
                diversity = construction_diversity(zones)
                geometry = diversity["symmetry_invariant_geometry_hash"]
                organization = diversity["major_organization_hash"]
                record["diversity"] = diversity
                if geometry in geometries:
                    record["status"] = "DUPLICATE_GEOMETRY_NOT_COUNTED"
                    continue
                geometries.add(geometry)
                if organization in organizations:
                    record["status"] = "SAME_MAJOR_ORGANIZATION_NOT_COUNTED"
                    continue
                organizations.add(organization)
                major_families.add(diversity["major_family_hash"])
                record["status"] = "CONSTRUCTION_ACCEPTED_NOT_P2D"
                result["candidates"].append(
                    {
                        "candidate_id": canonical_hash((sources, zone_geometry_hash(zones))),
                        "geometry_hash": zone_geometry_hash(zones),
                        "diversity": diversity,
                        "source_composition_identity": h.composition_identity,
                        "candidate_result": candidate,
                    }
                )
                if len(result["candidates"]) >= 5 and len(major_families) >= 3:
                    result["status"] = "CONSTRUCTION_TARGETS_MET_NOT_P2D"
                    break
            except LayoutAuthorityError as error:
                record["error"] = {"code": error.code, "details": error.details}
                record["status"] = "INTERRUPTED_NOT_ACCEPTED"
                # Never retry a partially accounted request or recycle its budget.
                result["status"] = "INTERRUPTED_UNKNOWN_NOT_PROJECT_INFEASIBLE"
                if "LIMIT" in error.code or "ALLOWANCE_EXHAUSTED" in error.code:
                    result["status"] = "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE"
                break
            finally:
                record["resources_after"] = _resources(ledger)
                ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        result["resource_ledger"] = _resources(ledger)
    result["construction_candidate_count"] = len(result["candidates"])
    result["validated_non_truck_candidate_count"] = len(result["candidates"])
    result["distinct_geometry_count"] = len(
        {
            a["diversity"]["symmetry_invariant_geometry_hash"]
            for a in result["attempts"]
            if "diversity" in a
        }
    )
    result["major_structural_family_count"] = len(
        {c["diversity"]["major_family_hash"] for c in result["candidates"]}
    )
    result["source_family_attempt_counts"] = dict(
        Counter(a["source_family_intent"] for a in result["attempts"])
    )
    result["canonical_result_hash"] = canonical_hash(result)
    return result
