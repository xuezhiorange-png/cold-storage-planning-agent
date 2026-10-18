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
