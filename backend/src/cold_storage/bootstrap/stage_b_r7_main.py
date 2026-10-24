"""Fixed R7 trusted registry; construction never approves or consumes a Grant."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r7_main_execution import R7MainStore


def approved_r7_main_store() -> R7MainStore:
    return R7MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
