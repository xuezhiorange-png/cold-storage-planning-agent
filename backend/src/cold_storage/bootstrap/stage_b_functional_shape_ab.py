"""Trusted fixed A/B task slots; no caller identity, quota or registry selection."""

from pathlib import Path

from cold_storage.modules.layout.infrastructure.stage_b_functional_shape_ab import (
    FunctionalShapeABStore,
)


def approved_functional_shape_ab_stores() -> tuple[FunctionalShapeABStore, FunctionalShapeABStore]:
    registry = Path.home() / ".local/state/cold-storage-planning-agent/owner-pools"
    return FunctionalShapeABStore(registry, "A"), FunctionalShapeABStore(registry, "B")
