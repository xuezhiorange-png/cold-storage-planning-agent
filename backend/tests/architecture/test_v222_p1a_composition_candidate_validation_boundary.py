"""The S4 bridge may orchestrate validators but cannot own or repair geometry."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = (
    ROOT / "src/cold_storage/modules/layout/application/composition_candidate_validation.py"
)
FORBIDDEN_MARKERS = ("svg", "mcp", "frontend", "database", "sqlalchemy")
ALLOWED_MODULES = {
    "cold_storage.modules.layout.application.access_routing",
    "cold_storage.modules.layout.application.composition_placement",
    "cold_storage.modules.layout.application.dimension_zones",
    "cold_storage.modules.layout.application.layout_authority_binding",
    "cold_storage.modules.layout.application.site_geometry",
    "cold_storage.modules.layout.application.structural_composition",
    "cold_storage.modules.layout.domain.adjacency",
    "cold_storage.modules.layout.domain.composition_placement",
    "cold_storage.modules.layout.domain.dimensioning",
    "cold_storage.modules.layout.domain.objective_profile",
    "cold_storage.modules.layout.domain.placement",
    "cold_storage.modules.layout.domain.site_geometry",
    "cold_storage.modules.layout.domain.truck_maneuver",
}


def test_composition_validation_application_imports_only_replay_and_existing_authorities() -> None:
    tree = ast.parse(APPLICATION.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(
                alias.name for alias in node.names if alias.name.startswith("cold_storage")
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("cold_storage")
        ):
            imported.add(node.module)
    assert imported <= ALLOWED_MODULES
    assert "cold_storage.modules.layout.application.access_routing" in imported
    assert "cold_storage.modules.layout.application.composition_placement" in imported
    assert "cold_storage.modules.layout.application.validated_candidate_selection" not in imported
    assert not any(marker in module.lower() for marker in FORBIDDEN_MARKERS for module in imported)


def test_bridge_uses_hash_reference_and_never_repairs_or_selects_geometry() -> None:
    source = APPLICATION.read_text()
    tree = ast.parse(source)
    public = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "validate_composition_candidate"
    )
    assert [argument.arg for argument in public.args.args][-1] == "candidate_hash"
    assert "CompositionPlacementCandidateV1" not in {argument.arg for argument in public.args.args}
    assert "route_site_placement(" in source
    assert "geometry_repair_performed" in source
    assert "place_zones(" not in source
    assert "select_validated_placement(" not in source
    assert "while " not in source
