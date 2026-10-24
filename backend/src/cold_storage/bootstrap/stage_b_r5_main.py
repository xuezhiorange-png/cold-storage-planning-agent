"""Fixed R5 trusted registry location; constructor never signs/approves/claims."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r5_main_execution import R5MainStore


def approved_r5_main_store() -> R5MainStore:
    return R5MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
