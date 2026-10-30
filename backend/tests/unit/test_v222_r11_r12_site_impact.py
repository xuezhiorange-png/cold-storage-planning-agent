"""Archived P01/P02 overlays, exact positive intersections and fail-closed inputs."""

import copy
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.functional_site_impact_review import (
    R11_PATH,
    _footprint,
    _overlay_status,
    _scene,
    _site_impact,
    review_functional_site_impact,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    HISTORICAL,
    HISTORICAL_FILES,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_fit import area
from cold_storage.modules.layout.domain.functional_site_impact import (
    contact_report,
    expansion_bands,
    orthogonal_tiles,
    positive_intersection,
    rectangular_union_area,
)
from cold_storage.modules.layout.domain.site_geometry import normalize_polygon
from cold_storage.modules.layout.infrastructure.functional_site_impact_evidence import (
    read_site_impact_evidence,
)
from cold_storage.modules.layout.infrastructure.functional_site_impact_page import (
    overlay_svg,
    review_page,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def forbid_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R11_SITE_IMPACT_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def files():
    return read_site_impact_evidence(ROOT)


@pytest.fixture(scope="module")
def candidates(files):
    return {
        key: json.loads(files[f"{HISTORICAL}/{p}"])
        for key, p in zip(("P01", "P02"), HISTORICAL_FILES[2:], strict=True)
    }


def run(files, candidates, scope=None):
    c = candidates["P01"]
    return review_functional_site_impact(
        files,
        project_scope_id=scope or c["source_zone_plan_hash"] + ":" + c["source_p1_handoff_hash"],
        candidate_records=candidates,
    )


@pytest.fixture(scope="module")
def result(files, candidates):
    return run(files, candidates)


@pytest.mark.parametrize("record", [0, 1])
def test_b_corridor_intersection_is_recomputed_from_each_archive(result, candidates, record):
    source = candidates[result["records"][record]["record"]]
    envelope = source["engineering_validation"]["corridors"][0]["envelope"][2]
    polygon = normalize_polygon(envelope, allow_numeric_string=True)
    box = orthogonal_tiles(polygon)[0]
    proposal = result["records"][record]["proposals"][2]
    east = next(b for b in proposal["expansion_bands"] if b["side"] == "EAST")
    overlap = positive_intersection(tuple(east["bounds_mm"]), box)
    assert overlap == (41031, 24275, 42700, 26275)
    report = proposal["corridor_intersections"]
    assert report["contacts"][0]["intersection_rectangles_mm"] == [list(overlap)]
    assert report["unique_intersection_area_mm2"] == area(overlap) == 3338000
    assert report["unique_intersection_area_m2"] == "3.338000"
    assert report["contacts"][0]["object_bounds_mm"] == [list(box)]
    assert f"proposal-0{record + 1}" in report["contacts"][0]["reference"]


@pytest.mark.parametrize("record", [0, 1])
def test_b_also_overlaps_archived_no_build_zone_without_double_counting(result, record):
    site = result["records"][record]["proposals"][2]["site"]
    contact = site["obstacles"]["no_build_zones"]["contacts"][0]
    assert contact["intersection_rectangles_mm"] == [[41718, 27000, 42700, 28000]]
    assert contact["intersection_area_mm2"] == 982000
    assert site["obstacles"]["hard_obstacles"]["unique_intersection_area_mm2"] == 982000
    assert site["unique_hard_and_no_build_intersection_area_mm2"] == 982000


@pytest.mark.parametrize("record", [0, 1])
@pytest.mark.parametrize("scheme", [0, 1])
def test_c_and_3850_north_bands_are_checked_independently(result, record, scheme):
    p = result["records"][record]["proposals"][scheme]
    assert p["expansion_bands"] == [
        dict(
            side="NORTH",
            bounds_mm=[14700, 26900, 41031, (27200, 27500)[scheme]],
            area_mm2=(7899300, 15798600)[scheme],
            area_m2=("7.899300", "15.798600")[scheme],
        )
    ]
    for report in [p["zone_intersections"], p["corridor_intersections"]]:
        assert report["status"] == "NO_POSITIVE_INTERSECTION_IN_CHECKED_INPUTS"
        assert report["unique_intersection_area_mm2"] == 0
    assert p["site"]["unique_hard_and_no_build_intersection_area_mm2"] == 0
    assert p["whole_factory_acceptance"] == "NOT_EVALUATED"


def test_independent_records_keep_actual_rotations_but_one_room_area(result):
    a, b = result["records"]
    assert a["candidate_hash"] != b["candidate_hash"]
    coating = [next(z for z in r["zones"] if z["id"] == "coating_room") for r in (a, b)]
    assert coating[0]["original_row"]["rotation_deg"] == 90
    assert coating[1]["original_row"]["rotation_deg"] == 0
    assert coating[0]["bounds_mm"] == coating[1]["bounds_mm"]
    assert result["physical_room_count"] == 1
    assert result["independently_checked_records"] == 2
    assert [p["additional_room_area_mm2"] for p in a["proposals"]] == [7899300, 15798600, 36224250]
    assert all(len(r["zones"]) == 12 for r in result["records"])


@pytest.mark.parametrize("record", [0, 1])
def test_b_original_access_is_affected_but_sorting_portal_is_not_relocated(result, record):
    access = result["records"][record]["proposals"][2]["access"]
    entrance = next(x for x in access if "main_entrance" in x["requirement_identity"])
    assert entrance["status"] == "ARCHIVED_CORRIDOR_INTERSECTION_DETECTED"
    assert entrance["corridor_redesign_required"]
    assert entrance["original_portal_segment_mm"] == [[41031, 24525], [41031, 26025]]
    assert entrance["hypothetical_portal_segment_mm"] == [[42700, 24525], [42700, 26025]]
    assert entrance["mapped_portal_identity"].startswith("hypothetical:")
    assert not entrance["archived_portal_still_on_counterfactual_boundary"]
    sorting = next(x for x in access if "sorting_packaging_room" in x["requirement_identity"])
    assert sorting["original_portal_segment_mm"] == [[27115, 23650], [28615, 23650]]
    assert sorting["hypothetical_portal_segment_mm"] == sorting["original_portal_segment_mm"]
    assert sorting["clear_width_mm"] == entrance["clear_width_mm"] == 1500
    assert not sorting["portal_mapped"]
    assert all(not x["full_access_revalidated"] for x in access)


def test_exact_union_metrics_are_diagnostic_not_a_quality_promotion(result):
    for r in result["records"]:
        for i, p in enumerate(r["proposals"]):
            fp = p["footprint"]
            assert fp["archived_union_reproduced"]
            assert fp["archived"]["area_mm2"] == 2345749990
            assert fp["delta"]["area_mm2"] == [7899300, 15798600, 32886250][i]
            assert fp["topology"]["connected_component_count"] == 1
            assert fp["topology"]["hole_count"] == 0
            assert p["whole_factory_acceptance"] == p["engineering_approval"] == "NOT_EVALUATED"
            assert all(x["positive_shared_edge"] for x in p["must_adjacencies"])
        b = r["proposals"][2]
        assert b["additional_room_area_mm2"] - b["footprint"]["delta"]["area_mm2"] == 3338000
        assert b["footprint"]["delta"]["perimeter_mm"] < 0


def test_truck_missing_envelope_is_unknown_not_clear(result):
    assert "TRUCK_AND_UNARCHIVED_OCCUPANCY_NOT_EVALUATED" in result["warnings"]
    assert result["calculation_basis"]["coefficients"] == []
    for record in result["records"]:
        for p in record["proposals"]:
            truck = p["truck_envelope_impact"]
            assert truck["archived_envelope_count"] == 0
            assert truck["status"] == "NOT_EVALUATED"
            assert "BLOCKED" in truck["archived_status"]
            assert p["unarchived_occupancy"]["status"] == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "field",
    [
        "source_site_geometry_hash",
        "source_zone_plan_hash",
        "source_p1_handoff_hash",
        "canonical_result_hash",
    ],
)
def test_wrong_source_or_project_candidate_rejected(files, candidates, field):
    bad = copy.deepcopy(candidates)
    bad["P02"][field] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        run(files, bad)


def test_wrong_scope_rejected(files, candidates):
    with pytest.raises(ValueError, match="PROJECT_SCOPE_MISMATCH"):
        run(files, candidates, scope="DIFFERENT_PROJECT")


def test_p01_p02_record_swap_rejected(files, candidates):
    with pytest.raises(ValueError, match="CANDIDATE_RECORD_MISMATCH"):
        run(files, {"P01": candidates["P02"], "P02": candidates["P01"]})


@pytest.mark.parametrize("mutation", ["portal", "corridor", "footprint", "zone"])
def test_changed_or_missing_archived_geometry_rejected(files, candidates, mutation):
    bad = copy.deepcopy(candidates)
    ev = bad["P01"]["engineering_validation"]
    if mutation == "portal":
        next(p for p in ev["portals"] if p["access_ref"] == "changing_room")["segment"]["start"][
            "x"
        ] = "999"
    elif mutation == "corridor":
        ev.pop("corridors")
    elif mutation == "footprint":
        ev["building_footprint"]["gross_area_m2"] = "999"
    else:
        ev["zones"].pop()
    with pytest.raises(ValueError):
        run(files, bad)


@pytest.mark.parametrize(
    "name",
    [
        f"{R11_PATH}/advisories.json",
        f"{R11_PATH}/source-manifest.json",
        f"{HISTORICAL}/server-authorities.json",
    ],
)
def test_forged_evidence_or_missing_file_never_produces_applicability(files, candidates, name):
    bad = dict(files)
    bad[name] = b"{}"
    with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
        run(bad, candidates)
    bad.pop(name)
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        run(bad, candidates)


def test_rehashed_advisory_status_cannot_become_approval(files, candidates):
    bad = dict(files)
    payload = json.loads(bad[f"{R11_PATH}/advisories.json"])
    payload[0]["approval_boundary"]["whole_factory_fit"] = "PASS"
    payload[0].pop("advisory_hash")
    payload[0]["advisory_hash"] = canonical_hash(payload[0])
    bad[f"{R11_PATH}/advisories.json"] = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
        run(bad, candidates)


def test_cross_record_evidence_cannot_replace_archived_file(files, candidates):
    bad = dict(files)
    bad[f"{HISTORICAL}/{HISTORICAL_FILES[2]}"] = files[f"{HISTORICAL}/{HISTORICAL_FILES[3]}"]
    with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
        run(bad, candidates)


def test_owner_template_contains_no_default_confirmed_parameter(result):
    template = result["owner_parameter_template"]
    assert template["state"] == "UNREVIEWED_TEMPLATE_NOT_AUTHORITY"
    assert all(
        v["value"] is None and v["status"] == "INPUT_REQUIRED"
        for v in template["dimensions_and_operation"].values()
    )
    assert template["reviewed_inputs"] == result["owner_confirmed_inputs"]


def test_missing_components_return_not_evaluated_instead_of_empty_clearance(files, candidates):
    c = copy.deepcopy(candidates["P01"])
    site = json.loads(files[f"{HISTORICAL}/server-authorities.json"])["site"]
    c["engineering_validation"]["corridors"] = []
    scene = _scene(c, site, "SYNTHETIC_MISSING_COMPONENT_DIAGNOSTIC")
    assert scene["corridors"] is None
    assert contact_report([(0, 0, 10, 10)], scene["corridors"])["status"] == "NOT_EVALUATED"
    assert _footprint(scene, scene["zones"])["status"] == "NOT_EVALUATED"
    result = _site_impact([(0, 0, 10, 10)], (0, 0, 10, 10), {})
    assert all(v["status"] == "NOT_EVALUATED" for v in result["boundaries"].values())
    assert all(v["status"] == "NOT_EVALUATED" for v in result["obstacles"].values())
    assert result["unique_hard_and_no_build_intersection_area_mm2"] is None
    status = _overlay_status(
        dict(
            zone_intersections=contact_report([], []),
            corridor_intersections=contact_report([], None),
            site=result,
        )
    )
    assert status == "NOT_EVALUATED"


def test_known_empty_is_distinct_from_missing_and_boundary_touch_is_not_overlap():
    assert (
        contact_report([(0, 0, 10, 10)], [])["status"]
        == "NO_POSITIVE_INTERSECTION_IN_CHECKED_INPUTS"
    )
    assert contact_report([(0, 0, 10, 10)], None)["status"] == "NOT_EVALUATED"
    assert positive_intersection((0, 0, 10, 10), (10, 0, 20, 10)) is None
    assert positive_intersection((0, 0, 10, 10), (9, 0, 20, 10)) == (9, 0, 10, 10)


def test_overlapping_envelopes_do_not_double_count_area():
    assert rectangular_union_area([(0, 0, 10, 10), (0, 0, 10, 10), (5, 0, 15, 10)]) == 150


def test_area_depends_on_actual_coordinates_not_known_b_constant():
    assert area(positive_intersection((10, 0, 14, 8), (10, 2, 25, 6))) == 16
    assert area(positive_intersection((10, 0, 15, 8), (10, 2, 25, 6))) == 20


def test_nonorthogonal_area_is_not_silently_approximated():
    with pytest.raises(ValueError, match="ORTHOGONAL_AREA_EVIDENCE_REQUIRED"):
        orthogonal_tiles(((0, 0), (10, 0), (5, 10)))


def test_expansion_bands_are_disjoint_and_anchored():
    bands = expansion_bands((1, 1, 5, 5), (1, 1, 8, 9))
    boxes = [tuple(v["bounds_mm"]) for v in bands]
    assert sum(area(b) for b in boxes) == rectangular_union_area(boxes) == 40
    with pytest.raises(ValueError, match="WEST_SOUTH_ANCHORED"):
        expansion_bands((1, 1, 5, 5), (0, 1, 8, 9))


def test_sources_and_candidate_bytes_unchanged_with_deterministic_output(files, candidates, result):
    original = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
    old = copy.deepcopy(candidates)
    returned = run(files, candidates)
    assert returned == result
    returned["records"][0]["zones"][0]["original_row"]["x"] = "999"
    returned["records"][0]["archived_portals"][0]["clear_width_m"] = "999"
    returned["records"][0]["proposals"][0]["access"][0]["original_centerline"][0]["x"] = "999"
    assert candidates == old
    assert original == {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}


def test_review_has_no_write_port(files, candidates, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("REVIEW_MUST_NOT_WRITE")

    for name in ("write_text", "write_bytes", "mkdir", "unlink"):
        monkeypatch.setattr(Path, name, fail)
    assert run(files, candidates)["final_factory_applicability"] == "NOT_EVALUATED"


def test_confirmed_facts_and_unapproved_conditions_remain_separate(result):
    assert result["owner_confirmed_inputs"]["BENCH_COUNT"]["value"] == 0
    assert result["owner_confirmed_inputs"]["USERS_PER_SHIFT"]["value"] == 53
    assert (
        result["owner_confirmed_inputs"]["CHANGING_LOCATION"]["value"] == "PERSONAL_CABINET_FRONT"
    )
    assert all(v["status"] == "INPUT_REQUIRED" for v in result["owner_confirmation_checklist"])
    c, s, b = result["records"][0]["proposals"]
    assert [p["conditions"]["parameters"]["finish_mm"] for p in (c, s, b)] == [20, 30, 20]


def test_both_native_apis_forbidden():
    for name in ("solve", "Solve"):
        with pytest.raises(RuntimeError, match="NATIVE_FORBIDDEN"):
            getattr(cp_model.CpSolver(), name)(None)


def test_b_svg_matches_source_rectangles_and_actual_intersections(result):
    record = result["records"][0]
    svg = ET.fromstring(overlay_svg(record, 2))
    rectangles = svg.findall(".//{http://www.w3.org/2000/svg}rect")
    rooms = [r for r in rectangles if r.get("data-object-id") in {z["id"] for z in record["zones"]}]
    assert len(rooms) == 12
    h5 = next(r for r in rooms if r.get("data-object-id") == "changing_room")
    assert [int(h5.get(k)) for k in ("x", "y", "width", "height")] == [14700, -26900, 26331, 3250]
    hits = {
        tuple(int(r.get(k)) for k in ("x", "y", "width", "height"))
        for r in rectangles
        if r.get("data-conflict")
    }
    assert hits == {(41031, -26275, 1669, 2000), (41718, -28000, 982, 1000)}


def test_all_full_plans_have_the_same_mm_viewport(result):
    assert (
        len(
            {
                ET.fromstring(overlay_svg(r, i)).get("viewBox")
                for r in result["records"]
                for i in range(3)
            }
        )
        == 1
    )


def test_page_has_mobile_viewport_review_controls_and_no_approval_action(result):
    page = review_page(result)
    assert 'name="viewport"' in page and 'id="record"' in page and 'id="scheme"' in page
    assert 'id="in"' in page and 'id="detail"' in page
    assert "fetch(" not in page and "localStorage" not in page and "<form" not in page
    assert "owner-input-template.json" in page


def test_new_file_is_in_actual_fast_ci_collection():
    workflow = (ROOT / ".github/workflows/ci-fast.yml").read_text()
    assert workflow.count("tests/unit/test_v222_r11_r12_site_impact.py") == 1
    assert "tests/unit/test_v222_r11_r11_sizing_advisory.py" in workflow
    assert "--junitxml=../artifacts/ci-fast/backend-regression.xml" in workflow
