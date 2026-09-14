"""P1 handoff scope, frozen legacy runtime and explicit non-placement boundary."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.dimension_handoff import IDENTITY, SCHEMA_VERSION
from cold_storage.modules.layout.domain.dimension_handoff import FLEXIBLE_ZONES

ROOT = Path(__file__).resolve().parents[3]
BASE = "a848c2a3b44c6625db7a2546596f4bb3ceb3d7d3"
SELF = "backend/tests/architecture/test_v22_p1d3_hybrid_handoff.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/packaging_dimensioning.py",
}
DOCS = {
    "docs/tasks/V2_2-P1D3-flexible-rectangle-handoff-contract.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/TECH_DEBT.md",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_scope_immutable_introducing_commit_or_precommit_candidate():
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    paths = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    else:
        paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert paths <= RUNTIME | DOCS | {SELF, "backend/tests/unit/test_v22_p1d3_hybrid_handoff.py"}
    # All permitted production files are additive, not edits to historic binders.
    for path in RUNTIME:
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"], cwd=ROOT, capture_output=True
            ).returncode
            != 0
        )


def test_hybrid_contract_not_p2_implementation():
    assert IDENTITY == "hybrid_zone_dimension_handoff@1.0.0"
    assert SCHEMA_VERSION == "1.0.0"
    assert set(FLEXIBLE_ZONES) == {"coating_room", "changing_room", "office"}
    text = (ROOT / "docs/tasks/V2_2-P1D3-flexible-rectangle-handoff-contract.md").read_text()
    for required in (
        "P1_REQUIRES_ALL_12_ZONES_FIXED_WIDTH_DEPTH=false",
        "P1_REQUIRES_ALL_ZONES_HAVE_DIMENSION_AUTHORITY=true",
        "P2_IMPLEMENTATION_AUTHORIZED=false",
        "ACCESS_PROFILE_REQUIRED=true",
        "PACKAGING_AISLE_IS_GEOMETRY_CONSTRAINT_NOT_ADDITIVE_AREA=true",
        "FLEXIBLE_AUTHORIZED",
    ):
        assert required in text
    for path in RUNTIME:
        tree = ast.parse((ROOT / path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(("fastapi", "sqlalchemy", "requests", "httpx"))
                if module.startswith("cold_storage"):
                    assert module.startswith("cold_storage.modules.layout.")
                    if "/domain/" in path:
                        assert module.startswith("cold_storage.modules.layout.domain.")
            if isinstance(node, ast.Import):
                assert all(n.name not in {"random", "requests", "httpx"} for n in node.names)
