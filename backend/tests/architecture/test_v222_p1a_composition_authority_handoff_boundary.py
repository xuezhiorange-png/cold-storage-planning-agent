"""The S2 binding layer stays upstream of placement and engineering validators."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = ROOT / "src/cold_storage/modules/layout/application/structural_composition.py"
PLACEMENT_APPLICATION = (
    ROOT / "src/cold_storage/modules/layout/application/composition_placement.py"
)
LEGACY_PLACEMENT_APPLICATION = ROOT / "src/cold_storage/modules/layout/application/placement.py"
SHARED_AUTHORITY_BINDING = (
    ROOT / "src/cold_storage/modules/layout/application/layout_authority_binding.py"
)
HANDOFF_DOMAIN = ROOT / "src/cold_storage/modules/layout/domain/composition_handoff.py"
STRUCTURAL_DOMAIN = ROOT / "src/cold_storage/modules/layout/domain/structural_composition.py"
COMPOSITION_PLACEMENT_DOMAIN = (
    ROOT / "src/cold_storage/modules/layout/domain/composition_placement.py"
)
FORBIDDEN_IMPORTS = (
    "access_routing",
    "truck_maneuver",
    "svg_projection",
    "mcp",
    "sqlalchemy",
    "database",
    "frontend",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return tuple(modules)


def test_composition_application_uses_existing_integrity_boundary_only() -> None:
    source = APPLICATION.read_text()
    imports = _imports(APPLICATION)
    assert any(module.endswith("application.layout_authority_binding") for module in imports)
    assert "bind_layout_authority" in source
    assert all(
        not any(marker in module.lower() for marker in FORBIDDEN_IMPORTS) for module in imports
    )
    assert "search_placement" not in source
    assert "enumerate_placement_candidates" not in source
    assert "validated_candidate_selection" not in source


def test_composition_placement_application_replays_server_owned_compositions() -> None:
    source = PLACEMENT_APPLICATION.read_text()
    imports = _imports(PLACEMENT_APPLICATION)
    assert "build_structural_compositions" in source
    assert "caller_handoff_consumed=False" in source
    assert "_assert_server_replay" in source
    assert all(
        not any(marker in module.lower() for marker in FORBIDDEN_IMPORTS) for module in imports
    )
    assert all("validated_candidate_selection" not in module for module in imports)


def test_exact_placement_domain_is_geometry_only_and_application_free() -> None:
    imports = _imports(COMPOSITION_PLACEMENT_DOMAIN)
    assert "cold_storage.modules.layout.domain.composition_handoff" in imports
    assert "cold_storage.modules.layout.domain.site_geometry" in imports
    assert "cold_storage.modules.layout.domain.adjacency" in imports
    assert all(
        ".application" not in module
        and not any(marker in module.lower() for marker in FORBIDDEN_IMPORTS)
        for module in imports
    )


def test_handoff_domain_has_no_application_or_downstream_runtime_dependency() -> None:
    imports = _imports(HANDOFF_DOMAIN)
    assert "cold_storage.modules.layout.domain.adjacency" in imports
    assert "cold_storage.modules.layout.domain.dimensioning" in imports
    assert all(
        ".application" not in module
        and not any(marker in module.lower() for marker in FORBIDDEN_IMPORTS)
        for module in imports
    )
    structural_imports = _imports(STRUCTURAL_DOMAIN)
    assert all(".application" not in module for module in structural_imports)


def test_s2_files_do_not_change_legacy_placement_selector_or_tool7_entrypoints() -> None:
    source = APPLICATION.read_text()
    assert "place_zones(" not in source
    assert "calculate_site_placement" not in source
    assert "Tool 7" not in source


def test_shared_authority_binding_is_reused_by_legacy_and_composition_paths() -> None:
    imports = _imports(LEGACY_PLACEMENT_APPLICATION)
    assert any(module.endswith("application.layout_authority_binding") for module in imports)
    assert "bind_layout_authority" in LEGACY_PLACEMENT_APPLICATION.read_text()
    assert "validate_canonical_zone_plan" in LEGACY_PLACEMENT_APPLICATION.read_text()
    assert "bind_layout_authority" in SHARED_AUTHORITY_BINDING.read_text()


def test_composition_placement_domain_does_not_reach_application_or_validators() -> None:
    source = COMPOSITION_PLACEMENT_DOMAIN.read_text()
    imports = _imports(COMPOSITION_PLACEMENT_DOMAIN)
    assert "construction_domain_is_hard_engineering_authority" in source.lower()
    assert all(
        ".application" not in module
        and not any(marker in module.lower() for marker in FORBIDDEN_IMPORTS)
        for module in imports
    )
    assert "access_routing_performed: bool = False" in source
    assert "truck_validation_performed: bool = False" in source
    assert "p2d_performed: bool = False" in source
