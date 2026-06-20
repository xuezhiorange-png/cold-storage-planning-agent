from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelResponse:
    text: str
    structured_output: dict[str, object]


class ModelGateway(Protocol):
    def complete(self, prompt: str) -> ModelResponse:
        """Return structured extraction without performing engineering calculations."""
