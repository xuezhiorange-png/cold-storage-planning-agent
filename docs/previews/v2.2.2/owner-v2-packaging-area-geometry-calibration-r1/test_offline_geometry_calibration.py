"""Read-only business/geometry facts, not an actual factory layout execution."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "geometry_calibration", HERE / "offline_geometry_calibration.py"
)
assert spec and spec.loader
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(scope="module")
def scenarios() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((HERE / "legacy-projection-scenarios.json").read_text()))


@pytest.fixture(scope="module")
def v2() -> Any:
    return c.load(c.V2, "offline_contract_v2.py")


def test_legacy_canonical_and_dimension_hashes_and_bytes_unchanged() -> None:
    module = c.load(
        HERE.parent / "owner-factory-p1-compatibility-readiness-r1", "offline_compatibility.py"
    )
    replay = module.legacy_replay()
    audit = json.loads((HERE / "legacy-geometry-authority-audit.json").read_text())
    assert (
        replay["canonical_result_hash"]
        == audit["legacy_canonical_hash"]
        == "sha256:61b59f8e6bd8e81c8b43751bd58ce52df82d349b82346bbfd6585a891139cddd"
    )
    assert (
        replay["dimension_handoff_hash"]
        == audit["legacy_p1_hash"]
        == "sha256:7a41ba026375a1f7085106772d761b946c32c32661320bb4db8565e02848c468"
    )


@pytest.mark.parametrize(
    "need,grid,raw,exact,report",
    [
        (20, (7, 3, 21), "565.76", "622.336", "622.34"),
        (18, (6, 3, 18), "489.6", "538.56", "538.56"),
        (28, (7, 4, 28), "690.56", "759.616", "759.62"),
    ],
)
def test_actual_legacy_function_and_exact_projection(
    need: int, grid: tuple[int, int, int], raw: str, exact: str, report: str
) -> None:
    p = c.projection(need)
    assert (p["n_long"], p["n_short"], p["n_actual"]) == grid
    assert p["A_raw_exact_m2"] == raw
    assert p["A_exact_p1c_form_m2"] == exact
    assert p["A_reported_m2"] == report
    assert Decimal(p["L_p1c_form_m"]) == Decimal(p["L_raw_m"]) * Decimal("1.1")
    assert p["D_p1c_form_m"] == p["D_raw_m"]
    assert Decimal(exact) == Decimal(raw) * Decimal("1.1")


def test_demand_twenty_is_not_twenty_one_installed_tables() -> None:
    p = c.projection(20)
    assert (p["n_need"], p["n_actual"], p["unused_cells"]) == (20, 21, 1)
    assert p["actual_device_footprint_m2"] is None


@pytest.mark.parametrize(
    "index,staff,tables,lockers,peak", [(0, (53, 53), 18, 106, 53), (1, (84, 21), 28, 105, 84)]
)
def test_owner_v2_actual_calculator_not_total_worker_tables(
    v2: Any, index: int, staff: tuple[int, int], tables: int, lockers: int, peak: int
) -> None:
    row = json.loads((c.V2 / "staffing-and-locker-calculation.json").read_text())["examples"][index]
    result = v2.calculate(row["input"], evidence_root=c.V2)
    assert result == row["result"]
    values = result["staffing_and_tables"]
    assert (values["SHIFT_1_WORKERS"], values["SHIFT_2_WORKERS"]) == staff
    assert values["PACKING_TABLE_COUNT"] == tables
    assert values["LOCKER_COUNT"] == sum(staff) == lockers
    assert values["PEAK_WORKERS"] == values["SIMULTANEOUS_CHANGING_USERS"] == peak
    assert values["TABLE_SHARED_BETWEEN_SHIFTS"] and values["WORKERS_PER_PACKING_TABLE"] == 3
    assert result["production_p1_area_m2"] is None and result["P1_AUTHORITY_PASS"] is False


def test_raw_mass_cannot_substitute_packaged_mass(v2: Any) -> None:
    row = json.loads((c.V2 / "staffing-and-locker-calculation.json").read_text())["examples"][0]
    bad = {**row["input"], "mass_basis": "RAW_INBOUND_FRUIT"}
    result = v2.calculate(bad, evidence_root=c.V2)
    assert result["status"] == "BLOCKED_INPUT"
    assert result["reason"] == "PACKAGED_PRODUCT_MASS_REQUIRED_NO_RAW_DEFAULT"
    assert result["staffing_and_tables"] is None


def test_no_formal_new_area_or_factory_total(scenarios: dict[str, Any]) -> None:
    assert scenarios["legacy_vs_owner_mass_comparison"] == "NOT_COMPARABLE"
    assert scenarios["new_formal_sorting_area_m2"] is None
    assert scenarios["new_factory_total_area_m2"] is None
    for row in scenarios["scenarios"]:
        assert row["geometry"]["v2_formal_p1_area_m2"] is None
        assert row["geometry"]["functional_pass"] is None


def test_pitch_not_equipment_and_aggregate_not_individual_aisles() -> None:
    matrix = json.loads((HERE / "packing-station-evidence-matrix.json").read_text())
    p = {r["FIELD_NAME"]: r for r in matrix["parameters"]}
    for field in ("PACKING_TABLE_PITCH_LONG_M", "PACKING_TABLE_PITCH_SHORT_M"):
        assert p[field]["CLASSIFICATION"] == "STATION_PITCH"
        assert p[field]["PHYSICAL_EVIDENCE"] == "UNAVAILABLE"
    for field in ("SORTING_CLEARANCE_LONG_M", "SORTING_CLEARANCE_SHORT_M"):
        assert p[field]["CLASSIFICATION"] == "UNDECOMPOSED_AGGREGATE_END_TERM"
    assert (
        p["SORTING_PACKAGING_AREA_FACTOR"]["FORMAL_AUTHORITY_STATUS"]
        == "LEGACY_PRESERVED_NOT_V2_APPROVED"
    )


def test_rank_prefers_grid_ratio_before_area_not_engineering_optimum() -> None:
    r = c.ranking_audit(20)
    assert (r["selected"]["n_long"], r["selected"]["n_short"]) == (7, 3)
    assert r["smallest_raw_area_in_same_finite_domain"]["raw_area_reported_m2"] == "504.64"
    assert not r["is_area_minimal_in_this_finite_domain"]
    assert r["global_engineering_optimality"] == "NOT_PROVEN"


def test_count_ratio_is_not_room_aspect() -> None:
    p = c.projection(20)
    assert p["count_ratio"] != p["physical_raw_aspect_ratio"] != p["physical_expanded_aspect_ratio"]


def test_binary_float_repr_and_decimal_report_are_separate() -> None:
    p = c.projection(20)
    assert p["native_float_area_repr"] == "565.7599999999999"
    assert p["A_exact_p1c_form_m2"] != p["A_reported_m2"]


@pytest.mark.parametrize("missing", list(c.COMPONENTS))
def test_missing_component_does_not_receive_default(missing: str) -> None:
    components: dict[str, list[tuple[int, ...]]] = {k: [] for k in c.COMPONENTS}
    del components[missing]
    result = c.envelope_diagnostic(components, [c.COMPONENTS[0]])
    assert result["status"] == "OWNER_INPUT_REQUIRED" and missing in result["missing"]
    assert result["formal_area_m2"] is None and result["functional_pass"] is None


def test_missing_state_not_assumed_production() -> None:
    assert (
        "EXPLICIT_STATE_AND_SIMULTANEITY"
        in c.envelope_diagnostic({k: [] for k in c.COMPONENTS}, None)["missing"]
    )


def test_simultaneous_overlap_not_automatically_shared() -> None:
    components: dict[str, list[tuple[int, ...]]] = {k: [] for k in c.COMPONENTS}
    components[c.COMPONENTS[0]] = [(0, 0, 1000, 1000)]
    components[c.COMPONENTS[1]] = [(500, 0, 1500, 1000)]
    out = c.envelope_diagnostic(components, [c.COMPONENTS[0], c.COMPONENTS[1]])
    assert out["union_area_mm2"] == 1500000
    assert (
        out["simultaneous_positive_overlaps_requiring_review"][0]["positive_overlap_mm2"] == 500000
    )
    assert out["time_sharing_automatically_approved"] is False and out["functional_pass"] is None


def test_touching_not_positive_overlap_and_holes_not_floor_area() -> None:
    components: dict[str, list[tuple[int, ...]]] = {k: [] for k in c.COMPONENTS}
    components[c.COMPONENTS[0]] = [(0, 0, 1000, 1000), (1000, 0, 2000, 500)]
    out = c.envelope_diagnostic(components, [c.COMPONENTS[0]])
    assert out["union_area_mm2"] == 1500000
    assert out["bounding_box_mm"] == [0, 0, 2000, 1000]
    assert out["simultaneous_positive_overlaps_requiring_review"] == []
    assert out["formal_area_m2"] is None


@pytest.mark.parametrize("rect", [(0, 0, 0, 1), (0, 0, 1.5, 2), (2, 0, 1, 2)])
def test_bad_envelope_rejected(rect: tuple[Any, ...]) -> None:
    components: dict[str, list[tuple[Any, ...]]] = {k: [] for k in c.COMPONENTS}
    components[c.COMPONENTS[0]] = [rect]
    with pytest.raises(ValueError, match="INVALID_INTEGER_MM_ENVELOPE"):
        c.envelope_diagnostic(components, [c.COMPONENTS[0]])


def test_eight_layouts_and_forty_eight_real_interfaces_unchanged() -> None:
    review = c.interface_review()
    assert c.encode(review) == (HERE / "real-layout-interface-review.json").read_bytes()
    assert review["candidate_count"] == 8 and review["sorting_interface_count"] == 48
    for row in review["layouts"]:
        assert Decimal(str(row["room"]["width_m"])) == Decimal("45.76")
        assert Decimal(str(row["room"]["depth_m"])) == Decimal("13.6")
        assert (
            row["v2_area_authority_pass"] is False and row["functional_station_layout_pass"] is None
        )
        assert all(r["topology"] == "DIRECT_SHARED_EDGE" for r in row["actual_interfaces"])
        p = next(r for r in row["actual_interfaces"] if r["packaging_authority_applies"])
        assert p["sorting_physical_wall"]["edge_class"] == "SHORT_EDGE"
        assert p["other_physical_wall"]["edge_class"] == "LONG_EDGE"


def test_wall_exact_and_rotated_room_support_without_access_search() -> None:
    rect = c.box({"x": 0, "y": 0, "width_m": 4, "depth_m": 2, "rotation_deg": 90})
    assert rect == (0, 0, 2000, 4000)
    assert (
        c.wall({"start": {"x": 0, "y": 0}, "end": {"x": 0, "y": 1}}, rect)["edge_class"]
        == "LONG_EDGE"
    )
    with pytest.raises(ValueError, match="RECORDED_PORTAL_NOT_ON_ROOM_WALL"):
        c.wall({"start": {"x": 1, "y": 0}, "end": {"x": 1, "y": 1}}, rect)


def test_sources_have_scope_limits_not_project_equipment_defaults() -> None:
    sources = json.loads((HERE / "engineering-sources.json").read_text())["sources"]
    assert len(sources) == 7
    required = {
        "SOURCE_TITLE",
        "SOURCE_URL",
        "PUBLISHER",
        "VERSION",
        "DATE",
        "APPLICABILITY",
        "ENGINEERING_FACT",
        "EVIDENCE_LEVEL",
        "LIMITATIONS",
    }
    assert all(required <= set(s) and s["LIMITATIONS"] for s in sources)
    assert (
        sources[5]["ID"] == "E06"
        and "not used as a proposed project size" in sources[5]["LIMITATIONS"]
    )


def test_protected_sources_contracts_and_owner_files_unchanged() -> None:
    audit = json.loads((HERE / "legacy-geometry-authority-audit.json").read_text())
    assert c.source_audit() == audit["files"]
    for relative, record in audit["files"].items():
        old = subprocess.check_output(["git", "show", f"{c.REFERENCE}:{relative}"], cwd=c.REPO)
        assert c.hashlib.sha256(old).hexdigest() == record["sha256"]
    for folder in (c.V2, HERE.parent / "owner-functional-input-contract-r1"):
        for relative, digest in json.loads((folder / "source_manifest.json").read_text())[
            "files"
        ].items():
            assert c.sha(folder / relative) == digest


def test_no_solver_or_grant_or_network_execution_imports() -> None:
    tree = ast.parse((HERE / "offline_geometry_calibration.py").read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(n.name for n in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(
        any(
            x in name
            for x in (
                "ortools",
                "global_cp_sat",
                "stage_b_pool_execution",
                "requests",
                "urllib",
                "httpx",
            )
        )
        for name in imports
    )


def test_generated_outputs_byte_deterministic_and_match_records() -> None:
    names = (
        "legacy-geometry-authority-audit.json",
        "legacy-projection-scenarios.json",
        "real-layout-interface-review.json",
        "station-space-requirements.json",
    )
    before = {name: (HERE / name).read_bytes() for name in names}
    outputs = c.build()
    assert {name: c.encode(value) for name, value in outputs.items()} == before
    assert {name: (HERE / name).read_bytes() for name in names} == before
