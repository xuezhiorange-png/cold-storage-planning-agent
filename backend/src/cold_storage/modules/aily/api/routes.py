"""HTTP inbound connector for 豆包工作伙伴 (Feishu Aily).

Thin routes: no engineering formulas and no chat parsing. 豆包 owns
semantics; this transport only forwards five KEY. Actor is the connector
transport, not model JSON.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from cold_storage.modules.aily.application.zone_plan_preview import preview_zone_plan
from cold_storage.modules.aily.domain.errors import AilyConnectorError

router = APIRouter(prefix="/api/v1/aily", tags=["aily"])


@router.post("/v1/zone-plan", response_model=None)
def post_zone_plan(
    payload: dict[str, Any],
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> JSONResponse:
    """Collect five KEY from 豆包, run the zone kernel, return a table."""
    try:
        body = preview_zone_plan(payload, correlation_id=x_correlation_id)
    except AilyConnectorError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "field_path": exc.field_path,
                    "missing_keys": list(exc.missing_keys),
                    "ask_operator": exc.ask_operator,
                    "details": dict(exc.details),
                }
            },
        )
    return JSONResponse(status_code=200, content=body)
