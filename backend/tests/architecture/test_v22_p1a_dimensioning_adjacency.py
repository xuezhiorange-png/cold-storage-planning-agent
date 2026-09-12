"""P1A authority, dependency and immutable task-scope locks."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_zones import GRID_ZONES, upstream_profiles
from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, ZONE_CODES, process_graph

ROOT = Path(__file__).resolve().parents[3]
BASE = "e963256c56d20f90a880a61d0bc721d28c0a9c38"
SELF = "backend/tests/architecture/test_v22_p1a_dimensioning_adjacency.py"
MODULE = "backend/src/cold_storage/modules/layout/"
DOC = "docs/tasks/V2_2-P1A-zone-dimensioning-adjacency-foundation.md"
DOCS = {
    DOC,
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_task_scope_uses_immutable_introducing_commit_not_future_head() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        changed = set(git("diff", "--name-only", BASE, target).splitlines())
    else:
        changed = set(git("diff", "--name-only", BASE).splitlines())
        changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    allowed = DOCS | {SELF, "backend/tests/unit/test_v22_p1a_dimensioning_adjacency.py"}
    assert changed
    assert all(path in allowed or path.startswith(MODULE) for path in changed)
    # The only production addition is the isolated layout foundation.
    if target:
        assert all(
            line.startswith("A\t")
            for line in git("diff", "--name-status", BASE, target, "--", MODULE).splitlines()
        )


def test_runtime_graph_matches_current_p0_not_a_duplicate_test_constant() -> None:
    contract = (ROOT / "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md").read_text()
    flow = re.findall(r"^主物流（方向固定）：(.+?)。$", contract, re.MULTILINE)
    assert flow == [" → ".join(PROCESS_FLOW)]
    graph = process_graph()
    must = re.findall(
        r"^\| MUST_ADJACENT / ZONE_ADJACENCY \| (\w+) ↔ (\w+) \|$", contract, re.MULTILINE
    )
    should = re.findall(
        r"^\| SHOULD_ADJACENT / ZONE_ADJACENCY \| (\w+) ↔ (\w+) \|$", contract, re.MULTILINE
    )
    proximity = re.findall(
        r"^\| SHOULD_ADJACENT / ZONE_ACCESS_PROXIMITY \| (\w+) ↔ (\w+) \|$", contract, re.MULTILINE
    )
    assert tuple(must) == graph.must_adjacencies and len(must) == 6
    assert tuple(should) == graph.should_adjacencies
    assert tuple(proximity) == graph.zone_access_proximities
    assert len(ZONE_CODES) == 12
    assert "packaging_material_storage" not in {a for pair in must for a in pair}


def test_layout_dependency_direction_and_no_parallel_planner() -> None:
    allowed_calculation_names = {
        "FORMULA_AUTHORITY",
        "PALLET_PITCH_ALONG_WALL_M",
        "PALLET_PITCH_DEPTH_M",
        "RAW_AISLE_M",
        "STORAGE_ONE_AISLE_M",
    }
    # Lock this foundation, not all future layout/API modules authorized in P2/P4.
    paths = ("domain/dimensioning.py", "domain/adjacency.py", "application/dimension_zones.py")
    for relative in paths:
        path = ROOT / MODULE / relative
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
                if node.module and node.module.startswith("cold_storage.modules.calculations"):
                    assert "application" in path.parts
                    assert node.module == "cold_storage.modules.calculations.domain.zone_planning"
                    assert {alias.name for alias in node.names} <= allowed_calculation_names
            else:
                continue
            for module in imports:
                if module.startswith("cold_storage.modules.calculations"):
                    assert isinstance(node, ast.ImportFrom)
                assert not module.startswith(
                    ("fastapi", "sqlalchemy", "requests", "httpx", "random")
                )
                if "domain" in path.parts:
                    assert ".application" not in module
                    assert ".calculations" not in module
        assert not re.search(r"\b(sqrt|_pack_rectangle|ColdRoomZonePlanner)\s*\(", path.read_text())


def test_profiles_only_bind_existing_geometry_and_no_unapproved_dimensions() -> None:
    profiles = upstream_profiles()
    assert {profile.zone_code for profile in profiles} == set(GRID_ZONES)
    assert len(profiles) == 4
    assert all(profile.dimensioning_mode == "UPSTREAM_GRID" for profile in profiles)
    assert all(profile.capacity_geometry_policy == "PRESERVE_UPSTREAM" for profile in profiles)
    assert all(profile.rotation_allowed == (0, 90) for profile in profiles)
    text = (ROOT / DOC).read_text()
    for flag in (
        "DIMENSIONED_ZONE_COUNT=4",
        "BLOCKED_ZONE_COUNT=8",
        "P2_AUTHORIZED=false",
        "SITE_PLACEMENT_IMPLEMENTED=false",
        "MCP_RUNTIME_CHANGED=false",
    ):
        assert flag in text
