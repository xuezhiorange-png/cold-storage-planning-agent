"""Fixed R10 R2 trusted registry; construction never approves or consumes a Grant."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r10_r2_main_execution import R10R2MainStore


def approved_r10_r2_main_store() -> R10R2MainStore:
    return R10R2MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
