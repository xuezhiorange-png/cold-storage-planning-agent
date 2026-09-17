"""Release-closure locks for the V2.2 P5 readiness boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cold_storage.modules.aily.api.mcp_sse import (
    _MCP_TOOL_ORDER,
    _PREVIEW_TOOL_ORDER,
)
from cold_storage.modules.aily.application.mcp_site_layout import (
    PREVIEW_SITE_LAYOUT_INPUT_FIELDS,
    PREVIEW_SITE_LAYOUT_TOOL_NAME,
)
from cold_storage.modules.calculations.application.factory_power_presentation import (
    FACTORY_POWER_CALCULATOR_IDENTITY,
    FACTORY_POWER_RESULT_SCHEMA_VERSION,
)
from cold_storage.modules.calculations.domain.factory_power_estimation import (
    CALCULATOR_VERSION as FACTORY_POWER_CALCULATOR_VERSION,
)
from cold_storage.modules.layout.application.access_handoff import (
    IDENTITY as ACCESS_HANDOFF_IDENTITY,
)
from cold_storage.modules.layout.application.dimension_handoff import (
    IDENTITY as DIMENSION_HANDOFF_IDENTITY,
)
from cold_storage.modules.layout.application.p1_project_handoff import (
    IDENTITY as P1_HANDOFF_IDENTITY,
)
from cold_storage.modules.layout.application.validated_candidate_selection import (
    IDENTITY as SELECTOR_IDENTITY,
)
from cold_storage.modules.layout.application.validated_candidate_selection import (
    RESULT_IDENTITY as SELECTOR_RESULT_IDENTITY,
)
from cold_storage.modules.layout.domain.access_routing import (
    IDENTITY as P2D_IDENTITY,
)
from cold_storage.modules.layout.domain.access_routing import (
    RESULT_IDENTITY as P2D_RESULT_IDENTITY,
)
from cold_storage.modules.layout.domain.dimensioning import IDENTITY as DIMENSIONING_IDENTITY
from cold_storage.modules.layout.domain.objective_profile import (
    IDENTITY as OBJECTIVE_PROFILE_IDENTITY,
)
from cold_storage.modules.layout.domain.placement import (
    IDENTITY as P2C_IDENTITY,
)
from cold_storage.modules.layout.domain.placement import (
    PLACEMENT_RESULT_IDENTITY,
)
from cold_storage.modules.layout.domain.site_geometry import IDENTITY as SITE_GEOMETRY_IDENTITY
from cold_storage.modules.layout.domain.svg_projection import SVG_PROJECTION_IDENTITY
from cold_storage.modules.layout.domain.truck_maneuver import (
    CONTRACT_IDENTITY as TRUCK_CONTRACT_IDENTITY,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "31c888f446d2d4c5704221426d60685da91f43d8"
SELF = "backend/tests/architecture/test_v22_p5_release_closure.py"
P5_DOC = "docs/tasks/V2_2-P5-release-closure.md"
VERSION_PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md"
CURRENT_STATE = "docs/audit/current-state.md"
ALLOWED_PATHS = {SELF, P5_DOC, VERSION_PLAN, ADR, CURRENT_STATE}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _historical_target() -> str | None:
    history = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", target, "HEAD"],
            cwd=REPO_ROOT,
            check=True,
        )
        return set(_git("diff", "--name-only", BASE_MAIN_SHA, target).splitlines())
    paths = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {path for path in paths if path}


def test_p5_scope_is_docs_and_architecture_only() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith("backend/src/") for path in changed)
    assert not any(path.startswith("frontend/") for path in changed)
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)


def test_release_lineage_and_historical_release_are_immutable() -> None:
    subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            "0a68597a40aa460ed31441c537ca37c3d4cfd1a7",
            "HEAD",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    assert _git("rev-parse", "v2.1.2^{commit}") == ("0a68597a40aa460ed31441c537ca37c3d4cfd1a7")
    for sha in (
        "3ffb3790f85a990283ce972733c3f43b44d1e899",
        "50210aa7cc876ed8a93a099c82ef4a4f287da82a",
        "ccd6336de4810012deec64c1b0a5f3256ff13d85",
        "fa884b8ddf2b93f34beb2335d646fe6b157a8f5f",
        "776d6836975d5f27a0261820548425e798919f03",
        "99116fb8f5999461f718ad6a4d5747f1ec865716",
        "a1d035c4d42a2bc4895e6d3806d3f5fe77e7e0d2",
        "efc1ce2e85b55e2e7fb907fee460ea4d2e84dc9d",
        "cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b",
        BASE_MAIN_SHA,
    ):
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=REPO_ROOT,
            check=True,
        )


def test_p5_document_closes_all_stages_without_authorizing_release_execution() -> None:
    source = _source(P5_DOC)
    for required in (
        "TASK_ID=V2_2_P5_RELEASE_CLOSURE_R1",
        "BASE_MAIN_SHA=31c888f446d2d4c5704221426d60685da91f43d8",
        "TARGET_VERSION=v2.2.0",
        "P0_COMPLETE=YES",
        "P1_COMPLETE=YES",
        "P2_COMPLETE=YES",
        "P3_COMPLETE=YES",
        "P4_COMPLETE=YES",
        "P5_AUTHORIZED=YES",
        "P5_STATUS=RELEASE_CLOSURE_DRAFT_REVIEW",
        "MCP_TOOL_COUNT=7",
        "REAL_TOOL7_FULL_CHAIN=PASS",
        "PROJECT_LAYOUT_VALIDATED=YES",
        "RELEASE_BLOCKERS=NONE",
        "TAG_AUTHORIZED=NO",
        "GITHUB_RELEASE_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert required in source


def test_mcp_surface_is_exactly_six_existing_tools_plus_tool_seven() -> None:
    expected_first_six = (
        "preview_zone_plan",
        "preview_cooling_load",
        "preview_equipment",
        "preview_installed_power",
        "preview_investment",
        "preview_factory_power",
    )
    assert expected_first_six == _PREVIEW_TOOL_ORDER
    assert (*expected_first_six, "preview_site_layout") == _MCP_TOOL_ORDER
    assert PREVIEW_SITE_LAYOUT_TOOL_NAME == "preview_site_layout"
    assert len(_MCP_TOOL_ORDER) == 7
    assert (
        *OPERATOR_V09_FIVE_KEY_FIELDS,
        "site_constraints",
        "truck_access",
        "truck_maneuver",
    ) == PREVIEW_SITE_LAYOUT_INPUT_FIELDS


def test_authority_identities_and_five_stage_calculation_boundary_are_preserved() -> None:
    assert P1_HANDOFF_IDENTITY == "p1-project-access-handoff@1.0.0"
    assert DIMENSION_HANDOFF_IDENTITY == "hybrid_zone_dimension_handoff@1.0.0"
    assert ACCESS_HANDOFF_IDENTITY == "p1-dimension-access-handoff@1.0.0"
    assert DIMENSIONING_IDENTITY == "zone_dimensioning_foundation@1.0.0"
    assert SITE_GEOMETRY_IDENTITY == "site-geometry-foundation@1.0.0"
    assert P2C_IDENTITY == "site-constrained-deterministic-placement@1.0.0"
    assert PLACEMENT_RESULT_IDENTITY == "site_constrained_factory_layout@1.0.0"
    assert P2D_IDENTITY == "site-access-routing-and-validation@1.0.0"
    assert P2D_RESULT_IDENTITY == "site_validated_layout@1.0.0"
    assert SELECTOR_IDENTITY == "p2-validated-candidate-selection-application@1.0.0"
    assert SELECTOR_RESULT_IDENTITY == "p2_validated_candidate_selection@1.0.0"
    assert OBJECTIVE_PROFILE_IDENTITY == "site-constrained-objective-profile@1.0.0"
    assert TRUCK_CONTRACT_IDENTITY == "truck-maneuver-template-contract@1.0.0"
    assert SVG_PROJECTION_IDENTITY == "validated-layout-svg-projection@1.0.0"
    assert FACTORY_POWER_CALCULATOR_VERSION == "2.0.0-p2"
    assert FACTORY_POWER_CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p2"
    assert FACTORY_POWER_RESULT_SCHEMA_VERSION == "2.0.0-p1"
    assert len(tuple(CalculationType)) == 5
    assert "factory_power" not in {member.value for member in CalculationType}


def test_p4_real_chain_evidence_and_no_production_imports_are_retained() -> None:
    p4_doc = _source("docs/tasks/V2_2-P4-mcp-tool7-doubao-feishu-integration.md")
    p4_unit = _source("backend/tests/unit/test_v22_p4_site_layout_mcp.py")
    for required in (
        "P4_COMPLETE=YES",
        "P4_PRODUCTION_FULL_PASS=YES",
        "P4_BLOCKER=NONE",
        "P2_VALIDATED_CANDIDATE_SELECTOR_USED=YES",
        "PACKAGING_SORTING_STRAIGHT_RULE_PRESERVED=YES",
    ):
        assert required in p4_doc
    for required in (
        "test_tool7_real_chain_selects_later_p2d_full_pass_and_projects_svg",
        "invoke_preview_site_layout_tool",
        "candidate_validation_trace",
        "svg_sha256",
    ):
        assert required in p4_unit
