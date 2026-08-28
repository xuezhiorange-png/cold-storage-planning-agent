"""HTTP inbound connector for 豆包工作伙伴 (Feishu Aily).

Thin routes: no engineering formulas and no chat parsing. 豆包 owns
semantics; this transport only forwards five KEY. Actor is the connector
transport, not model JSON.

Optional transport auth: when ``COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET`` is
set, callers must send matching ``X-Aily-Connector-Key``. Unset/blank keeps
the route open for local/test defaults. This is not production RBAC.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.aily.application.connector_auth import (
    CONNECTOR_KEY_HEADER,
    UNAUTHORIZED_CODE,
    verify_connector_key,
)
from cold_storage.modules.aily.application.zone_plan_preview import preview_zone_plan
from cold_storage.modules.aily.domain.errors import AilyConnectorError

router = APIRouter(prefix="/api/v1/aily", tags=["aily"])


def _connector_error_response(exc: AilyConnectorError) -> JSONResponse:
    status_code = 401 if exc.code == UNAUTHORIZED_CODE else 400
    return JSONResponse(
        status_code=status_code,
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


@router.post("/v1/zone-plan", response_model=None)
def post_zone_plan(
    payload: dict[str, Any],
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    x_aily_connector_key: str | None = Header(default=None, alias=CONNECTOR_KEY_HEADER),
) -> JSONResponse:
    """Collect five KEY from 豆包, run the zone kernel, return a table.

    Optional header ``X-Aily-Connector-Key`` must match
    ``COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET`` when that secret is configured.
    """
    try:
        verify_connector_key(
            x_aily_connector_key,
            get_settings().aily_connector_shared_secret,
        )
        body = preview_zone_plan(payload, correlation_id=x_correlation_id)
    except AilyConnectorError as exc:
        return _connector_error_response(exc)
    return JSONResponse(status_code=200, content=body)
