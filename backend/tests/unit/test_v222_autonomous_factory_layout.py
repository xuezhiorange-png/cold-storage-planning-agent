"""Non-native real-input generation, provenance and geometry regressions."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.autonomous_factory_layout import (
    bind_autonomous_input,
    generate_autonomous_layouts,
    structural_signature,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "docs/previews/v2.2.2/autonomous-factory-layout-v1/inputs/project-input.json"


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    return json.loads(INPUT.read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def result(project: dict[str, Any]) -> dict[str, Any]:
    return generate_autonomous_layouts(project)


def test_complete_twelve_roles_are_actually_generated(result: dict[str, Any]) -> None:
    assert result["candidate_count"] >= 1
    for c in result["candidates"]:
        assert {z["zone_code"] for z in c["rooms"]} == set(ZONE_CODES)
        assert len(c["rooms"]) == 12
        assert c["room_non_overlap_and_MUST"]["geometry_passed"]
        assert c["legacy_room_obstacle_oracle"]["status"] == "PASS"


def test_fixed_p1_dimensions_and_area_provenance_unchanged(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    ctx = bind_autonomous_input(project)
    for c in result["candidates"]:
        for z in c["rooms"]:
            a = ctx.binding.dimension_authorities[z["zone_code"]]
            assert z["area_requirement"] == a["area_requirement"]
            if a["dimension_mode"] != "FLEXIBLE_RECTANGLE":
                assert Decimal(z["authority_width_m"]) == Decimal(a["geometry"]["width_m"])
                assert Decimal(z["authority_depth_m"]) == Decimal(a["geometry"]["depth_m"])
            else:
                assert Decimal(z["area_m2"]) >= Decimal(a["required_area_m2"])


def test_rooms_inside_actual_wall_faces_not_axis_bbox(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    a = project["building"]["clear_building_bbox_mm"]
    assert a[0] > 0 and a[2] < 108000
    for c in result["candidates"]:
        for z in c["rooms"]:
            b = z["bbox_mm"]
            assert a[0] <= b[0] < b[2] <= a[2]
            assert a[1] <= b[1] < b[3] <= a[3]


def test_retained_columns_report_net_area_and_cannot_be_cut(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    any_column = False
    for c in result["candidates"]:
        for z in c["rooms"]:
            assert Decimal(z["floor_minus_columns_m2"]) == Decimal(z["area_m2"]) - Decimal(
                z["column_area_m2"]
            )
            for col in project["building"]["columns"]:
                if positive_intersection(z["bbox_mm"], col["bbox_mm"]):
                    any_column = True
                    a, b = z["bbox_mm"], col["bbox_mm"]
                    assert a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
    assert any_column


def test_equipment_coordinates_are_inside_rooms_and_do_not_overlap(result: dict[str, Any]) -> None:
    for c in result["candidates"]:
        rooms = {z["zone_code"]: z["bbox_mm"] for z in c["rooms"]}
        previous = []
        for q in c["equipment"]["items"]:
            a, b = rooms[q["room"]], q["bbox_mm"]
            assert a[0] <= b[0] < b[2] <= a[2]
            assert a[1] <= b[1] < b[3] <= a[3]
            assert not any(positive_intersection(b, other["bbox_mm"]) for other in previous)
            assert not any(
                positive_intersection(b, col["bbox_mm"])
                for col in c["original_building"]["columns"]
            )
            previous.append(q)


def test_all_required_major_equipment_is_counted_even_if_rejected(result: dict[str, Any]) -> None:
    for c in result["candidates"]:
        all_items = c["equipment"]["items"] + c["equipment"]["rejected_items"]
        for kind, n in (("packing_line", 6), ("case_erector", 5), ("ten_door_locker", 11)):
            assert sum(q["kind"] == kind for q in all_items) == n
    assert any(
        c["equipment"]["placed_counts"].get("packing_line") == 6
        and c["equipment"]["placed_counts"].get("case_erector") == 5
        for c in result["candidates"]
    )


def test_rejected_equipment_and_operation_conflicts_not_turned_into_pass(
    result: dict[str, Any],
) -> None:
    for c in result["candidates"]:
        for item in c["equipment"]["rejected_items"]:
            assert item["conflicts"] and item["status"] == "PLACEMENT_REJECTED"
        assert c["equipment"]["full_equipment_engineering_pass"] is False
        for space in c["equipment"]["operating_spaces"]:
            assert (space["status"] == "GEOMETRIC_CONFLICT") == bool(space["conflicts"])


def test_no_truck_or_p2d_or_engineering_approval_is_invented(result: dict[str, Any]) -> None:
    for c in result["candidates"]:
        assert c["P2D_full_pass"] is False
        assert c["truck_route_validated"] is False
        assert c["engineering_approval"] == "NOT_EVALUATED"
        assert len(c["access_results"]) == 12
        assert any(
            q["flow_kind"] == "TRUCK" and q["status"].startswith("INPUT_REQUIRED")
            for q in c["access_results"]
        )


def test_source_result_hash_and_deterministic_repetition(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    assert result["source_input_hash"] == canonical_hash(project)
    assert generate_autonomous_layouts(project)["result_hash"] == result["result_hash"]


def test_change_storage_days_recalculates_authority_and_geometry(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    changed = copy.deepcopy(project)
    changed["business"]["finished_storage_days"] = 8
    other = generate_autonomous_layouts(changed)
    assert other["source_input_hash"] != result["source_input_hash"]
    assert other["p1_handoff_hash"] != result["p1_handoff_hash"]

    def zone(r):
        return next(
            z for z in r["zone_plan"]["result"]["zones"] if z["zone_code"] == "finished_goods_room"
        )

    assert zone(other)["required_area_m2"] != zone(result)["required_area_m2"]
    if other["candidates"]:

        def dimensions(body: dict[str, Any]) -> set[tuple[int, int]]:
            return {
                tuple(sorted((q["width_mm"], q["depth_mm"])))
                for c in body["candidates"]
                for q in c["rooms"]
                if q["zone_code"] == "finished_goods_room"
            }

        assert dimensions(other) != dimensions(result)
    else:
        assert (
            other["status"] == "BOUNDED_SEARCH_NO_CANDIDATE"
            and not other["global_infeasibility_proven"]
        )


def test_distinct_structure_not_just_translation_or_mirror(result: dict[str, Any]) -> None:
    signatures = [q["structural_signature"] for q in result["candidates"]]
    assert len(signatures) == len(set(signatures))
    q = PlacedRectangleV1("a", Decimal(1), Decimal(2), Decimal(3), Decimal(4))
    r = PlacedRectangleV1("b", Decimal(4), Decimal(2), Decimal(3), Decimal(4))
    q2 = PlacedRectangleV1("a", Decimal(100), Decimal(200), Decimal(3), Decimal(4))
    r2 = PlacedRectangleV1("b", Decimal(103), Decimal(200), Decimal(3), Decimal(4))
    assert structural_signature({"a": q, "b": r}) == structural_signature({"a": q2, "b": r2})


@pytest.mark.parametrize(
    "key", ["rooms", "initial_layout", "hints", "historical_coordinates", "equipment_positions"]
)
def test_historical_layout_payload_rejected(project: dict[str, Any], key: str) -> None:
    bad = copy.deepcopy(project)
    bad["building"][key] = []
    with pytest.raises(LayoutAuthorityError, match="HISTORICAL_LAYOUT_INPUT_FORBIDDEN"):
        bind_autonomous_input(bad)


def test_wrong_source_rejected(project: dict[str, Any]) -> None:
    bad = copy.deepcopy(project)
    bad["building"]["source_type"] = "V3_B1_LAYOUT_RESULT"
    with pytest.raises(LayoutAuthorityError, match="ORIGINAL_BUILDING_STRUCTURE_SOURCE_REQUIRED"):
        bind_autonomous_input(bad)


def test_axis_18_or_102m_regression_rejected(project: dict[str, Any]) -> None:
    bad = copy.deepcopy(project)
    bad["building"]["coordinate_mapping"]["axis_x_mm"] = list(range(0, 102001, 6000))
    with pytest.raises(LayoutAuthorityError, match="ARCHIVED_AXIS_MAPPING_MISMATCH"):
        bind_autonomous_input(bad)


def test_generation_works_without_historical_files(project: dict[str, Any], tmp_path: Path) -> None:
    source = tmp_path / "only-building-and-project.json"
    source.write_text(json.dumps(project))
    script = """
import json,sys
from pathlib import Path
project=json.loads(Path(sys.argv[1]).read_text())
opened=[]
def audit(event,args):
    if event=='open' and isinstance(args[0],str):
        value=args[0]
        banned=('blueberry-factory-layout-v2','blueberry-factory-layout-v3',
                'candidate-index','stage-b-r9-resource','stage-b-r10-r2-real','main_pool.json')
        if any(x in value for x in banned):
            raise RuntimeError('HISTORICAL_LAYOUT_READ_FORBIDDEN:'+value)
        opened.append(value)
sys.addaudithook(audit)
from cold_storage.modules.layout.application.autonomous_factory_layout import (
    generate_autonomous_layouts,
)
r=generate_autonomous_layouts(project)
print(json.dumps({'count':r['candidate_count'],
                  'rooms':[len(c['rooms']) for c in r['candidates']],
                  'opened':opened,'native':r['native_calls']}))
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend/tests/functional_native_guard")
        + os.pathsep
        + str(ROOT / "backend/src"),
        "R11_FUNCTIONAL_GUARD_AUDIT": str(tmp_path / "native-guard"),
    }
    p = subprocess.run(
        [sys.executable, "-c", script, str(source)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stderr
    body = json.loads(p.stdout)
    assert body["count"] >= 1 and all(n == 12 for n in body["rooms"])
    assert body["native"] == 0


def test_parent_child_native_apis_are_blocked(tmp_path: Path) -> None:
    script = (
        "from ortools.sat.python import cp_model; s=cp_model.CpS"
        "olver(); m=cp_model.CpModel();\nfor f in (s.solve,s.Solv"
        "e):\n try:f(m)\n except RuntimeError:pass\n else:raise Run"
        "timeError('NATIVE_GUARD_MISSING')"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend/tests/functional_native_guard"),
        "R11_FUNCTIONAL_GUARD_AUDIT": str(tmp_path),
    }
    p = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30
    )
    assert p.returncode == 0, p.stderr
    text = "".join(x.read_text() for x in tmp_path.glob("process-*.jsonl"))
    assert text.count("NATIVE_REQUEST_BLOCKED") == 2


def test_declared_search_bound_is_enforced(project: dict[str, Any]) -> None:
    from cold_storage.modules.layout.domain.autonomous_room_search import search_room_arrangements

    c = bind_autonomous_input(project)
    rows, stats = search_room_arrangements(
        c.binding.dimension_authorities,
        c.boundary,
        c.walls,
        internal_columns=c.columns,
        profile="LINEAR_BANDED",
        node_budget=1,
    )
    assert not rows
    assert stats["nodes_used"] <= 1
    assert not stats["global_infeasibility_proven"]


def test_original_full_width_route_predicate_rejects_blocked_equipment() -> None:
    from cold_storage.modules.layout.domain.autonomous_process_routes import (
        route_equipment_aware_interiors,
    )

    room = PlacedRectangleV1("changing_room", Decimal(0), Decimal(0), Decimal(10), Decimal(10))

    def portal(y: int) -> dict[str, Any]:
        return {"segment": {"start": {"x": 4, "y": y}, "end": {"x": 6, "y": y}}}

    access = [
        {
            "status": "PASS",
            "from_ref": "main_entrance",
            "to_ref": "changing_room",
            "requirement_identity": "in",
            "portal_to": portal(0),
            "flow_kind": "PERSONNEL",
        },
        {
            "status": "PASS",
            "from_ref": "changing_room",
            "to_ref": "outside",
            "requirement_identity": "out",
            "portal_from": portal(10),
            "flow_kind": "PERSONNEL",
        },
    ]
    clear = route_equipment_aware_interiors({"changing_room": room}, access, {"items": []}, [])
    assert clear[0]["status"] == "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
    assert clear[0]["length_mm"] == 8000
    blocked = route_equipment_aware_interiors(
        {"changing_room": room},
        access,
        {"items": [{"room": "changing_room", "bbox_mm": [0, 4000, 10000, 6000]}]},
        [],
    )
    assert blocked[0]["status"] == "BOUNDED_PATH_NOT_FOUND"
    assert not blocked[0]["full_material_handling_or_personnel_pass"]


def test_same_json_draws_a1_true_scale_and_coordinate_attributes(
    result: dict[str, Any],
    tmp_path: Path,
) -> None:
    import xml.etree.ElementTree as ET

    import fitz

    from cold_storage.modules.layout.infrastructure.autonomous_layout_export import (
        draw_autonomous_candidate,
    )

    candidate = result["candidates"][0]
    target = tmp_path / "drawing"
    draw_autonomous_candidate(candidate, target, "A")
    root = ET.parse(target.with_suffix(".svg")).getroot()
    assert root.attrib["width"] == "841mm" and root.attrib["height"] == "594mm"
    drawn = {q.attrib["data-zone"]: q for q in root.iter() if "data-zone" in q.attrib}
    assert len(drawn) == 12
    for room in candidate["rooms"]:
        rect = drawn[room["zone_code"]]
        assert rect.attrib["data-world-bbox-mm"] == ",".join(map(str, room["bbox_mm"]))
        assert float(rect.attrib["width"]) * 200 == pytest.approx(room["width_mm"])
    with fitz.open(target.with_suffix(".pdf")) as doc:
        assert doc[0].rect.width * 25.4 / 72 == pytest.approx(841, abs=0.01)
        assert doc[0].rect.height * 25.4 / 72 == pytest.approx(594, abs=0.01)
        assert "1:200" in doc[0].get_text()
    assert fitz.Pixmap(str(target.with_suffix(".png"))).width >= 6000
