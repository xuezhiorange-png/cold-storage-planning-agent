"""P1E approved profiles, additive scope and no placement/engineering invention."""

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.layout.application.access_handoff import (
    IDENTITY,
    required_access_connections,
)
from cold_storage.modules.layout.domain.access_authority import (
    TRUCK_REQUIRED_FIELDS,
    TruckAccessContractV1,
    approved_access_profiles,
)
from cold_storage.modules.layout.domain.adjacency import process_graph

ROOT = Path(__file__).resolve().parents[3]
BASE = "3910b4fbb4dde1952c1e05d2f7720e87119d3b57"
SELF = "backend/tests/architecture/test_v22_p1e_access_authority.py"
RUNTIME = {
    "backend/src/cold_storage/modules/layout/application/access_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/access_authority.py",
    "backend/src/cold_storage/modules/layout/domain/access_predicates.py",
}
DOC = "docs/tasks/V2_2-P1E-access-profile-authority.md"
ALLOWED = RUNTIME | {
    SELF,
    DOC,
    "backend/tests/unit/test_v22_p1e_access_authority.py",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/TECH_DEBT.md",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_p1e_scope_uses_immutable_introduction_or_precommit_candidate():
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    history = git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    target = history.splitlines()[0] if history else None
    paths = set(git("diff", "--name-only", BASE, *([target] if target else [])).splitlines())
    if target:
        subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=ROOT, check=True)
    else:
        paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert paths <= ALLOWED
    # Runtime is strictly additive: no original dimension/area/MCP/graph code edited.
    for path in RUNTIME:
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{BASE}:{path}"], cwd=ROOT, capture_output=True
            ).returncode
            != 0
        )


def test_p1e_import_boundary_no_calculators_or_routing_engines():
    for path in RUNTIME:
        for node in ast.walk(ast.parse((ROOT / path).read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "/domain/" in path:
                    assert module.startswith("cold_storage.modules.layout.domain.") or module in {
                        "collections.abc",
                        "dataclasses",
                        "decimal",
                        "enum",
                        "typing",
                    }
                else:
                    assert module.startswith("cold_storage.modules.layout.") or module in {
                        "collections.abc",
                        "dataclasses",
                        "typing",
                        "cold_storage.modules.projects.application.operator_process_input",
                    }
                    if module == "cold_storage.modules.projects.application.operator_process_input":
                        assert {alias.name for alias in node.names} == {
                            "REFRIGERATED_ZONE_REGISTRY"
                        }
            if isinstance(node, ast.Import):
                raise AssertionError(f"Unexpected import: {ast.unparse(node)}")


def test_p1e_doc_truth_up_and_unresolved_truck_is_not_p1_complete():
    text = (ROOT / DOC).read_text()
    for token in (
        "DIMENSIONED_ZONE_COUNT=9",
        "FLEXIBLE_AUTHORIZED_ZONE_COUNT=3",
        "PERSONNEL_ACCESS_AUTHORITY_COMPLETE=true",
        "MATERIAL_ACCESS_AUTHORITY_COMPLETE=true",
        "TRUCK_ACCESS_CONTRACT_COMPLETE=true",
        "TRUCK_ACCESS_ENGINEERING_VALUES_COMPLETE=false",
        "P1_COMPLETE=false",
        "P1_CLOSURE_REQUIRES_CONTRACT_DECISION=true",
        "P2_AUTHORIZED=false",
        "READY_AUTHORIZED=false",
        "MERGE_AUTHORIZED=false",
        "TAG_AUTHORIZED=false",
        "GITHUB_RELEASE_AUTHORIZED=false",
        "DEPLOYMENT_AUTHORIZED=false",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "OFFICE_SHIPPING_PERSONNEL_PORTAL_REQUIRED=false",
        "full_access_validated=false",
        "MANUAL_PALLET_JACK",
    ):
        assert token in text
    assert IDENTITY == "p1-dimension-access-handoff@1.0.0"
    truck = TruckAccessContractV1().to_dict()
    assert len(TRUCK_REQUIRED_FIELDS) == 5
    assert all(truck[field] is None for field in TRUCK_REQUIRED_FIELDS)
    assert truck["status"] == "OWNER_INPUT_REQUIRED"
    assert truck["outdoor_only"] and not truck["inside_building_allowed"]


def test_p1e_bindings_do_not_mutate_graph_or_add_engineering_parameters():
    graph = process_graph()
    assert len(graph.must_adjacencies) == 7
    assert len(graph.should_adjacencies) == 5
    requirements = required_access_connections()
    assert len(requirements) == 12
    assert {(r.from_ref, r.to_ref) for r in requirements if r.flow_kind != "TRUCK"} == {
        (flow.from_ref, flow.to_ref) for flow in graph.flows
    }
    for profile in approved_access_profiles():
        assert not profile.door_height_validation
        assert "FORKLIFT" not in profile.transport_mode
        assert "@1.0.0" in profile.identity
