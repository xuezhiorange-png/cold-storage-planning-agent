"""Real archived evidence only: source matching cannot confer engineering approval."""

import copy
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.functional_sizing_handoff import (
    preview_functional_sizing_handoff,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    ANCHORS,
    HISTORICAL,
    HISTORICAL_FILES,
    R10,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_sizing_advisory import (
    APPROVAL_BOUNDARY,
    FunctionalRoomSizingAdvisoryV1,
    advisory_json_schema,
)
from cold_storage.modules.layout.infrastructure.functional_sizing_evidence import (
    read_functional_sizing_evidence,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def forbid_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R11_ADVISORY_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def evidence():
    return read_functional_sizing_evidence(ROOT)


@pytest.fixture(scope="module")
def candidates(evidence):
    return [json.loads(evidence[f"{HISTORICAL}/{path}"]) for path in HISTORICAL_FILES[2:]]


def run(evidence, candidates, **kwargs):
    scope = candidates[0]["source_zone_plan_hash"] + ":" + candidates[0]["source_p1_handoff_hash"]
    return preview_functional_sizing_handoff(
        evidence, project_scope_id=scope, layout_candidates=candidates, **kwargs
    )


@pytest.fixture(scope="module")
def preview(evidence, candidates):
    return run(evidence, candidates)


@pytest.mark.parametrize(
    "i,length,width,area,added,finish,install,margin",
    [
        (0, 26331, 3550, "93.475050", "7.899300", 20, 20, 50),
        (1, 26331, 3850, "101.374350", "15.798600", 30, 40, 70),
        (2, 28000, 4350, "121.800000", "36.224250", 20, 20, 150),
    ],
)
def test_real_advisory_dimensions_and_own_conditions(
    preview, i, length, width, area, added, finish, install, margin
):
    advice = preview["advisories"][i]
    room = advice["advised_room"]
    assert (room["length_mm"], room["width_mm"], room["area_m2"], room["additional_area_m2"]) == (
        length,
        width,
        area,
        added,
    )
    assert advice["conditions"]["parameters"]["finish_mm"] == finish
    assert advice["conditions"]["parameters"]["installation_gap_mm"] == install
    assert advice["margins"]["minimum_mm"] == margin
    assert advice["approval_boundary"] == APPROVAL_BOUNDARY
    assert advice["p1_requirement"]["required_area_mm2"] == 40000000


def test_p1_is_existing_immutable_reference_not_new_authority(preview):
    assert preview["p1_required_area_m2"] == "40.000000"
    for a in preview["advisories"]:
        p = a["p1_requirement"]
        assert (
            p["dimension_authority_ref"]["source_p1_handoff_hash"]
            == a["project"]["source_p1_handoff_hash"]
        )
        assert p["original_authority"]["p2_may_change_required_area"] is False
        assert p["immutable_reference"].startswith("sha256:") and p["modifies_authority"] is False
        assert "sealed-r10:server-authorities.json" in p["original_sealed_reference"]["reference"]


def test_two_distinct_candidate_hashes_are_one_physical_room(evidence, candidates, preview):
    assert candidates[0]["canonical_result_hash"] != candidates[1]["canonical_result_hash"]
    first, second = run(evidence, candidates[:1]), run(evidence, candidates[1:])
    assert first["physical_room_id"] == second["physical_room_id"] == preview["physical_room_id"]
    assert (
        preview["physical_room_count"] == 1 and preview["original_room"]["area_m2"] == "85.575750"
    )
    assert len(preview["advisories"][0]["physical_room"]["aliases"]) == 2


def test_duplicate_record_rejected_not_silently_counted(evidence, candidates):
    with pytest.raises(ValueError, match="DUPLICATE_CANDIDATE"):
        run(evidence, [candidates[0], candidates[0]])


@pytest.mark.parametrize(
    "field",
    [
        "source_p1_handoff_hash",
        "source_zone_plan_hash",
        "source_site_geometry_hash",
        "source_composition_hash",
        "canonical_result_hash",
    ],
)
def test_other_candidate_or_source_cannot_reuse_advice(evidence, candidates, field):
    changed = copy.deepcopy(candidates)
    changed[0][field] = "sha256:" + "0" * 64
    scope = candidates[0]["source_zone_plan_hash"] + ":" + candidates[0]["source_p1_handoff_hash"]
    with pytest.raises(ValueError, match="LAYOUT_SOURCE_MISMATCH"):
        preview_functional_sizing_handoff(
            evidence, project_scope_id=scope, layout_candidates=changed
        )


@pytest.mark.parametrize("kind", ["project_scope_id", "project_input_identity"])
def test_other_project_scope_or_fixture_identity_rejected(evidence, candidates, kind):
    kwargs = dict(
        project_scope_id=candidates[0]["source_zone_plan_hash"]
        + ":"
        + candidates[0]["source_p1_handoff_hash"]
    )
    kwargs[kind] = "OTHER_PROJECT"
    with pytest.raises(ValueError, match="PROJECT_SCOPE_MISMATCH"):
        preview_functional_sizing_handoff(evidence, layout_candidates=candidates, **kwargs)


@pytest.mark.parametrize("kind", ["rectangle", "portal", "acceptance"])
def test_changed_historical_geometry_and_acceptance_rejected(evidence, candidates, kind):
    changed = copy.deepcopy(candidates)
    if kind == "rectangle":
        changed[0]["engineering_validation"]["zones"][0]["x"] = "999"
    elif kind == "portal":
        changed[0]["engineering_validation"]["portals"][0]["clear_width_m"] = "9"
    else:
        changed[0]["stage_a_engineering_accepted"] = False
    with pytest.raises(ValueError, match="LAYOUT_SOURCE_MISMATCH"):
        run(evidence, changed)


@pytest.mark.parametrize(
    "path",
    [
        f"{R10}/selected-evidence.json.gz",
        f"{R10}/evaluation-grid.jsonl.gz",
        f"{HISTORICAL}/server-authorities.json",
        f"{HISTORICAL}/{HISTORICAL_FILES[2]}",
        f"{HISTORICAL}/r10-remote-ci/backend-regression.xml",
        "docs/tasks/V2_2_2-r11-r8-reviewed-cabinet-front-facts.txt",
        "docs/previews/v2.2.2/r11-r9-h5-space-relayout-r1/execution-boundary-exception.md",
    ],
)
def test_missing_real_source_fails_closed(evidence, candidates, path):
    altered = dict(evidence)
    altered.pop(path)
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        run(altered, candidates)


def test_altered_p1_source_and_rehashed_manifest_still_rejected(evidence, candidates):
    altered = dict(evidence)
    name = next(iter(ANCHORS))
    manifest = json.loads(altered[name])
    manifest["derived_files"]["selected-evidence.json.gz"] = "0" * 64
    altered[name] = json.dumps(manifest).encode()
    with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
        run(altered, candidates)


@pytest.mark.parametrize(
    "kind",
    ["conditions", "approval", "area", "margin", "source", "scope", "room_type", "owner_source"],
)
def test_modified_advisory_and_recomputed_hash_never_promotes(evidence, candidates, preview, kind):
    p = copy.deepcopy(preview["advisories"][0])
    p.pop("advisory_hash")
    if kind == "conditions":
        p["conditions"]["classification"] = "OWNER_CONFIRMED"
    elif kind == "approval":
        p["approval_boundary"]["engineering_approval"] = "PASS"
    elif kind == "area":
        p["advised_room"]["area_mm2"] = 1
    elif kind == "margin":
        p["margins"]["minimum_mm"] = 9999
    elif kind == "source":
        p["functional_evidence"]["witness_sha256"] = "0" * 64
    elif kind == "scope":
        p["project"]["scope_id"] = "other"
    elif kind == "room_type":
        p["physical_room"]["room_code"] = "office"
    else:
        p["project"]["owner_confirmed_inputs"]["USERS_PER_SHIFT"]["value"] = 10
    p["advisory_hash"] = canonical_hash(p)
    with pytest.raises(ValueError):
        run(evidence, candidates, advisory_payloads=[p])


def test_advisory_roundtrip_and_selection_require_current_evidence(evidence, candidates, preview):
    a = FunctionalRoomSizingAdvisoryV1.from_dict(preview["advisories"][1])
    assert a.to_dict() == preview["advisories"][1]
    result = run(evidence, candidates, advisory_payloads=[a.to_dict()])
    assert result["advisories"] == [a.to_dict()]
    with pytest.raises(FrozenInstanceError):
        a.payload_json = "{}"
    mutable = a.to_dict()
    mutable["advised_room"]["width_mm"] = 1
    assert a.to_dict()["advised_room"]["width_mm"] == 3850


@pytest.mark.parametrize("room", ["office", "coating_room", "unknown_room"])
def test_other_functional_rooms_are_not_implicitly_supported(evidence, candidates, room):
    result = run(evidence, candidates, room_code=room)
    assert result["status"] == "FUNCTIONAL_ADAPTER_REQUIRED" and result["advisories"] == []


def test_conditions_grouping_is_not_optimality_or_safety_claim(preview):
    c, s, b = preview["advisories"]
    assert c["comparison_scope"]["conditions_hash"] == b["comparison_scope"]["conditions_hash"]
    assert c["comparison_scope"]["conditions_hash"] != s["comparison_scope"]["conditions_hash"]
    assert not s["margins"]["template_target_met"] and s["margins"]["minimum_mm"] == 70
    assert all(a["comparison_scope"]["ranking"] == "NOT_EVALUATED" for a in preview["advisories"])


@pytest.mark.parametrize(
    "i,dx,dy,moved", [(0, 0, 300, False), (1, 0, 600, False), (2, 1669, 1100, True)]
)
def test_external_impacts_remain_unvalidated(preview, i, dx, dy, moved):
    impact = preview["advisories"][i]["external_impact"]
    assert (
        impact["length_increase_mm"],
        impact["width_increase_mm"],
        impact["any_portal_moved"],
    ) == (dx, dy, moved)
    assert impact["original_factory_can_accommodate_expansion"] == "NOT_EVALUATED"
    for key in ["site", "footprint", "external_access", "neighboring_rooms_and_process"]:
        assert impact[key].startswith("NOT_EVALUATED")


def test_both_shift_complete_proofs_and_real_margin_locations(preview):
    for a in preview["advisories"]:
        shifts = a["functional_evidence"]["shifts"]
        assert [s["completed_users"] for s in shifts] == [53, 53]
        assert all(
            len(set(s["completed_person_ids"])) == 53 and s["event_count"] > 0 for s in shifts
        )
        assert a["margins"]["minimum"]["bounds_mm"]
    assert preview["advisories"][1]["margins"]["minimum"]["location"] == "HOME-41"


def test_confirmed_facts_are_not_reintroduced_as_unknown(preview):
    facts = preview["owner_confirmed_inputs"]
    assert facts["BENCH_COUNT"]["value"] == 0
    assert facts["CHANGING_LOCATION"]["value"] == "PERSONAL_CABINET_FRONT"
    assert facts["USERS_PER_SHIFT"]["value"] == 53
    assert facts["CABINET_STRUCTURE"]["value"] == "FIVE_TIER_FIVE_DOOR"
    assert {r["id"] for r in preview["owner_confirmation_checklist"]} == {
        "CABINET_MODEL",
        "CLOTHING_SEPARATION",
        "CABINET_DOORS",
        "FINISHED_DIMENSIONS",
        "HUMAN_ENVELOPES",
        "OPERATING_PROTOCOL",
        "HYGIENE_AND_ROOM_DOORS",
        "OPERATION_TIMES",
        "EXTERNAL_EXPANSION",
    }


def test_preview_is_deterministic_and_does_not_change_inputs(evidence, candidates):
    before = {p: hashlib.sha256(b).hexdigest() for p, b in evidence.items()}
    c = copy.deepcopy(candidates)
    first = run(evidence, candidates)
    second = run(evidence, candidates)
    assert first == second and candidates == c
    assert before == {p: hashlib.sha256(b).hexdigest() for p, b in evidence.items()}


def test_precheck_has_no_filesystem_write_port(evidence, candidates, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("PRECHECK_MUST_NOT_WRITE")

    for name in ["write_text", "write_bytes", "mkdir", "unlink"]:
        monkeypatch.setattr(Path, name, fail)
    result = run(evidence, candidates)
    assert result["writes_production"] is False and result["native_solves"] == 0


def test_current_parent_native_apis_are_disabled():
    for name in ("solve", "Solve"):
        with pytest.raises(RuntimeError, match="NATIVE_FORBIDDEN"):
            getattr(cp_model.CpSolver(), name)(None)


def test_schema_does_not_allow_engineering_approval_labels(preview):
    schema = advisory_json_schema()
    assert schema["properties"]["approval_boundary"]["const"] == APPROVAL_BOUNDARY
    assert set(schema["required"]) == set(preview["advisories"][0])
    changed = copy.deepcopy(preview["advisories"][0])
    changed["approved"] = True
    with pytest.raises(ValueError, match="SCHEMA_UNSUPPORTED"):
        FunctionalRoomSizingAdvisoryV1.from_dict(changed)


def test_contract_schema_is_stable_across_python_hash_seeds():
    script = (
        "import json; from cold_storage.modules.layout.domain.functional_sizing_advisory "
        "import advisory_json_schema; print(json.dumps(advisory_json_schema()))"
    )
    outputs = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        env["PYTHONPATH"] = str(ROOT / "backend/src") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_approval_and_evidence_anchors_are_immutable():
    with pytest.raises(TypeError):
        APPROVAL_BOUNDARY["engineering_approval"] = "PASS"
    with pytest.raises(TypeError):
        ANCHORS["other_manifest"] = "0" * 64
