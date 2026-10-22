"""Synthetic exact-geometry tests and immutable history checks; no factory search."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any

import jsonschema
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_examples as examples  # noqa: E402
import offline_station_geometry as geo  # noqa: E402
from offline_station_renderer import fmt, render  # noqa: E402


def evaluate(doc: dict[str, Any], root: Path) -> dict[str, Any]:
    examples.seal(doc, root)
    return geo.evaluate(doc, root)


def read(name: str) -> Any:
    return json.loads((HERE / name).read_bytes())


def test_complete_synthetic_single_has_three_operators_and_no_approval(tmp_path: Path) -> None:
    result = evaluate(examples.example(), tmp_path)
    assert result["SYNTHETIC_GEOMETRY_TEST_PASS"] is True
    assert {op["OPERATOR_ID"] for op in result["OPERATORS"]} == {
        "OPERATOR_1",
        "OPERATOR_2",
        "OPERATOR_3",
    }
    assert all(op["TASK"] and op["ENTRY_PATH"] for op in result["OPERATORS"])
    assert result["MODULE_ENGINEERING_APPROVAL"] == "NOT_APPROVED"
    assert (
        not result["REAL_PROJECT_MODULE_VALIDATED"]
        and not result["FORMAL_MODULE_DIMENSIONS_APPROVED"]
    )


@pytest.mark.parametrize("count", [0, 2, 4])
def test_exactly_three_workers_required(tmp_path: Path, count: int) -> None:
    doc = examples.example()
    doc["OPERATORS"] = (doc["OPERATORS"] + [deepcopy(doc["OPERATORS"][0])])[:count]
    assert evaluate(doc, tmp_path)["GEOMETRY_INPUT_STATUS"] == "INPUT_REQUIRED_OR_INVALID"


def test_distinct_worker_ids_required(tmp_path: Path) -> None:
    doc = examples.example()
    doc["OPERATORS"][2]["OPERATOR_ID"] = "OPERATOR_2"
    assert not evaluate(doc, tmp_path)["SYNTHETIC_GEOMETRY_TEST_PASS"]


@pytest.mark.parametrize(
    "field", ["TASK", "STANDING_COMPONENT", "REACH_COMPONENT", "ENTRY_PATH", "WORK_DIRECTION"]
)
def test_worker_missing_task_geometry_or_path_rejected(tmp_path: Path, field: str) -> None:
    doc = examples.example()
    del doc["OPERATORS"][0][field]
    assert evaluate(doc, tmp_path)["MODULE_BOUNDS"] is None


def test_missing_equipment_geometry_no_real_dimensioned_result(tmp_path: Path) -> None:
    doc = examples.example()
    doc["COMPONENTS"][0]["GEOMETRY"] = None
    result = evaluate(doc, tmp_path)
    assert result["MODULE_BOUNDS"] is None and result["FUNCTIONAL_ROOM_AREA"] is None
    assert not result["REAL_PROJECT_MODULE_VALIDATED"]


@pytest.mark.parametrize(
    "change",
    [
        "unknown_type",
        "unknown_role",
        "float",
        "bool",
        "metres",
        "rotation",
        "polygon",
        "degenerate",
    ],
)
def test_geometry_input_fail_closed(tmp_path: Path, change: str) -> None:
    doc = examples.example()
    item = doc["COMPONENTS"][0]
    if change == "unknown_type":
        item["COMPONENT_TYPE"] = "UNKNOWN"
    elif change == "unknown_role":
        item["ROLE"] = "UNKNOWN"
    elif change == "float":
        item["GEOMETRY"]["BOUNDS_MM"][0] = 1000.5
    elif change == "bool":
        item["GEOMETRY"]["BOUNDS_MM"][0] = True
    elif change == "metres":
        item["DIMENSION_UNIT"] = "m"
    elif change == "rotation":
        item["TRANSFORM"]["ROTATION_DEG"] = 45
    elif change == "polygon":
        item["GEOMETRY"]["TYPE"] = "POLYGON"
    else:
        item["GEOMETRY"]["BOUNDS_MM"][2] = 1000
    result = evaluate(doc, tmp_path)
    assert result["GEOMETRY_INPUT_STATUS"] == "INPUT_REQUIRED_OR_INVALID"
    assert result["MODULE_GEOMETRIC_AREA"] is None


def test_actual_source_hash_and_entire_geometry_fact_binding(tmp_path: Path) -> None:
    doc = examples.example()
    examples.seal(doc, tmp_path)
    doc["COMPONENTS"][0]["GEOMETRY"]["BOUNDS_MM"][0] += 1
    result = geo.evaluate(doc, tmp_path)
    assert "SOURCE_FACT_DOES_NOT_BIND_RECORD" in result["DIAGNOSTICS"][0]
    doc = examples.example()
    examples.seal(doc, tmp_path)
    (tmp_path / "synthetic-evidence.json").write_text("{}")
    assert "SOURCE_CONTENT_HASH_MISMATCH" in geo.evaluate(doc, tmp_path)["DIAGNOSTICS"][0]


def test_source_path_escape_rejected(tmp_path: Path) -> None:
    doc = examples.example()
    examples.seal(doc, tmp_path)
    doc["SOURCES"]["synthetic"]["PATH"] = "../outside.json"
    assert "OUTSIDE_EVIDENCE_ROOT" in geo.evaluate(doc, tmp_path)["DIAGNOSTICS"][0]


def test_malformed_source_content_is_fail_closed_not_traceback(tmp_path: Path) -> None:
    doc = examples.example()
    examples.seal(doc, tmp_path)
    path = tmp_path / "synthetic-evidence.json"
    path.write_bytes(b"[]")
    doc["SOURCES"]["synthetic"]["SHA256"] = geo.digest(path.read_bytes())
    result = geo.evaluate(doc, tmp_path)
    assert result["DIAGNOSTICS"] == ["SOURCE_OBJECT_WITH_FACTS_REQUIRED"]
    assert result["PACKAGING_AREA_CALIBRATION_READY"] is False
    assert result["NATIVE_SOLVER_CALLS"] == 0 and result["NEW_OWNER_GRANT"] is False


def test_source_container_not_an_object_rejects(tmp_path: Path) -> None:
    doc = examples.example()
    doc["SOURCES"] = []
    assert geo.evaluate(doc, tmp_path)["DIAGNOSTICS"] == ["SOURCE_OBJECT_REQUIRED"]


def test_synthetic_sources_cannot_masquerade_as_project(tmp_path: Path) -> None:
    doc = examples.example()
    examples.seal(doc, tmp_path)
    doc["MODE"] = "OWNER_PROJECT"
    result = geo.evaluate(doc, tmp_path)
    assert result["MODULE_BOUNDS"] is None and not result["REAL_PROJECT_MODULE_VALIDATED"]
    assert "CANNOT_BE_PROJECT_EVIDENCE" in result["DIAGNOSTICS"][0]


def test_caller_verified_approval_cannot_override(tmp_path: Path) -> None:
    doc = examples.example()
    doc["COMPONENTS"][0]["APPROVAL_STATUS"] = "PROJECT_APPROVED"
    assert "CANNOT_ASSERT" in evaluate(doc, tmp_path)["DIAGNOSTICS"][0]


def test_source_matched_project_data_still_never_engineering_approval(tmp_path: Path) -> None:
    doc = examples.example()
    examples.seal(doc, tmp_path)
    path = tmp_path / "synthetic-evidence.json"
    source = json.loads(path.read_bytes())
    source["EVIDENCE_KIND"] = "PROJECT_INPUT"
    path.write_bytes(geo.encode(source))
    doc["MODE"] = "OWNER_PROJECT"
    doc["SOURCES"]["synthetic"].update(
        EVIDENCE_KIND="PROJECT_INPUT", SHA256=geo.digest(path.read_bytes())
    )
    result = geo.evaluate(doc, tmp_path)
    assert result["GEOMETRY_INPUT_STATUS"] == "VALID_SOURCE_BOUND_OFFLINE_INPUT"
    assert result["MODULE_ENGINEERING_APPROVAL"] == "NOT_APPROVED"
    assert (
        result["SYNTHETIC_GEOMETRY_TEST_PASS"] is False
        and not result["REAL_PROJECT_MODULE_VALIDATED"]
    )


def test_equipment_body_collision_is_hard(tmp_path: Path) -> None:
    doc = examples.example("LINEAR_ARRANGEMENT")
    doc["INSTANCES"][1]["TRANSFORM"] = deepcopy(examples.ZERO)
    # Delete assembly-only links; no invented connection used to rescue collision.
    doc["ASSEMBLY_CIRCULATION"] = []
    doc["ASSEMBLY_ROUTES"] = []
    doc["SHARING_CONDITIONS"] = []
    result = evaluate(doc, tmp_path)
    assert any(r["TYPE"] == "SOLID_OR_STANDING_COLLISION" for r in result["GEOMETRIC_COLLISIONS"])
    assert not result["SYNTHETIC_GEOMETRY_TEST_PASS"]


def test_standing_equipment_conflict_cannot_be_shared_away(tmp_path: Path) -> None:
    doc = examples.example()
    doc["COMPONENTS"][0]["GEOMETRY"]["BOUNDS_MM"] = [1000, 1500, 3400, 2100]
    doc["SHARING_CONDITIONS"] = [
        {
            "RULE_ID": "NOT_A_BYPASS",
            "COMPONENT_KEYS": ["A/EQUIPMENT", "A/STAND_1"],
            "STATES": ["NORMAL_PRODUCTION"],
            "CONDITION_TEXT": "Attempt to permit a physical collision",
            "SOURCE_ID": "synthetic",
        }
    ]
    result = evaluate(doc, tmp_path)
    assert any(
        r["TYPE"] == "STANDING_VS_EQUIPMENT" and r["STATUS"] == "FAIL"
        for r in result["GEOMETRIC_COLLISIONS"]
    )
    assert not result["SYNTHETIC_GEOMETRY_TEST_PASS"]


def test_reach_overlap_not_body_collision_or_automatic_permission(tmp_path: Path) -> None:
    result = evaluate(examples.example(), tmp_path)
    assert not result["GEOMETRIC_COLLISIONS"]
    assert any(
        r["TYPE"] == "REACH_INTERACTION_NOT_SOLID_COLLISION" and r["STATUS"] == "REVIEW_REQUIRED"
        for r in result["FUNCTIONAL_CONFLICTS"]
    )
    assert result["OPERATOR_FIT_STATUS"] == "REVIEW_REQUIRED_TASK_AND_REACH"


def test_supply_outfeed_overlap_reported(tmp_path: Path) -> None:
    doc = examples.example()
    doc["COMPONENTS"][1]["GEOMETRY"]["BOUNDS_MM"] = [200, 2400, 4200, 3000]
    result = evaluate(doc, tmp_path)
    assert any(
        r["TYPE"] == "SUPPLY_OUTFEED_OR_FLOW_INTERACTION" for r in result["FUNCTIONAL_CONFLICTS"]
    )


def test_width_checked_not_centerline_only(tmp_path: Path) -> None:
    doc = examples.example()
    # Centerline remains inside200mm strip, but actual500mm swept path does not.
    doc["ROUTES"][-2]["WIDTH_MM"] = 500
    result = evaluate(doc, tmp_path)
    assert any(
        p["KEY"] == "A/SUPPLY_PATH" and not p["FULL_WIDTH_COVERED"] for p in result["PATH_CHECKS"]
    )
    assert result["MATERIAL_FLOW_STATUS"] == "FAIL"


def test_personnel_material_crossing_retains_review(tmp_path: Path) -> None:
    doc = examples.example()
    doc["ROUTES"][-2]["POINTS_MM"] = [
        [100, 2700],
        [100, 800],
        [1600, 800],
        [1600, 1200],
        [500, 1200],
        [500, 2700],
    ]
    # Explicit synthetic circulation supports the detour, but crossing is not approval.
    shared = examples.component(
        "TEST_PATH", 4, "SHARED_AISLE", [450, 750, 550, 2750], list(geo.STATES)
    )
    shared.update(COORDINATE_SYSTEM="ASSEMBLY_GLOBAL", OVERLAP_POLICY="EXPLICIT_SHARED_REVIEW")
    doc["ASSEMBLY_CIRCULATION"] = [shared]
    result = evaluate(doc, tmp_path)
    assert any(
        r["TYPE"] == "PERSONNEL_MATERIAL_OR_FLOW_CROSSING" for r in result["FUNCTIONAL_CONFLICTS"]
    )


@pytest.mark.parametrize("missing", ["aisle", "service", "material_route"])
def test_missing_flow_or_maintenance_not_filled(tmp_path: Path, missing: str) -> None:
    doc = examples.example()
    if missing == "aisle":
        doc["COMPONENTS"] = [c for c in doc["COMPONENTS"] if c["COMPONENT_TYPE"] != geo.TYPES[4]]
    elif missing == "service":
        doc["COMPONENTS"] = [c for c in doc["COMPONENTS"] if c["ROLE"] != "SERVICE"]
    else:
        doc["ROUTES"] = [r for r in doc["ROUTES"] if r["FLOW_KIND"] != "MATERIAL_IN"]
    result = evaluate(doc, tmp_path)
    assert result["MODULE_BOUNDS"] is None and not result["SYNTHETIC_GEOMETRY_TEST_PASS"]


def test_states_not_unconditional_max_or_disappearing_body(tmp_path: Path) -> None:
    doc = examples.example()
    result = evaluate(doc, tmp_path)
    assert "A/SERVICE" not in result["STATES"]["NORMAL_PRODUCTION"]["ACTIVE_COMPONENT_KEYS"]
    assert "A/SERVICE" in result["STATES"]["CLEANING"]["ACTIVE_COMPONENT_KEYS"]
    assert "A/STAND_1" not in result["STATES"]["CLEANING"]["ACTIVE_COMPONENT_KEYS"]
    assert result["SHIFT_CHANGE_STATUS"] == "REVIEW_REQUIRED_NO_ZERO_TIME_ASSUMPTION"
    doc["COMPONENTS"][0]["ACTIVE_STATES"] = ["NORMAL_PRODUCTION"]
    assert "CANNOT_DISAPPEAR" in evaluate(doc, tmp_path)["DIAGNOSTICS"][0]


def test_disjoint_state_overlap_is_not_time_sharing_approval(tmp_path: Path) -> None:
    doc = examples.example()
    service = next(c for c in doc["COMPONENTS"] if c["ROLE"] == "SERVICE")
    service["GEOMETRY"]["BOUNDS_MM"] = [1100, 1500, 1700, 2100]
    result = evaluate(doc, tmp_path)
    assert result["NON_SIMULTANEOUS_OCCUPATIONS"]
    assert all(
        r["STATUS"].endswith("NOT_SHARING_APPROVAL") for r in result["NON_SIMULTANEOUS_OCCUPATIONS"]
    )
    assert result["MODULE_ENGINEERING_APPROVAL"] == "NOT_APPROVED"


def test_outfeed_direction_cannot_be_inverted_by_label(tmp_path: Path) -> None:
    doc = examples.example()
    path = doc["ROUTES"][-1]
    path["FROM_INTERFACE"], path["TO_INTERFACE"] = path["TO_INTERFACE"], path["FROM_INTERFACE"]
    path["POINTS_MM"].reverse()
    assert "FLOW_DIRECTION_INTERFACE_KIND_MISMATCH" in evaluate(doc, tmp_path)["DIAGNOSTICS"][0]


@pytest.mark.parametrize(
    "arrangement,count",
    [("LINEAR_ARRANGEMENT", 2), ("OPPOSED_ARRANGEMENT", 2), ("PARALLEL_ROWS", 4)],
)
def test_multi_station_explicit_geometry_paths_and_union(
    tmp_path: Path, arrangement: str, count: int
) -> None:
    result = evaluate(examples.example(arrangement), tmp_path)
    assert result["SYNTHETIC_GEOMETRY_TEST_PASS"]
    assert len(result["OPERATORS"]) == 3 * count
    assert result["ASSEMBLY_CONNECTIVITY_STATUS"] == "EXPLICIT_PERSONNEL_ROUTES_CONNECTED"
    normal = result["STATES"]["NORMAL_PRODUCTION"]
    assert Fraction(normal["GEOMETRIC_UNION_AREA_MM2"]) < Fraction(
        normal["SUM_COMPONENT_AREAS_MM2"]
    )
    assert normal["FUNCTIONAL_ROOM_AREA"] is None
    assert any(r.get("SOURCE_BOUND_CONDITIONS") for r in result["FUNCTIONAL_CONFLICTS"])


def test_arrangement_name_does_not_infer_connectivity(tmp_path: Path) -> None:
    doc = examples.example("LINEAR_ARRANGEMENT")
    doc["ASSEMBLY_ROUTES"] = []
    result = evaluate(doc, tmp_path)
    assert result["ASSEMBLY_CONNECTIVITY_STATUS"] == "REVIEW_REQUIRED_UNCONNECTED_STATIONS"
    assert not result["SYNTHETIC_GEOMETRY_TEST_PASS"]


def test_union_bounding_and_room_area_not_interchangeable(tmp_path: Path) -> None:
    result = evaluate(examples.example(), tmp_path)
    normal = result["STATES"]["NORMAL_PRODUCTION"]
    assert Fraction(normal["GEOMETRIC_UNION_AREA_MM2"]) < Fraction(
        normal["BOUNDING_RECTANGLE_AREA_MM2"]
    )
    assert result["FUNCTIONAL_ROOM_AREA"] is None
    assert result["MODULE_GEOMETRIC_AREA"]["FUNCTIONAL_ROOM_AREA"] is None
    assert (
        geo.union_area(
            [
                (Fraction(0), Fraction(0), Fraction(2), Fraction(2)),
                (Fraction(1), Fraction(0), Fraction(3), Fraction(1)),
            ]
        )
        == 5
    )


def test_integer_quarter_turn_and_exact_odd_width() -> None:
    pose = {"TRANSLATION_MM": [100, 200], "ROTATION_DEG": 90}
    assert geo.transform_rect([0, 0, 300, 100], [pose]) == tuple(
        Fraction(v) for v in (0, 200, 100, 500)
    )
    assert geo.transform(geo.point([300, 0]), pose) == geo.point([100, 500])
    r = geo.path_envelope([geo.point([0, 0]), geo.point([1000, 0])], 301)[0]
    assert r[1] == Fraction(-301, 2) and geo.union_area([r]) == 1301 * 301


def test_svg_coordinate_formatting_is_exact_without_float_or_context_rounding() -> None:
    value = 10**90 + 1
    assert fmt(value) == str(value)
    assert fmt(Fraction(-301, 2)) == "-150.5"
    with pytest.raises(geo.InputError, match="NOT_APPROXIMATED"):
        fmt(Fraction(1, 3))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_operator_positions_directions_and_paths_rotate_together(
    tmp_path: Path, rotation: int
) -> None:
    doc = examples.example()
    doc["INSTANCES"][0]["TRANSFORM"]["ROTATION_DEG"] = rotation
    result = evaluate(doc, tmp_path)
    assert result["SYNTHETIC_GEOMETRY_TEST_PASS"]
    expected = geo.transform(
        geo.point([0, 1]), {"TRANSLATION_MM": [0, 0], "ROTATION_DEG": rotation}
    )
    assert result["OPERATORS"][0]["DIRECTION"] == list(expected)


def test_svg_xml_determinism_same_scale_and_no_external_resources(tmp_path: Path) -> None:
    for arrangement in ("SINGLE", "LINEAR_ARRANGEMENT", "OPPOSED_ARRANGEMENT", "PARALLEL_ROWS"):
        doc = examples.example(arrangement)
        evaluate(doc, tmp_path)
        for state in geo.STATES:
            svg = render(doc, tmp_path, state)
            assert svg == render(doc, tmp_path, state)
            tree = ET.fromstring(svg)
            assert tree.attrib["data-scale-px-per-mm"] == "0.1"
            assert b"SYNTHETIC_TEST_GEOMETRY" in svg and b"NO P1 AREA" in svg
            assert b"<script" not in svg and b"<image" not in svg and b"href=" not in svg


def test_missing_project_svg_not_dimensioned(tmp_path: Path) -> None:
    doc = examples.example()
    doc["MODE"] = "OWNER_PROJECT"
    doc["SOURCES"] = {}
    svg = render(doc, tmp_path)
    assert b"SCHEMATIC_NOT_TO_SCALE" in svg and b"1000" not in svg
    assert b"data-scale-px-per-mm" not in svg


def test_schema_validates_all_positive_examples() -> None:
    schema = read("station-envelope-schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    for path in (HERE / "examples").glob("synthetic-*input.json"):
        jsonschema.validate(json.loads(path.read_bytes()), schema)


def test_examples_reproduce_without_geometry_or_svg_drift() -> None:
    for label in ("station", "multiple", "opposed", "parallel"):
        doc = read(f"examples/synthetic-{label}-input.json")
        actual = geo.evaluate(doc, HERE / "examples")
        assert geo.encode(actual) == (HERE / f"examples/synthetic-{label}-result.json").read_bytes()
    doc = read("examples/synthetic-station-input.json")
    assert (
        render(doc, HERE / "examples")
        == (HERE / "examples/synthetic-single-station.svg").read_bytes()
    )
    assert (
        render(doc, HERE / "examples", "CLEANING")
        == (HERE / "examples/synthetic-cleaning-maintenance.svg").read_bytes()
    )


def test_both_actual_command_line_interfaces_work_from_other_directory(tmp_path: Path) -> None:
    common = [
        str(HERE / "examples/synthetic-station-input.json"),
        "--evidence-root",
        str(HERE / "examples"),
    ]
    geometry = subprocess.check_output(
        [sys.executable, str(HERE / "offline_station_geometry.py"), *common], cwd=tmp_path
    )
    svg = subprocess.check_output(
        [sys.executable, str(HERE / "offline_station_renderer.py"), *common, "--state", "CLEANING"],
        cwd=tmp_path,
    )
    assert geometry == (HERE / "examples/synthetic-station-result.json").read_bytes()
    assert svg == (HERE / "examples/synthetic-cleaning-maintenance.svg").read_bytes()


def test_historical_eight_layout_hashes_and_forty_eight_portals_unchanged() -> None:
    record = read("sorting-room-interface-contract.json")
    assert record == examples.historical_contract()
    assert record["CANDIDATE_COUNT"] == 8 and record["INTERFACE_COUNT"] == 48
    assert record["FIT_18_OR_28_STATIONS"] is None
    for row in record["LAYOUTS"]:
        assert geo.digest((examples.REPO / row["svg_path"]).read_bytes()) == row["svg_sha256"]


def test_v1_v2_contract_hashes_and_legacy_p1_replay_unchanged() -> None:
    for name in (
        "owner-functional-input-contract-r1",
        "owner-functional-input-contract-r2",
        "owner-v2-packaging-area-geometry-calibration-r1",
    ):
        folder = HERE.parent / name
        for relative, expected in json.loads((folder / "source_manifest.json").read_bytes())[
            "files"
        ].items():
            assert geo.digest((folder / relative).read_bytes()) == expected
    folder = HERE.parent / "owner-factory-p1-compatibility-readiness-r1"
    spec = importlib.util.spec_from_file_location(
        "station_legacy_replay", folder / "offline_compatibility.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.legacy_replay()
    assert (
        result["canonical_result_hash"]
        == "sha256:61b59f8e6bd8e81c8b43751bd58ce52df82d349b82346bbfd6585a891139cddd"
    )
    assert (
        result["dimension_handoff_hash"]
        == "sha256:7a41ba026375a1f7085106772d761b946c32c32661320bb4db8565e02848c468"
    )
    v2 = HERE.parent / "owner-functional-input-contract-r2"
    spec = importlib.util.spec_from_file_location("station_owner_v2", v2 / "offline_contract_v2.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stored = json.loads((v2 / "staffing-and-locker-calculation.json").read_bytes())["examples"]
    for row in stored:
        assert module.calculate(row["input"], evidence_root=v2) == row["result"]


def test_no_production_changes_or_solver_grant_imports() -> None:
    import ast

    reference = "6e6972e1adf012b397343bd5d53a2c65c9d81fad"
    for relative in (
        "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
        "backend/src/cold_storage/modules/layout/application/sorting_dimension_authority.py",
    ):
        original = subprocess.check_output(
            ["git", "show", reference + ":" + relative], cwd=examples.REPO
        )
        assert original == (examples.REPO / relative).read_bytes()
    for filename in ("offline_station_geometry.py", "offline_station_renderer.py"):
        tree = ast.parse((HERE / filename).read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports.extend(v.name for n in ast.walk(tree) if isinstance(n, ast.Import) for v in n.names)
        assert not any(
            any(
                bad in name
                for bad in ("cold_storage", "ortools", "pool_execution", "httpx", "requests")
            )
            for name in imports
        )
    result = read("examples/synthetic-station-result.json")
    assert (
        result["REAL_FACTORY_SOLVES"] == result["NATIVE_SOLVER_CALLS"] == 0
        and not result["NEW_OWNER_GRANT"]
    )
