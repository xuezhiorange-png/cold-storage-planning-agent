"""Authorization rules for the planning agent."""

from __future__ import annotations

from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel
from cold_storage.modules.planning_agent.domain.errors import (
    ApprovedVersionWriteError,
    UnauthorizedError,
)


def check_authorization(
    level: AuthorizationLevel,
    *,
    is_admin: bool = False,
    is_session_owner: bool = False,
    version_status: str | None = None,
) -> None:
    """Validate that the caller is authorized for the given operation level."""
    if level == AuthorizationLevel.ADMINISTRATIVE and not is_admin:
        raise UnauthorizedError("Administrative operations require admin role")
    if (
        level in (AuthorizationLevel.WRITE, AuthorizationLevel.CALCULATE)
        and not is_admin
        and not is_session_owner
    ):
        raise UnauthorizedError(
            f"Operation requires admin or session owner for level {level.value}"
        )
    if (
        level in (AuthorizationLevel.WRITE, AuthorizationLevel.CALCULATE)
        and version_status == "approved"
    ):
        raise ApprovedVersionWriteError("approved version")


def requires_confirmation(level: AuthorizationLevel) -> bool:
    """Whether the given authorization level requires user confirmation."""
    return level in (AuthorizationLevel.WRITE, AuthorizationLevel.CALCULATE)
