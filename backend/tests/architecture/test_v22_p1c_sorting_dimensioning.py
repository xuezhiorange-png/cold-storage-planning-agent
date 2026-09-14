"""Immutable P1C scope and narrow sorting-only production authority boundary."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_zones import IDENTITY, upstream_profiles
from cold_storage.modules.layout.application.sorting_dimension_authority import sorting_profile
from cold_storage.modules.layout.domain.precool_dimensioning import precool_profiles

ROOT = Path(__file__).resolve().parents[3]
BASE = "7785e877461a2c82980ed4e318bd04eabc0287df"
SELF = "backend/tests/architecture/test_v22_p1c_sorting_dimensioning.py"
MODULE = "backend/src/cold_storage/modules/layout/"
RUNTIME = {
    MODULE + "domain/dimensioning.py",
    MODULE + "application/dimension_zones.py",
    MODULE + "application/sorting_dimension_authority.py",
}
ALLOWED = RUNTIME | {
    SELF,
    "backend/tests/architecture/test_v22_p1c0_area_precision.py",
    "backend/tests/unit/test_v22_p1c_sorting_dimensioning.py",
    "backend/tests/unit/test_v22_p1a_dimensioning_adjacency.py",
    "backend/tests/unit/test_v22_p1b_precool_dimensioning.py",
    "backend/tests/unit/test_v22_p1c0_area_precision.py",
    "backend/tests/v22_p1c0_historical_application.py",
    "docs/tasks/V2_2-P1C-sorting-packaging-dimension-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_immutable_scope_preserves_upstream_and_all_non_layout_runtime() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    changed = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    else:
        changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed and changed <= ALLOWED
    assert {p for p in changed if p.startswith("backend/src/")} <= RUNTIME


def test_one_new_profile_and_no_solver_or_consumer_entrypoint() -> None:
    assert IDENTITY == "zone_dimensioning_foundation@1.3.0"
    assert len(upstream_profiles()) == 4 and len(precool_profiles()) == 2
    profile = sorting_profile()
    assert profile.identity == "upstream-sorting-long-edge-envelope@1.0.0"
    assert profile.zone_code == "sorting_packaging_room"
    assert profile.dimensioning_mode == "UPSTREAM_GRID"
    binder = (ROOT / MODULE / "application/sorting_dimension_authority.py").read_text()
    allowed = {
        "collections.abc",
        "decimal",
        "typing",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.calculations.domain.zone_planning",
    }
    for node in ast.walk(ast.parse(binder)):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
            if node.module == "cold_storage.modules.calculations.domain.zone_planning":
                assert {a.name for a in node.names} == {
                    "FORMULA_AUTHORITY",
                    "PACKING_TABLE_PITCH_LONG_M",
                    "PACKING_TABLE_PITCH_SHORT_M",
                    "SORTING_CLEARANCE_LONG_M",
                    "SORTING_CLEARANCE_SHORT_M",
                    "SORTING_PACKAGING_AREA_FACTOR",
                }
        elif isinstance(node, ast.Import):
            assert all(a.name in allowed for a in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"ceil", "sqrt", "round", "range", "ColdRoomZonePlanner"}
    domain = (ROOT / MODULE / "domain/dimensioning.py").read_text()
    assert "sorting_packaging_room" not in domain
    assert "if actual < requirement.geometric_lower_bound_m2:" in domain
    doc = (ROOT / "docs/tasks/V2_2-P1C-sorting-packaging-dimension-authority.md").read_text()
    for flag in (
        "NO_EPSILON=true",
        "NO_GEOMETRY_INFLATION=true",
        "P2_AUTHORIZED=false",
        "MCP_RUNTIME_CHANGED=false",
        "SITE_PLACEMENT_IMPLEMENTED=false",
        "DIMENSIONED_ZONE_COUNT=7",
        "BLOCKED_ZONE_COUNT=5",
    ):
        assert flag in doc
