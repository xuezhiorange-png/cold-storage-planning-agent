"""P2B1 maneuver-template contract, scope and non-solver architecture locks."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.truck_maneuver import (
    CONTRACT_IDENTITY,
    DEFAULT_MANEUVER_GEOMETRY_ALLOWED,
    DEFAULT_TRUCK_ALLOWED,
    DOCK_REVERSE,
    KINEMATIC_SOLVER_REQUIRED,
    MANEUVER_90_DEGREE_TURN,
    MANEUVER_DOCK_REVERSE,
    MANEUVER_STRAIGHT_APPROACH,
    P2_COMPLETE,
    P3_AUTHORIZED,
    STRAIGHT_APPROACH,
    SUPPORTED_MANEUVER_CLASSES,
    SUPPORTED_TRANSFORM_ROTATIONS,
    TEMPLATE_SCHEMA_VERSION,
    TRUCK_REPRESENTATION,
    TURN_90,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = "ccd6336de4810012deec64c1b0a5f3256ff13d85"
SELF = "backend/tests/architecture/test_v22_p2b1_truck_maneuver_template_contract.py"
RUNTIME = {"backend/src/cold_storage/modules/layout/domain/truck_maneuver.py"}
UNIT = "backend/tests/unit/test_v22_p2b1_truck_maneuver_templates.py"
DOC = "docs/tasks/V2_2-P2B1-truck-maneuver-template-contract.md"
ALLOWED = RUNTIME | {
    SELF,
    UNIT,
    DOC,
    "docs/tasks/V2_2-version-plan.md",
    "docs/tasks/V2_2-P2A-site-geometry-foundation.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
}

PROTECTED = {
    "backend/src/cold_storage/modules/layout/domain/project_truck_input.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/p1_project_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        paths = set(git("diff", "--name-only", BASE, target).splitlines())
    else:
        paths = set(git("diff", "--name-only", BASE).splitlines())
        paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def test_scope_is_additive_from_p2a_and_does_not_touch_prior_authority() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    changed = _changed_paths()
    assert changed <= ALLOWED
    assert not changed & PROTECTED
    for path in PROTECTED:
        if (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"], cwd=ROOT, capture_output=True
            ).returncode
            == 0
        ):
            subprocess.run(
                ["git", "diff", "--quiet", BASE, "HEAD", "--", path], cwd=ROOT, check=True
            )


def test_template_module_has_only_layout_domain_dependencies_and_no_solver_language() -> None:
    path = ROOT / next(iter(RUNTIME))
    source = path.read_text()
    lowered = source.lower()
    for forbidden in (
        "wheelbase",
        "steering_angle",
        "ackermann",
        "minimum_turn_radius",
        "dynamic_simulation",
        "path_discretization",
        "swept_path_generation",
        "placement_search",
        "route_search",
        "objective_profile",
        "site_placement",
        "portal_placement",
        "generate_svg",
        "generate_pdf",
        "generate_dxf",
    ):
        assert forbidden not in lowered

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"json", "re"}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in {
                "__future__",
                "collections.abc",
                "dataclasses",
                "decimal",
                "typing",
            } or (module.startswith("cold_storage.modules.layout.domain."))
            assert not module.startswith(("fastapi", "sqlalchemy", "requests", "httpx"))


def test_owner_representation_and_non_placement_flags_are_frozen() -> None:
    assert CONTRACT_IDENTITY == "truck-maneuver-template-contract@1.0.0"
    assert TEMPLATE_SCHEMA_VERSION == "1.0.0"
    assert TRUCK_REPRESENTATION == "OPTION_C_APPROVED_MANEUVER_TEMPLATES"
    assert SUPPORTED_MANEUVER_CLASSES == (STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE)
    assert MANEUVER_STRAIGHT_APPROACH
    assert MANEUVER_90_DEGREE_TURN
    assert MANEUVER_DOCK_REVERSE
    assert SUPPORTED_TRANSFORM_ROTATIONS == (0, 90, 180, 270)
    assert DEFAULT_TRUCK_ALLOWED is False
    assert DEFAULT_MANEUVER_GEOMETRY_ALLOWED is False
    assert KINEMATIC_SOLVER_REQUIRED is False
    assert P2_COMPLETE is False
    assert P3_AUTHORIZED is False


def test_p2b1_docs_record_the_decision_and_explicit_boundaries() -> None:
    text = (ROOT / DOC).read_text()
    for token in (
        "TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES",
        "OWNER_APPROVED=true",
        "MANEUVER_CLASSES=STRAIGHT_APPROACH,TURN_90,DOCK_REVERSE",
        "DEFAULT_TRUCK=false",
        "DEFAULT_TEMPLATE=false",
        "KINEMATIC_SOLVER=false",
        "PLACEMENT_SEARCH=false",
        "OBJECTIVE_PROFILE_FROZEN=false",
        "P2_COMPLETE=false",
        "P3_AUTHORIZED=false",
        "P1F_HISTORICAL_INPUT_SCHEMA_MUTATED=false",
        "FLOAT_EPSILON_ALLOWED=false",
        "REFERENCE_FRAME=LOCAL_TEMPLATE_FRAME",
        "DOCK_FACE_REFERENCE=shipping_channel.LONG_EDGE_LOADING_FACE",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert token in text


def test_old_p1f_input_contract_is_not_a_template_alias() -> None:
    source = (
        ROOT / "backend/src/cold_storage/modules/layout/domain/project_truck_input.py"
    ).read_text()
    template = (
        ROOT / "backend/src/cold_storage/modules/layout/domain/truck_maneuver.py"
    ).read_text()
    assert 'IDENTITY = "truck-project-access-input@1.0.0"' in source
    assert "TruckProjectAccessInputV1" not in template
    assert "truck-project-access-input@1.0.0" not in template
