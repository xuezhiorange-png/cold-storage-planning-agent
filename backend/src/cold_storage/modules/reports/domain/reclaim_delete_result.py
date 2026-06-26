"""Domain types for reclaim delete result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ReclaimDeleteResult:
    """Result of a reclaim_delete operation.

    Attributes
    ----------
    status:
        "deleted" — the file was actually removed.
        "already_missing" — the file was already gone; caller should treat
        this as success when debt ownership fully matches.
    storage_key:
        The storage key that was (or would have been) deleted.
    """

    status: Literal["deleted", "already_missing"]
    storage_key: str
