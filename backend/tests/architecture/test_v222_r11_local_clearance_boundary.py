"""No Native/approval/production wiring in the opt-in R15 R4 adapter."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_domain_has_no_io_native_or_outer_layer_imports():
    tree = ast.parse((LAYOUT / "domain/ten_door_local_clearance.py").read_text())
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(
        any(
            x in m
            for x in (
                "application",
                "infrastructure",
                "ortools",
                "pathlib",
                "subprocess",
                "sqlalchemy",
                "requests",
                "fastapi",
            )
        )
        for m in imports
    )


def test_application_cannot_solve_approve_claim_or_write():
    tree = ast.parse((LAYOUT / "application/ten_door_clearance_review.py").read_text())
    calls = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    assert not calls & {
        "open",
        "write_text",
        "write_bytes",
        "approve",
        "claim",
        "solve",
        "Solve",
        "execute",
        "commit",
    }


def test_no_new_registration_in_production_or_mcp_and_old_validators_remain_imports():
    src = ROOT / "src/cold_storage"
    files = [
        *(src / "bootstrap").rglob("*.py"),
        *[p for p in src.rglob("*.py") if "/api/" in str(p) or "mcp" in p.name],
    ]
    assert all(
        "ten_door_local_clearance" not in p.read_text()
        and "ten_door_clearance_review" not in p.read_text()
        for p in files
    )
    text = (LAYOUT / "domain/ten_door_local_clearance.py").read_text()
    for name in ("validate_use", "activity_proof", "sizing_snapshot", "certified_sweep_distance"):
        assert name in text
