"""Synthetic fixed-slot accounting only; never touch the actual Owner registry."""

import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.bootstrap.stage_b_functional_shape_ab import approved_functional_shape_ab_stores
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_functional_shape_ab as ab
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin


def setup(tmp_path, monkeypatch):
    _, common = _fair_registry(tmp_path)
    raw = ("SYNTHETIC ACCOUNTING ONLY " + " ".join(ab.SLOTS.values())).encode()
    monkeypatch.setattr(ab, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    common["runtime_dependency_hash"] = "synthetic-runtime-byte-fingerprint"
    stores = [ab.FunctionalShapeABStore(tmp_path / "ab", arm) for arm in ("A", "B")]
    bindings = [ab.arm_binding(common, arm) for arm in ("A", "B")]
    for s, b in zip(stores, bindings, strict=True):
        s.approve(raw, b)
    return stores, bindings, raw


def test_bootstrap_fixed_slots_cannot_alias_old_grants():
    assert not inspect.signature(approved_functional_shape_ab_stores).parameters
    a, b = approved_functional_shape_ab_stores()
    assert a.task_id == "V2_2_2_STAGE_B_AB_R1_ARM_A_MAIN"
    assert b.task_id == "V2_2_2_STAGE_B_AB_R1_ARM_B_MAIN"
    assert a.root != b.root and a.shared_root == b.shared_root
    assert a.owner_digest == b.owner_digest == ab.OWNER_SHA256


def test_two_sequential_main_only_no_replay_or_reallocation(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError):
        stores[1].open("MAIN")
    for s, binding in zip(stores, bindings, strict=True):
        with pytest.raises(LayoutAuthorityError, match="NO_REPLAY"):
            s.open("REPLAY")
        ledger = s.open("MAIN")
        lease = admit(ledger, binding)
        with pytest.raises(LayoutAuthorityError, match="EXCLUSIVE"):
            stores[1].open("MAIN")
        for i in range(6):
            begin(lease, binding, i)
            ledger.charge("SYNTHETIC_ACCOUNTING", 1)
            ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        lease.finish_pool()
    assert stores[1].shared_state()["totals"]["observable_work"] == 12
    for s in stores:
        with pytest.raises(LayoutAuthorityError):
            s.open("MAIN")


@pytest.mark.parametrize(
    "arm,key",
    [
        (a, k)
        for a in (0, 1)
        for k in (
            "ab_arm",
            "ab_contract_hash",
            "final_guidance_policy_hash",
            "ab_common_binding_hash",
            "zone_plan_hash",
            "schedule_hash",
            "runtime_dependency_hash",
        )
    ],
)
def test_policy_source_arm_or_budget_binding_tamper_denied(tmp_path, monkeypatch, arm, key):
    stores, bindings, raw = setup(tmp_path, monkeypatch)
    bindings[arm][key] = "caller-forged"
    with pytest.raises(LayoutAuthorityError):
        stores[arm].approve(raw, bindings[arm])


def test_two_arms_share_native_counters_but_not_reserved_seconds(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    a = stores[0].open("MAIN")
    lease = admit(a, bindings[0])
    begin(lease, bindings[0], 0)
    a.solver_wall = a.solver_monotonic_wall = 40
    a.attempts.extend({"synthetic": i} for i in range(60))
    a.checkpoint("SYNTHETIC_ACCOUNTED")
    assert a.remaining_solver_seconds() == pytest.approx(9.8)
    lease.finish_pool()
    b = stores[1].open("MAIN")
    second = admit(b, bindings[1])
    begin(second, bindings[1], 0)
    assert b.remaining_solver_seconds() == pytest.approx(49.8)  # unused A time does not transfer
    b.attempts.extend({"synthetic": i} for i in range(40))
    b.checkpoint("SYNTHETIC_ACCOUNTED")
    assert second.totals()["native_solver_seconds"] == 40
    assert second.totals()["native_calls"] == 100
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        b.remaining_solver_seconds()
    second.finish_pool()


@pytest.mark.parametrize(
    "field,value",
    [("solver_wall", 49.91), ("model_work", 600001), ("peak_rss_bytes", 513 * 1024 * 1024)],
)
def test_original_and_stricter_arm_guards_fail_closed(tmp_path, monkeypatch, field, value):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


def test_unknown_native_interruption_prevents_b_and_restart(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    lease = admit(ledger, bindings[0])
    begin(lease, bindings[0], 0)
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.solver_history_verified = False
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED"):
        stores[1].open("MAIN")
    with pytest.raises(LayoutAuthorityError):
        stores[0].open("MAIN")


def test_shared_file_tamper_and_counter_rollback_rejected(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.charge("SYNTHETIC", 5)
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    ledger.model_work = 4
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        ledger.guard()
    ledger.model_work = 5
    file = stores[0].shared_root / "shared-resource-ledger.json"
    file.write_text(file.read_text() + " ")
    with pytest.raises(LayoutAuthorityError, match="SHARED_HISTORY_CHANGED"):
        ledger.guard()


def test_insufficient_remaining_wall_time_denies_b_reserve(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.execution_authorization.finish_pool()
    file = stores[0].shared_root / "shared-resource-ledger.json"
    state = json.loads(file.read_text())
    state["started_monotonic"] -= 100
    file.write_text(json.dumps(state))
    with pytest.raises(LayoutAuthorityError, match="NOT_EXECUTED_RESOURCE_LIMIT"):
        stores[1].open("MAIN")


def test_operator_ci_gate_precedes_any_approval_and_exposes_no_budget(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("run_stage_b_functional_shape_ab")
    source = tmp_path / "owner.txt"
    source.write_bytes(b"synthetic-owner-instruction")
    monkeypatch.setattr(module, "OWNER_SHA256", hashlib.sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(module, "committed_source", lambda *_: None)

    def blocked(*args):
        raise LayoutAuthorityError("GUIDED_FAIR_EXACT_HEAD_CI_ADMISSION_BLOCKED")

    monkeypatch.setattr(module, "github_admission", blocked)
    monkeypatch.setattr(
        module, "execute", lambda *a: pytest.fail("CI-blocked must never approve/open")
    )
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["entry", "--owner-instruction", str(source), "--output", str(tmp_path / "out")],
    )
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        module.main()
    assert not (tmp_path / "out").exists()


def test_missing_shared_history_cannot_recreate_consumed_allowance(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.execution_authorization.finish_pool()
    (stores[0].shared_root / "shared-resource-ledger.json").unlink()
    with pytest.raises(LayoutAuthorityError, match="HISTORY"):
        stores[1].open("MAIN")


def test_exhausted_target_is_resource_not_infeasible(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.solver_wall = ledger.solver_monotonic_wall = 49.8
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
        ledger.remaining_solver_seconds()


@pytest.mark.parametrize("arm", [0, 1])
def test_declared_arm_rejects_other_arm_actual_final_guidance_receipt(tmp_path, monkeypatch, arm):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    first = stores[0].open("MAIN")
    if arm:
        first.execution_authorization.finish_pool()
        ledger = stores[1].open("MAIN")
    else:
        ledger = first
    lease = admit(ledger, bindings[arm])
    begin(lease, bindings[arm], 0)
    sources = {
        **{k: bindings[arm][k] for k in ("zone_plan_hash", "p1_hash", "site_hash")},
        "composition_hash": bindings[arm]["compositions"][0]["composition_hash"],
    }
    wrong = ab.ARM_POLICIES["A" if arm else "B"]
    with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT_MISMATCH"):
        lease.record_enumeration(
            sources,
            {
                "kind": "FINAL_MODEL_GUIDANCE_APPLIED",
                "guidance": {"policy": wrong[0], "policy_hash": wrong[1]},
            },
        )
    expected = ab.ARM_POLICIES["B" if arm else "A"]
    lease.record_enumeration(
        sources,
        {
            "kind": "FINAL_MODEL_GUIDANCE_APPLIED",
            "guidance": {"policy": expected[0], "policy_hash": expected[1]},
        },
    )
    assert len(lease.record["enumeration_events"]) == 1


def test_peer_summary_cannot_erase_verified_consumption(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.charge("SYNTHETIC_ACCOUNTED_WORK", 50)
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    ledger.execution_authorization.finish_pool()
    path = stores[0].shared_root / "shared-resource-ledger.json"
    state = json.loads(path.read_text())
    state["arms"]["A"]["totals"]["observable_work"] = 0
    path.write_text(json.dumps(state))
    with pytest.raises(LayoutAuthorityError, match="CONSUMPTION_UNVERIFIED"):
        stores[1].open("MAIN")


def test_no_candidates_report_is_deterministic_and_inconclusive(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("analyze_stage_b_functional_shape_ab")
    output = tmp_path / "analysis"
    output.mkdir()
    (output / "source-admission.json").write_text(json.dumps({"head": "synthetic"}))
    for arm in ("a", "b"):
        root = output / ("arm-" + arm)
        root.mkdir()
        (root / "pool.json").write_text(
            json.dumps(
                {
                    "status": "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE",
                    "distinct_physical_geometry_count": 0,
                    "distinct_meaningful_construction_count": 0,
                    "major_structural_family_count": 0,
                    "compositions": [],
                    "candidates": [],
                    "sources": {},
                }
            )
        )
        (root / "resource-ledger.json").write_text(
            json.dumps(
                {
                    "pools": [
                        {
                            "counters": {"checked_solutions": 0, "attempts": []},
                        }
                    ]
                }
            )
        )
    repo = Path(__file__).resolve().parents[3]
    reports = tmp_path / "reports"
    before = _evidence_hashes(output)
    module.analyze(output, repo, output=reports)
    first = _evidence_hashes(reports)
    module.analyze(output, repo, output=reports)
    assert first == _evidence_hashes(reports)
    assert before == _evidence_hashes(output)
    receipt = json.loads((reports / "ab-conclusion.json").read_text())
    assert receipt["conclusion"] == "INCONCLUSIVE"
    assert receipt["real_replay_determinism"] == "NOT_EVALUATED"


def _analyzer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("analyze_stage_b_functional_shape_ab")


def _evidence_hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _topology(certificate):
    return {"kind": "TOPOLOGY_REJECTED_WITNESS_CUT", "certificate": certificate}


@pytest.mark.parametrize(
    "holes,error,category,known,anomalies",
    [
        (2, "ENCLOSED_HOLE", "CONFIRMED_HOLE", True, 0),
        (0, "MULTIPLE_COMPONENTS", "MULTIPLE_COMPONENTS", True, 0),
        (None, "SINGULAR_POINT_CONTACT", "SINGULAR_POINT_CONTACT", False, 0),
        ("2", "ENCLOSED_HOLE", "UNCLASSIFIED_CERTIFICATE", False, 1),
        (True, "ENCLOSED_HOLE", "UNCLASSIFIED_CERTIFICATE", False, 1),
        (1.0, "ENCLOSED_HOLE", "UNCLASSIFIED_CERTIFICATE", False, 1),
        (-1, "ENCLOSED_HOLE", "UNCLASSIFIED_CERTIFICATE", False, 1),
        (0, "NONPOSITIVE_OR_EMPTY_RECTANGLE_UNION", "OTHER_TOPOLOGY_REJECTION", True, 0),
    ],
)
def test_offline_topology_count_semantics(monkeypatch, holes, error, category, known, anomalies):
    module = _analyzer(monkeypatch)
    result = module.classify_topology_rejections([_topology({"hole_count": holes, "error": error})])
    row = result["witnesses"][0]
    assert category in row["categories"]
    assert row["hole_count_status"] == ("KNOWN" if known else "UNKNOWN")
    assert result["certificate_field_anomaly_count"] == anomalies
    if not known:
        assert row["hole_count"] is None
        assert result["total_hole_loop_count"] is None
        assert not result["total_hole_loop_count_determinable"]


@pytest.mark.parametrize("certificate", [{}, None, [], "malformed", {"error": "ENCLOSED_HOLE"}])
def test_offline_missing_or_invalid_certificate_never_becomes_zero(monkeypatch, certificate):
    result = _analyzer(monkeypatch).classify_topology_rejections([_topology(certificate)])
    assert result["unknown_hole_count_witness_count"] == 1
    assert result["total_hole_loop_count"] is None
    assert result["certificate_field_anomaly_count"] > 0
    assert result["unclassified_certificate_count"] == 1


def test_topology_facts_overlap_and_hole_loops_are_not_witness_counts(monkeypatch):
    module = _analyzer(monkeypatch)
    events = [
        _topology({"hole_count": 3, "error": "ENCLOSED_HOLE", "connected_component_count": 2}),
        _topology({"hole_count": 2, "error": "ENCLOSED_HOLE"}),
        _topology({"hole_count": None, "error": "SINGULAR_POINT_CONTACT"}),
        {"kind": "VALIDATION_RESULT", "certificate": {"hole_count": 99}},
        None,
    ]
    result = module.classify_topology_rejections(events)
    assert result["rejected_witness_count"] == 3
    assert result["hole_rejected_witness_count"] == 2
    assert result["confirmed_hole_loop_count"] == 5
    assert result["multiple_component_witness_count"] == 1
    assert result["singular_contact_witness_count"] == 1
    assert result["unknown_hole_count_witness_count"] == 1
    assert result["total_hole_loop_count"] is None
    assert result["certificate_field_anomaly_count"] == 0
    assert not result["categories_are_mutually_exclusive"]
    assert json.dumps(result, sort_keys=True) == json.dumps(
        module.classify_topology_rejections(events), sort_keys=True
    )


def test_zero_holes_is_known_but_not_confirmed_hole_rejection(monkeypatch):
    result = _analyzer(monkeypatch).classify_topology_rejections(
        [
            _topology(
                {"hole_count": 0, "error": "MULTIPLE_COMPONENTS", "connected_component_count": 2}
            )
        ]
    )
    assert result["total_hole_loop_count"] == 0
    assert result["total_hole_loop_count_determinable"]
    assert result["hole_rejected_witness_count"] == 0


@pytest.mark.parametrize("relative", [".", "reports", ".."])
def test_analysis_cannot_write_into_or_above_sealed_source(tmp_path, monkeypatch, relative):
    source = tmp_path / "sealed"
    with pytest.raises(ValueError, match="DISJOINT"):
        _analyzer(monkeypatch).analyze(source, tmp_path, output=source / relative)
    assert not source.exists()


def _synthetic_analysis_source(tmp_path, monkeypatch):
    """Synthetic consumer fixture, not project data or a new geometry validator."""
    module = _analyzer(monkeypatch)
    root = tmp_path / "sealed"
    root.mkdir()
    module.dump(root / "source-admission.json", {"head": "SYNTHETIC_NOT_EXECUTION_HEAD"})
    v1s, v2s, facts = {}, {}, {}
    for arm in ("a", "b"):
        accepted = []
        for i in range(2):
            key = f"{arm}-{i}"
            v1 = {"symmetry_invariant_geometry_hash": key, "major_family_hash": "same-family"}
            v2 = {"meaningful_construction_hash": "same-organization", "countable": True}
            v1s[key], v2s[key] = v1, v2
            body = {
                "identity": "SYNTHETIC",
                "canonical_result_hash": key,
                "composition_handoff": {"composition_identity": "same-handoff", "family": "intent"},
                "proposal": {"zones": key},
                "engineering_validation": {
                    "access_results": key,
                    "building_footprint": {},
                    "source_zone_plan_hash": "synthetic",
                    "source_p1_handoff_hash": "synthetic",
                    "source_site_geometry_hash": "synthetic",
                    "truck_route_status": "BLOCKED",
                    "truck_route_validated": False,
                    "project_layout_validated": False,
                    "p2_complete": False,
                },
                "independent_validation": {"pass": True},
                "native_independent_validation": {"pass": True},
                "acceptance_status": "SYNTHETIC",
                "stage_a_engineering_accepted": True,
                **{
                    f"source_{s}_hash": "synthetic"
                    for s in (
                        "zone_plan",
                        "p1_handoff",
                        "site_geometry",
                        "composition",
                        "composition_handoff",
                    )
                },
            }
            path = root / "previews" / f"arm-{arm}" / f"candidate-{i}"
            path.mkdir(parents=True)
            module.dump(path / "candidate.json", body)
            module.dump(
                path / "diversity.json",
                {
                    "v1": v1,
                    "v2": v2,
                    "geometry_hash": key,
                    "major_family_hash": "same-family",
                    "v2_construction_counted": i == 0,
                },
            )
            module.dump(
                path / "drawing_provenance.json",
                {
                    "candidate_file_sha256": hashlib.sha256(
                        (path / "candidate.json").read_bytes()
                    ).hexdigest(),
                    "source_application_hash": module.canonical_hash(
                        body["engineering_validation"]
                    ),
                    "candidate_canonical_hash": key,
                },
            )
            metrics = {
                name: {"STATUS": "DERIVED", "VALUE": "1"}
                for name in (
                    "PERSONNEL_ROUTE_LENGTH_M",
                    "PERSONNEL_ROUTE_TURN_COUNT",
                    "BUILDING_AREA_M2",
                    "BUILDING_PERIMETER_M",
                    "EXTERIOR_TURN_COUNT",
                    "EXTERIOR_REFLEX_CORNER_COUNT",
                    "MAJOR_ZONE_GRID_ALIGNMENT_RATE",
                )
            }
            metrics["PROCESS_FLOW"] = {"STATUS": "UNAVAILABLE", "VALUE": None}
            metrics["ROOM_DIMENSION_FACTS"] = {
                "STATUS": "MEASURED",
                "VALUE": [
                    {"zone": role, "width_m": "2", "depth_m": "3", "aspect_exact": "3/2"}
                    for role in ("office", "changing_room", "coating_room")
                ],
            }
            facts[key] = {"METRICS": metrics}
            if i == 0:
                accepted.append(
                    {
                        "candidate_id": f"accepted-{key}",
                        "geometry_hash": key,
                        "candidate_result": body,
                    }
                )
        folder = root / f"arm-{arm}"
        folder.mkdir()
        module.dump(
            folder / "pool.json",
            {
                "status": "BOUNDED",
                "candidates": accepted,
                "distinct_physical_geometry_count": 2,
                "distinct_meaningful_construction_count": 1,
                "major_structural_family_count": 1,
                "compositions": [],
                "sources": {k: "synthetic" for k in ("zone_plan_hash", "p1_hash", "site_hash")},
            },
        )
        module.dump(
            folder / "resource-ledger.json",
            {
                "pools": [
                    {
                        "counters": {
                            "checked_solutions": 2,
                            "attempts": [],
                        },
                        "enumeration_events": [
                            _topology({"error": "SINGULAR_POINT_CONTACT", "hole_count": None})
                        ],
                    }
                ]
            },
        )
    monkeypatch.setattr(module, "construction_diversity", lambda key: v1s[key])
    monkeypatch.setattr(module, "construction_branch_diversity", lambda key, _: v2s[key])
    monkeypatch.setattr(
        module,
        "quality_extractor",
        lambda _: SimpleNamespace(
            analyze=lambda projection: facts[projection["canonical_result_hash"]]
        ),
    )
    return module, root


def test_offline_full_consumer_preserves_variants_hashes_ledgers_and_determinism(
    tmp_path, monkeypatch
):
    module, source = _synthetic_analysis_source(tmp_path, monkeypatch)
    # Fail immediately if analysis tries to invoke a native solver or execution authorization.
    from ortools.sat.python import cp_model

    def forbidden(*args, **kwargs):
        pytest.fail("Offline analysis must not solve or access any execution lease")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)
    monkeypatch.setattr(ab.FunctionalShapeABStore, "approve", forbidden)
    monkeypatch.setattr(ab.FunctionalShapeABStore, "open", forbidden)
    before = _evidence_hashes(source)
    reports = tmp_path / "reports"
    result = module.analyze(source, tmp_path, output=reports)
    first = _evidence_hashes(reports)
    assert before == _evidence_hashes(source)
    assert result["arms"]["A"]["physical_geometry_count"] == 2
    assert result["arms"]["A"]["meaningful_constructions"] == 1
    assert result["arms"]["A"]["major_families"] == 1
    assert len(result["arms"]["A"]["candidates"]) == 2  # retain uncounted variant facts
    assert result["arms"]["A"]["topology_rejections"]["total_hole_loop_count"] is None
    assert result["arms"]["A"]["metric_distributions"]["BUILDING_AREA_M2"]["count"] == 2
    module.analyze(source, tmp_path, output=reports)
    assert first == _evidence_hashes(reports)
    assert before == _evidence_hashes(source)


def test_offline_tampered_candidate_or_counts_stop_without_rewriting_source(tmp_path, monkeypatch):
    module, source = _synthetic_analysis_source(tmp_path, monkeypatch)
    path = source / "previews/arm-a/candidate-0/candidate.json"
    path.write_bytes(path.read_bytes() + b" ")
    before = _evidence_hashes(source)
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        module.analyze(source, tmp_path, output=tmp_path / "reports")
    assert before == _evidence_hashes(source)


def test_offline_variant_cannot_inflate_accepted_counts(tmp_path, monkeypatch):
    module, source = _synthetic_analysis_source(tmp_path, monkeypatch)
    path = source / "arm-a/pool.json"
    pool = json.loads(path.read_text())
    pool["distinct_meaningful_construction_count"] = 2
    module.dump(path, pool)
    before = _evidence_hashes(source)
    with pytest.raises(ValueError, match="POOL_COUNTS_INCONSISTENT"):
        module.analyze(source, tmp_path, output=tmp_path / "reports")
    assert before == _evidence_hashes(source)


def test_offline_json_tuple_roundtrip_preserves_existing_diversity_identity(tmp_path, monkeypatch):
    module, source = _synthetic_analysis_source(tmp_path, monkeypatch)
    original = module.construction_branch_diversity

    def tuple_signature(key, routes):
        return {**original(key, routes), "signature": ("same", "identity")}

    monkeypatch.setattr(module, "construction_branch_diversity", tuple_signature)
    for path in source.glob("previews/*/candidate-*/diversity.json"):
        div = json.loads(path.read_text())
        div["v2"]["signature"] = ["same", "identity"]
        module.dump(path, div)
    module.analyze(source, tmp_path, output=tmp_path / "reports")


def test_offline_module_has_no_execution_or_native_imports(monkeypatch):
    import ast

    module = _analyzer(monkeypatch)
    tree = ast.parse(Path(module.__file__).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        name
        and any(
            x in name
            for x in ("ortools", "run_stage_b", "bootstrap", "infrastructure", "subprocess")
        )
        for name in imports
    )
