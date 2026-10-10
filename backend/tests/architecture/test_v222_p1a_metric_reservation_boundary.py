"""P2 isolates metric domains and mechanically shares unchanged shape authority."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from cold_storage.modules.layout.application import metric_interface_reservation
from cold_storage.modules.layout.domain import authority_shapes, composition_placement


def test_authority_shape_extraction_is_ast_identical_to_start_head() -> None:
    root = Path(__file__).resolve().parents[3]
    baseline = (root / "backend/tests/fixtures/v22/pre_p2_authority_shapes.py.txt").read_text()
    # Pure symbol renaming is the only difference in the extracted implementation.
    for old, new in (
        ("_Shape", "AuthoritativeZoneShapeV1"),
        ("_authority_shapes", "authoritative_zone_shapes"),
        ("_canonical_construction_shapes", "canonical_construction_shapes"),
    ):
        baseline = baseline.replace(old, new)
    before = ast.parse(baseline)
    current = ast.parse(inspect.getsource(authority_shapes))
    nodes = {n.name: n for n in current.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for node in before.body:
        assert isinstance(node, (ast.FunctionDef, ast.ClassDef))
        assert ast.dump(node, include_attributes=False) == ast.dump(
            nodes[node.name], include_attributes=False
        )
    assert composition_placement._authority_shapes is authority_shapes.authoritative_zone_shapes


def test_metric_boundary_does_not_run_placement_or_validators() -> None:
    source = inspect.getsource(metric_interface_reservation)
    assert "bind_layout_authority(" in source and "build_structural_compositions(" in source
    assert "_assert_server_replay(" in source
    for forbidden in (
        "enumerate_composition_placements(",
        "route_site_placement(",
        "validate_truck",
        "p2d_performed=True",
    ):
        assert forbidden not in source
