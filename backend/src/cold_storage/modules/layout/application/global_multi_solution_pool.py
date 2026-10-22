"""Opt-in multi-solution collection; unchanged server schedule and acceptance."""

from collections import Counter
from collections.abc import Mapping
from typing import Any, cast

from cold_storage.modules.layout.application.global_composition_enumeration import (
    MultiSolutionSolver,
    generate_global_composition_candidates,
    resource_interrupted,
)
from cold_storage.modules.layout.application.global_composition_pool import (
    _eligible,
    _resources,
    generate_global_composition_pool,
)
from cold_storage.modules.layout.application.global_composition_solver import (
    GlobalCompositionSolver,
    StageALedger,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.stage_b_search_policy import (
    POLICY,
    POLICY_HASH,
    schedule_hash,
)
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.construction_branch_diversity import (
    construction_branch_diversity,
)
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash

MAX_ACCEPTED_PER_HANDOFF = 5


def generate_multi_solution_pool(
    plan: Mapping[str, Any],
    p1: Mapping[str, Any],
    site: ValidatedSiteGeometryV1,
    *,
    solver: MultiSolutionSolver,
    execution_ledger: StageALedger | None = None,
    fair_search: bool = False,
) -> dict[str, Any]:
    # This quota-free call only derives the original deterministic server schedule.
    # Its solver port is never called without a ledger.
    result = generate_global_composition_pool(
        plan, p1, site, solver=cast(GlobalCompositionSolver, solver)
    )
    result.pop("canonical_result_hash")
    result.update(identity="controlled-multi-solution-construction@1.0.0", compositions=[])
    if fair_search:
        if getattr(solver, "policy_hash", None) != POLICY_HASH:
            raise LayoutAuthorityError("STAGE_B_FAIR_SOLVER_POLICY_MISMATCH")
        result["sources"]["schedule_hash"] = schedule_hash(result["sources"]["schedule_hash"])
        result.update(
            identity="controlled-fair-multi-solution-construction@1.0.0", search_policy=dict(POLICY)
        )
    ledger = execution_ledger
    lease = ledger.execution_authorization if ledger else None
    admit = getattr(lease, "validate_pool", None)
    if ledger is None or admit is None or not callable(getattr(lease, "record_enumeration", None)):
        result["status"] = "OWNER_MULTI_SOLUTION_POOL_EXECUTION_QUOTA_REQUIRED"
        result["canonical_result_hash"] = canonical_hash(result)
        return result
    result["execution_authorization_receipt"] = dict(
        admit(ledger, result["sources"], tuple(result["schedule"]))
    )
    binding = bind_layout_authority(plan, p1, site)
    identities = {r["identity"] for r in binding.access_requirements if r["flow_kind"] != "TRUCK"}
    handoffs = {
        h.composition_identity: h
        for h in build_structural_compositions(plan, p1, site).placement_handoffs
    }
    geometries: set[str] = set()
    organizations: set[str] = set()
    families: set[str] = set()
    legacy_organizations: set[str] = set()
    result["status"] = "BOUNDED_SCHEDULE_COMPLETE_TARGET_NOT_MET"
    stop = False
    for index, identity in enumerate(result["schedule"]):
        h = handoffs[identity]
        composition = {"composition_identity": identity, "resources_before": _resources(ledger)}
        result["compositions"].append(composition)
        stream = generate_global_composition_candidates(
            plan, p1, site, solver=solver, composition_identity=identity, execution_ledger=ledger
        )
        accepted = 0
        try:
            ledger.guard()
            ledger.remaining_solver_seconds()
            if fair_search:
                start_handoff = getattr(solver, "start_handoff", None)
                if not callable(start_handoff):
                    raise LayoutAuthorityError("STAGE_B_FAIR_SOLVER_POLICY_MISMATCH")
                start_handoff(ledger, len(result["schedule"]) - index)
            for candidate in stream:
                record = {
                    "composition_identity": identity,
                    "source_family_intent": h.family.value,
                    "candidate_result": candidate,
                    "candidate_result_hash": candidate["canonical_result_hash"],
                    "solver_status": candidate["proposal"].get("solver_status"),
                    "resources_after": _resources(ledger),
                }
                result["attempts"].append(record)
                expected = result["sources"]
                if (
                    candidate.get("source_zone_plan_hash") != expected["zone_plan_hash"]
                    or candidate.get("source_p1_handoff_hash") != expected["p1_hash"]
                    or candidate.get("source_site_geometry_hash") != expected["site_hash"]
                    or candidate.get("source_composition_handoff_hash")
                    != canonical_hash(h.to_dict())
                    or candidate["canonical_result_hash"]
                    != canonical_hash(
                        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
                    )
                ):
                    raise LayoutAuthorityError("STAGE_B_CANDIDATE_SOURCE_OR_HASH_MISMATCH")
                ledger.guard()
                if fair_search and "STAGE_B_HANDOFF_SHARE_EXHAUSTED" in candidate["proposal"].get(
                    "codes", []
                ):
                    record["status"] = "HANDOFF_SHARE_COMPLETE_NOT_INFEASIBLE"
                    break
                if record["solver_status"] == "BOUNDED_TOPOLOGY_REFINEMENT_LIMIT":
                    record["status"] = "SHARED_CHECKED_ASSIGNMENT_LIMIT_NOT_COUNTED"
                    result["status"] = "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE"
                    stop = True
                    break
                if resource_interrupted(candidate):
                    record["status"] = "RESOURCE_INTERRUPTED_NOT_COUNTED"
                    result["status"] = "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE"
                    stop = True
                    break
                if not _eligible(candidate, identities):
                    record["status"] = {
                        "UNKNOWN": "SEARCH_UNKNOWN_NOT_ACCEPTED",
                        "INFEASIBLE": "BOUNDED_MODEL_UNSAT_NOT_PROJECT_INFEASIBLE",
                    }.get(record["solver_status"], "ENGINEERING_INCOMPLETE_NOT_COUNTED")
                    continue
                diversity = construction_diversity(candidate["proposal"]["zones"])
                geometry = diversity["symmetry_invariant_geometry_hash"]
                organization = diversity["major_organization_hash"]
                legacy_organizations.add(organization)
                if fair_search:
                    branches = construction_branch_diversity(
                        candidate["proposal"]["zones"],
                        candidate["engineering_validation"]["access_results"],
                    )
                    record["functional_diversity"] = branches
                    if not branches["countable"]:
                        record["status"] = "FUNCTIONAL_EVIDENCE_INCOMPLETE_NOT_COUNTED"
                        geometries.add(geometry)
                        continue
                    organization = branches["meaningful_construction_hash"]
                record["diversity"] = diversity
                if geometry in geometries:
                    record["status"] = "DUPLICATE_GEOMETRY_NOT_COUNTED"
                    continue
                geometries.add(geometry)
                if organization in organizations:
                    record["status"] = (
                        "SAME_FUNCTIONAL_ORGANIZATION_NOT_COUNTED"
                        if fair_search
                        else "SAME_MAJOR_ORGANIZATION_NOT_COUNTED"
                    )
                    continue
                organizations.add(organization)
                record["status"] = "CONSTRUCTION_ACCEPTED_NOT_P2D"
                result["candidates"].append(
                    {
                        "candidate_id": canonical_hash((expected, geometry)),
                        "geometry_hash": geometry,
                        "source_composition_identity": identity,
                        "diversity": diversity,
                        "candidate_result": candidate,
                    }
                )
                families.add(diversity["major_family_hash"])
                accepted += 1
                if fair_search:
                    result["candidates"][-1]["functional_diversity"] = branches
                if len(result["candidates"]) >= 5 and len(families) >= 3:
                    result["status"] = "CONSTRUCTION_TARGETS_MET_NOT_P2D"
                    stop = True
                    break
                if accepted >= MAX_ACCEPTED_PER_HANDOFF:
                    break
        except LayoutAuthorityError as error:
            composition["error"] = {"code": error.code, "details": error.details}
            if fair_search and error.code == "STAGE_B_HANDOFF_SHARE_EXHAUSTED":
                composition["status"] = "HANDOFF_SHARE_COMPLETE_NOT_INFEASIBLE"
            else:
                result["status"] = "INTERRUPTED_UNKNOWN_NOT_PROJECT_INFEASIBLE"
                stop = True
        finally:
            stream.close()
            composition["resources_after"] = _resources(ledger)
            ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        if stop:
            break
    result.update(
        construction_candidate_count=len(result["candidates"]),
        validated_non_truck_candidate_count=len(result["candidates"]),
        distinct_geometry_count=len(geometries),
        distinct_construction_count=len(organizations),
        major_structural_family_count=len(families),
        exported_solver_proposal_count=sum(
            bool(a["candidate_result"]["proposal"].get("zones")) for a in result["attempts"]
        ),
        checked_physical_assignment_count=ledger.checked_solutions,
        candidate_validation_count=ledger.resource_events.get("STAGE_B_CANDIDATE_VALIDATION", 0),
        resource_ledger=_resources(ledger),
        source_family_attempt_counts=dict(
            Counter(a["source_family_intent"] for a in result["attempts"])
        ),
    )
    if fair_search:
        result.update(
            distinct_physical_geometry_count=len(geometries),
            distinct_meaningful_construction_count=len(organizations),
            legacy_distinct_organization_count=len(legacy_organizations),
            historical_statistics_rewritten=False,
        )
    result["canonical_result_hash"] = canonical_hash(result)
    return result
