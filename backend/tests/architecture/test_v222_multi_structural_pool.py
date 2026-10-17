"""Stage B stays internal, reuses Stage A, and issues no execution grant."""

import ast
import inspect

from cold_storage.bootstrap.global_composition import generate_controlled_global_layout_pool
from cold_storage.modules.layout.application import global_composition_pool
from cold_storage.modules.layout.domain import construction_diversity


def test_diversity_is_domain_only_without_solver_or_application_dependencies() -> None:
    tree = ast.parse(inspect.getsource(construction_diversity))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all(
        not any(
            bad in (name or "")
            for bad in (".application", ".infrastructure", "ortools", "fastapi", "sqlalchemy")
        )
        for name in imports
    )


def test_pool_reuses_complete_existing_generation_and_acceptance_chain() -> None:
    source = inspect.getsource(global_composition_pool)
    assert "generate_global_composition_candidate(" in source
    assert "validate_pool" in source
    assert "remaining_solver_seconds()" in source
    assert "ProductionReplayStore(" not in source
    assert "OwnerExecutionStore(" not in source
    assert "cp_model" not in source


def test_internal_entry_cannot_take_coordinates_labels_or_external_handoffs() -> None:
    assert set(inspect.signature(generate_controlled_global_layout_pool).parameters) == {
        "canonical_zone_plan",
        "p1_handoff",
        "site_geometry",
        "execution_ledger",
    }
