"""Precision contract and immutable task scope; no sorting profile authority."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_zones import IDENTITY, upstream_profiles
from cold_storage.modules.layout.domain.dimensioning import AREA_PROJECTION_IDENTITY
from cold_storage.modules.layout.domain.precool_dimensioning import precool_profiles

ROOT = Path(__file__).resolve().parents[3]
BASE = "09d9973d1c0fb0ea1ead09601d252c22448d213a"
SELF = "backend/tests/architecture/test_v22_p1c0_area_precision.py"
ALLOWED = {
    SELF,
    "backend/src/cold_storage/modules/layout/domain/dimensioning.py",
    "backend/src/cold_storage/modules/layout/application/dimension_zones.py",
    "backend/tests/unit/test_v22_p1c0_area_precision.py",
    "backend/tests/unit/test_v22_p1b_precool_dimensioning.py",
    "docs/tasks/V2_2-P1C0-area-precision-contract.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/tasks/V2_2-P1A-zone-dimensioning-adjacency-foundation.md",
    "docs/tasks/V2_2-P1B-precool-dimension-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_immutable_scope_no_upstream_profile_or_infra_changes() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    paths = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target is None:
        paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    else:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    assert paths and paths <= ALLOWED


def test_versioned_precision_no_production_exact_binder_or_zone_special_case() -> None:
    assert IDENTITY == "zone_dimensioning_foundation@1.2.0"
    assert AREA_PROJECTION_IDENTITY == "cold-room-zone-plan-binary64-product-2dp@1.0.0"
    assert len(upstream_profiles()) == 4 and len(precool_profiles()) == 2
    app = (
        ROOT / "backend/src/cold_storage/modules/layout/application/dimension_zones.py"
    ).read_text()
    assert "ExactAreaAuthorityV1" not in app
    domain = (ROOT / "backend/src/cold_storage/modules/layout/domain/dimensioning.py").read_text()
    assert "sorting_packaging_room" not in domain
    for node in ast.walk(ast.parse(domain)):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("cold_storage.modules.calculations")
    text = (ROOT / "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md").read_text()
    assert "actual_area_m2>=exact_geometry_required_area_m2" in text
    assert "actual_area_m2>=reported_required_area_m2" in text
    assert "NO_EPSILON=true" in text
    assert "NO_GEOMETRY_INFLATION_FOR_REPORTING_ROUNDING=true" in text
