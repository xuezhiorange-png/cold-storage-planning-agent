"""P0 contract/schema locks and immutable v2.1.2 boundary evidence.

No placement or geometric predicate implementation lives in these tests.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
BASE = "0a68597a40aa460ed31441c537ca37c3d4cfd1a7"
SELF = "backend/tests/architecture/test_v22_p0_site_constrained_layout_contract.py"
CONTRACT = "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md"
SCHEMA = "docs/tasks/V2_2-site-layout-input-v1.schema.json"
ALLOWED = {
    SELF,
    CONTRACT,
    PLAN,
    ADR,
    SCHEMA,
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}
FROZEN = (
    "backend/src",
    "frontend/src",
    "backend/alembic",
    ".github/workflows",
    "deployment",
    "docs/contracts/aily",
    "docs/runbooks",
)
ZONE_CODES = {
    "office",
    "changing_room",
    "primary_precooling_room",
    "secondary_precooling_room",
    "raw_fruit_buffer",
    "sorting_packaging_room",
    "coating_room",
    "finished_goods_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
    "packaging_material_storage",
    "shipping_channel",
}
FIVE_KEYS = [
    "daily_inbound_mass_kg",
    "finished_storage_days",
    "frozen_storage_days",
    "main_packaging_storage_days",
    "auxiliary_packaging_storage_days",
]
TOOLS = [
    "preview_zone_plan",
    "preview_cooling_load",
    "preview_equipment",
    "preview_installed_power",
    "preview_investment",
    "preview_factory_power",
]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _scope_target() -> str | None:
    # The introducing commit contains the entire reviewed P0 candidate, including
    # this guard. Its object id is immutable; later lanes do not extend its diff.
    # Before that first commit exists, local validation checks the working candidate.
    commits = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return commits.splitlines()[0] if commits else None


def _task_text(path: str) -> str:
    target = _scope_target()
    return _git("show", f"{target}:{path}") if target else (ROOT / path).read_text()


def test_p0_scope_is_immutable_and_production_is_unchanged() -> None:
    assert _git("rev-parse", "v2.1.2^{}") == BASE
    target = _scope_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        changed = set(_git("diff", "--name-only", BASE, target).splitlines())
        subprocess.run(
            ["git", "diff", "--exit-code", BASE, target, "--", *FROZEN], cwd=ROOT, check=True
        )
    else:
        changed = set(_git("diff", "--name-only", BASE).splitlines())
        changed.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
        subprocess.run(["git", "diff", "--exit-code", BASE, "--", *FROZEN], cwd=ROOT, check=True)
    assert changed == ALLOWED


def test_p0_reads_actual_immutable_zone_planner_and_mcp_contract() -> None:
    # Execute the *released source*, never substitute current constants for history.
    # This proves the real 12-row planner and six-tool/five-key boundary while
    # allowing separately authorized future production development.
    archive = subprocess.check_output(["git", "archive", BASE, "backend/src"], cwd=ROOT)
    script = """
import json
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanner, ColdRoomZonePlanInput,
)
from cold_storage.modules.aily.api.mcp_sse import _PREVIEW_TOOL_ORDER
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
data = ColdRoomZonePlanInput(daily_inbound_mass_kg=20000, working_time_h_per_day=16,
    finished_storage_days=7, packaging_storage_days=3, precooling_required_ratio=1,
    frozen_storage_days=10, main_packaging_storage_days=4, auxiliary_packaging_storage_days=12)
result = ColdRoomZonePlanner().plan(data)
print(json.dumps({"success": result.success,
    "zones": [z["zone_code"] for z in result.result["zones"]],
    "tools": list(_PREVIEW_TOOL_ORDER), "keys": list(OPERATOR_V09_FIVE_KEY_FIELDS)}))
"""
    with TemporaryDirectory(prefix="v22-p0-historical-") as directory:
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(directory, filter="data")
        env = {**os.environ, "PYTHONPATH": str(Path(directory) / "backend/src")}
        actual = json.loads(
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=directory,
                env=env,
                text=True,
            )
        )
    assert actual["success"] is True
    assert len(actual["zones"]) == len(set(actual["zones"])) == 12
    assert set(actual["zones"]) == ZONE_CODES
    assert actual["tools"] == TOOLS
    assert actual["keys"] == FIVE_KEYS
    # Exact runtime tree equality above also protects the tools' inputSchema
    # and P1 upstream authority, not just names or counts.


def test_layout_authority_geometry_and_downstream_gates_are_frozen() -> None:
    contract = _task_text(CONTRACT)
    for marker in (
        "CANONICAL_LAYOUT_AUTHORITY=STRUCTURED_LAYOUT_JSON",
        "COORDINATE_SYSTEM=LOCAL_CARTESIAN_METERS",
        "COORDINATE_UNIT=m",
        "ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN",
        "ZONE_COUNT=12",
        "SITE_LAYOUT_MAY_NOT_RECALCULATE_ZONE_AREA=true",
        "FUTURE_MCP_TOOL_NAME=preview_site_layout",
        "FUTURE_MCP_TOOL_POSITION=7",
        "FUTURE_IDENTITY=site_constrained_factory_layout@1.0.0",
        "EXISTING_MCP_TOOL_COUNT=6",
        "EXISTING_MCP_CONTRACT_CHANGED=false",
        "EXISTING_FIVE_KEY_SCHEMA_CHANGED=false",
        "ORTHOGONAL_LAYOUT_ONLY=true",
        "FREE_ROTATION=false",
        "RECTANGULAR_ZONE_FOOTPRINT=true",
        "V22_P0_MCP_IMPLEMENTATION=false",
        "V22_P0_RUNTIME_IMPLEMENTATION=false",
        "V22_P0_FRONTEND_IMPLEMENTATION=false",
        "V22_P0_LAYOUT_ENGINE_IMPLEMENTATION=false",
        "DETERMINISTIC_LAYOUT_REQUIRED=true",
        "RANDOM_LAYOUT_WITHOUT_FIXED_SEED=false",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in contract
    for phase in range(1, 6):
        assert f"P{phase}_AUTHORIZED=false" in contract
        assert f"P{phase}_AUTHORIZED=false" in _task_text(PLAN)
    for code in ZONE_CODES:
        assert code in contract
    for field in (
        "source_zone_plan",
        "building",
        "zones",
        "accesses",
        "flows",
        "constraint_evaluation",
        "SiteLayoutResultV1",
        "schema_version=1.0.0",
    ):
        assert field in contract
    assert "ZONE_PLAN_GEOMETRY_REUSED_AS_UPSTREAM=true" in _task_text(ADR)
    assert "LAYOUT_DIMENSIONING_HAS_SEPARATE_AUTHORITY=true" in _task_text(ADR)
    assert "n_long / n_short" in _task_text(ADR)
    assert "不是外墙长宽比的硬限制" in _task_text(ADR)


def test_geometry_hard_constraints_and_failure_categories_are_explicit() -> None:
    contract = _task_text(CONTRACT)
    for code in (
        "INVALID_SITE_BOUNDARY",
        "SELF_INTERSECTING_SITE_BOUNDARY",
        "INVALID_BUILDABLE_BOUNDARY",
        "BUILDABLE_BOUNDARY_OUTSIDE_SITE",
        "INVALID_ENTRANCE",
        "NO_BUILD_ZONE_OUTSIDE_SITE",
        "EXISTING_BUILDING_OUTSIDE_SITE",
        "ZONE_PLAN_REQUIRED",
        "ZONE_PLAN_IDENTITY_INVALID",
        "INSUFFICIENT_BUILDABLE_AREA",
        "LAYOUT_INFEASIBLE",
        "HARD_CONSTRAINT_UNSATISFIABLE",
        "INVALID_INPUT",
        "VALID_INPUT_BUT_NO_FEASIBLE_LAYOUT",
        "LAYOUT_SEARCH_EXHAUSTED",
        "ZONE_DIMENSIONING_AUTHORITY_REQUIRED",
        "ACCESS_PROFILE_REQUIRED",
        "MUST_ADJACENT",
        "SHOULD_ADJACENT",
        "AVOID_ADJACENT",
        "ZONE_ADJACENCY",
        "ZONE_ACCESS_PROXIMITY",
        "ENGINEERING_DECISION_REQUIRED",
    ):
        assert code in contract
    assert "角点接触不算邻接" in contract
    assert "不能仅测试顶点" in contract
    assert "actual_area_m2>=required_area_m2" in contract
    assert "不静默删除点" in contract
    assert "不授权拆除" in contract


def _site() -> dict[str, Any]:
    return {
        "site_boundary": {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 80},
                {"x": 0, "y": 80},
            ],
        },
        "main_entrance": {"start": {"x": 1, "y": 0}, "end": {"x": 3, "y": 0}},
        "truck_entrance": {"start": {"x": 5, "y": 0}, "end": {"x": 12, "y": 0}},
    }


def _validator() -> Draft202012Validator:
    schema = json.loads(_task_text(SCHEMA))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_future_site_schema_accepts_explicit_shared_access_and_optional_defaults() -> None:
    site = _site()
    site["truck_entrance"] = deepcopy(site["main_entrance"])
    _validator().validate(site)
    assert "buildable_boundary" not in site  # validation must not fabricate geometry
    assert "north_angle_degrees" not in site


@pytest.mark.parametrize(
    "field",
    [
        "factory_area_m2",
        "cold_storage_area_m2",
        "zone_area_m2",
        "latitude",
        "longitude",
        "EPSG",
        "zone_plan",
        "fake_area",
    ],
)
def test_future_site_schema_rejects_engineering_area_and_gis_injection(field: str) -> None:
    site = _site()
    site[field] = 999
    assert not _validator().is_valid(site)


@pytest.mark.parametrize(
    "case",
    [
        "missing_site",
        "missing_access",
        "few_vertices",
        "duplicate_close",
        "bad_north",
        "bad_loading",
        "boolean_x",
    ],
)
def test_future_site_schema_rejects_structural_hostile_inputs(case: str) -> None:
    site = _site()
    if case == "missing_site":
        del site["site_boundary"]
    elif case == "missing_access":
        del site["truck_entrance"]
    elif case == "few_vertices":
        site["site_boundary"]["points"] = site["site_boundary"]["points"][:2]
    elif case == "duplicate_close":
        site["site_boundary"]["points"].append({"x": 0, "y": 0})
    elif case == "bad_north":
        site["north_angle_degrees"] = 360
    elif case == "bad_loading":
        site["preferred_loading_side"] = "NORTHEAST"
    else:
        site["site_boundary"]["points"][0]["x"] = True
    assert not _validator().is_valid(site)


def test_governance_current_release_is_distinct_from_historical_snapshots() -> None:
    for path in (
        PLAN,
        "docs/audit/current-state.md",
        "docs/audit/gap-analysis.md",
        "docs/roadmap/DEVELOPMENT_PLAN.md",
        "docs/TECH_DEBT.md",
    ):
        text = _task_text(path)
        assert "CURRENT_RELEASE=v2.1.2" in text
        assert "V2_1_2_RELEASED=true" in text
        assert f"RELEASE_TARGET_SHA={BASE}" in text
        assert "ACTIVE_GOVERNANCE_LANE=V2.2_P0" in text
        assert "DEPLOYMENT_EXECUTED=false" in text
