"""New admission/export wiring only; no real task registry or factory solve."""

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from cold_storage.bootstrap.global_composition import (
    MULTI_SOLUTION_OWNER_TASK,
    approved_stage_b_multi_solution_store,
    approved_stage_b_pool_store,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution_execution import (
    ENUMERATION_CONTRACT,
    MultiSolutionPoolExecutionStore,
)
from tests.unit.test_v222_stage_b_pool_execution import admit, begin, registry


def new_store(tmp_path):
    _, binding = registry(tmp_path)
    instruction = b"SYNTHETIC_POOL_TEST not a real project approval"
    store = MultiSolutionPoolExecutionStore(
        tmp_path / "multi",
        "SYNTHETIC_POOL_TEST",
        hashlib.sha256(instruction).hexdigest(),
    )
    binding["enumeration_contract"] = dict(ENUMERATION_CONTRACT)
    store.approve(instruction, binding)
    return store, binding


def test_trusted_new_slot_is_pinned_and_cannot_alias_old_grant():
    assert not inspect.signature(approved_stage_b_multi_solution_store).parameters
    assert MULTI_SOLUTION_OWNER_TASK == "REAL_MULTI_SOLUTION_VALIDATION_01"
    assert approved_stage_b_multi_solution_store().root != approved_stage_b_pool_store().root
    assert (
        approved_stage_b_multi_solution_store().owner_digest
        != approved_stage_b_pool_store().owner_digest
    )


@pytest.mark.parametrize("key", list(ENUMERATION_CONTRACT))
def test_enumeration_contract_cannot_be_missing_or_caller_changed(tmp_path, key):
    store, binding = new_store(tmp_path)
    binding["enumeration_contract"][key] = "caller-change"
    with pytest.raises(LayoutAuthorityError, match="ENUMERATION_CONTRACT"):
        store.approve(b"SYNTHETIC_POOL_TEST not a real project approval", binding)


def test_native_call_count_is_shared_and_denied_before_next_native_call(tmp_path):
    store, binding = new_store(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.attempts.extend({"synthetic_counter_test": i} for i in range(60))
    ledger.checkpoint("UNIT_ACCOUNTED_COUNTERS")
    lease.finish_pool()
    replay = store.open("REPLAY")
    second = admit(replay, binding)
    begin(second, binding, 0)
    replay.attempts.extend({"synthetic_counter_test": i} for i in range(40))
    replay.checkpoint("UNIT_ACCOUNTED_COUNTERS")
    assert second.totals()["native_calls"] == 100
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        replay.remaining_solver_seconds()
    second.finish_pool()


def test_twenty_checked_assignments_are_shared_not_per_composition(tmp_path):
    store, binding = new_store(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.checked_solutions = 20
    ledger.guard()
    ledger.checkpoint("UNIT_ACCOUNTED_COUNTERS")
    ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    begin(lease, binding, 1)
    assert ledger.checked_solutions == 20
    ledger.checked_solutions += 1
    with pytest.raises(LayoutAuthorityError, match="ENUMERATION_RESOURCE_LIMIT"):
        ledger.guard()
    lease.finish_pool()


def test_operator_entry_exposes_no_geometry_or_budget_arguments(monkeypatch):
    import importlib
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    module = importlib.import_module("run_stage_b_multi_solution_pool")
    monkeypatch.setattr(sys, "argv", ["run_stage_b_multi_solution_pool.py", "--help"])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0


def test_export_preserves_geometry_and_does_not_upgrade_renderer_claims(tmp_path, monkeypatch):
    import importlib
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("run_stage_b_multi_solution_pool")
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg"><rect x="2" y="3" width="4" height="5"/>'
        "<text>Layout status: VALIDATED Access: 12/12 Truck route: VALIDATED</text></svg>"
    )
    monkeypatch.setattr(
        module,
        "build_projection_payload",
        lambda *a, **k: {
            "svg": raw,
            "p2_complete": True,
            "project_layout_validated": True,
        },
    )
    body = {
        "engineering_validation": {
            "p2_complete": False,
            "project_layout_validated": False,
            "access_results": [{"flow_kind": "MATERIAL", "status": "PASS"} for _ in range(11)],
        },
        "independent_validation": {},
        "native_independent_validation": {},
        "resource_ledger": {},
    }
    result = {"candidates": [{"candidate_result": body, "diversity": {}}]}
    module.export_pool(tmp_path / "pool", result, SimpleNamespace(to_dict=lambda: {}))
    path = tmp_path / "pool/candidate-01"
    svg = (path / "layout.svg").read_text()
    assert "Truck route: VALIDATED" not in svg
    assert "Non-Truck Access: 11/11" in svg
    assert ET.fromstring(raw)[0].attrib == ET.fromstring(svg)[0].attrib
    projection = json.loads((path / "projection.json").read_text())
    assert projection["p2_complete"] is projection["project_layout_validated"] is False
    assert projection["svg_sha256"] == "sha256:" + hashlib.sha256(svg.encode()).hexdigest()
    assert (path / "layout.native.svg").read_text() == raw


def _fair_registry(tmp_path):
    from cold_storage.modules.layout.application.stage_b_search_policy import (
        POLICY_HASH,
        schedule_hash,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
        FAIR_ENUMERATION_CONTRACT,
        FairMultiSolutionPoolExecutionStore,
    )

    _, binding = registry(tmp_path)
    instruction = b"SYNTHETIC_POOL_TEST not a real project approval"
    binding.update(
        server_schedule_hash=binding["schedule_hash"],
        schedule_hash=schedule_hash(binding["schedule_hash"]),
        fair_search_policy_hash=POLICY_HASH,
        enumeration_contract=dict(FAIR_ENUMERATION_CONTRACT),
    )
    store = FairMultiSolutionPoolExecutionStore(
        tmp_path / "fair", "SYNTHETIC_POOL_TEST", hashlib.sha256(instruction).hexdigest()
    )
    store.approve(instruction, binding)
    return store, binding


def test_fair_bootstrap_slot_pins_new_owner_and_never_aliases_consumed_slots():
    from cold_storage.bootstrap.global_composition import (
        FAIR_POOL_OWNER_SHA256,
        FAIR_POOL_OWNER_TASK,
        approved_stage_b_fair_pool_store,
    )

    assert not inspect.signature(approved_stage_b_fair_pool_store).parameters
    assert FAIR_POOL_OWNER_TASK == "REAL_FAIR_MULTI_STRUCTURE_VALIDATION_01"
    assert (
        FAIR_POOL_OWNER_SHA256 == "0df70b59d3b7789d226af941018e36f8709db3213763bf37a0a041a193ea49ff"
    )
    assert approved_stage_b_fair_pool_store().root not in {
        approved_stage_b_multi_solution_store().root,
        approved_stage_b_pool_store().root,
    }


@pytest.mark.parametrize(
    "key",
    ["enumeration_contract", "server_schedule_hash", "schedule_hash", "fair_search_policy_hash"],
)
def test_fair_binding_tamper_rejected_before_admission(tmp_path, key):
    store, binding = _fair_registry(tmp_path)
    binding[key] = "caller-change"
    with pytest.raises(LayoutAuthorityError, match="FAIR_EXECUTION_BINDING"):
        store.approve(b"SYNTHETIC_POOL_TEST not a real project approval", binding)


def test_fair_lease_reuses_order_claims_shared_native_cap_and_replay(tmp_path):
    store, binding = _fair_registry(tmp_path)
    for mode, count in (("MAIN", 60), ("REPLAY", 40)):
        ledger = store.open(mode)
        lease = admit(ledger, binding)
        begin(lease, binding, 0)
        ledger.attempts.extend({"synthetic_counter_test": i} for i in range(count))
        ledger.checkpoint("UNIT_ACCOUNTED_COUNTERS")
        if mode == "REPLAY":
            assert lease.totals()["native_calls"] == 100
            with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
                ledger.remaining_solver_seconds()
        lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        store.open("MAIN")


def test_fair_runner_builds_bound_server_schedule_and_exposes_only_operator_args(monkeypatch):
    import importlib
    import sys

    from cold_storage.modules.layout.application.stage_b_search_policy import (
        POLICY_HASH,
        schedule_hash,
    )
    from tests.unit.test_v222_p1a_composition_authority_handoff import _context

    repo = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(repo / "backend/scripts"))
    module = importlib.import_module("run_stage_b_fair_pool")
    plan, p1, site = _context()
    binding = module.fair_binding(repo, plan, p1.to_dict(), site)
    probe = module.generate_fair_multi_solution_global_layout_pool(plan, p1.to_dict(), site)
    assert probe["status"] == "OWNER_MULTI_SOLUTION_POOL_EXECUTION_QUOTA_REQUIRED"
    assert probe["sources"] == {key: binding[key] for key in probe["sources"]}
    assert binding["schedule_hash"] == schedule_hash(binding["server_schedule_hash"])
    assert binding["fair_search_policy_hash"] == POLICY_HASH
    assert len(binding["compositions"]) == 6
    assert (
        binding["enumeration_contract"]["diversity_policy"]
        == "main-process-and-personnel-interface-organization@2.0.0"
    )
    monkeypatch.setattr(sys, "argv", ["run_stage_b_fair_pool.py", "--help"])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    monkeypatch.setattr(sys, "argv", ["run_stage_b_fair_pool.py", "--budget", "999"])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 2


def test_fair_export_keeps_uncounted_geometry_visible_without_false_acceptance(
    tmp_path, monkeypatch
):
    import importlib
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace

    from cold_storage.modules.layout.domain.dimensioning import canonical_hash
    from tests.unit.test_v222_stage_b_fair_search import _collect_families, _family_proposal

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("run_stage_b_fair_pool")
    result = _collect_families(
        monkeypatch, [_family_proposal(), _family_proposal(defect="microshift")]
    )
    for attempt in result["attempts"]:
        body = attempt["candidate_result"]
        body["resource_ledger"] = {"synthetic_test_only": True}
        body["canonical_result_hash"] = canonical_hash(
            {k: v for k, v in body.items() if k != "canonical_result_hash"}
        )
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg"><rect x="2" y="3" width="4" height="5"/>'
        "<text>Layout status: VALIDATED Access: 12/12 Truck route: VALIDATED</text></svg>"
    )
    monkeypatch.setattr(module, "build_projection_payload", lambda *a, **k: {"svg": raw})
    ids = {
        r["requirement_identity"]
        for r in result["candidates"][0]["candidate_result"]["engineering_validation"][
            "access_results"
        ]
    }
    module.export_fair_pool(tmp_path / "pool", result, SimpleNamespace(to_dict=lambda: {}), ids)
    rows = json.loads((tmp_path / "pool/engineering_exports.json").read_text())
    assert [r["v2_construction_counted"] for r in rows] == [True, False]
    for row in rows:
        path = tmp_path / "pool" / row["directory"]
        svg = (path / "layout.svg").read_text()
        assert (
            ET.fromstring(svg).find("{http://www.w3.org/2000/svg}rect").attrib
            == ET.fromstring(raw).find("{http://www.w3.org/2000/svg}rect").attrib
        )
        assert "Truck route: VALIDATED" not in svg
        assert row["truck"] == "BLOCKED" and row["p2d_full_pass"] is False


def test_fair_replay_comparison_includes_counts_branch_metadata_and_stop_reason(monkeypatch):
    import importlib
    from copy import deepcopy

    from tests.unit.test_v222_stage_b_fair_search import _collect_families, _family_proposal

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("run_stage_b_fair_pool")
    result = _collect_families(monkeypatch, [_family_proposal()])
    before = module.fair_semantics(result)
    for key in ("status", "major_structural_family_count"):
        changed = deepcopy(result)
        changed[key] = "DIFFERENT"
        assert module.fair_semantics(changed) != before
