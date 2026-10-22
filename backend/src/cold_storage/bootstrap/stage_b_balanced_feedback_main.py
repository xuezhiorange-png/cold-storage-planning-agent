"""Fixed, initially unarmed balanced experiment; no caller-selected identity."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_balanced_feedback_main_execution import (
    BalancedMainStore,
)


def approved_balanced_main_store() -> BalancedMainStore:
    return BalancedMainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
