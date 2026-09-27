"""Architecture locks for R7's geometry-based evaluation admission."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "backend/src/cold_storage/modules/layout"


def _class_methods(path: Path, class_name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    model = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {node.name: node for node in model.body if isinstance(node, ast.FunctionDef)}


def _string_keys(method: ast.FunctionDef) -> set[str]:
    return {
        key.value
        for node in ast.walk(method)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def test_discovery_and_evaluation_identity_remain_internal_to_tool7_serialization() -> None:
    methods = _class_methods(
        LAYOUT / "domain/main_process_skeleton.py", "MainProcessSkeletonCandidateV1"
    )
    public_keys = _string_keys(methods["to_dict"])
    evaluation_keys = _string_keys(methods["to_evaluation_dict"])

    provenance_keys = {
        "canonical_topology_owner",
        "discovery_topology",
        "discovery_family",
        "canonical_family",
    }
    assert not public_keys & provenance_keys
    assert provenance_keys <= evaluation_keys


def test_topology_owner_is_not_an_admission_predicate() -> None:
    topology_source = (LAYOUT / "domain/main_process_topology.py").read_text(encoding="utf-8")
    selection_source = (LAYOUT / "application/validated_candidate_selection.py").read_text(
        encoding="utf-8"
    )

    assert "SKIP_NON_OWNER_TAIL" not in topology_source
    assert "skeleton_lifecycle_by_hash: dict[str, dict[str, Any]]" in selection_source
    assert "global_skeleton_geometry_registry.get(skeleton_hash)" in selection_source
    assert "tail_search_started" in topology_source
    assert "geometry_previously_seen" in topology_source
