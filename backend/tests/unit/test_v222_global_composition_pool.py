"""Stage B orchestration with synthetic ports, no Owner quota and no CP-SAT."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cold_storage.bootstrap.global_composition import generate_controlled_global_layout_pool
from cold_storage.modules.layout.application import global_composition_pool as pool
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from tests.unit.test_v222_construction_diversity import rooms
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


class SyntheticLease:
    """Only a test double, never installed at bootstrap or persisted as approval."""

    def __init__(self):
        self.admissions = []

    def validate_pool(self, ledger, sources, plan):
        self.admissions.append((id(ledger), sources, plan))
        return {"mode": "SYNTHETIC_TEST_ONLY", "approval": "NOT_A_REAL_EXECUTION_GRANT"}

    def validate(self, ledger):
        assert ledger.solver_history_verified

    def checkpoint(self, *args):
        pass

    def begin(self, sources):
        assert sources["composition_hash"]


def setup_ports(monkeypatch, outcomes):
    plan, p1, site = _context()
    requirements = pool.bind_layout_authority(plan, p1.to_dict(), site).access_requirements
    ids = {r["identity"] for r in requirements if r["flow_kind"] != "TRUCK"}
    handoffs = pool.build_structural_compositions(plan, p1.to_dict(), site).placement_handoffs
    binding = pool.bind_layout_authority(plan, p1.to_dict(), site)
    calls = []

    def generate(*args, execution_ledger, composition_identity, **kwargs):
        calls.append((id(execution_ledger), composition_identity))
        execution_ledger.model_work += 10
        value = outcomes[len(calls) - 1]
        if isinstance(value, Exception):
            raise value
        body = {
            "proposal": {"solver_status": "FEASIBLE", "zones": rooms(value)},
            "stage_a_engineering_accepted": True,
            "independent_validation": {"pass": True},
            "native_independent_validation": {"pass": True, "coexistence": True},
            "engineering_validation": {
                "building_footprint": {"synthetic": True},
                "access_results": [
                    {"requirement_identity": i, "flow_kind": "MATERIAL", "status": "PASS"}
                    for i in sorted(ids)
                ],
            },
            "source_zone_plan_hash": binding.canonical_zone_plan_hash,
            "source_p1_handoff_hash": binding.p1_handoff_hash,
            "source_site_geometry_hash": binding.site_geometry_hash,
            "source_composition_handoff_hash": canonical_hash(
                next(
                    h.to_dict() for h in handoffs if h.composition_identity == composition_identity
                )
            ),
        }
        body["canonical_result_hash"] = canonical_hash(body)
        return body

    monkeypatch.setattr(pool, "generate_global_composition_candidate", generate)
    lease = SyntheticLease()
    ledger = StageALedger(solver_history_verified=True, execution_authorization=lease)
    return plan, p1.to_dict(), site, ledger, lease, calls


def test_bootstrap_without_separate_quota_cannot_invoke_native_solver(monkeypatch) -> None:
    solve = Mock(side_effect=AssertionError("unauthorized native solve"))
    monkeypatch.setattr(
        "cold_storage.bootstrap.global_composition.OrToolsGlobalCompositionSolver.solve", solve
    )
    plan, p1, site = _context()
    result = generate_controlled_global_layout_pool(plan, p1.to_dict(), site)
    assert result["status"] == "OWNER_POOL_EXECUTION_QUOTA_REQUIRED"
    assert result["construction_candidate_count"] == result["p2d_full_pass_count"] == 0
    assert result["attempts"] == []
    solve.assert_not_called()


def test_old_stage_a_lease_cannot_admit_pool(monkeypatch) -> None:
    plan, p1, site = _context()
    ledger = StageALedger(execution_authorization=SimpleNamespace(validate=lambda _: None))
    result = pool.generate_global_composition_pool(
        plan,
        p1.to_dict(),
        site,
        solver=Mock(),
        execution_ledger=ledger,
    )
    assert result["status"] == "OWNER_POOL_EXECUTION_QUOTA_REQUIRED"


def test_five_geometric_organizations_collected_and_reproducible(monkeypatch) -> None:
    signatures = ["EEEEEE", "EEENNN", "EENNWW", "ENENEN", "EEEENN", "ENNEEE"]
    results = []
    for _ in range(2):
        plan, p1, site, ledger, lease, calls = setup_ports(monkeypatch, signatures)
        result = pool.generate_global_composition_pool(
            plan, p1, site, solver=Mock(), execution_ledger=ledger
        )
        assert result["construction_candidate_count"] == 5
        assert result["major_structural_family_count"] == 4
        assert result["status"] == "CONSTRUCTION_TARGETS_MET_NOT_P2D"
        assert len(lease.admissions) == 1
        assert len({c[0] for c in calls}) == 1
        assert ledger.model_work == 50
        assert result["p2d_full_pass_count"] == 0
        assert len(set(result["schedule"])) == 6
        assert len({a["source_family_intent"] for a in result["attempts"][:3]}) == 3
        results.append(result)
    assert results[0] == results[1]


def test_same_geometry_other_family_labels_does_not_count(monkeypatch) -> None:
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 6
    assert result["construction_candidate_count"] == 1
    assert result["distinct_geometry_count"] == 1
    assert sum(a["status"] == "DUPLICATE_GEOMETRY_NOT_COUNTED" for a in result["attempts"]) == 5


@pytest.mark.parametrize("code", ["STAGE_A_RESOURCE_LIMIT", "CP_SAT_CUMULATIVE_HISTORY_UNVERIFIED"])
def test_resource_or_unknown_interruption_not_infeasible_or_retried(monkeypatch, code) -> None:
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, [LayoutAuthorityError(code)])
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 1
    assert result["construction_candidate_count"] == 0
    assert "NOT_PROJECT_INFEASIBLE" in result["status"]
    assert result["attempts"][0]["resources_after"]["model_work"] == 10


@pytest.mark.parametrize(
    "field", ["independent", "native", "coexistence", "footprint", "access", "identity"]
)
def test_candidate_specific_failed_engineering_cannot_inherit_pass(monkeypatch, field) -> None:
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    original = pool.generate_global_composition_candidate

    def invalid(*args, **kwargs):
        result = deepcopy(original(*args, **kwargs))
        if field == "independent":
            result["independent_validation"]["pass"] = False
        elif field in ("native", "coexistence"):
            result["native_independent_validation"]["pass" if field == "native" else field] = False
        elif field == "footprint":
            result["engineering_validation"]["building_footprint"] = None
        else:
            row = result["engineering_validation"]["access_results"][0]
            row["status" if field == "access" else "requirement_identity"] = "UNKNOWN"
        result["canonical_result_hash"] = canonical_hash(
            {k: v for k, v in result.items() if k != "canonical_result_hash"}
        )
        return result

    monkeypatch.setattr(pool, "generate_global_composition_candidate", invalid)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 6
    assert result["construction_candidate_count"] == 0
    assert all(a["status"] == "ENGINEERING_INCOMPLETE_NOT_COUNTED" for a in result["attempts"])


@pytest.mark.parametrize("solver_status", ["UNKNOWN", "INFEASIBLE"])
def test_real_server_validation_chain_runs_each_handoff_without_native_solve(solver_status) -> None:
    plan, p1, site = _context()
    seen = []

    class InspectOnly:
        def solve(self, context, handoff):
            seen.append((id(context.ledger), handoff.family.value))
            assert len(context.binding.dimension_authorities) == 12
            assert len(context.must) == 7
            return {"solver_status": solver_status}

    ledger = StageALedger(solver_history_verified=True, execution_authorization=SyntheticLease())
    result = pool.generate_global_composition_pool(
        plan, p1.to_dict(), site, solver=InspectOnly(), execution_ledger=ledger
    )
    assert len(seen) == 6
    assert len({s[0] for s in seen}) == 1
    assert len({s[1] for s in seen}) == 3
    assert result["construction_candidate_count"] == 0
    assert ledger.solver_wall == 0 and ledger.attempts == []
    assert all(a["solver_status"] == solver_status for a in result["attempts"])
    assert result["project_infeasible_proven"] is False


def test_pool_admission_failure_cannot_fall_back_to_stage_a_quota(monkeypatch) -> None:
    plan, p1, site, ledger, lease, calls = setup_ports(monkeypatch, [])
    lease.validate_pool = Mock(side_effect=LayoutAuthorityError("POOL_OWNER_APPROVAL_MISSING"))
    with pytest.raises(LayoutAuthorityError, match="POOL_OWNER_APPROVAL_MISSING"):
        pool.generate_global_composition_pool(
            plan, p1, site, solver=Mock(), execution_ledger=ledger
        )
    assert calls == []


def test_cross_candidate_provenance_or_mutated_result_rejected(monkeypatch) -> None:
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    original = pool.generate_global_composition_candidate

    def swapped(*args, **kwargs):
        result = original(*args, **kwargs)
        result["source_composition_handoff_hash"] = "sha256:" + "0" * 64
        return result

    monkeypatch.setattr(pool, "generate_global_composition_candidate", swapped)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 1
    assert result["construction_candidate_count"] == 0
    assert result["attempts"][0]["error"]["code"] == "STAGE_B_CANDIDATE_SOURCE_OR_HASH_MISMATCH"


def test_shared_resource_exhaustion_stops_pool_without_family_refill(monkeypatch) -> None:
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    original = pool.generate_global_composition_candidate

    def consume(*args, **kwargs):
        result = original(*args, **kwargs)
        # Exercise the REAL existing ledger guard, not a replacement threshold.
        ledger.model_work += 500_000
        return result

    monkeypatch.setattr(pool, "generate_global_composition_candidate", consume)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 3
    assert ledger.model_work == 1_500_030
    assert result["status"] == "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE"
    assert result["construction_candidate_count"] == 1


def test_previous_candidate_resource_evidence_is_not_mutated_by_next_attempt(monkeypatch) -> None:
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    original = pool.generate_global_composition_candidate

    def shared_list(*args, **kwargs):
        result = original(*args, **kwargs)
        ledger.attempts.append({"synthetic": len(ledger.attempts)})
        result["resource_ledger"] = {"attempts": ledger.attempts}
        result["canonical_result_hash"] = canonical_hash(
            {k: v for k, v in result.items() if k != "canonical_result_hash"}
        )
        return result

    monkeypatch.setattr(pool, "generate_global_composition_candidate", shared_list)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    candidate = result["candidates"][0]["candidate_result"]
    assert len(candidate["resource_ledger"]["attempts"]) == 1
    assert len(ledger.attempts) == 6
    assert candidate["canonical_result_hash"] == canonical_hash(
        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
    )


def test_five_role_allocations_in_one_band_family_do_not_claim_three_families(monkeypatch) -> None:
    paths = ["E" * i + "N" * (6 - i) for i in range(1, 6)] + ["ENNNNN"]
    plan, p1, site, ledger, _, calls = setup_ports(monkeypatch, paths)
    result = pool.generate_global_composition_pool(
        plan, p1, site, solver=Mock(), execution_ledger=ledger
    )
    assert len(calls) == 6
    assert result["construction_candidate_count"] == 5
    assert result["major_structural_family_count"] == 1
    assert result["status"] == "BOUNDED_SCHEDULE_COMPLETE_TARGET_NOT_MET"
