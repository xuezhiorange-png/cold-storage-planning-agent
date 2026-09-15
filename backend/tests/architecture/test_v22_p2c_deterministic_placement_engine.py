"""P2C placement scope, authority bindings and non-routing architecture locks."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.objective_profile import (
    PLACEMENT_OBJECTIVE_ORDER,
    approved_objective_profile,
)
from cold_storage.modules.layout.domain.placement import (
    FLEXIBLE_ZONE_CODES,
    IDENTITY,
    PLACEMENT_RESULT_IDENTITY,
    PLACEMENT_ZONE_ORDER,
    SCHEMA_VERSION,
    SEARCH_PROFILE_IDENTITY,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = "776d6836975d5f27a0261820548425e798919f03"
SELF = "backend/tests/architecture/test_v22_p2c_deterministic_placement_engine.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
}
UNIT = "backend/tests/unit/test_v22_p2c_deterministic_placement.py"
DOC = "docs/tasks/V2_2-P2C-deterministic-placement-engine.md"
ALLOWED = RUNTIME | {
    SELF,
    UNIT,
    DOC,
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
}
PROTECTED_RUNTIME = {
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/layout/domain/adjacency.py",
    "backend/src/cold_storage/modules/layout/domain/dimensioning.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/domain/objective_profile.py",
    "backend/src/cold_storage/modules/layout/domain/truck_maneuver.py",
    "backend/src/cold_storage/modules/layout/application/dimension_zones.py",
    "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/p1_project_handoff.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        return set(git("diff", "--name-only", BASE, target).splitlines())
    paths = set(git("diff", "--name-only", BASE, "HEAD").splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def test_scope_is_additive_and_protects_all_prior_runtime_authority() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    changed = _historical_changed_paths()
    assert changed <= ALLOWED
    assert not changed & PROTECTED_RUNTIME
    for path in RUNTIME:
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            != 0
        )


def test_placement_domain_has_only_domain_dependencies() -> None:
    path = ROOT / "backend/src/cold_storage/modules/layout/domain/placement.py"
    source = path.read_text()
    lowered = source.lower()
    for forbidden in (
        "fastapi",
        "sqlalchemy",
        "requests",
        "httpx",
        "portal_placement",
        "corridor_generation",
        "truck_path_solver",
        "kinematic_solver",
        "generate_svg",
        "generate_pdf",
        "generate_dxf",
        "a_star",
    ):
        assert forbidden not in lowered
    allowed_stdlib = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "decimal",
        "fractions",
        "math",
        "typing",
    }
    allowed_domain = {
        "cold_storage.modules.layout.domain.adjacency",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.layout.domain.objective_profile",
        "cold_storage.modules.layout.domain.site_geometry",
    }
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"json"}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_stdlib | allowed_domain
            if module.startswith("cold_storage"):
                assert module in allowed_domain
                assert module.startswith("cold_storage.modules.layout.domain.")


def test_p2c_identity_zone_set_and_objective_binding_are_exact() -> None:
    graph = process_graph()
    assert IDENTITY == "site-constrained-deterministic-placement@1.0.0"
    assert PLACEMENT_RESULT_IDENTITY == "site_constrained_factory_layout@1.0.0"
    assert SEARCH_PROFILE_IDENTITY == "deterministic-placement-search@1.0.0"
    assert SCHEMA_VERSION == "1.0.0"
    assert len(PLACEMENT_ZONE_ORDER) == len(ZONE_CODES) == 12
    assert set(PLACEMENT_ZONE_ORDER) == set(ZONE_CODES)
    assert FLEXIBLE_ZONE_CODES == ("coating_room", "changing_room", "office")
    assert len(graph.must_adjacencies) == 7
    assert len(graph.should_adjacencies) == 5
    assert approved_objective_profile().placement_priority_order == PLACEMENT_OBJECTIVE_ORDER
    assert PLACEMENT_OBJECTIVE_ORDER == ("SHOULD_ADJACENT", "LOADING_SIDE_PREFERENCE")


def test_p2c_runtime_status_does_not_claim_route_or_final_layout_validation() -> None:
    source = (ROOT / "backend/src/cold_storage/modules/layout/domain/placement.py").read_text()
    application = (
        ROOT / "backend/src/cold_storage/modules/layout/application/placement.py"
    ).read_text()
    for text in (source,):
        assert "p2_complete" in text
        assert "routing_validated" in text
        assert "access_route_validated" in text
        assert "truck_route_validated" in text
        assert "project_layout_validated" in text
    assert "search_placement" in application
    doc = (ROOT / DOC).read_text()
    for token in (
        "P2C_AUTHORIZED=true",
        "P2C_STATUS=IMPLEMENTED_DRAFT_REVIEW",
        "PLACEMENT_SEARCH_IMPLEMENTED=true",
        "PLACEMENT_FOUND",
        "LAYOUT_SEARCH_EXHAUSTED",
        "LAYOUT_INFEASIBLE_PROOF_IMPLEMENTED=false",
        "ROUTING_IMPLEMENTED=false",
        "ACCESS_ROUTE_VALIDATED=false",
        "TRUCK_ROUTE_VALIDATED=false",
        "PROJECT_LAYOUT_VALIDATED=false",
        "P2_COMPLETE=false",
        "P3_AUTHORIZED=false",
        "P4_AUTHORIZED=false",
        "P5_AUTHORIZED=false",
        "NO_MCP_TOOL_7=true",
        "NO_SVG_PDF_DXF=true",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert token in doc


def test_p2c_documents_preserve_objective_and_authority_boundaries() -> None:
    doc = (ROOT / DOC).read_text()
    for token in (
        "ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN",
        "FIXED_RECTANGLE_RESIZE_ALLOWED=false",
        "DETERMINISTIC_GRID_RECTANGLE_RESIZE_ALLOWED=false",
        "FLEXIBLE_DIMENSION_SELECTION_ALLOWED=true",
        "NO_ASPECT_RATIO_AUTHORITY_CREATED=true",
        "MUST_ADJACENT_COUNT=7",
        "SHOULD_ADJACENT_COUNT=5",
        "OBJECTIVE_AGGREGATION=LEXICOGRAPHIC",
        "NEAREST_TRUCK_ENTRANCE_COMPARATOR=EXACT_MIN_SEGMENT_TO_SEGMENT_SQUARED_EUCLIDEAN_DISTANCE",
        "FLOAT_EPSILON_ALLOWED=false",
        "SQRT_REQUIRED_FOR_RANKING=false",
        "COMPACTNESS_ACTIVE=false",
        "SHAPE_REGULARITY_ACTIVE=false",
        "UNUSED_SITE_EFFICIENCY_ACTIVE=false",
        "PORTAL_PLACEMENT=false",
        "CORRIDOR_GENERATION=false",
        "TRUCK_PATH_SEARCH=false",
    ):
        assert token in doc
