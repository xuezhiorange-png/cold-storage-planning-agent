"""Durable P2D access-routing and final-layout architecture locks."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.access_handoff import required_access_connections
from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    MATERIAL,
    PACKAGING,
    PERSONNEL,
    AccessClassV1,
    personnel_truck_policy,
)
from cold_storage.modules.layout.domain.access_routing import (
    CROSSING_NECESSITY_INFERRED_FROM_GEOMETRY,
    INCIDENT_ZONE_INTERIOR_TRANSIT_ALLOWED,
    PORTAL_ONLY_ZONE_BOUNDARY_TRANSIT,
    RESULT_IDENTITY,
    ROUTE_SEARCH_PROFILE_IDENTITY,
    SCHEMA_VERSION,
    TRUCK_REPRESENTATION,
    TRUCK_SEARCH_PROFILE_IDENTITY,
)
from cold_storage.modules.layout.domain.access_routing import (
    IDENTITY as ROUTING_IDENTITY,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
BASE = "99116fb8f5999461f718ad6a4d5747f1ec865716"
SELF = "backend/tests/architecture/test_v22_p2d_access_routing_and_truck_validation.py"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/access_routing.py"
APPLICATION = "backend/src/cold_storage/modules/layout/application/access_routing.py"
UNIT = "backend/tests/unit/test_v22_p2d_access_routing.py"
DOC = "docs/tasks/V2_2-P2D-access-routing-and-truck-validation.md"
ALLOWED = {DOMAIN, APPLICATION, UNIT, SELF, DOC}
ALLOWED |= {
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
}
PROTECTED_RUNTIME = {
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/access_authority.py",
    "backend/src/cold_storage/modules/layout/domain/access_predicates.py",
    "backend/src/cold_storage/modules/layout/domain/truck_maneuver.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target is not None:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", target, "HEAD"],
            cwd=REPO_ROOT,
            check=True,
        )
        return set(_git("diff", "--name-only", BASE, target).splitlines())
    paths = set(_git("diff", "--name-only", BASE, "HEAD").splitlines())
    paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_p2d_scope_is_historical_and_additive() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=REPO_ROOT, check=True)
    changed = _historical_changed_paths()
    assert changed <= ALLOWED
    assert not changed & PROTECTED_RUNTIME


def test_p2d_domain_has_only_layout_domain_dependencies() -> None:
    tree = ast.parse(_source(DOMAIN))
    allowed_stdlib = {
        "__future__",
        "collections",
        "collections.abc",
        "dataclasses",
        "decimal",
        "itertools",
        "typing",
    }
    allowed_domain = {
        "cold_storage.modules.layout.domain.access_authority",
        "cold_storage.modules.layout.domain.access_predicates",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.layout.domain.site_geometry",
        "cold_storage.modules.layout.domain.truck_maneuver",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= set()
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_stdlib | allowed_domain
            if module.startswith("cold_storage"):
                assert module in allowed_domain
                assert module.startswith("cold_storage.modules.layout.domain.")


def test_p2d_application_does_not_bypass_authority_or_add_mcp_paths() -> None:
    tree = ast.parse(_source(APPLICATION))
    allowed_application = {
        "cold_storage.modules.layout.application.dimension_zones",
        "cold_storage.modules.layout.application.placement",
        "cold_storage.modules.layout.application.site_geometry",
    }
    allowed_domain = {
        "cold_storage.modules.layout.domain.access_routing",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.layout.domain.objective_profile",
        "cold_storage.modules.layout.domain.placement",
        "cold_storage.modules.layout.domain.site_geometry",
        "cold_storage.modules.layout.domain.truck_maneuver",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module.startswith("cold_storage"):
            assert module in allowed_application | allowed_domain
            assert not module.startswith("cold_storage.modules.calculations")
            assert not module.startswith("cold_storage.modules.aily")
            assert not module.startswith("cold_storage.modules.projects")
    source = _source(APPLICATION)
    assert "_validate_p1_authority" in source
    assert "route_access_requirement" in source
    assert "validate_truck_maneuver_chain" in source
    assert "calculate_cooling_load" not in source
    assert "calculate_factory_power" not in source
    assert "preview_site_layout" not in source


def test_p2d_identity_and_authoritative_requirement_count_are_exact() -> None:
    requirements = required_access_connections()
    assert ROUTING_IDENTITY == "site-access-routing-and-validation@1.0.0"
    assert RESULT_IDENTITY == "site_validated_layout@1.0.0"
    assert SCHEMA_VERSION == "1.0.0"
    assert ROUTE_SEARCH_PROFILE_IDENTITY == "deterministic-rectilinear-access-routing@1.0.0"
    assert TRUCK_SEARCH_PROFILE_IDENTITY == "truck-maneuver-chain-search@1.0.0"
    assert TRUCK_REPRESENTATION == "OPTION_C_APPROVED_MANEUVER_TEMPLATES"
    assert INCIDENT_ZONE_INTERIOR_TRANSIT_ALLOWED is False
    assert PORTAL_ONLY_ZONE_BOUNDARY_TRANSIT is True
    assert CROSSING_NECESSITY_INFERRED_FROM_GEOMETRY is False
    assert len(requirements) == 12
    assert len({row.identity for row in requirements}) == 12
    assert sum(row.access_class == AccessClassV1.TRUCK for row in requirements) == 1
    assert sum(row.access_class == AccessClassV1.PERSONNEL for row in requirements) == 2
    assert sum(row.access_class == AccessClassV1.MATERIAL_LOGISTICS for row in requirements) == 9
    assert sum(row.profile_identity == PACKAGING for row in requirements) == 1
    assert sum(bool(row.cold_room_refs) for row in requirements) == 9
    assert COLD_ROOM not in {row.profile_identity for row in requirements}


def test_p2d_runtime_contract_keeps_final_validation_fail_closed() -> None:
    domain = _source(DOMAIN)
    application = _source(APPLICATION)
    for token in (
        "GRID_M = GRID",
        "portal_clear_width_m",
        "corridor_clear_width_m",
        "DIRECT_SHARED_EDGE",
        "CORRIDOR_MEDIATED",
        "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED",
        "ROUTE_SEARCH_EXHAUSTED",
        "BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED",
        "TRUCK_MANEUVER_SEARCH_EXHAUSTED",
        "PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW",
        "PERSONNEL_TRUCK_INTERACTION_REQUIRES_ENGINEERING_REVIEW",
        "CORRIDOR_INCIDENT_ZONE_CROSSING",
        "source_truck_maneuver_binding_hash",
        "project_layout_validated",
        "p2_complete",
    ):
        assert token in domain or token in application
    assert '"objective_optimization_active": False' in application
    assert '"p2_complete": project_valid' in application
    assert "midpoint" not in domain
    assert "crossing_necessary=crossing" not in domain
    assert '"crossing_necessary": "UNDETERMINED"' in domain


def test_p2d_owner_profiles_and_policy_are_not_reinvented() -> None:
    material = next(
        profile for profile in required_access_connections() if profile.profile_identity == MATERIAL
    )
    personnel = next(
        profile
        for profile in required_access_connections()
        if profile.profile_identity == PERSONNEL
    )
    assert material.profile_identity == MATERIAL
    assert personnel.profile_identity == PERSONNEL
    policy = personnel_truck_policy()
    assert policy["shared_route_allowed"] is False
    assert policy["crossing_allowed_if_necessary"] is True
    assert policy["crossing_requires_review"] is True
