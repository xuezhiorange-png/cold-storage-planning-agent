"""No-Native R3 screening, project provenance and original functional-oracle tests."""

import copy
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.changing_locker_review import (
    PROJECT_SCOPE,
    bind_r3_project,
    build_r3_catalog,
    evaluate_reviewed_locker_witness,
    hypothetical_review,
)
from cold_storage.modules.layout.domain.changing_locker_screening import (
    HypotheticalLockerParameters,
)
from cold_storage.modules.layout.domain.changing_shift_use import PLAN_FIELD
from cold_storage.modules.layout.domain.functional_room_fit import (
    STATES,
    BasisValue,
    evaluate_functional_room,
)
from cold_storage.modules.layout.infrastructure.changing_locker_review_page import (
    preview_request,
    render_page,
    response,
)
from cold_storage.modules.layout.infrastructure.functional_room_fit_examples import scenario

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("R11_R3_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture()
def sources():
    review = json.loads(
        (ROOT / "docs/previews/v2.2.2/r11-functional-room-fit-r1/review-data.json").read_bytes()
    )
    owner = (
        ROOT
        / "docs/previews/v2.2.2/owner-functional-input-contract-r2"
        / "owner-confirmed-business-rules-v2.json"
    ).read_bytes()
    confirmation = (ROOT / "docs/tasks/V2_2_2-r11-r3-reviewed-project-fact.txt").read_bytes()
    return review, owner, confirmation


@pytest.fixture()
def catalog(sources):
    return build_r3_catalog(*sources)


def test_owner_confirmed_mass_is_bound_through_r2_and_history_unchanged(sources):
    review, owner, confirmation = sources
    before = copy.deepcopy(review)
    bound = bind_r3_project(review, owner, confirmation)
    assert bound["project_reviewed_facts"]["PACKAGED_PRODUCT_MASS_KG_PER_DAY"]["value"] == 20000
    staff = bound["workforce"]
    assert staff["separate_personal_lockers"] == [53, 53]
    assert staff["simultaneous_changing_users"] == 53
    assert staff["required_packing_tables"] == 18
    assert [r["packaged_product_mass_kg"] for r in staff["per_shift_capacity"]] == [
        "10000.0",
        "10000.0",
    ]
    assert staff["shift_workload_allocation_basis"] == "OWNER_V2_DEFAULT_EQUAL_SPLIT"
    assert bound["r3_project_basis_status"] == "CONFIRMED_PROJECT_BASIS"
    assert not bound["functional_approval"]
    assert review == before


@pytest.mark.parametrize(
    "bad",
    [
        b'{"source_label":"OWNER_CONFIRMED","value":20000}',
        b"PACKAGED_PRODUCT_MASS_KG_PER_DAY=30000",
        b"",
    ],
)
def test_json_label_or_changed_document_cannot_self_approve(sources, bad):
    with pytest.raises(ValueError, match="REVIEWED_OWNER_PROJECT_SOURCE_CHANGED"):
        bind_r3_project(sources[0], sources[1], bad)


def test_owner_fact_is_scoped_to_the_actual_project(sources):
    review, owner, confirmation = sources
    review = copy.deepcopy(review)
    for row in review["room_evaluations"]:
        row["room"]["scope_id"] = row["room"]["scope_id"].replace(
            PROJECT_SCOPE.split(":")[1], "a" * 64
        )
    with pytest.raises(ValueError, match="PROJECT_SCOPE_MISMATCH"):
        bind_r3_project(review, owner, confirmation)


def test_nine_records_eight_physical_groups_and_real_two_portals_preserved(catalog, sources):
    assert len(catalog["groups"]) == 8
    assert catalog["groups"][0]["records"] == ["P01", "P02"]
    assert sum(len(g["records"]) for g in catalog["groups"]) == 9
    assert catalog["design_counts"]["locker_count"] == 106
    originals = {
        r["record"]: r["room"]
        for r in sources[0]["room_evaluations"]
        if r["room"]["room_code"] == "changing_room"
    }
    for group in catalog["groups"]:
        assert group["room"] == originals[group["records"][0]]
        assert len(group["room"]["portals"]) == 2
        assert {p["clear_width_mm"] for p in group["room"]["portals"]} == {1500}
        evaluation = group["project_evaluation"]
        assert evaluation["functional_status"] == "INPUT_REQUIRED"
        assert evaluation["input_facts"]["shift_locker_counts"]["value"] == [53, 53]
        assert "locker_model" in evaluation["missing_inputs"]
        assert "finished_clear_bounds_mm" in evaluation["missing_inputs"]


@pytest.mark.parametrize("group", [f"G{i:02}" for i in range(2, 9)])
def test_all_h6_single_side_ideal_bound_is_99_and_portals_reduce_it(catalog, group):
    result = hypothetical_review(
        catalog, group, HypotheticalLockerParameters(arrangement="SINGLE_SIDE")
    )
    s = result["screening"]
    assert s["ideal_single_side_capacity"] == 99
    assert s["required_length_mm"] == 42400
    assert s["necessary_condition_status"] == "CONFIGURATION_NOT_FIT"
    assert s["placed_lockers"] < 99
    assert "IDEAL_CONTINUOUS_ROW_LENGTH_SHORTFALL" in s["reasons"]
    assert s["source_label"] == "HYPOTHETICAL_NOT_APPROVED"
    assert result["project_status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize("group", [f"G{i:02}" for i in range(2, 9)])
def test_all_h6_opposed_rows_leave_only_eight_to_fifteen_mm(catalog, group):
    result = hypothetical_review(catalog, group, HypotheticalLockerParameters())
    s = result["screening"]
    assert 8 <= s["ideal_remaining_aisle_mm"] <= 15
    assert s["required_width_mm"] == 2200
    assert s["operation_width_required_mm"] == 3400
    assert "CABINETS_AND_CLEAR_AISLE_WIDTH_SHORTFALL" in s["reasons"]
    assert result["project_evaluation"]["functional_status"] == "INPUT_REQUIRED"


def test_h5_double_side_necessary_pass_does_not_imply_functional_pass(catalog):
    r = hypothetical_review(catalog, "G01", HypotheticalLockerParameters())
    s = r["screening"]
    assert s["required_length_mm"] == 21200
    assert s["required_width_mm"] == 2200
    assert s["necessary_condition_status"] == "NECESSARY_CONDITIONS_MET_ONLY"
    assert s["placed_lockers"] == 106
    assert "PERSON_OPERATION_AND_CLEAR_AISLE_SHORTFALL" in s["reasons"]
    assert s["functional_status"] == "INPUT_REQUIRED"
    assert r["project_status"] == "INPUT_REQUIRED"
    assert len({c["id"] for c in s["components"]}) == len(s["components"])
    lockers = [c for c in s["components"] if c["role"] == "LOCKER"]
    assert [sum(c["shift"] == i for c in lockers) for i in (1, 2)] == [53, 53]


@pytest.mark.parametrize(
    "change",
    [
        {"locker_width_mm": 0},
        {"aisle_mm": True},
        {"person_depth_mm": 1.5},
        {"bench_count": 11},
        {"active_shift": 3},
        {"arrangement": "ZIGZAG"},
    ],
)
def test_explicit_bounded_hypothetical_parameters(catalog, change):
    with pytest.raises(ValueError):
        hypothetical_review(catalog, "G01", replace(HypotheticalLockerParameters(), **change))


def test_parameter_and_shift_changes_never_promote_project_approval(catalog):
    before = copy.deepcopy(catalog)
    p = HypotheticalLockerParameters(
        front_clearance_mm=400, person_depth_mm=400, bench_count=1, active_shift=2
    )
    r = hypothetical_review(catalog, "G01", p)
    assert any(c["role"] == "BENCH" for c in r["screening"]["components"])
    assert len([c for c in r["screening"]["components"] if c["role"] == "PERSON"]) == 53
    assert r["project_status"] == "INPUT_REQUIRED"
    assert r["screening"]["requires_review"]
    assert catalog == before


def test_unplaced_second_shift_people_are_reported_as_a_template_shortfall(catalog):
    r = hypothetical_review(
        catalog, "G02", HypotheticalLockerParameters(arrangement="SINGLE_SIDE", active_shift=2)
    )
    s = r["screening"]
    assert s["placed_lockers"] == 94
    assert s["placed_person_spaces"] == 41
    assert "ACTIVE_SHIFT_LOCKER_OR_PERSON_POSITIONS_INSUFFICIENT" in s["reasons"]
    assert r["project_status"] == "INPUT_REQUIRED"


def test_svg_is_valid_and_page_uses_python_preview_without_approval_import(catalog):
    presets = {}
    for group in catalog["groups"]:
        for mode in ("SINGLE_SIDE", "DOUBLE_SIDE"):
            r = hypothetical_review(
                catalog, group["group"], HypotheticalLockerParameters(arrangement=mode)
            )
            presets[group["group"] + ":" + mode] = response(r)
    for data in presets.values():
        ET.fromstring(data["svg"])
    page = render_page(catalog, presets)
    assert "CONFIRMED_PROJECT_BASIS" in page
    assert "HYPOTHETICAL_NOT_APPROVED" in page
    assert "fetch('/preview'" in page
    assert "input type='number'" in page
    assert "APPROVE" not in page.replace("APPROVED", "")
    assert len(asdict(HypotheticalLockerParameters())) == 17


def complete_synthetic_design(binding):
    """A supplied 26x8m unit fixture; never a new historical/factory layout."""
    room, refs, witness, basis = scenario("DOUBLE_SIDE")
    room["scope_id"] = PROJECT_SCOPE + ":SYNTHETIC_UNIT_NOT_PROJECT:changing_room"
    room["local_bounds_mm"] = [0, 0, 26000, 8000]
    room["portals"].append(
        dict(id="exit", segment_mm=[[26000, 3250], [26000, 4750]], clear_width_mm=1500)
    )
    components = []

    def add(identifier, role, rect, **extra):
        components.append(
            dict(id=identifier, role=role, bounds_mm=rect, states=list(STATES), **extra)
        )

    for i in range(106):
        x = 500 + i % 53 * 400
        top = i >= 53
        add(
            f"locker-{i + 1}",
            "LOCKER",
            [x, 7000 if top else 500, x + 400, 7500 if top else 1000],
            shift=2 if top else 1,
            front="S" if top else "N",
        )
    for i in range(53):
        x = 500 + i * 400
        add(
            f"person-{i + 1}", "PERSON", [x, 1000, x + 400, 1600], shift=1, serves=f"locker-{i + 1}"
        )
        components[-1]["states"] = ["USE", "SHIFT_CHANGE"]
    add("front-low", "AISLE", [500, 1600, 25000, 2800])
    add("front-high", "AISLE", [500, 5200, 25000, 6400])
    add("link", "AISLE", [23800, 1600, 25000, 6400])
    add("main", "AISLE", [0, 3400, 26000, 4600])
    add("entry-pocket", "DOOR_OPERATION", [0, 4750, 100, 6250], portal_id="entry")
    add("exit-pocket", "DOOR_OPERATION", [25900, 4750, 26000, 6250], portal_id="exit")
    witness = {
        "components": components,
        "routes": [
            dict(
                id="two-real-portals",
                points_mm=[[0, 4000], [26000, 4000]],
                width_mm=1200,
                states=list(STATES),
            )
        ],
    }
    basis = {k: replace(v, scope_id=room["scope_id"]) for k, v in basis.items()}
    basis["finished_clear_bounds_mm"] = replace(
        basis["finished_clear_bounds_mm"], value=room["local_bounds_mm"]
    )
    basis["door_operation_envelopes_mm"] = replace(
        basis["door_operation_envelopes_mm"],
        value={"entry": [[0, 4750, 100, 6250]], "exit": [[25900, 4750, 26000, 6250]]},
    )
    return room, refs, witness, basis


def reviewed_dual_design(binding):
    room, refs, first, basis = complete_synthetic_design(binding)
    second = copy.deepcopy(first)
    for c in second["components"]:
        if c["role"] == "PERSON":
            i = int(c["id"].split("-")[-1])
            x = c["bounds_mm"][0]
            c.update(shift=2, serves=f"locker-{i + 53}", bounds_mm=[x, 6400, x + 400, 7000])
    plan = {}
    for shift in (1, 2):
        active = [
            c["id"] for c in first["components"] if c["role"] == "LOCKER" and c["shift"] == shift
        ]
        plan[str(shift)] = {
            state: dict(
                active_locker_ids=active,
                inactive_lockers_closed=True,
                door_motion_basis=(
                    "Synthetic reviewed no-floor-sweep unit locker, not a project selection"
                ),
                locker_door_motion={
                    key: dict(mode="NO_FLOOR_SWEEP", exclusions_mm=[]) for key in active
                },
            )
            for state in STATES
        }
    refs[PLAN_FIELD] = PLAN_FIELD
    basis[PLAN_FIELD] = BasisValue(
        plan,
        "mapping",
        "ENGINEERING_DERIVED",
        "tests/unit/test_v222_r11_r3_locker_review.py#reviewed_dual_design:synthetic",
        room["scope_id"],
        PLAN_FIELD,
    )
    return room, refs, {1: first, 2: second}, basis


def test_complete_reviewed_fixture_delegates_to_original_r11_all_four_states(catalog):
    binding = catalog["project_binding"]
    room, refs, witnesses, basis = reviewed_dual_design(binding)
    result = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=witnesses
    )
    assert result["functional_status"] == "CONDITIONAL_FIT", result
    assert set(result["shift_results"]) == {"1", "2"}
    for shift in ("1", "2"):
        checked = result["shift_results"][shift]
        assert checked["r3"]["status"] == "SHIFT_USE_VALIDATED"
        assert set(checked["r3"]["state_results"]) == set(STATES)
        for state in ("USE", "SHIFT_CHANGE"):
            proof = checked["r3"]["state_results"][state]
            assert proof["people_count"] == 53
            assert len(set(proof["person_to_locker"].values())) == 53
            assert len(proof["proven_portal_ids"]) == 2
    assert not result["engineering_approval"]


@pytest.mark.parametrize(
    "failure",
    ["person_missing", "duplicate_identity", "blocked_door", "extra_locker", "wrong_review_scope"],
)
def test_full_witness_failures_never_become_conditional_fit(catalog, failure):
    binding = catalog["project_binding"]
    room, refs, witnesses, basis = reviewed_dual_design(binding)
    witness = witnesses[1]
    if failure == "person_missing":
        witness["components"] = [c for c in witness["components"] if c["id"] != "person-53"]
    elif failure == "duplicate_identity":
        witness["components"][1]["id"] = witness["components"][0]["id"]
    elif failure == "blocked_door":
        witness["components"][0]["bounds_mm"] = [0, 3800, 400, 4300]
    elif failure == "extra_locker":
        witness["components"].append(
            dict(
                id="extra",
                role="LOCKER",
                bounds_mm=[22200, 500, 22600, 1000],
                states=list(STATES),
                shift=1,
                front="N",
            )
        )
    else:
        basis["locker_model"] = replace(basis["locker_model"], scope_id="OTHER")
    result = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=witnesses
    )
    assert result["functional_status"] in {"INPUT_REQUIRED", "CONFIGURATION_NOT_FIT"}


def test_hypothetical_dictionary_is_not_reviewed_functional_basis(catalog):
    room = catalog["groups"][0]["room"]
    bad = BasisValue(
        400, "mm", "ENGINEERING_DERIVED", "UNREVIEWED", "OTHER", "locker_dimensions_mm"
    )
    result = evaluate_reviewed_locker_witness(
        room,
        catalog["project_binding"],
        field_refs={"locker_dimensions_mm": "bad"},
        reviewed_basis={"bad": bad},
    )
    assert result["functional_status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "extra",
    [
        {"source_label": "OWNER_CONFIRMED"},
        {"status": "CONDITIONAL_FIT"},
        {"reviewed_basis": {}},
        {"witness": {}},
    ],
)
def test_preview_endpoint_cannot_import_approval_or_reviewed_witness(catalog, extra):
    with pytest.raises(ValueError, match="NO_REVIEW_IMPORT"):
        preview_request(catalog, {"group": "G01", "parameters": {}, **extra})


def test_preview_parameters_cannot_override_project_or_portals(catalog):
    with pytest.raises(ValueError, match="HYPOTHETICAL_PARAMETERS_ONLY"):
        preview_request(catalog, {"group": "G01", "parameters": {"locker_count": 1}})
    result = preview_request(catalog, {"group": "G01", "parameters": {"bench_count": 1}})
    assert result["result"]["project_status"] == "INPUT_REQUIRED"
    assert result["result"]["design_counts"]["locker_count"] == 106


@pytest.mark.parametrize("first,expected", [(53, 21200), (90, 36000), (1, 42000)])
def test_unequal_opposed_rows_use_longest_row_not_half_total(catalog, first, expected):
    r = hypothetical_review(catalog, "G01", HypotheticalLockerParameters(first_row_count=first))
    assert r["screening"]["required_length_mm"] == expected
    if first != 53:
        assert r["screening"]["necessary_condition_status"] == "CONFIGURATION_NOT_FIT"
        assert r["screening"]["unplaced_lockers"] > 0


def test_single_shift_legacy_positive_is_not_two_shift_proof(catalog):
    binding = catalog["project_binding"]
    room, refs, witnesses, basis = reviewed_dual_design(binding)
    assert (
        evaluate_functional_room(room, refs, witnesses[1], reviewed_basis=basis)[
            "functional_status"
        ]
        == "CONDITIONAL_FIT"
    )
    for supplied in ({1: witnesses[1]}, {2: witnesses[2]}):
        r = evaluate_reviewed_locker_witness(
            room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=supplied
        )
        assert r["functional_status"] == "INPUT_REQUIRED"
    r = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, witness=witnesses[1]
    )
    assert r["functional_status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "failure",
    [
        "reused_first_shift_people",
        "wrong_locker_front",
        "same_locker_twice",
        "changed_body",
        "missing_motion_review",
        "bad_review_scope",
        "door_sweep_hits_person",
    ],
)
def test_each_shift_needs_identity_front_and_motion_evidence(catalog, failure):
    binding = catalog["project_binding"]
    room, refs, w, basis = reviewed_dual_design(binding)
    people = [c for c in w[2]["components"] if c["role"] == "PERSON"]
    if failure == "reused_first_shift_people":
        w[2] = copy.deepcopy(w[1])
    elif failure == "wrong_locker_front":
        people[0]["bounds_mm"] = [500, 1000, 900, 1600]
    elif failure == "same_locker_twice":
        people[0]["serves"] = people[1]["serves"]
    elif failure == "changed_body":
        next(c for c in w[2]["components"] if c["role"] == "LOCKER")["bounds_mm"][0] += 1
    elif failure == "missing_motion_review":
        del basis[PLAN_FIELD]
    elif failure == "bad_review_scope":
        basis[PLAN_FIELD] = replace(basis[PLAN_FIELD], scope_id="OTHER")
    else:
        plan = copy.deepcopy(basis[PLAN_FIELD].value)
        plan["2"]["USE"]["locker_door_motion"]["locker-54"] = {
            "mode": "EXCLUSION_RECTANGLES",
            "exclusions_mm": [[500, 6400, 900, 7000]],
        }
        basis[PLAN_FIELD] = replace(basis[PLAN_FIELD], value=plan)
    r = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=w
    )
    assert r["functional_status"] != "CONDITIONAL_FIT"


def test_original_r11_positive_with_people_in_net_aisle_is_rejected_by_r3(catalog):
    binding = catalog["project_binding"]
    room, refs, w, basis = reviewed_dual_design(binding)
    next(c for c in w[1]["components"] if c["id"] == "front-low")["bounds_mm"][1] = 1000
    old = evaluate_functional_room(room, refs, w[1], reviewed_basis=basis)
    assert old["functional_status"] == "CONDITIONAL_FIT", old
    r = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=w
    )
    assert r["functional_status"] == "CONFIGURATION_NOT_FIT"
    assert any(c["code"] == "OCCUPIED_SPACE_INTRUDES_NET_AISLE" for c in r["conflicts"])


@pytest.mark.parametrize("state", ["USE", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE"])
def test_exclusive_occupancy_cannot_block_route_in_any_state(catalog, state):
    binding = catalog["project_binding"]
    room, refs, w, basis = reviewed_dual_design(binding)
    w[1]["components"].append(
        dict(
            id="occupied-route",
            role="MAINTENANCE",
            bounds_mm=[1000, 3400, 2000, 4600],
            states=[state],
        )
    )
    old = evaluate_functional_room(room, refs, w[1], reviewed_basis=basis)
    assert old["functional_status"] == "CONDITIONAL_FIT", old
    r = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=w
    )
    assert r["functional_status"] == "CONFIGURATION_NOT_FIT"
    assert any(
        c["code"] == "OCCUPIED_SPACE_INTRUDES_NET_ROUTE" and c["state"] == state
        for c in r["conflicts"]
    )


def test_h5_staggered_example_proves_both_shifts_only_under_unapproved_assumptions(catalog):
    r = response(hypothetical_review(catalog, "G01", HypotheticalLockerParameters()))
    case = r["result"]["conditional_simulation"]
    assert case["simulation_status"] == "GEOMETRY_VALID_ONLY_UNDER_HYPOTHESES", case
    assert r["result"]["project_status"] == "INPUT_REQUIRED"
    assert case["source_label"] == "HYPOTHETICAL_NOT_APPROVED"
    assert [case["shifts"][s]["route_center_y_mm"] for s in ("1", "2")] == [1700, 1550]
    for shift in ("1", "2"):
        c = case["shifts"][shift]
        assert c["r3"]["status"] == "SHIFT_USE_VALIDATED"
        assert c["r3"]["state_results"]["USE"]["people_count"] == 53
        assert len(c["r3"]["state_results"]["USE"]["proven_portal_ids"]) == 2
        ET.fromstring(r["shift_svgs"][shift])


@pytest.mark.parametrize("missing", ["closed_bank", "door_model", "second_plan"])
def test_incomplete_reviewed_operation_plan_never_approves(catalog, missing):
    binding = catalog["project_binding"]
    room, refs, w, basis = reviewed_dual_design(binding)
    plan = copy.deepcopy(basis[PLAN_FIELD].value)
    if missing == "closed_bank":
        del plan["2"]["USE"]["inactive_lockers_closed"]
    elif missing == "door_model":
        del plan["2"]["MAINTENANCE"]["locker_door_motion"]["locker-54"]
    else:
        del plan["2"]
    basis[PLAN_FIELD] = replace(basis[PLAN_FIELD], value=plan)
    r = evaluate_reviewed_locker_witness(
        room, binding, field_refs=refs, reviewed_basis=basis, shift_witnesses=w
    )
    assert r["functional_status"] == "INPUT_REQUIRED"


def test_h5_bench_conflict_is_not_hidden_by_staggered_usage(catalog):
    r = response(hypothetical_review(catalog, "G01", HypotheticalLockerParameters(bench_count=1)))
    assert (
        r["result"]["conditional_simulation"]["simulation_status"]
        != "GEOMETRY_VALID_ONLY_UNDER_HYPOTHESES"
    )
    assert r["result"]["project_status"] == "INPUT_REQUIRED"


def test_p01_p02_have_independent_original_access_readbacks(sources):
    preview = ROOT / "docs/previews/v2.2.2/r11-r3-locker-layout-review-r1"
    data = json.loads((preview / "record-access-readbacks.json").read_bytes())
    selected = {r["record"]: r for r in data if r["record"] in {"P01", "P02"}}
    assert set(selected) == {"P01", "P02"}
    assert selected["P01"]["source_sha256"] != selected["P02"]["source_sha256"]
    originals = {
        r["record"]: r
        for r in sources[0]["room_evaluations"]
        if r["room"]["room_code"] == "changing_room"
    }
    for record, row in selected.items():
        assert row["source_sha256"] == originals[record]["source_candidate_sha256"]
        assert row["candidate_hash"] == originals[record]["room"]["candidate_hash"]
        assert row["two_access_passes"] and row["portal_geometry_matches"]
        assert len(row["access_results"]) == 2
        assert {a["status"] for a in row["access_results"]} == {"PASS"}
