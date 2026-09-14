"""Immutable P1D1 scope and explicit partial-authority guards."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_zones import IDENTITY
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.shipping_dimensioning import shipping_profile

ROOT = Path(__file__).resolve().parents[3]
BASE = "4f8c3a0c3b8e866695a917990588caffdd60defc"
SELF = "backend/tests/architecture/test_v22_p1d1_owner_authority.py"
PREFIX = "backend/src/cold_storage/modules/layout/"
RUNTIME = {
    PREFIX + p
    for p in (
        "application/dimension_zones.py",
        "domain/adjacency.py",
        "domain/shipping_dimensioning.py",
    )
}
ALLOWED = RUNTIME | {
    SELF,
    "backend/tests/architecture/test_v22_p0_site_constrained_layout_contract.py",
    "backend/tests/architecture/test_v22_p1a_dimensioning_adjacency.py",
    "backend/tests/architecture/test_v22_p1c_sorting_dimensioning.py",
    "backend/tests/unit/test_v22_p1a_dimensioning_adjacency.py",
    "backend/tests/unit/test_v22_p1c_sorting_dimensioning.py",
    "backend/tests/unit/test_v22_p1d1_shipping_dimensioning.py",
    "backend/tests/v22_p1c_historical_application.py",
    "backend/tests/v22_p1c0_historical_application.py",
    "docs/tasks/V2_2-P1D1-remaining-zone-owner-authority.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_immutable_scope_no_capacity_mcp_or_placement_change():
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    paths = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    else:
        paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert paths and paths <= ALLOWED
    assert {p for p in paths if p.startswith("backend/src/")} <= RUNTIME


def test_versioned_shipping_and_partial_owner_authority():
    assert IDENTITY == "zone_dimensioning_foundation@1.4.0"
    p = shipping_profile()
    assert (
        str(p.fixed_width_m),
        str(p.pit_width_m),
        str(p.min_pit_to_pit_clearance_m),
        str(p.min_pit_to_side_wall_clearance_m),
    ) == ("6.5", "2.0", "2.5", "2.5")
    assert p.loading_face == "LONG_EDGE"
    g = process_graph()
    assert g.identity == "charles-v22-process-flow@1.1.0"
    assert len(g.must_adjacencies) == 7 and len(g.should_adjacencies) == 5
    text = (ROOT / "docs/tasks/V2_2-P1D1-remaining-zone-owner-authority.md").read_text()
    for flag in (
        "COATING_REMAINS_BLOCKED=true",
        "PACKAGING_MODULE_AUTHORITY=PARTIAL",
        "PACKAGING_ROW_COLUMN_RULE_AUTHORIZED=false",
        "PACKAGING_POSITION_MODULE=1.2x1.0m",
        "PACKAGING_LONG_EDGE_AISLE_MIN_M=3.0",
        "PACKAGING_DIMENSION_PROFILE_IMPLEMENTED=false",
        "CHANGING_ROOM_REMAINS_BLOCKED=true",
        "OFFICE_DIMENSION_STATUS=BLOCKED",
        "P2_AUTHORIZED=false",
        "NO_EPSILON=true",
    ):
        assert flag in text
    source = (ROOT / PREFIX / "domain/shipping_dimensioning.py").read_text()
    allowed = {
        "collections.abc",
        "dataclasses",
        "decimal",
        "typing",
        "cold_storage.modules.layout.domain.dimensioning",
    }
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Import):
            assert all(a.name in allowed for a in node.names)
    assert "ROUND_CEILING" in source
    assert "localcontext(Context(prec=80))" in source
