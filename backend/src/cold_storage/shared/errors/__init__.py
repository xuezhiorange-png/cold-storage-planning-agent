from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    details: dict[str, Any]


class DomainError(Exception):
    code = "DOMAIN_ERROR"


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class MissingEngineeringParameterError(DomainError):
    code = "MISSING_ENGINEERING_PARAMETER"


class InvalidEngineeringInputError(DomainError):
    code = "INVALID_ENGINEERING_INPUT"


class ProjectVersionLockedError(ApplicationError):
    code = "PROJECT_VERSION_LOCKED"
