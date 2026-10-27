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


def test_shift_capacity_shortfall_is_not_a_valid_staffing_basis():
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
    assert result["workforce"]["shift_1_workers"] is None


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
