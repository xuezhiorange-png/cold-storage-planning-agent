"""Optional shared-secret gate for the inbound Aily zone-plan connector.

Transport authentication only — not production RBAC, not mark_reviewed, not
user roles. When ``COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET`` is unset or
blank, the connector remains open for local/test backward compatibility.
"""

from __future__ import annotations

import hmac
from typing import TypeGuard

from cold_storage.modules.aily.domain.errors import AilyConnectorError

CONNECTOR_KEY_HEADER = "X-Aily-Connector-Key"
UNAUTHORIZED_CODE = "AILY_CONNECTOR_UNAUTHORIZED"


def connector_secret_configured(secret: str | None) -> TypeGuard[str]:
    """Return True when a non-blank shared secret is configured."""
    return secret is not None and bool(secret.strip())


def verify_connector_key(
    header_value: str | None,
    configured_secret: str | None,
) -> None:
    """Validate the inbound connector header against the configured secret.

    Fail closed when a secret is configured: missing or wrong header raises
    ``AilyConnectorError`` with code ``AILY_CONNECTOR_UNAUTHORIZED``. When the
    secret is unset or blank, auth is bypassed.
    """
    if not connector_secret_configured(configured_secret):
        return

    expected = configured_secret.strip()
    provided = header_value or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise AilyConnectorError(
            code=UNAUTHORIZED_CODE,
            message="Invalid or missing Aily connector authentication",
            field_path=f"headers.{CONNECTOR_KEY_HEADER}",
        )
