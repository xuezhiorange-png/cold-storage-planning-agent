"""P3 changes consumption, not hard authority, zone order or scheduling."""

import ast
import inspect
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain import composition_placement as exact

ROOT = Path(__file__).resolve().parents[3]
START = "112f30115d201dd8ef2daf541f5352b92d2154fe"
PATH = "backend/src/cold_storage/modules/layout/domain/composition_placement.py"


def test_p3_preserves_order_authority_and_finite_fallback_algorithms() -> None:
    baseline = subprocess.run(
        ["git", "show", f"{START}:{PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    names = {
        "_zone_order",
        "_composition_shape_order",
        "_domain_arrangement",
        "_domain_derived_anchors",
        "_generic_fallback_anchors",
        "_candidate_rejection",
        "_side_ok",
        "_partial_intent_possible",
        "_intent_preserved",
    }

    def selected(source):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name in names
        }

    assert selected(baseline) == selected(inspect.getsource(exact))

    def schedule(source):
        fn = next(
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name == "enumerate_composition_placements"
        )
        nodes = []
        for n in fn.body:
            if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name)
                and t.id
                in {"tasks", "per_attempt_budget", "initial_family_budget", "continuation_budget"}
                for t in n.targets
            ):
                nodes.append(ast.dump(n, include_attributes=False))
            if (
                isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Attribute)
                and isinstance(n.value.func.value, ast.Name)
                and n.value.func.value.id == "tasks"
            ):
                nodes.append(ast.dump(n, include_attributes=False))
        return nodes

    assert len(schedule(baseline)) == 7
    assert schedule(baseline) == schedule(inspect.getsource(exact))
    assert exact.DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET == 60000
