"""Agent Orchestrator — coordinates model gateway + tool execution.

The orchestrator does NOT hold a DB session. It receives data from the service
and returns results. All persistence goes through the repository passed in.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.planning_agent.application.tool_registry import ToolRegistry
from cold_storage.modules.planning_agent.domain.enums import (
    DecisionType,
    MessageRole,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import (
    InvalidStructuredOutputError,
    ModelGatewayError,
    ToolCallLimitExceededError,
    UnregisteredToolError,
)
from cold_storage.modules.planning_agent.domain.gateways import (
    AgentModelGateway,
    AgentModelRequest,
)
from cold_storage.modules.planning_agent.domain.lifecycle import (
    validate_session_transition,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
    AgentTurn,
    sha256_json,
)
from cold_storage.modules.planning_agent.infrastructure.tool_adapters import ToolAdapter

# V1 prompt version
PROMPT_VERSION = "planning-agent-system-v1"

_SYSTEM_PROMPT = """你是冷库规划设计 Agent。
你的职责是理解用户规划意图，识别缺失参数，选择经过注册的工具，提出待执行操作。
你不得直接进行工程计算。所有数值必须来自工具结果。
制冷能力与冷负荷单位: kW(r)，电输入: kW(e)，热排放: kW(th)，能量: kWh。
请以 JSON 格式返回结构化决策。"""


class AgentOrchestrator:
    """Coordinates model gateway decisions with tool execution."""

    def __init__(self, tool_adapters: dict[str, ToolAdapter] | None = None) -> None:
        self._adapters: dict[str, ToolAdapter] = tool_adapters or {}

    def register_adapter(self, tool_name: str, adapter: ToolAdapter) -> None:
        self._adapters[tool_name] = adapter

    def orchestrate_turn(
        self,
        *,
        session: AgentSession,
        turn: AgentTurn,
        user_message: AgentMessage,
        gateway: AgentModelGateway,
        registry: ToolRegistry,
        repo: Any,
    ) -> dict[str, Any]:
        """Full turn orchestration: gateway -> decision -> tools -> result."""
        # Build message history
        messages = [{"role": "user", "content": user_message.content}]

        # Build tools list for gateway
        tool_defs = []
        for t in registry.list_tools():
            tool_defs.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
            )

        request = AgentModelRequest(
            system_prompt=_SYSTEM_PROMPT,
            messages=messages,
            tools=tool_defs,
        )

        # Get decision from gateway
        try:
            decision = gateway.generate_decision(request)
        except Exception as exc:
            raise ModelGatewayError(f"Gateway error: {exc}") from exc

        # Validate decision
        if decision.decision_type not in DecisionType:
            raise InvalidStructuredOutputError(f"Unknown decision type: {decision.decision_type}")

        # Process based on decision type
        tool_calls: list[AgentToolCall] = []
        confirmation_required = False

        if decision.decision_type == DecisionType.PROPOSE_TOOLS:
            if len(decision.tool_requests) > registry._tools.__len__() + 10:
                pass  # limit check below

            if len(decision.tool_requests) > 5:
                raise ToolCallLimitExceededError(5)

            for tool_req in decision.tool_requests:
                if not registry.is_registered(tool_req.tool_name):
                    raise UnregisteredToolError(tool_req.tool_name)
                registry.validate_arguments(tool_req.tool_name, tool_req.arguments)

                tool = registry.get(tool_req.tool_name)
                check_level = tool.authorization_level
                needs_confirm = tool.requires_confirmation

                tc = AgentToolCall(
                    session_id=session.id,
                    turn_id=turn.id,
                    tool_name=tool_req.tool_name,
                    tool_version=tool.version,
                    authorization_level=check_level,
                    arguments=tool_req.arguments,
                    arguments_sha256=sha256_json(tool_req.arguments),
                )

                if needs_confirm:
                    tc = AgentToolCall(
                        **{
                            **asdict(tc),
                            "status": ToolCallStatus.AWAITING_CONFIRMATION,
                        }
                    )
                    confirmation_required = True
                else:
                    # Auto-execute read/calculate tools
                    tc = AgentToolCall(
                        **{
                            **asdict(tc),
                            "status": ToolCallStatus.EXECUTING,
                            "executed_at": datetime.now(UTC),
                        }
                    )
                    try:
                        result = self.execute_single_tool(
                            tool_req.tool_name, tool_req.arguments, registry
                        )
                        tc = AgentToolCall(
                            **{
                                **asdict(tc),
                                "status": ToolCallStatus.SUCCEEDED,
                                "result": result.output,
                                "warning_messages": result.warnings,
                                "requires_review": result.requires_review,
                                "completed_at": datetime.now(UTC),
                            }
                        )
                    except Exception as exc:
                        tc = AgentToolCall(
                            **{
                                **asdict(tc),
                                "status": ToolCallStatus.FAILED,
                                "error_code": type(exc).__name__,
                                "error_message": str(exc),
                                "completed_at": datetime.now(UTC),
                            }
                        )
                        # Stop on failure
                        break

                repo.add_tool_call(tc)
                tool_calls.append(tc)

        # Build assistant message
        assistant_content = decision.assistant_message
        if tool_calls:
            tc_summary = [f"{tc.tool_name}({tc.status.value})" for tc in tool_calls]
            assistant_content += f"\n工具调用: {', '.join(tc_summary)}"

        now = datetime.now(UTC)
        assistant_msg = AgentMessage(
            session_id=session.id,
            sequence=session.next_message_sequence,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            structured_content={
                "decision_type": decision.decision_type.value,
                "missing_parameters": decision.missing_parameters,
                "citations": decision.citations,
                "requires_review": decision.requires_review,
                "warnings": decision.warnings,
            },
            created_at=now,
        )
        repo.add_message(assistant_msg)

        # Update session
        updated_session = AgentSession(
            **{
                **asdict(session),
                "next_message_sequence": session.next_message_sequence + 1,
                "updated_at": now,
                "version": session.version + 1,
            }
        )
        repo.update_session(updated_session)

        # Complete turn
        turn_status = (
            TurnStatus.AWAITING_CONFIRMATION if confirmation_required else TurnStatus.COMPLETED
        )
        completed_turn = AgentTurn(
            **{
                **asdict(turn),
                "status": turn_status,
                "assistant_message_id": assistant_msg.id,
                "model_provider": "fake" if hasattr(gateway, "get_metadata") else "unknown",
                "model_name": gateway.get_metadata().model_name
                if hasattr(gateway, "get_metadata")
                else "",
                "prompt_version": PROMPT_VERSION,
                "request_sha256": sha256_json(messages),
                "decision_snapshot": {
                    "decision_type": decision.decision_type.value,
                    "tool_calls": [tc.tool_name for tc in tool_calls],
                },
                "warning_messages": decision.warnings,
                "requires_review": decision.requires_review
                or any(tc.requires_review for tc in tool_calls),
                "completed_at": now,
            }
        )
        repo.update_turn(completed_turn)

        # Update session status if awaiting confirmation
        if confirmation_required:
            validate_session_transition(session.status, SessionStatus.AWAITING_CONFIRMATION)
            awaiting = AgentSession(
                **{
                    **asdict(updated_session),
                    "status": SessionStatus.AWAITING_CONFIRMATION,
                    "updated_at": now,
                    "version": updated_session.version + 1,
                }
            )
            repo.update_session(awaiting)

        return {
            "session_id": session.id,
            "turn_id": turn.id,
            "assistant_message": assistant_msg.content,
            "decision_type": decision.decision_type.value,
            "tool_calls": [
                {
                    "id": tc.id,
                    "tool_name": tc.tool_name,
                    "status": tc.status.value,
                    "requires_confirmation": tc.status == ToolCallStatus.AWAITING_CONFIRMATION,
                }
                for tc in tool_calls
            ],
            "missing_parameters": decision.missing_parameters,
            "requires_review": decision.requires_review,
            "warnings": decision.warnings,
            "prompt_version": PROMPT_VERSION,
            "model_metadata": gateway.get_metadata() if hasattr(gateway, "get_metadata") else {},
        }

    def execute_single_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        registry: ToolRegistry,
    ) -> Any:
        """Execute a single tool through its adapter."""
        registry.validate_arguments(tool_name, arguments)
        adapter = self._adapters.get(tool_name)
        if adapter is None:
            raise UnregisteredToolError(tool_name)
        return adapter.execute(arguments)
