"""Architecture and evidence locks for the V2.2.2 P0 contract-only task."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "64f335bbfbbaf061b9ba08c18f2068db411f8922"
SELF = "backend/tests/architecture/test_v222_p0_process_flow_layout_regularity_contract.py"
P1G_SCOPE_GUARD = "backend/tests/architecture/test_v221_p1g_release_closure.py"
CONTRACT = "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md"
ADR = "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md"
VERSION_PLAN = "docs/tasks/V2_2-version-plan.md"
ALLOWED = {SELF, P1G_SCOPE_GUARD, CONTRACT, ADR, VERSION_PLAN}

PLACEMENT = "backend/src/cold_storage/modules/layout/domain/placement.py"
OBJECTIVE = "backend/src/cold_storage/modules/layout/domain/objective_profile.py"
ADJACENCY = "backend/src/cold_storage/modules/layout/domain/adjacency.py"
SELECTOR = "backend/src/cold_storage/modules/layout/application/validated_candidate_selection.py"
ROUTING = "backend/src/cold_storage/modules/layout/application/access_routing.py"
ACCESS_ROUTING_DOMAIN = "backend/src/cold_storage/modules/layout/domain/access_routing.py"
P4 = "backend/src/cold_storage/modules/aily/application/site_layout_preview.py"


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
    paths.update(git("diff", "--name-only").splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def _base_source(path: str) -> str:
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True)


def _assignment(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return node.value
    raise AssertionError(f"assignment not found: {name}")


def _literal_assignment(source: str, name: str) -> object:
    return ast.literal_eval(_assignment(source, name))


def _tuple_symbols(source: str, name: str) -> tuple[str, ...]:
    value = _assignment(source, name)
    assert isinstance(value, ast.Tuple)
    return tuple(
        element.id if isinstance(element, ast.Name) else str(ast.literal_eval(element))
        for element in value.elts
    )


def test_p0_changes_only_the_contract_adr_version_plan_and_architecture_lock() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    assert _changed_paths() == ALLOWED
    assert not any(
        path.startswith(("backend/src/", "frontend/", "database/", "backend/alembic/"))
        for path in _changed_paths()
    )


def test_audit_matches_the_immutable_v221_runtime_baseline() -> None:
    placement = _base_source(PLACEMENT)
    objective = _base_source(OBJECTIVE)
    adjacency = _base_source(ADJACENCY)
    selector = _base_source(SELECTOR)
    routing = _base_source(ROUTING)
    access_routing_domain = _base_source(ACCESS_ROUTING_DOMAIN)
    p4 = _base_source(P4)

    assert _literal_assignment(placement, "PLACEMENT_ZONE_ORDER") == (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
        "office",
        "changing_room",
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    )
    assert "constrained-first technical search order" in placement
    assert _tuple_symbols(objective, "PLACEMENT_OBJECTIVE_ORDER") == (
        "SHOULD_ADJACENT",
        "LOADING_SIDE_PREFERENCE",
    )
    for flag in ("COMPACTNESS_ACTIVE", "SHAPE_REGULARITY_ACTIVE", "UNUSED_SITE_EFFICIENCY_ACTIVE"):
        assert _literal_assignment(objective, flag) is False
    assert "SATISFIED_COUNT" in objective
    assert "_is_better(" in placement
    assert "candidate_should > best_should" in placement
    assert "candidate_match" in placement
    assert "candidate_distance < best_distance" in placement

    assert _literal_assignment(adjacency, "PROCESS_FLOW") == (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    assert "process_rank" not in adjacency
    assert "main_flow_backtrack_count" not in placement.lower()
    assert "main_flow_turn_count" not in placement.lower()
    assert "grid_alignment" not in placement.lower()
    assert "depth_alignment" not in placement.lower()
    assert "building_compactness" not in placement.lower()
    assert "functional_group" not in placement.lower()

    assert "select_validated_placement" in selector
    assert "route_site_placement(" in selector
    assert "p2d_full_pass_candidate_count" in selector
    assert "select_validated_placement" in p4
    assert "turn_count" in routing
    assert "route_length_m" in routing
    assert "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED" in access_routing_domain
    assert "MAIN_FLOW_TURN_COUNT" not in routing


def test_contract_freezes_roles_gates_metrics_and_non_authority_boundaries() -> None:
    contract = (ROOT / CONTRACT).read_text()
    adr = (ROOT / ADR).read_text()
    version_plan = (ROOT / VERSION_PLAN).read_text()
    p1g_scope_guard = (ROOT / P1G_SCOPE_GUARD).read_text()

    required_contract_tokens = (
        "RAW_RECEIVING",
        "RAW_TEMP_STORAGE",
        "PRIMARY_PRECOOL",
        "SORTING_PACKAGING",
        "SECONDARY_PRECOOL",
        "FINISHED_STORAGE",
        "SHIPPING",
        "COATING",
        "PROCESS_FLOW_ORDER_PASS",
        "MAIN_FLOW_BACKTRACK_COUNT",
        "MAIN_FLOW_TURN_COUNT",
        "FUNCTIONAL_GROUPING_PASS",
        "SIDE_BRANCH_CROSSES_MAIN_FLOW",
        "PERSONNEL_LOGISTICS_SEPARATION",
        "MAJOR_ZONE_GRID_ALIGNMENT_RATE",
        "MAJOR_ZONE_DEPTH_ALIGNMENT_RATE",
        "MAIN_BUILDING_COMPONENT_COUNT",
        "BOUNDING_RECTANGLE_OCCUPANCY",
        "EXTERIOR_NOTCH_COUNT",
        "EXTERIOR_REFLEX_CORNER_COUNT",
        "ISOLATED_APPENDAGE_COUNT",
        "REQUIRED_ADJACENCY_SHARED_EDGE_RATIO",
        "MAIN_PROCESS_ROUTE_LENGTH_M",
        "PROCESS_ROUTE_EFFICIENCY_RATIO",
        "LAYOUT_REGULARITY_SCORE",
        "LAYOUT_REGULARITY_VALIDATED",
        "HARD_FEASIBILITY",
        "QUALITY_RANKING",
        "WHY_THIS_CANDIDATE_WON",
        "PRIMARY_GOLDEN_REFERENCE=GD-005_PANLONG",
        "GOLDEN_ENGINEERING_AUTHORITY=false",
        "ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false",
        "XINZHAO_SITE_LAYOUT_INPUT_V3_PRESENT=false",
        "MISSING_CANONICAL_FIXTURE=true",
        "V2.2.1",
        "FUTURE_CANONICAL_HASH_CHANGE_ALLOWED=true",
        "P1_IMPLEMENTATION_AUTHORIZED=false",
        "DEPLOYMENT_AUTHORIZED=false",
    )
    for token in required_contract_tokens:
        assert token in contract, token
    assert "implementation is not authorized by this ADR" in adr
    assert "weighted score" in contract.lower()
    assert "64f335bbfbbaf061b9ba08c18f2068db411f8922" in version_plan
    assert "DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_CALIBRATED" in version_plan
    assert "P0_CONTRACT_ONLY=true" in version_plan
    assert "P1_IMPLEMENTATION_AUTHORIZED=false" in version_plan
    assert 'P1G_ACCEPTED_HEAD_SHA = "83d43e6432165a2ef8d7b20683e10ac1103f50ee"' in p1g_scope_guard
    assert "P1G_ACCEPTED_HEAD_SHA" in p1g_scope_guard


def test_hard_gates_precede_quality_and_v221_baseline_is_not_a_future_hash_lock() -> None:
    contract = (ROOT / CONTRACT).read_text()
    assert contract.index("HARD_FEASIBILITY") < contract.index("QUALITY_RANKING")
    assert "LAYOUT_REGULARITY_SCORE" in contract
    assert "cannot hide a failed atom" in contract
    assert "FUTURE_CANONICAL_HASH_CHANGE_ALLOWED=true" in contract
    assert "is preserved as baseline evidence only" in contract
    assert "P3 SVG" in contract
    assert "P1A–P1F renderer" in contract
