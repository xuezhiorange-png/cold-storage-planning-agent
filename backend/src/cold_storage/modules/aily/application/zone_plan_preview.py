"""Run the existing zone-plan kernel for an Aily / 豆包 conversation.

Does not persist projects. Does not let the model compute engineering values.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.stage_preview import (
    preview_zone_plan as _preview_zone_plan,
)

ZONE_CALCULATOR_NAME = "cold_room_zone_plan"
ZONE_CALCULATOR_VERSION = "1.0.0"


def preview_zone_plan(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run cold_room_zone_plan, return a conversation table."""
    return _preview_zone_plan(payload, correlation_id=correlation_id)
