"""Physical source boundary, fresh two-shift rechecks and unchanged archives."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.physical_room_calibration_review import (
    R12,
    bind_physical_inputs,
    calibration_context,
    historical_hypothesis_packet,
    input_template,
    review_calibration,
    review_reference,
    supported_projection,
    witness_is_current,
)
from cold_storage.modules.layout.domain.physical_room_calibration import (
    FIELDS,
    case_physical_checks,
    storage_checks,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
    read_proposed_documents,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_page import (
    cabinet_door_plan,
    cabinet_elevation,
    calibration_plan,
    review_page,
)

ROOT = Path(__file__).resolve().parents[3]
C_KEY = "R10-L26331-W3550-M50-MIXED"
W_KEY = "R10-L26331-W3850-M100-MIXED-SENSITIVITY"


@pytest.fixture(scope="module", autouse=True)
def forbid_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R13_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def source_files():
    return read_calibration_evidence(ROOT)


@pytest.fixture(scope="module")
def ctx(source_files):
    return calibration_context(source_files)


@pytest.fixture(scope="module")
def template(ctx):
    return input_template(ctx)


@pytest.fixture(scope="module")
def example(ctx):
    return historical_hypothesis_packet(ctx, C_KEY)


@pytest.fixture(scope="module")
def rechecks(ctx):
    return {
        key: review_calibration(ctx, *historical_hypothesis_packet(ctx, key))
        for key in (C_KEY, W_KEY)
    }


def changed(example, field, value):
    packet, docs = copy.deepcopy(example)
    packet["parameters"][field]["value"] = value
    if value is None:
        packet["parameters"][field].update(document_id=None, locator=None)
    else:
        packet["parameters"][field].update(
            document_id="historical_hypothesis", locator="/parameters/" + field
        )
    doc = packet["source_documents"]["historical_hypothesis"]
    blob = json.loads(docs[doc["file_name"]])
    blob["parameters"][field] = value
    docs[doc["file_name"]] = json.dumps(blob, ensure_ascii=False).encode()
    doc["sha256"] = hashlib.sha256(docs[doc["file_name"]]).hexdigest()
    return packet, docs


def external_document(example):
    packet, docs = copy.deepcopy(example)
    doc = packet["source_documents"]["historical_hypothesis"]
    docs[doc["file_name"]] = json.dumps(
        dict(
            identity="SYNTHETIC_SOURCE_REVIEW_UNIT_TEST_ONLY",
            parameters={k: v["value"] for k, v in packet["parameters"].items()},
        )
    ).encode()
    doc["sha256"] = hashlib.sha256(docs[doc["file_name"]]).hexdigest()
    return packet, docs


def test_missing_real_equipment_has_no_default_or_pass(ctx, template):
    result = review_calibration(ctx, template, {})
    assert all(p["value"] is None for p in template["parameters"].values())
    assert result["actual_calibration"] == "INPUT_REQUIRED"
    assert result["engineering_approval"] == result["factory_applicability"] == "NOT_EVALUATED"
    assert all(c["summary"] is None for c in result["cases"])
    assert all(
        p["review_status"] == "INPUT_REQUIRED" for p in result["binding"]["parameters"].values()
    )


def test_owner_facts_are_source_bound_and_one_physical_room(ctx, template):
    b = bind_physical_inputs(ctx, template, {})
    facts = b["owner_requirements"]
    assert facts["USERS_PER_SHIFT"]["value"] == facts["SIMULTANEOUS_USERS"]["value"] == 53
    assert facts["CABINET_COLUMNS"]["value"] == 22
    assert facts["COMPARTMENT_CAPACITY"]["value"] == 110
    assert facts["PACKAGED_PRODUCT_MASS_KG_PER_DAY"]["value"] == 20000
    assert facts["BENCH_COUNT"]["value"] == facts["SEPARATE_CHANGING_AREA_COUNT"]["value"] == 0
    assert ctx["overlay"]["physical_room_count"] == 1
    assert [r["record"] for r in ctx["overlay"]["records"]] == ["P01", "P02"]


@pytest.mark.parametrize(
    "key", ["project_scope_id", "physical_room_id", "owner_template_sha256", "schema_version"]
)
def test_other_project_room_or_source_rejected(ctx, template, key):
    packet = copy.deepcopy(template)
    packet[key] = "foreign"
    with pytest.raises(ValueError, match="MISMATCH"):
        bind_physical_inputs(ctx, packet, {})


@pytest.mark.parametrize(
    "field,value",
    [
        ("USERS_PER_SHIFT", 52),
        ("SIMULTANEOUS_USERS", 52),
        ("required_compartments", 100),
        ("CABINET_COLUMNS", 21),
    ],
)
def test_design_counts_cannot_be_lowered_in_input(ctx, template, field, value):
    packet = copy.deepcopy(template)
    packet["parameters"][field] = dict(value=value, unit="count", document_id=None, locator=None)
    with pytest.raises(ValueError, match="VOCABULARY"):
        bind_physical_inputs(ctx, packet, {})


@pytest.mark.parametrize("position", ["root", "parameter", "document"])
def test_json_approved_flags_are_not_review(ctx, example, position):
    packet, docs = copy.deepcopy(example)
    target = (
        packet
        if position == "root"
        else packet["parameters"]["finish_mm"]
        if position == "parameter"
        else packet["source_documents"]["historical_hypothesis"]
    )
    target["approved"] = True
    with pytest.raises(ValueError):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize("label", ["OWNER_CONFIRMED", "ENGINEERING_DERIVED", "APPROVED"])
def test_raw_source_type_cannot_claim_review(ctx, example, label):
    packet, docs = copy.deepcopy(example)
    packet["source_documents"]["historical_hypothesis"]["source_type"] = label
    with pytest.raises(ValueError, match="UNREVIEWED_SOURCE"):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize("kind", ["SUPPLIER_UNREVIEWED", "SITE_MEASUREMENT_UNREVIEWED"])
def test_unreviewed_sources_remain_unreviewed(ctx, example, kind):
    packet, docs = external_document(example)
    packet["source_documents"]["historical_hypothesis"]["source_type"] = kind
    bound = bind_physical_inputs(ctx, packet, docs)
    assert bound["parameters"]["finish_mm"]["review_status"] == kind
    assert not bound["parameters"]["finish_mm"]["is_reviewed"]
    assert bound["owner_requirements"] == ctx["owner_template"]["reviewed_inputs"]


def test_existing_typed_review_boundary_reused_with_exact_reference(ctx, example):
    packet, docs = external_document(example)
    doc = packet["source_documents"]["historical_hypothesis"]
    doc["source_type"] = "SUPPLIER_UNREVIEWED"
    datum = ReviewedProjectDatum(
        "finish_mm",
        20,
        "mm",
        packet["project_scope_id"],
        "ENGINEERING_DERIVED",
        review_reference(doc, packet["parameters"]["finish_mm"]["locator"]),
    )
    result = bind_physical_inputs(ctx, packet, docs, reviewed_project={"finish_mm": datum})
    p = result["parameters"]["finish_mm"]
    assert p["is_reviewed"] and p["source_type"] == "SUPPLIER_UNREVIEWED"
    assert p["reviewed_project_datum"]["source_label"] == "ENGINEERING_DERIVED"
    assert result["unreviewed"]
    with pytest.raises(ValueError, match="TYPED_PROJECT"):
        bind_physical_inputs(ctx, packet, docs, reviewed_project={"finish_mm": vars(datum)})


def test_hypothesis_cannot_be_reviewed_as_actual(ctx, example):
    packet, docs = copy.deepcopy(example)
    doc = packet["source_documents"]["historical_hypothesis"]
    datum = ReviewedProjectDatum(
        "finish_mm",
        20,
        "mm",
        packet["project_scope_id"],
        "OWNER_CONFIRMED",
        review_reference(doc, packet["parameters"]["finish_mm"]["locator"]),
    )
    with pytest.raises(ValueError, match="REVIEW_SOURCE_SCOPE_OR_VALUE"):
        bind_physical_inputs(ctx, packet, docs, reviewed_project={"finish_mm": datum})


def test_known_historical_example_cannot_be_relabeled_supplier(ctx, example):
    packet, docs = copy.deepcopy(example)
    packet["source_documents"]["historical_hypothesis"]["source_type"] = "SUPPLIER_UNREVIEWED"
    with pytest.raises(ValueError, match="CANNOT_BE_RELABELLED"):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize("corruption", ["bytes", "hash", "scope", "date", "missing"])
def test_document_integrity_and_applicability_rejected(ctx, example, corruption):
    packet, docs = copy.deepcopy(example)
    doc = packet["source_documents"]["historical_hypothesis"]
    if corruption == "bytes":
        docs[doc["file_name"]] += b"x"
    elif corruption == "hash":
        doc["sha256"] = "0" * 64
    elif corruption == "scope":
        doc["project_scope_id"] = "other-project"
    elif corruption == "date":
        doc["document_date"] = "2026-02-31"
    else:
        docs = {}
    with pytest.raises(ValueError):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize("value", [20.0, True, "20", -1])
def test_integer_mm_required(ctx, example, value):
    with pytest.raises(ValueError, match="INTEGER_PHYSICAL"):
        bind_physical_inputs(ctx, *changed(example, "finish_mm", value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_tier_count", 4),
        ("tier_2_bottom_mm", 101),
        ("tier_5_clear_height_mm", 1000),
        ("tier_1_clear_width_mm", 999),
    ],
)
def test_invalid_five_tier_structure_refused(ctx, example, field, value):
    packet, docs = changed(example, field, value)
    if packet["parameters"][field]["document_id"] is None:
        packet["parameters"][field].update(
            document_id="historical_hypothesis", locator="/parameters/" + field
        )
    with pytest.raises(ValueError, match="PHYSICAL_CONFIGURATION_INPUT_CONFLICT"):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize("axis", ["depth", "width"])
def test_net_dimensions_and_actual_panels_cannot_exceed_unit(ctx, example, axis):
    packet, docs = changed(example, "tier_1_clear_" + axis + "_mm", 490 if axis == "depth" else 390)
    packet, docs = changed(
        (packet, docs),
        "back_panel_mm" if axis == "depth" else "side_panel_mm",
        50 if axis == "depth" else 25,
    )
    with pytest.raises(ValueError, match="PHYSICAL_CONFIGURATION_INPUT_CONFLICT"):
        bind_physical_inputs(ctx, packet, docs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit_width_mm", 850),
        ("door_open_angle_deg", 120),
        ("hinge_side", "RIGHT"),
        ("door_leaf_thickness_mm", 25),
        ("turn_width_mm", 900),
        ("operation_sequence", "OTHER"),
        ("partial_unit_available", "UNAVAILABLE"),
        ("static_width_mm", 500),
        ("transport_width_mm", 400),
        ("activity_width_mm", 450),
        ("waiting_gap_mm", 20),
        ("aisle_required_mm", 1000),
    ],
)
def test_unsupported_real_configuration_not_silently_projected(ctx, example, field, value):
    b = bind_physical_inputs(ctx, *changed(example, field, value))
    p = supported_projection(b)
    assert p["status"] == "UNSUPPORTED_PHYSICAL_CONFIGURATION"
    assert p["conditions"] is None and p["unsupported"]


def test_missing_partial_unit_is_not_procurement_assumption(ctx, example):
    projection = supported_projection(
        bind_physical_inputs(ctx, *changed(example, "partial_unit_available", None))
    )
    assert projection["status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize("key", [C_KEY, W_KEY])
def test_same_parameters_and_new_input_bound_witnesses(rechecks, key):
    r = rechecks[key]
    a, b = r["cases"]
    assert a["witness"]["input_fingerprint"] == b["witness"]["input_fingerprint"]
    assert (
        a["witness"]["payload"]["projection"]["conditions"]
        == b["witness"]["payload"]["projection"]["conditions"]
    )
    assert a["witness"]["evidence_hash"] != b["witness"]["evidence_hash"]
    assert a["physical_room_count"] == b["physical_room_count"] == 1
    assert [a["area_m2"], b["area_m2"]] == ["93.475050", "101.374350"]
    assert all(witness_is_current(r["binding"], c["witness"]) for c in (a, b))


def test_twenty_twenty_both_complete_real_two_shift_simulations(rechecks):
    for c in rechecks[C_KEY]["cases"]:
        s = c["summary"]
        assert (
            s["full_flow_verified"] and s["home_count"] == 53 and s["completed_users"] == [53, 53]
        )
        flows = c["witness"]["payload"]["case"]["shifts"]
        for flow in flows:
            assert flow["initial_service_occupancy"] == flow["completed_users"] == 53
            assert len(set(flow["completed_person_ids"])) == 53
            assert any(e["operation"] == "PARALLEL_STANDING_CHANGE" for e in flow["events"])
        assert c["physical_checks"]["door_person_checks"] > 0
        assert not c["physical_checks"]["door_person_conflicts"]


def test_thirty_forty_c_is_not_upgraded_from_historical_pass(rechecks):
    c, w = rechecks[W_KEY]["cases"]
    assert c["summary"]["home_count"] == 40
    assert c["summary"]["static_status"] == "STATIC_GEOMETRY_REJECTED"
    assert c["summary"]["full_flow_status"] == "NOT_EVALUATED_UPSTREAM_REJECTED"
    assert c["witness"]["payload"]["case"]["shifts"] == []
    assert w["summary"]["completed_users"] == [53, 53]
    assert w["summary"]["minimum_margin_mm"] == 70 and not w["summary"]["margin_target_met"]


def test_changed_value_or_document_invalidates_old_witness(ctx, example, rechecks):
    packet, docs = changed(example, "finish_mm", 21)
    binding = bind_physical_inputs(ctx, packet, docs)
    assert not witness_is_current(binding, rechecks[C_KEY]["cases"][0]["witness"])
    packet, docs = copy.deepcopy(example)
    doc = packet["source_documents"]["historical_hypothesis"]
    docs[doc["file_name"]] += b"\n"
    doc["sha256"] = hashlib.sha256(docs[doc["file_name"]]).hexdigest()
    assert not witness_is_current(
        bind_physical_inputs(ctx, packet, docs), rechecks[C_KEY]["cases"][0]["witness"]
    )


def test_witness_payload_corruption_detected(rechecks):
    r = rechecks[C_KEY]
    w = copy.deepcopy(r["cases"][0]["witness"])
    w["payload"]["label"] = "forged"
    assert not witness_is_current(r["binding"], w)


@pytest.mark.parametrize("where", ["values", "parameters", "owner_requirements"])
def test_editing_bound_input_invalidates_old_witness(rechecks, where):
    r = rechecks[C_KEY]
    binding = copy.deepcopy(r["binding"])
    if where == "values":
        binding["values"]["finish_mm"] = 21
    elif where == "parameters":
        binding["parameters"]["finish_mm"]["value"] = 21
    else:
        binding["owner_requirements"]["USERS_PER_SHIFT"]["value"] = 52
    assert not witness_is_current(binding, r["cases"][0]["witness"])


def test_returned_data_does_not_mutate_source_context(ctx, example):
    before = copy.deepcopy(ctx["overlay"])
    hashes = dict(ctx["source_hashes"])
    result = review_calibration(ctx, *example)
    result["cases"][0]["site"][0]["outer_bounds_mm"][0] = -999
    result["binding"]["source_hashes"][next(iter(hashes))] = "changed"
    assert ctx["overlay"] == before and ctx["source_hashes"] == hashes


def test_construction_tolerance_is_explicit_same_projection(ctx, example):
    b = bind_physical_inputs(ctx, *changed(example, "construction_tolerance_mm", 5))
    p = supported_projection(b)
    assert p["conditions"]["finish_mm"] == 25
    assert p["conditions"]["installation_gap_mm"] == 20
    assert "PER_FACE_INWARD" in p["construction_tolerance_projection"]


def test_valid_but_nonuniform_layers_are_not_approximated(ctx, example):
    b = bind_physical_inputs(ctx, *changed(example, "tier_1_clear_height_mm", 290))
    assert supported_projection(b)["status"] == "UNSUPPORTED_PHYSICAL_CONFIGURATION"


def test_insufficient_clothing_and_net_dimensions_never_pass(rechecks):
    for c in rechecks[C_KEY]["cases"]:
        storage = c["physical_checks"]["storage"]
        assert (
            storage["arithmetic_capacity"] == 110
            and storage["independent_compartment_demand"] == 106
        )
        assert storage["actual_storage_function"] == "INPUT_REQUIRED"
        assert all(
            t["storage"]["status"] == "INPUT_REQUIRED"
            and t["retrieval"]["status"] == "INPUT_REQUIRED"
            for t in storage["cells"]
        )


def test_storage_envelope_clear_opening_and_reach_checks_are_independent(example):
    v = {k: p["value"] for k, p in example[0]["parameters"].items()}
    for tier in range(1, 6):
        v.update(
            {
                f"tier_{tier}_clear_width_mm": 360,
                f"tier_{tier}_clear_depth_mm": 480,
                f"tier_{tier}_operation_height_mm": 200 + (tier - 1) * 320,
            }
        )
    v.update(
        work_bundle_width_mm=180,
        work_bundle_depth_mm=300,
        work_bundle_height_mm=200,
        private_bundle_width_mm=180,
        private_bundle_depth_mm=300,
        private_bundle_height_mm=200,
        partition_mm=20,
        separation_kind="SIDE_BY_SIDE",
        clothing_use_method="FOLDED_BUNDLE_THROUGH_CLEAR_OPENING",
        retrieval_width_mm=300,
        retrieval_depth_mm=400,
        retrieval_height_mm=200,
        door_opening_clear_width_mm=250,
        door_opening_clear_height_mm=290,
    )
    result = storage_checks(v)
    assert all(c["storage"]["status"] == "CONFIGURATION_NOT_FIT" for c in result["cells"])
    assert all(c["retrieval"]["status"] == "CONFIGURATION_NOT_FIT" for c in result["cells"])
    v["reach_high_mm"] = 1000
    assert storage_checks(v)["cells"][-1]["reach"]["status"] == "CONFIGURATION_NOT_FIT"
    assert result["actual_storage_function"] == "INPUT_REQUIRED"


def test_actual_door_body_collision_is_not_ignored(rechecks):
    r = rechecks[C_KEY]
    case = copy.deepcopy(r["cases"][0]["witness"]["payload"]["case"])
    s = case["geometry"]["snapshots"][0]
    door = s["doors"][0]
    hx, hy = door["hinge_mm"]
    person = s["people"][0]
    person["bounds_mm"] = [hx, hy, hx + 450, hy + 650]
    person["volumes_mm"] = [[hx, hy, 0, hx + 450, hy + 650, 1800]]
    result = case_physical_checks(case, r["binding"]["values"])
    assert result["door_status"] == "CONFIGURATION_NOT_FIT"
    assert any(c["person"] == person["id"] for c in result["door_person_conflicts"])


@pytest.mark.parametrize("separation", ["OTHER", "TWO_COMPARTMENTS"])
def test_unknown_separation_is_not_approximated_as_internal_partition(example, separation):
    values = {k: p["value"] for k, p in example[0]["parameters"].items()}
    values["separation_kind"] = separation
    r = storage_checks(values)
    assert all(c["storage"]["status"] == "UNSUPPORTED_PHYSICAL_CONFIGURATION" for c in r["cells"])
    assert r["actual_storage_function"] == "INPUT_REQUIRED"
    if separation == "TWO_COMPARTMENTS":
        assert r["separation_required_compartments"] == 212
        assert r["separation_capacity_status"] == "CONFIGURATION_NOT_FIT_110_LESS_THAN_212"


def test_fresh_site_checks_keep_b_conflicts_and_one_room(rechecks):
    for r in rechecks.values():
        for c in r["cases"]:
            assert [s["record"] for s in c["site"]] == ["P01", "P02"]
            assert all(
                s["recomputed_from_archived_geometry"] and not s["uses_archived_functional_pass"]
                for s in c["site"]
            )
        assert all(
            b["corridor_intersection_m2"] == "3.338000"
            and b["prohibited_intersection_m2"] == "0.982000"
            for b in r["historical_b_preserved"]
        )


def test_historical_bytes_and_inputs_unchanged_by_comparison(source_files, ctx, example):
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in source_files.items()}
    before = copy.deepcopy(example)
    review_calibration(ctx, *example)
    assert hashes == {n: hashlib.sha256(b).hexdigest() for n, b in source_files.items()}
    assert before == example
    assert (
        ctx["overlay"]["records"][0]["proposals"][2]["corridor_intersections"][
            "unique_intersection_area_m2"
        ]
        == "3.338000"
    )


def test_identical_input_is_deterministic(ctx, example, rechecks):
    a = review_calibration(ctx, *example)
    assert json.dumps(a, sort_keys=True) == json.dumps(rechecks[C_KEY], sort_keys=True)


@pytest.mark.parametrize("record", ["P01", "P02"])
def test_r12_wrong_portal_or_cross_record_file_rejected(source_files, record):
    files = dict(source_files)
    name = next(
        n
        for n in files
        if n.endswith("candidate.json")
        and ("proposal-01" if record == "P01" else "proposal-02") in n
    )
    obj = json.loads(files[name])
    obj["engineering_validation"]["portals"][0]["clear_width_m"] = "1.4"
    files[name] = json.dumps(obj).encode()
    with pytest.raises(ValueError, match="MISMATCH"):
        calibration_context(files)


def test_untrusted_document_cannot_escape_source_directory(tmp_path):
    packet = dict(source_documents={"d": dict(file_name="../private-data")})
    with pytest.raises(ValueError, match="OUTSIDE_INPUT_ROOT"):
        read_proposed_documents(packet, tmp_path)


def test_preserved_manifest_cannot_be_rewritten(source_files):
    files = dict(source_files)
    name = f"{R12}/source-manifest.json"
    files[name] += b" "
    with pytest.raises(ValueError, match="MISMATCH"):
        calibration_context(files)


def test_editor_is_unreviewed_and_plot_evidence_is_explicit(ctx, template, rechecks):
    result = rechecks[C_KEY]
    data = dict(
        reports={"20-20": dict(label="未批准", review=result)},
        confirmation_items=["真实柜型 INPUT_REQUIRED"],
    )
    page = review_page(
        data,
        template,
        {
            k: dict(
                group=s.group,
                label=s.label,
                unit=s.unit,
                choices=list(s.choices),
                minimum=s.minimum,
            )
            for k, s in FIELDS.items()
        },
    )
    assert (
        "crypto.subtle.digest" in page
        and "导出待审输入JSON" in page
        and "input_fingerprint" in page
    )
    assert "输入已变更" in page and "SUPPLIER_UNREVIEWED" in page
    assert "fetch(" not in page and "localStorage" not in page
    for c in result["cases"]:
        for svg in (calibration_plan(c), cabinet_elevation(c), cabinet_door_plan(c)):
            ET.fromstring(svg)
        assert "净宽不等于" not in cabinet_elevation(c) or "INPUT_REQUIRED" in cabinet_elevation(c)
        assert "净格宽" in cabinet_elevation(c)


def test_new_unit_module_is_in_real_fast_ci_list():
    workflow = (ROOT / ".github/workflows/ci-fast.yml").read_text()
    assert "tests/unit/test_v222_r11_r13_physical_calibration.py" in workflow
    assert "tests/unit/test_v222_r11_r12_site_impact.py" in workflow
    assert "tests/unit/test_v222_r11_r10_reverse_sizing.py" in workflow


def test_complete_export_has_fresh_case_files_schema_and_source_hashes(tmp_path, template):
    from build_r11_r13_physical_calibration import packet_schema, write_review

    output = tmp_path / "review"
    result = write_review(ROOT, output)
    assert set(result["reports"]) == {"actual", "20-20", "30-40"}
    assert result["actual_calibration"] == "INPUT_REQUIRED"
    assert packet_schema()["properties"]["parameters"]["required"] == list(FIELDS)
    assert json.loads((output / "physical-input-template.json").read_text()) == template
    for group in ("actual", "20-20", "30-40"):
        for case in ("C", "3850"):
            for kind in ("plan", "elevation", "door"):
                ET.parse(output / (group + "-" + case + "-" + kind + ".svg"))
    manifest = json.loads((output / "source-manifest.json").read_text())
    assert all(
        hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
        for name, digest in manifest["derived_files"].items()
    )
    assert "3.338㎡" in (output / "calibration-report.md").read_text()
    with pytest.raises(ValueError, match="FRESH_R13_OUTPUT"):
        write_review(ROOT, output)


@pytest.mark.parametrize("api", ["solve", "Solve"])
def test_parent_native_forbidden(api):
    with pytest.raises(RuntimeError, match="NATIVE_FORBIDDEN"):
        getattr(cp_model.CpSolver(), api)(cp_model.CpModel())


@pytest.mark.parametrize("api", ["solve", "Solve"])
def test_child_native_forbidden_with_original_startup_guard(tmp_path, api):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "backend/tests/functional_native_guard")
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(tmp_path)
    code = (
        "from ortools.sat.python import cp_model\ntry:\n cp_model.CpSolver()."
        + api
        + "(cp_model.CpModel())\nexcept RuntimeError as e:\n"
        " assert 'NATIVE_FORBIDDEN' in str(e)\nelse:\n"
        " raise AssertionError('Native was not blocked')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    logs = [
        json.loads(line) for p in tmp_path.glob("*.jsonl") for line in p.read_text().splitlines()
    ]
    assert any(r["kind"] == "NATIVE_REQUEST_BLOCKED" for r in logs)
