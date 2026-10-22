"""Trusted fixed slot; no caller-selected task identity, registry, budget or strategy."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    FeasibilityFirstMainStore,
)


def approved_feasibility_first_main_store() -> FeasibilityFirstMainStore:
    return FeasibilityFirstMainStore(
        Path.home() / ".local/state/cold-storage-planning-agent/owner-pools"
    )
