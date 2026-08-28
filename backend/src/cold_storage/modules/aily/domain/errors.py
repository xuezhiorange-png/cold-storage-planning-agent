"""Fail-closed errors for the Aily conversation connector."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AilyConnectorError(Exception):
    """Inbound connector rejection. Not an engineering formula error."""

    code: str
    message: str
    field_path: str
    missing_keys: tuple[str, ...] = ()
    ask_operator: str = ""
    details: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
