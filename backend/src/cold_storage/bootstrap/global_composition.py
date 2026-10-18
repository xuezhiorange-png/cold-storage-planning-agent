"""Explicit internal stage-A composition root; intentionally not wired to MCP.

Callers supply business-derived server authorities, never room coordinates.
The official P1A/P3 selector, deployment and production numerical budgets stay
unchanged. This root is opt-in until a formal CP-SAT resource mapping is approved.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.global_composition_pool import (
    generate_global_composition_pool,
)
from cold_storage.modules.layout.application.global_composition_solver import (
    DEFAULT_STAGE_A_COMPOSITION,
    StageALedger,
    generate_global_composition_candidate,
)
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)
from cold_storage.modules.layout.infrastructure.stage_a_execution import OwnerExecutionStore
from cold_storage.modules.layout.infrastructure.stage_a_production_execution import (
    ProductionReplayStore,
)
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    StageBGuidedConstructionSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution import (
    StageBMultiSolutionSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution_execution import (
    MultiSolutionPoolExecutionStore,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolExecutionStore

INDEPENDENT_OWNER_TASK = "V2_2_2_R16_INDEPENDENT_EXECUTION_AND_ENGINEERING_VALIDATION_R1"
INDEPENDENT_OWNER_INSTRUCTION_SHA256 = (
    "4c511e5ec43e6eba17b091dcf239a8df643a820b22d36684e22506c1baed4f83"
)
STAGE_B_OWNER_TASK = "REAL_MULTI_STRUCTURAL_CONSTRUCTION_AND_VALIDATION"
STAGE_B_OWNER_SHA256 = "d24dde1e2a51abfb35920884165cf0e01e72d5f1f731c88c7de01b77073af1e3"
MULTI_SOLUTION_OWNER_TASK = "REAL_MULTI_SOLUTION_VALIDATION_01"
MULTI_SOLUTION_OWNER_SHA256 = "5e2c4a256aaa61c4d0572bf533c184d06d397df7efec63489b8248f8f3aa27e1"


def approved_stage_b_multi_solution_store() -> MultiSolutionPoolExecutionStore:
    """New explicitly approved task slot; never reopens the old consumed grant."""
    return MultiSolutionPoolExecutionStore(
        Path.home() / ".local/state/cold-storage-planning-agent/owner-pools",
        MULTI_SOLUTION_OWNER_TASK,
        MULTI_SOLUTION_OWNER_SHA256,
    )


def approved_stage_b_pool_store() -> PoolExecutionStore:
    """Pinned trusted operator grant; no MCP/caller registry or approval input."""
    return PoolExecutionStore(
        Path.home() / ".local/state/cold-storage-planning-agent/owner-pools",
        STAGE_B_OWNER_TASK,
        STAGE_B_OWNER_SHA256,
    )


def production_replay_execution_store() -> ProductionReplayStore:
    """Two approved replays share one task slot; never used by the public selector."""
    return ProductionReplayStore(
        Path.home()
        / "Documents/Codex/cold-storage-planning-agent/artifacts/execution-authorizations",
        "V2_2_2_STAGE_A_FINAL_PRODUCTION_CLOSURE_R2",
        "8b9b539b9d4b3713b40ccd9b08fb7ac66d5c739695f5f5cae2b75015e50664f9",
    )


def owner_approved_execution_store() -> OwnerExecutionStore:
    """Trusted local stage-A registry; neither MCP nor output paths configure it.

    This explicit Owner grant is a one-task research authorization, not a default
    server selector or a general public authorization API. Tests use isolated
    registries, never this real grant's one allocation slot.
    """
    registry = (
        Path.home()
        / "Documents/Codex/cold-storage-planning-agent/artifacts"
        / "execution-authorizations"
    )
    return OwnerExecutionStore(
        registry, INDEPENDENT_OWNER_TASK, INDEPENDENT_OWNER_INSTRUCTION_SHA256
    )


def generate_controlled_global_layout(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    composition_identity: str = DEFAULT_STAGE_A_COMPOSITION,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    return generate_global_composition_candidate(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        solver=OrToolsGlobalCompositionSolver(),
        composition_identity=composition_identity,
        execution_ledger=execution_ledger,
    )


def generate_controlled_global_layout_pool(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    """Internal Stage B only; no MCP/selector hookup and no inherited A grant.

    Without a separately approved durable pool lease this returns quota-required
    BEFORE any native solve. This task deliberately issues no such lease.
    """
    return generate_global_composition_pool(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        solver=OrToolsGlobalCompositionSolver(),
        execution_ledger=execution_ledger,
    )


def generate_guided_global_layout_pool(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    """Explicit Stage-B soft-guidance entry; no quota or public Tool7 contract.

    Original Stage-A and pool entry signatures/behavior are preserved. A new
    real execution still requires a separately approved, source-bound PoolLease.
    """
    return generate_global_composition_pool(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        solver=StageBGuidedConstructionSolver(),
        execution_ledger=execution_ledger,
    )


def generate_multi_solution_global_layout_pool(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    """Explicit internal enumeration; never creates or refreshes an Owner grant."""
    return generate_multi_solution_pool(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        solver=StageBMultiSolutionSolver(),
        execution_ledger=execution_ledger,
    )
