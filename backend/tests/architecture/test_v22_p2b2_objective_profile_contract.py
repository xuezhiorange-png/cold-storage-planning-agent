"""P2B2 objective contract, scope and non-solver architecture locks."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.objective_profile import (
    ACTUAL_ROUTE_LENGTH_METRIC,
    CARDINAL_LOADING_SIDE_METRIC,
    COMPACTNESS_ACTIVE,
    DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE,
    FINAL_TIE_BREAK,
    IDENTITY,
    OBJECTIVE_ORDER,
    ROUTE_PROXY_ALLOWED,
    SHAPE_REGULARITY_ACTIVE,
    SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT,
    SHOULD_ADJACENT_COUNT,
    SHOULD_ADJACENT_METRIC,
    SHOULD_ADJACENT_METRIC_ID,
    SOFT_OBJECTIVE_COUNT,
    UNUSED_SITE_EFFICIENCY_ACTIVE,
    approved_objective_profile,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = "fa884b8ddf2b93f34beb2335d646fe6b157a8f5f"
SELF = "backend/tests/architecture/test_v22_p2b2_objective_profile_contract.py"
UNIT = "backend/tests/unit/test_v22_p2b2_objective_profile.py"
RUNTIME = {"backend/src/cold_storage/modules/layout/domain/objective_profile.py"}
DOC = "docs/tasks/V2_2-P2B2-objective-profile-contract.md"
ALLOWED = RUNTIME | {
    SELF,
    UNIT,
    DOC,
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}

PROTECTED = {
    "backend/src/cold_storage/modules/layout/domain/adjacency.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/domain/truck_maneuver.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/application/access_handoff.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
        return set(git("diff", "--name-only", BASE, target).splitlines())
    paths = set(git("diff", "--name-only", BASE, "HEAD").splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    return paths


def test_scope_is_additive_and_does_not_touch_layout_authorities() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    changed = _historical_changed_paths()
    assert changed <= ALLOWED
    assert not changed & PROTECTED
    for path in PROTECTED:
        if (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            == 0
        ):
            subprocess.run(
                ["git", "diff", "--quiet", BASE, "HEAD", "--", path], cwd=ROOT, check=True
            )


def test_objective_module_has_only_domain_level_imports() -> None:
    source = (ROOT / next(iter(RUNTIME))).read_text()
    tree = ast.parse(source)
    allowed_from = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "typing",
        "cold_storage.modules.layout.domain.dimensioning",
    }
    allowed_dimensioning_names = {"LayoutAuthorityError", "canonical_hash", "canonical_json"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not node.names
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed_from
            if node.module == "cold_storage.modules.layout.domain.dimensioning":
                assert {alias.name for alias in node.names} <= allowed_dimensioning_names
            else:
                assert node.module != "fastapi"


def test_owner_objective_contract_is_exactly_frozen() -> None:
    profile = approved_objective_profile()
    assert IDENTITY == "site-constrained-objective-profile@1.0.0"
    assert profile.aggregation == "LEXICOGRAPHIC"
    assert profile.weighted_score is False
    assert profile.priority_order == OBJECTIVE_ORDER
    assert len(OBJECTIVE_ORDER) == SOFT_OBJECTIVE_COUNT == 8
    assert profile.hard_constraints_first is True
    assert profile.hard_violation_cannot_be_offset is True
    assert SHOULD_ADJACENT_COUNT == 5
    assert SHOULD_ADJACENT_METRIC == "SATISFIED_COUNT"
    assert SHOULD_ADJACENT_METRIC_ID == "SATISFIED_SHOULD_ADJACENCY_COUNT"
    assert SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT is False
    assert ROUTE_PROXY_ALLOWED is False
    assert ACTUAL_ROUTE_LENGTH_METRIC == "ACTUAL_PORTAL_CORRIDOR_ROUTE_LENGTH"
    assert CARDINAL_LOADING_SIDE_METRIC == "BINARY_MATCH"
    assert COMPACTNESS_ACTIVE is False
    assert SHAPE_REGULARITY_ACTIVE is False
    assert UNUSED_SITE_EFFICIENCY_ACTIVE is False
    assert DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE is True
    assert profile.final_tie_break == FINAL_TIE_BREAK
    assert profile.final_tie_break_after_exact_objective_vector is True
    assert profile.raw_mapping_order_allowed is False
    assert profile.hash_as_tie_break is False


def test_profile_does_not_implement_placement_or_route_search() -> None:
    source = (ROOT / next(iter(RUNTIME))).read_text().lower()
    for forbidden in (
        "placement_search",
        "route_search",
        "path_finder",
        "a_star",
        "generate_route",
        "generate_placement",
        "optimizer",
        "site_placement",
    ):
        assert forbidden not in source


def test_p2b2_document_records_owner_rules_and_boundaries() -> None:
    text = (ROOT / DOC).read_text()
    for token in (
        "OBJECTIVE_AGGREGATION=LEXICOGRAPHIC",
        "WEIGHTED_SCORE=false",
        "SHOULD_ADJACENT_EQUAL_PRIORITY=true",
        "SHOULD_ADJACENT_METRIC=SATISFIED_COUNT",
        "SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT=false",
        "ROUTE_OBJECTIVES_REQUIRE_ACTUAL_PORTAL_CORRIDOR_ROUTE=true",
        "CENTROID_PROXY_ALLOWED=false",
        "EDGE_MANHATTAN_PROXY_ALLOWED=false",
        "STRAIGHT_LINE_PROXY_ALLOWED=false",
        "CARDINAL_LOADING_SIDE_METRIC=BINARY_MATCH",
        "UNSPECIFIED_LOADING_SIDE_SCORING=DISABLED",
        "NEAREST_TRUCK_ENTRANCE_METRIC=MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE",
        "COMPACTNESS_ACTIVE=false",
        "SHAPE_REGULARITY_ACTIVE=false",
        "UNUSED_SITE_EFFICIENCY_ACTIVE=false",
        "PLACEMENT_SEARCH_IMPLEMENTED=false",
        "ROUTING_IMPLEMENTED=false",
        "P2C_AUTHORIZED=false",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert token in text
