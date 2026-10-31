"""R15 is a read-only domain adapter, without native or approval plumbing."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_new_domain_files_have_no_native_io_or_application_dependencies():
    for filename in ("ten_door_local_relayout.py", "ten_door_sweep_clearance.py"):
        tree = ast.parse((LAYOUT / "domain" / filename).read_text())
        names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(
            any(
                x in m
                for x in (
                    "application",
                    "infrastructure",
                    "ortools",
                    "sqlalchemy",
                    "requests",
                    "pathlib",
                    "subprocess",
                    "fastapi",
                )
            )
            for m in names
        )


def test_application_cannot_approve_write_or_solve():
    tree = ast.parse((LAYOUT / "application/ten_door_relayout_review.py").read_text())
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


def test_no_new_strategy_runner_mcp_or_production_registration():
    src = ROOT / "src/cold_storage"
    files = [
        *(src / "bootstrap").rglob("*.py"),
        *[p for p in src.rglob("*.py") if "/api/" in str(p) or "mcp" in p.name],
    ]
    assert all(
        "ten_door_local_relayout" not in p.read_text()
        and "ten_door_relayout_review" not in p.read_text()
        for p in files
    )
