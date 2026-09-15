"""P2A scope, boundary and non-placement architecture locks."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain.site_geometry import (
    COORDINATE_SYSTEM,
    GRID_M,
    IDENTITY,
    SCHEMA_VERSION,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.unit.test_v22_p1f_project_truck_input import truck_input

ROOT = Path(__file__).resolve().parents[3]
BASE = "50210aa7cc876ed8a93a099c82ef4a4f287da82a"
SELF = "backend/tests/architecture/test_v22_p2a_site_geometry_foundation.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
}
DOCS = {
    "docs/tasks/V2_2-P2A-site-geometry-foundation.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}
ALLOWED = RUNTIME | DOCS | {SELF, "backend/tests/unit/test_v22_p2a_site_geometry.py"}
PROTECTED_RUNTIME = {
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def historical_target() -> str | None:
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def test_scope_is_additive_and_uses_immutable_introduction_commit() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    target = historical_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        changed = set(git("diff", "--name-only", BASE, target).splitlines())
    else:
        changed = set(git("diff", "--name-only", BASE).splitlines())
        changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
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


def test_geometry_module_has_no_solver_or_forbidden_runtime_dependency() -> None:
    for path in RUNTIME:
        source = (ROOT / path).read_text()
        tree = ast.parse(source)
        assert "epsilon" not in source.lower()
        assert "random" not in source.lower()
        assert "A*" not in source
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert {alias.name for alias in node.names} <= {"json"}
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(("fastapi", "sqlalchemy", "requests", "httpx"))
                if "/domain/" in path:
                    assert not module.startswith("cold_storage.modules.layout.application")
                else:
                    assert module.startswith("cold_storage.modules.layout.") or module in {
                        "collections.abc",
                        "dataclasses",
                        "decimal",
                        "__future__",
                        "typing",
                    }
        assert not any(
            name in source
            for name in (
                "site_placement",
                "placement_search",
                "route_solver",
                "generate_svg",
                "generate_pdf",
                "generate_dxf",
            )
        )


def test_p2a_contract_identity_and_non_placement_status() -> None:
    assert IDENTITY == "site-geometry-foundation@1.0.0"
    assert SCHEMA_VERSION == "1.0.0"
    assert COORDINATE_SYSTEM == "LOCAL_CARTESIAN_METERS"
    assert str(GRID_M) == "0.001"
    body = validate_site_geometry(
        {
            "site_constraints": {
                "site_boundary": {
                    "type": "polygon",
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 100, "y": 0},
                        {"x": 100, "y": 80},
                        {"x": 0, "y": 80},
                    ],
                },
                "main_entrance": {
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 5, "y": 0},
                },
                "truck_entrance": {
                    "start": {"x": 10, "y": 0},
                    "end": {"x": 20, "y": 0},
                },
            },
            "truck_access": truck_input(),
        },
        build_p1_project_handoff(snapshot(), truck_input()),
    ).to_dict()
    assert body["source_p1_handoff_identity"] == "p1-project-access-handoff@1.0.0"
    assert body["validation_status"] == "VALIDATED_GEOMETRY_FOUNDATION"
    assert body["placement_implemented"] is False
    assert body["routes_implemented"] is False
    assert body["portals_implemented"] is False
    assert body["requires_review"] is True


def test_p1_authority_and_existing_contracts_are_not_replaced() -> None:
    for path in PROTECTED_RUNTIME:
        subprocess.run(
            ["git", "diff", "--quiet", BASE, "HEAD", "--", path],
            cwd=ROOT,
            check=True,
        )
    p0 = (ROOT / "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md").read_text()
    for token in (
        "SITE_LAYOUT_MAY_NOT_RECALCULATE_ZONE_AREA=true",
        "raw_fruit_buffer → primary_precooling_room → sorting_packaging_room",
        "P1_COMPLETE=true",
    ):
        assert token in p0


def test_p2a_boundary_and_truck_decision_flags_are_explicit_in_docs() -> None:
    text = (ROOT / "docs/tasks/V2_2-P2A-site-geometry-foundation.md").read_text()
    for token in (
        "P2A_STATUS=IMPLEMENTED_DRAFT_REVIEW",
        "P2_PLACEMENT_ENGINE_COMPLETE=false",
        "P2_OBJECTIVE_PROFILE_FROZEN=false",
        "P2_TRUCK_TURNING_REPRESENTATION_FROZEN=false",
        "P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true",
        "NO_LAYOUT_ALGORITHM_IMPLEMENTATION",
        "NO_SVG_GENERATION",
        "NO_MCP_TOOL_7",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert token in text
