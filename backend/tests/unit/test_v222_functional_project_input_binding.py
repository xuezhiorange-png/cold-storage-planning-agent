"""R11 R2 trusted project binding; never infer staff from frozen inbound mass."""

import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
    bind_project_functional_inputs,
    project_candidate_room_inputs,
)

ROOT = Path(__file__).resolve().parents[3]
REVIEW = ROOT / "docs/previews/v2.2.2/r11-functional-room-fit-r1/review-data.json"
OWNER = (
    ROOT / "docs/previews/v2.2.2/owner-functional-input-contract-r2/"
    "owner-confirmed-business-rules-v2.json"
)


def inputs():
    return json.loads(REVIEW.read_bytes()), OWNER.read_bytes()


def fact(review, name, value, unit, scope=None):
    room = review["room_evaluations"][0]["room"]
    project_scope = ":".join(room["scope_id"].split(":")[:4])
    return ReviewedProjectDatum(
        field_name=name,
        value=value,
        unit=unit,
        project_scope_id=scope or project_scope,
        source_label="OWNER_CONFIRMED",
        reference="SYNTHETIC_REVIEWED_PROJECT_DOCUMENT:" + name,
    )


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def denied(*_a, **_k):
        pytest.fail("R11_R2_NATIVE_SOLVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", denied)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", denied)


def test_missing_project_inputs_preserve_all_27_original_unknowns():
    review, owner = inputs()
    result = bind_project_functional_inputs(review, owner)
    assert result["user_supplied_inbound_kg_per_day_not_used"]
    assert result["binding_status"] == "INPUT_REQUIRED"
    assert result["workforce"]["shift_1_workers"] is None
    assert result["office"]["factory_size"] is None
    assert result["coating"]["equipment_model"] is None
    rows = project_candidate_room_inputs(review, result)
    assert len(rows) == 27
    assert {r["functional_status"] for r in rows} == {"INPUT_REQUIRED"}
    assert {r["p1_area_status"] for r in rows} == {"AREA_SATISFIED"}
    assert {r["original_engineering_status"] for r in rows} == {"EXISTING_STAGE_B_ELIGIBLE"}
    assert all(r["source_scope"].endswith(":" + r["room_code"]) for r in rows)
    changing = next(x for x in rows if x["room_code"] == "changing_room")
    assert changing["project_fields_bound"] == [
        "internal_clothing_separation",
        "shift_change_policy",
    ]


def test_verified_packaged_mass_derives_two_shifts_without_inbound_substitution():
    review, owner = inputs()
    mass = fact(review, "PACKAGED_PRODUCT_MASS_KG_PER_DAY", "19200", "kg/day")
    result = bind_project_functional_inputs(
        review, owner, reviewed_project={"PACKAGED_PRODUCT_MASS_KG_PER_DAY": mass}
    )
    assert result["workforce"]["shift_1_workers"] == 50
    assert result["workforce"]["shift_2_workers"] == 50
    assert result["workforce"]["separate_personal_lockers"] == [50, 50]
    assert result["workforce"]["simultaneous_changing_users"] == 50
    assert result["workforce"]["required_packing_tables"] == 17
    assert result["workforce"]["derived_from_packaged_product_mass"]
    assert result["workforce"]["capacity_validation"] == "SATISFIED"
    assert result["workforce"]["shift_workload_allocation_basis"] == "OWNER_V2_DEFAULT_EQUAL_SPLIT"
    assert [r["packaged_product_mass_kg"] for r in result["workforce"]["per_shift_capacity"]] == [
        "9600.0",
        "9600.0",
    ]
    changing = next(
        r
        for r in project_candidate_room_inputs(review, result)
        if r["room_code"] == "changing_room"
    )
    assert "shift_locker_counts" in changing["project_fields_bound"]
    assert "simultaneous_users" in changing["project_fields_bound"]
    assert changing["functional_status"] == "INPUT_REQUIRED"


def test_factory_size_selection_is_conditional_not_an_automatic_20t_class():
    review, owner = inputs()
    assert bind_project_functional_inputs(review, owner)["office"]["staff_count"] is None
    selected = fact(review, "FACTORY_SIZE", "MEDIUM", "factory_size")
    result = bind_project_functional_inputs(
        review, owner, reviewed_project={"FACTORY_SIZE": selected}
    )
    assert result["office"]["staff_count"] == 20
    assert all(
        "staff_count" in row["project_fields_bound"]
        and row["functional_status"] == "INPUT_REQUIRED"
        for row in project_candidate_room_inputs(review, result)
        if row["room_code"] == "office"
    )


def test_explicit_both_shift_counts_supported_without_missing_mass_becoming_fact():
    review, owner = inputs()
    counts = {
        key: fact(review, key, value, "people")
        for key, value in (("SHIFT_1_WORKERS", 12), ("SHIFT_2_WORKERS", 14))
    }
    result = bind_project_functional_inputs(review, owner, reviewed_project=counts)
    assert result["workforce"]["separate_personal_lockers"] == [12, 14]
    assert result["workforce"]["simultaneous_changing_users"] == 14
    assert result["workforce"]["capacity_validation"] == "INPUT_REQUIRED_PACKAGED_MASS"
    assert "PACKAGED_PRODUCT_MASS_KG_PER_DAY" in result["missing_project_inputs"]


def test_single_shift_override_never_falls_back_to_default_even_with_mass():
    review, owner = inputs()
    request = {
        "PACKAGED_PRODUCT_MASS_KG_PER_DAY": fact(
            review, "PACKAGED_PRODUCT_MASS_KG_PER_DAY", "19200", "kg/day"
        ),
        "SHIFT_1_WORKERS": fact(review, "SHIFT_1_WORKERS", 50, "people"),
    }
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    assert result["binding_status"] == "INPUT_CONFLICT"
    assert result["workforce"]["separate_personal_lockers"] is None


def test_total_capacity_shortfall_conflicts_but_preserves_reviewed_people():
    review, owner = inputs()
    request = {
        "PACKAGED_PRODUCT_MASS_KG_PER_DAY": fact(
            review, "PACKAGED_PRODUCT_MASS_KG_PER_DAY", "20000", "kg/day"
        ),
        "SHIFT_1_WORKERS": fact(review, "SHIFT_1_WORKERS", 10, "people"),
        "SHIFT_2_WORKERS": fact(review, "SHIFT_2_WORKERS", 10, "people"),
    }
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    assert result["binding_status"] == "INPUT_CONFLICT"
    assert result["workforce"]["status"] == "REVIEWED_PROJECT_BASIS"
    assert result["workforce"]["separate_personal_lockers"] == [10, 10]
    assert result["workforce"]["aggregate_capacity_validation"] == "INSUFFICIENT_TOTAL"
    assert result["workforce"]["capacity_validation"] == "CONFLICT"
    assert result["conflict"] == "REVIEWED_SHIFT_CAPACITY_BELOW_PACKAGED_MASS"


@pytest.mark.parametrize("value", [0, "0", "-1", "NaN", "Infinity", 1.5, True])
def test_invalid_packaged_mass_is_not_reviewed(value):
    review, owner = inputs()
    entry = fact(review, "PACKAGED_PRODUCT_MASS_KG_PER_DAY", value, "kg/day")
    with pytest.raises(ValueError):
        bind_project_functional_inputs(
            review, owner, reviewed_project={"PACKAGED_PRODUCT_MASS_KG_PER_DAY": entry}
        )


@pytest.mark.parametrize("reason", ["wrong_scope", "wrong_field", "wrong_unit", "no_reference"])
def test_reviewed_datum_must_match_source_semantics(reason):
    review, owner = inputs()
    datum = fact(review, "FACTORY_SIZE", "SMALL", "factory_size")
    if reason == "wrong_scope":
        datum = replace(datum, project_scope_id="ANOTHER_PROJECT")
    elif reason == "wrong_field":
        datum = replace(datum, field_name="SHIFT_1_WORKERS")
    elif reason == "wrong_unit":
        datum = replace(datum, unit="people")
    else:
        datum = replace(datum, reference="")
    with pytest.raises(ValueError):
        bind_project_functional_inputs(review, owner, reviewed_project={"FACTORY_SIZE": datum})


def test_untyped_request_string_cannot_self_certify_owner_review():
    review, owner = inputs()
    with pytest.raises(ValueError, match="TRUSTED_APPLICATION_REVIEW_REQUIRED"):
        bind_project_functional_inputs(
            review,
            owner,
            reviewed_project={
                "FACTORY_SIZE": {"value": "SMALL", "source_label": "OWNER_CONFIRMED"}
            },
        )


def test_owner_contract_changed_is_not_silently_accepted():
    review, owner = inputs()
    with pytest.raises(ValueError, match="OWNER_V2_SOURCE_HASH_MISMATCH"):
        bind_project_functional_inputs(review, owner + b" ")


def test_archive_binding_does_not_pretend_this_is_xinzhao_or_equipment_approved():
    review, owner = inputs()
    result = bind_project_functional_inputs(review, owner)
    assert result["project_identity"] == "FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO"
    assert result["coating"]["runtime_hours"] is None
    assert not result["functional_approval"]
    assert not result["p1_modified"]
    assert not result["quality_comparators_modified"]
    assert result["native_solves"] == 0


def test_report_generator_reads_sealed_inputs_and_writes_only_new_output(tmp_path, monkeypatch):
    original_review = REVIEW.read_bytes()
    original_owner = OWNER.read_bytes()
    out = tmp_path / "report"
    monkeypatch.setattr(sys, "argv", ["build_r11_project_input_binding.py", "--output", str(out)])
    runpy.run_path(
        str(ROOT / "backend/scripts/build_r11_project_input_binding.py"), run_name="__main__"
    )
    binding = json.loads((out / "project-binding.json").read_bytes())
    rows = json.loads((out / "room-input-projection.json").read_bytes())
    request = json.loads((out / "project-input-request.json").read_bytes())
    assert len(rows) == 27
    assert {row["functional_status"] for row in rows} == {"INPUT_REQUIRED"}
    assert binding["project_reviewed_facts"] == {}
    assert binding["workforce"]["separate_personal_lockers"] is None
    assert request["status"] == "UNREVIEWED_PROPOSAL_NOT_APPROVED"
    assert "SHIFT_1_PACKAGED_PRODUCT_MASS_KG" in request["values"]
    assert "SHIFT_2_PACKAGED_PRODUCT_MASS_KG" in request["values"]
    assert all(value["value"] is None for value in request["values"].values())
    assert (out / "index.html").read_text().count("<tr>") == 28
    assert "INPUT_REQUIRED" in (out / "readiness-report.md").read_text()
    assert REVIEW.read_bytes() == original_review
    assert OWNER.read_bytes() == original_owner
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError):
        runpy.run_path(
            str(ROOT / "backend/scripts/build_r11_project_input_binding.py"), run_name="__main__"
        )
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def explicit_staffing(review, workers=(1, 199), total="20000", workloads=None):
    request = {
        "PACKAGED_PRODUCT_MASS_KG_PER_DAY": fact(
            review, "PACKAGED_PRODUCT_MASS_KG_PER_DAY", total, "kg/day"
        ),
        "SHIFT_1_WORKERS": fact(review, "SHIFT_1_WORKERS", workers[0], "people"),
        "SHIFT_2_WORKERS": fact(review, "SHIFT_2_WORKERS", workers[1], "people"),
    }
    if workloads is not None:
        request.update(
            (name, fact(review, name, value, "kg/shift"))
            for name, value in zip(
                ("SHIFT_1_PACKAGED_PRODUCT_MASS_KG", "SHIFT_2_PACKAGED_PRODUCT_MASS_KG"),
                workloads,
                strict=True,
            )
        )
    return request


@pytest.mark.parametrize("workers", [(1, 199), (199, 1), (100, 100)])
def test_sufficient_total_without_reviewed_allocation_never_validates_each_shift(workers):
    review, owner = inputs()
    request = explicit_staffing(review, workers=workers)
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    staff = result["workforce"]
    assert staff["status"] == "REVIEWED_PROJECT_BASIS"
    assert staff["separate_personal_lockers"] == list(workers)
    assert staff["aggregate_capacity_validation"] == "SUFFICIENT_TOTAL_ONLY"
    assert staff["capacity_validation"] == "INPUT_REQUIRED_SHIFT_WORKLOAD_ALLOCATION"
    assert staff["shift_workload_allocation_basis"] is None
    assert not staff["derived_from_packaged_product_mass"]
    assert all(r["packaged_product_mass_kg"] is None for r in staff["per_shift_capacity"])
    assert {r["status"] for r in staff["per_shift_capacity"]} == {"INPUT_REQUIRED_SHIFT_WORKLOAD"}
    assert "SHIFT_WORKLOAD_ALLOCATION_BASIS" in result["missing_project_inputs"]
    assert result["binding_status"] == "INPUT_REQUIRED"
    rows = project_candidate_room_inputs(review, result)
    assert len(rows) == 27
    assert all(r["functional_status"] == "INPUT_REQUIRED" for r in rows)
    assert all(
        "shift_locker_counts" in r["project_fields_bound"]
        for r in rows
        if r["room_code"] == "changing_room"
    )


def test_full_reviewed_unbalanced_allocation_verifies_each_shift_at_boundary():
    review, owner = inputs()
    request = explicit_staffing(review, workloads=("192", "19808"))
    request["FACTORY_SIZE"] = fact(review, "FACTORY_SIZE", "SMALL", "factory_size")
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    staff = result["workforce"]
    assert result["conflict"] is None
    assert result["binding_status"] == "PROJECT_STAFFING_BASIS_READY_ROOM_FIT_PENDING"
    assert staff["capacity_validation"] == "SATISFIED"
    assert staff["shift_workload_allocation_basis"] == "REVIEWED_SHIFT_WORKLOADS"
    assert [r["packaged_product_mass_kg"] for r in staff["per_shift_capacity"]] == ["192", "19808"]
    assert [r["capacity_kg"] for r in staff["per_shift_capacity"]] == ["192.0", "38208.0"]
    assert all(r["status"] == "SATISFIED" for r in staff["per_shift_capacity"])
    assert "SHIFT_1_PACKAGED_PRODUCT_MASS_KG" in staff["shift_workload_source_reference"]
    assert "SHIFT_WORKLOAD_ALLOCATION_BASIS" not in result["missing_project_inputs"]
    assert all(
        r["functional_status"] == "INPUT_REQUIRED"
        for r in project_candidate_room_inputs(review, result)
    )


@pytest.mark.parametrize("loads", [("10000", "10000"), ("192.001", "19807.999")])
@pytest.mark.parametrize("workers", [(1, 199), (199, 1)])
def test_actual_shift_over_capacity_rejects_even_with_sufficient_total(loads, workers):
    review, owner = inputs()
    result = bind_project_functional_inputs(
        review, owner, reviewed_project=explicit_staffing(review, workers=workers, workloads=loads)
    )
    staff = result["workforce"]
    assert staff["aggregate_capacity_validation"] == "SUFFICIENT_TOTAL_ONLY"
    assert staff["capacity_validation"] == "CONFLICT"
    assert result["binding_status"] == "INPUT_CONFLICT"
    assert result["conflict"] == "REVIEWED_SHIFT_WORKLOAD_EXCEEDS_CAPACITY"
    assert staff["per_shift_capacity"][workers.index(1)]["status"] == "EXCEEDED"
    assert staff["separate_personal_lockers"] == list(workers)


def test_reviewed_workload_sum_must_match_reviewed_daily_mass():
    review, owner = inputs()
    result = bind_project_functional_inputs(
        review,
        owner,
        reviewed_project=explicit_staffing(review, workers=(100, 100), workloads=("9600", "9600")),
    )
    assert result["conflict"] == "REVIEWED_SHIFT_WORKLOADS_DO_NOT_SUM_TO_DAILY_MASS"
    assert result["workforce"]["capacity_validation"] == "CONFLICT"
    assert all(r["status"] != "SATISFIED" for r in result["workforce"]["per_shift_capacity"])


@pytest.mark.parametrize("explicit", [True, False])
def test_partial_reviewed_workload_does_not_trigger_equal_split(explicit):
    review, owner = inputs()
    request = explicit_staffing(review)
    if not explicit:
        del request["SHIFT_1_WORKERS"]
        del request["SHIFT_2_WORKERS"]
    key = "SHIFT_1_PACKAGED_PRODUCT_MASS_KG"
    request[key] = fact(review, key, "100", "kg/shift")
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    staff = result["workforce"]
    assert staff["capacity_validation"] != "SATISFIED"
    assert staff["shift_workload_allocation_basis"] is None
    assert staff["per_shift_capacity"][1]["packaged_product_mass_kg"] is None
    assert "SHIFT_2_PACKAGED_PRODUCT_MASS_KG" in result["missing_project_inputs"]
    assert "SHIFT_1_PACKAGED_PRODUCT_MASS_KG" not in result["missing_project_inputs"]


def test_reviewed_workloads_without_explicit_staffing_derive_the_actual_split():
    review, owner = inputs()
    request = explicit_staffing(review, workloads=("192", "19808"))
    del request["SHIFT_1_WORKERS"]
    del request["SHIFT_2_WORKERS"]
    result = bind_project_functional_inputs(review, owner, reviewed_project=request)
    assert result["workforce"]["separate_personal_lockers"] == [1, 104]
    assert result["workforce"]["shift_workload_allocation_basis"] == "REVIEWED_SHIFT_WORKLOADS"
    assert result["workforce"]["capacity_validation"] == "SATISFIED"


def test_reviewed_zero_workload_is_not_replaced_by_equal_split():
    review, owner = inputs()
    result = bind_project_functional_inputs(
        review, owner, reviewed_project=explicit_staffing(review, workloads=("0", "20000"))
    )
    assert result["workforce"]["per_shift_capacity"][0]["packaged_product_mass_kg"] == "0"
    assert result["workforce"]["capacity_validation"] == "SATISFIED"


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", 1.5, True])
def test_invalid_reviewed_shift_workload_rejected(value):
    review, owner = inputs()
    with pytest.raises(ValueError):
        bind_project_functional_inputs(
            review, owner, reviewed_project=explicit_staffing(review, workloads=(value, "20000"))
        )


@pytest.mark.parametrize(
    "change",
    [
        {"project_scope_id": "OTHER"},
        {"unit": "kg/day"},
        {"reference": ""},
        {"field_name": "SHIFT_2_PACKAGED_PRODUCT_MASS_KG"},
    ],
)
def test_shift_workload_requires_exact_reviewed_field_scope_units_and_source(change):
    review, owner = inputs()
    request = explicit_staffing(review, workloads=("192", "19808"))
    key = "SHIFT_1_PACKAGED_PRODUCT_MASS_KG"
    request[key] = replace(request[key], **change)
    with pytest.raises(ValueError, match="REVIEWED_PROJECT_SOURCE_OR_SCOPE_MISMATCH"):
        bind_project_functional_inputs(review, owner, reviewed_project=request)
