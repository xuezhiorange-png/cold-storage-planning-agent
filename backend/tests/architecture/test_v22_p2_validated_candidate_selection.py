"""Architecture locks for the P2C-to-P2D validated candidate selector."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b"
SELF = "backend/tests/architecture/test_v22_p2_validated_candidate_selection.py"
UNIT = "backend/tests/unit/test_v22_p2_validated_candidate_selection.py"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/placement.py"
PLACEMENT_APP = "backend/src/cold_storage/modules/layout/application/placement.py"
SELECTOR = "backend/src/cold_storage/modules/layout/application/validated_candidate_selection.py"
DOC = "docs/tasks/V2_2-P2-validated-candidate-selection-implementation.md"
ALLOWED = {DOMAIN, PLACEMENT_APP, SELECTOR, SELF, UNIT, DOC}
PROTECTED = {
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_preview.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        return set(git("diff", "--name-only", BASE, target).splitlines())
    paths = set(git("diff", "--name-only", BASE, "HEAD").splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def _imports(path: str) -> list[str]:
    tree = ast.parse((ROOT / path).read_text())
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return values


def test_scope_is_additive_and_does_not_touch_p2d_or_p4() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    changed = _changed_paths()
    assert changed <= ALLOWED
    assert not changed & PROTECTED


def test_p2c_exposes_lazy_enumeration_without_a_complete_candidate_cutoff() -> None:
    source = (ROOT / DOMAIN).read_text()
    for token in (
        "class PlacementCandidateEnumerationV1",
        "def enumerate_placement_candidates(",
        "def _walk_complete_candidate_payloads(",
        "complete_candidate_limit_stops_search",
        "node_budget_is_only_search_cutoff",
        "search_tree_exhausted",
        "node_budget_exhausted",
    ):
        assert token in source
    assert "if complete_candidates >= complete_candidate_limit" not in source
    assert "route_site_placement" not in source
    assert "access_routing" not in " ".join(_imports(DOMAIN))


def test_application_selector_owns_p2d_filtering_and_p2c_ranking_only() -> None:
    source = (ROOT / SELECTOR).read_text()
    for token in (
        "enumerate_placement_candidates(",
        "route_site_placement(",
        "placement_candidate_is_better(",
        "P2C_CANDIDATE_SELECTION_BASIS",
        "candidate_validation_trace",
        "objective_optimal_within_search_family",
        "route_objective_optimization_active",
        "p4_candidate_selection",
        "not a mathematical infeasibility proof",
    ):
        assert token in source
    for forbidden in (
        "weighted_score",
        "route_length_m",
        "centroid",
        "manhattan",
        "straight_line_distance",
        "site_layout_preview",
    ):
        assert forbidden not in source.lower()
    assert "cold_storage.modules.layout.application.access_routing" in _imports(SELECTOR)
    assert "cold_storage.modules.layout.application.placement" in _imports(SELECTOR)
    assert "cold_storage.modules.layout.modules" not in _imports(SELECTOR)


def test_p2d_authority_errors_fail_fast_in_the_application_boundary() -> None:
    source = (ROOT / SELECTOR).read_text()
    tree = ast.parse(source)
    assert "project_layout_validated" in source
    assert "p2_complete" in source
    assert not any(
        isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "LayoutAuthorityError"
        for node in ast.walk(tree)
    )


def test_p2c_application_exposes_the_same_authority_bound_search() -> None:
    source = (ROOT / PLACEMENT_APP).read_text()
    for token in (
        "def enumerate_placement_candidates(",
        "_validate_p1_authority(",
        "enumerate_domain_placement_candidates(",
        "access_requirements=access_requirements",
        "spatial_relationships=spatial_relationships",
    ):
        assert token in source
    assert "route_site_placement" not in source


def test_decision_document_freezes_the_authority_boundary() -> None:
    doc = (ROOT / DOC).read_text()
    for token in (
        "P2C_RESPONSIBILITY_PRESERVED=YES",
        "P2D_RESPONSIBILITY_PRESERVED=YES",
        "P2C_CANDIDATE_ENUMERATION_IMPLEMENTED=YES",
        "P2_APPLICATION_SELECTION_IMPLEMENTED=YES",
        "NEW_ROUTE_OBJECTIVE_ADDED=NO",
        "PACKAGING_SORTING_STRAIGHT_RULE_PRESERVED=YES",
        "P4_CANDIDATE_SELECTION_IMPLEMENTED=NO",
        "SEARCH_TREE_EXHAUSTED",
        "NODE_BUDGET_EXHAUSTED",
        "OBJECTIVE_OPTIMAL_WITHIN_SEARCH_FAMILY",
        "NO_MATHEMATICAL_INFEASIBILITY_PROOF=YES",
        "P2_COMPLETE=false",
        "P4_AUTHORIZED=false",
    ):
        assert token in doc
