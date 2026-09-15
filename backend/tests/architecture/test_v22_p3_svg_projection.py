"""Durable architecture locks for the V2.2 P3 SVG projection."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.svg_projection import (
    SVG_PROJECTION_IDENTITY,
)
from cold_storage.modules.layout.domain.svg_projection import (
    EXPECTED_ZONE_CODES,
    LAYER_ORDER,
    SVG_SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
BASE = "a1d035c4d42a2bc4895e6d3806d3f5fe77e7e0d2"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
APPLICATION = "backend/src/cold_storage/modules/layout/application/svg_projection.py"
UNIT = "backend/tests/unit/test_v22_p3_svg_projection.py"
SELF = "backend/tests/architecture/test_v22_p3_svg_projection.py"
DOC = "docs/tasks/V2_2-P3-validated-layout-svg-projection.md"
ALLOWED = {DOMAIN, APPLICATION, UNIT, SELF, DOC}
ALLOWED |= {
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
}
PROTECTED_RUNTIME = {
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "frontend/src",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target is None:
        return set()
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=REPO_ROOT, check=True
    )
    return set(_git("diff", "--name-only", BASE, target).splitlines())


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_p3_scope_is_historical_and_projection_only() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=REPO_ROOT, check=True)
    changed = _historical_changed_paths()
    assert changed <= ALLOWED
    assert not any(
        path in PROTECTED_RUNTIME or path.startswith("frontend/src/") for path in changed
    )


def test_p3_does_not_change_p2_or_downstream_runtime() -> None:
    target = _historical_target()
    if target is None:
        diff = _git("diff", "--name-only", BASE, "HEAD").splitlines()
        diff.extend(_git("ls-files", "--others", "--exclude-standard").splitlines())
    else:
        diff = _git("diff", "--name-only", BASE, target).splitlines()
    protected_paths = sorted(path for path in PROTECTED_RUNTIME if "/" in path)
    assert not set(diff).intersection(protected_paths)
    assert "backend/src/cold_storage/modules/aily/api/mcp_sse.py" not in diff


def test_p3_identity_layers_and_source_requirements_are_frozen() -> None:
    assert SVG_PROJECTION_IDENTITY == "validated-layout-svg-projection@1.0.0"
    assert SVG_SCHEMA_VERSION == "1.0.0"
    assert LAYER_ORDER == (
        "site-boundary",
        "site-constraints",
        "building-footprint",
        "zones",
        "portals",
        "corridors",
        "truck-maneuvers",
        "entrances",
        "dimensions",
        "labels",
        "legend",
    )
    assert len(EXPECTED_ZONE_CODES) == 12
    assert len(set(EXPECTED_ZONE_CODES)) == 12
    application = _source(APPLICATION)
    assert "project_layout_validated" in application
    assert "p2_complete" in application
    assert "VALIDATED_LAYOUT_REQUIRED" in application
    assert "source_site_geometry_hash" in application


def test_p3_application_uses_validated_inputs_without_engineering_bypass() -> None:
    tree = ast.parse(_source(APPLICATION))
    allowed = {
        "cold_storage.modules.layout.application.access_routing",
        "cold_storage.modules.layout.application.site_geometry",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.layout.domain.svg_projection",
        "__future__",
        "collections.abc",
        "re",
        "typing",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"re"}
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed
    source = _source(APPLICATION)
    assert "route_site_placement" not in source
    assert "calculate_" not in source
    assert "mcp" not in source.lower()
    assert "fastapi" not in source.lower()


def test_p3_domain_is_static_svg_serialization_only() -> None:
    tree = ast.parse(_source(DOMAIN))
    allowed_modules = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "decimal",
        "hashlib",
        "typing",
        "xml.sax.saxutils",
        "cold_storage.modules.layout.domain.dimensioning",
        "cold_storage.modules.layout.domain.site_geometry",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"hashlib", "json", "re"}
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_modules
    source = _source(DOMAIN)
    for forbidden in (
        "route_site_placement",
        "calculate_",
        "random",
        "timestamp",
        "foreignObject",
        "javascript:",
        "onload",
        "onclick",
    ):
        assert forbidden not in source
    assert "projection_only" in source
    assert "engineering_coordinates_mutated" in source
    assert "escape(" in source
    assert "quoteattr(" in source
    assert "SVG_THEME_INVALID" in source
    assert "^#[0-9A-Fa-f]{6}$" in source
