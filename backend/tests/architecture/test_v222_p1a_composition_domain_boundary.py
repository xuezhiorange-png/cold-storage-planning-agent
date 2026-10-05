"""The composition core must remain isolated from downstream runtime authorities."""

from __future__ import annotations

import ast
from pathlib import Path

MODULE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cold_storage"
    / "modules"
    / "layout"
    / "domain"
    / "structural_composition.py"
)
FORBIDDEN_IMPORT_MARKERS = (
    "access_routing",
    "truck_maneuver",
    "svg_projection",
    "mcp",
    "sqlalchemy",
    "database",
    ".application",
)


def test_composition_domain_imports_only_composition_and_adjacency_primitives() -> None:
    tree = ast.parse(MODULE.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    assert "cold_storage.modules.layout.domain.adjacency" in imports
    assert all(
        not any(marker in module.lower() for marker in FORBIDDEN_IMPORT_MARKERS)
        for module in imports
    )


def test_composition_domain_does_not_reference_downstream_runtime_entrypoints() -> None:
    source = MODULE.read_text()
    forbidden = (
        "route_access_requirement",
        "validate_truck_maneuver_chain",
        "route_site_placement",
        "project_layout_svg",
        "mcp.server",
        "Session(",
    )
    assert all(term not in source for term in forbidden)
