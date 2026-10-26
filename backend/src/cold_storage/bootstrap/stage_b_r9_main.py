"""Fixed R9 trusted registry; construction never approves or consumes a Grant."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r9_main_execution import R9MainStore


def approved_r9_main_store() -> R9MainStore:
    return R9MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
