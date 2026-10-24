"""Fixed R6 trusted registry; construction never approves or consumes a Grant."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_r6_main_execution import R6MainStore


def approved_r6_main_store() -> R6MainStore:
    return R6MainStore(Path.home() / ".local/state/cold-storage-planning-agent/owner-pools")
