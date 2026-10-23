"""Fixed R4 trusted registry location; constructor never signs/approves/claims."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r4_main_execution import R4MainStore


def approved_r4_main_store() -> R4MainStore:
    return R4MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
