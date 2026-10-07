"""R1 changes the authority source, not search or shape algorithms."""

import ast
import hashlib
import inspect

from cold_storage.modules.layout.application import metric_interface_reservation as metric
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)


def test_p2_and_exact_placement_share_one_hard_obstacle_parser() -> None:
    assert exact.validated_hard_obstacle_polygons is validated_hard_obstacle_polygons
    assert metric.validated_hard_obstacle_polygons is validated_hard_obstacle_polygons
    for module in (exact, metric):
        source = inspect.getsource(module)
        assert "validated_hard_obstacle_polygons(" in source
        assert 'get("no_build_zones"' not in source
        assert '["hard_obstacles"]' not in source


def test_search_and_candidate_acceptance_ast_unchanged_from_r1_start() -> None:
    nodes = [
        node
        for node in ast.parse(inspect.getsource(exact)).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        and node.name != "enumerate_composition_placements"
    ]
    digest = hashlib.sha256(
        "\n".join(ast.dump(node, include_attributes=False) for node in nodes).encode()
    ).hexdigest()
    # Captured from the actual pinned START Git object before this remediation.
    assert digest == "d6ba8525ae18e7a420ea4cad6aa5188c408b1228f0c0a16223c4cb1fe44300d3"


def test_shared_parser_relocation_preserves_the_complete_function_ast() -> None:
    node = ast.parse(inspect.getsource(validated_hard_obstacle_polygons)).body[0]
    digest = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    # Actual function AST from 3147194d before relocation; not a second parser.
    assert digest == "da84ad9ccf1f0ae3d6b24fe1f0348fd7ea1637328edd6f78ba39403f3e8455e6"
