"""Immutable P1B scope, narrow authority imports and exact approved profile set."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_zones import upstream_profiles
from cold_storage.modules.layout.domain.precool_dimensioning import PRECOOL_ZONES, precool_profiles

ROOT = Path(__file__).resolve().parents[3]
BASE = "ae9794d0454fa64ba7db6a94d9a3faeba5df00bd"
SELF = "backend/tests/architecture/test_v22_p1b_precool_dimensioning.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/domain/precool_dimensioning.py",
    "backend/src/cold_storage/modules/layout/application/dimension_zones.py",
}
ALLOWED = RUNTIME | {
    SELF,
    "backend/tests/unit/test_v22_p1b_precool_dimensioning.py",
    "backend/tests/unit/test_v22_p1a_dimensioning_adjacency.py",
    "docs/tasks/V2_2-P1B-precool-dimension-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_immutable_p1b_scope_and_no_existing_engineering_changes() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    changed = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if not target:
        changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    else:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    assert changed and changed <= ALLOWED
    assert {p for p in changed if p.startswith("backend/src/")} <= RUNTIME


def test_exact_two_shared_precool_profiles_no_other_new_authority() -> None:
    profiles = precool_profiles()
    assert [
        (p.identity, str(p.single_room_width_m), str(p.single_room_depth_m)) for p in profiles
    ] == [
        ("precool-room-6-position@1.0.0", "4.90", "10.05"),
        ("precool-room-8-position@1.0.0", "4.90", "12.95"),
    ]
    assert PRECOOL_ZONES == ("primary_precooling_room", "secondary_precooling_room")
    assert len(upstream_profiles()) == 4
    assert all(p.room_arrangement == "LONG_SIDES_PARALLEL" for p in profiles)
    text = (ROOT / "docs/tasks/V2_2-P1B-precool-dimension-authority.md").read_text()
    for flag in (
        "DIMENSIONED_ZONE_COUNT=6",
        "BLOCKED_ZONE_COUNT=6",
        "P2_AUTHORIZED=false",
        "MCP_RUNTIME_CHANGED=false",
        "SITE_PLACEMENT_IMPLEMENTED=false",
    ):
        assert flag in text


def test_new_domain_has_no_planner_dependency_or_capacity_solver() -> None:
    source = (
        ROOT / "backend/src/cold_storage/modules/layout/domain/precool_dimensioning.py"
    ).read_text()
    allowed = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "decimal",
        "typing",
        "cold_storage.modules.layout.domain.dimensioning",
    }
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"ceil", "sqrt", "round", "ColdRoomZonePlanner"}
