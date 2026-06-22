"""Application ports for the planning agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cold_storage.modules.planning_agent.domain.models import AgentDecision


@dataclass(frozen=True)
class AgentModelRequest:
    """Structured request sent to the model gateway."""

    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.0
    max_tokens: int = 4096


class AgentModelGateway(Protocol):
    """Port for the model gateway — returns structured decisions only."""

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision: ...


@dataclass(frozen=True)
class GatewayMetadata:
    provider: str = ""
    model_name: str = ""
    gateway_version: str = "1.0.0"
    production_ready: bool = False
    requires_review: bool = True
