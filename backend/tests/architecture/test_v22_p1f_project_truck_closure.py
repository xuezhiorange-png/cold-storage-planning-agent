"""P1F immutable task scope, schema composition and version/project separation."""

import ast
import json
import subprocess
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
BASE = "4244379953028899958ce1579d488288a49c5b82"
SELF = "backend/tests/architecture/test_v22_p1f_project_truck_closure.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/domain/project_truck_input.py",
    "backend/src/cold_storage/modules/layout/application/p1_project_handoff.py",
}
DOC = "docs/tasks/V2_2-P1F-project-truck-input-and-p1-closure.md"
SCHEMAS = (
    "V2_2-site-layout-input-v1.schema.json",
    "V2_2-truck-project-access-input-v1.schema.json",
    "V2_2-site-layout-project-input-v1.schema.json",
)
ALLOWED = RUNTIME | {
    SELF,
    DOC,
    "backend/tests/unit/test_v22_p1f_project_truck_input.py",
    *(f"docs/tasks/{name}" for name in SCHEMAS[1:]),
    "docs/tasks/V2_2-version-plan.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/TECH_DEBT.md",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_immutable_scope_and_unchanged_site_schema():
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    changed = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    else:
        changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed <= ALLOWED
    for path in RUNTIME:
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"], cwd=ROOT, capture_output=True
            ).returncode
            != 0
        )
    path = f"docs/tasks/{SCHEMAS[0]}"
    original = git("show", f"{BASE}:{path}")
    candidate = git("show", f"{target}:{path}") if target else (ROOT / path).read_text().strip()
    assert original == candidate


def test_no_solver_or_engineering_default_dependencies():
    for path in RUNTIME:
        for node in ast.walk(ast.parse((ROOT / path).read_text())):
            if isinstance(node, ast.Import):
                assert {n.name for n in node.names} <= {"re"}
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module in {"collections.abc", "decimal", "typing"} or module.startswith(
                    "cold_storage.modules.layout."
                )
                if "/domain/" in path and module.startswith("cold_storage"):
                    assert module.startswith("cold_storage.modules.layout.domain.")


def test_composition_schema_preserves_v1_and_has_no_truck_defaults():
    from tests.unit.test_v22_p1f_project_truck_input import truck_input

    uri = "https://contracts.example.invalid/"
    schemas = {
        name: json.loads((ROOT / "docs/tasks" / name).read_text(), parse_float=Decimal)
        for name in SCHEMAS
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources(
        (uri + name, Resource.from_contents(schema)) for name, schema in schemas.items()
    )
    composition = {**schemas[SCHEMAS[2]], "$id": uri + SCHEMAS[2]}
    validator = Draft202012Validator(composition, registry=registry)
    project = {
        "site_constraints": {
            "site_boundary": {
                "type": "polygon",
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
            },
            "main_entrance": {"start": {"x": 0, "y": 0}, "end": {"x": 1, "y": 0}},
            "truck_entrance": {"start": {"x": 2, "y": 0}, "end": {"x": 3, "y": 0}},
        },
        "truck_access": json.loads(json.dumps(truck_input()), parse_float=Decimal),
    }
    assert not list(validator.iter_errors(project))
    del project["truck_access"]["vehicle_width_m"]
    assert list(validator.iter_errors(project))
    assert '"default"' not in json.dumps(schemas[SCHEMAS[1]], default=str)
    assert "truck_access" not in schemas[SCHEMAS[0]]["properties"]


def test_closure_evidence_and_prior_stages_lineage():
    text = (ROOT / DOC).read_text()
    for phase in ("P1A", "P1B", "P1C0", "P1C", "P1D1", "P1D3", "P1E"):
        assert f"{phase}_STATUS=MERGED" in text
    for token in (
        "P1_COMPLETE=true",
        "P1_CLOSURE_BLOCKERS=NONE",
        "TRUCK_PROJECT_INPUT_CONTRACT_COMPLETE=true",
        "TRUCK_VERSION_LEVEL_ENGINEERING_VALUES_REQUIRED=false",
        "P2_AUTHORIZED=false",
        "P3_AUTHORIZED=false",
        "P4_AUTHORIZED=false",
        "P5_AUTHORIZED=false",
        "READY_AUTHORIZED=false",
        "MERGE_AUTHORIZED=false",
        "TAG_AUTHORIZED=false",
        "GITHUB_RELEASE_AUTHORIZED=false",
        "DEPLOYMENT_AUTHORIZED=false",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true",
    ):
        assert token in text
    for sha in (
        "ae9794d0454fa64ba7db6a94d9a3faeba5df00bd",
        "09d9973d1c0fb0ea1ead09601d252c22448d213a",
        "7785e877461a2c82980ed4e318bd04eabc0287df",
        "4f8c3a0c3b8e866695a917990588caffdd60defc",
        "a848c2a3b44c6625db7a2546596f4bb3ceb3d7d3",
        "3910b4fbb4dde1952c1e05d2f7720e87119d3b57",
        BASE,
    ):
        assert sha in text
        subprocess.run(["git", "merge-base", "--is-ancestor", sha, BASE], cwd=ROOT, check=True)
