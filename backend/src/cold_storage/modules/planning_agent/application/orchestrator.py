"""Agent Orchestrator — coordinates model gateway + tool execution.

The orchestrator does NOT hold a DB session. It receives data from the service
and returns results. All persistence goes through the repository passed in.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
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
    UnauthorizedError,
    UnregisteredToolError,
)
from cold_storage.modules.planning_agent.domain.gateways import (
    AgentModelGateway,
    AgentModelRequest,
    GatewayMetadata,
)
from cold_storage.modules.planning_agent.domain.lifecycle import (
    validate_session_transition,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentConfirmation,
    AgentMessage,
    AgentSession,
    AgentToolCall,
    AgentTurn,
    sha256_json,
)
from cold_storage.modules.planning_agent.infrastructure.tool_adapters import ToolAdapter
from cold_storage.modules.planning_agent.prompts.system_v1 import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_V1,
)

# Confirmation token TTL: 30 minutes
_CONFIRMATION_TOKEN_TTL = timedelta(minutes=30)


class AgentOrchestrator:
    """Coordinates model gateway decisions with tool execution."""

    def __init__(
        self,
        tool_adapters: dict[str, ToolAdapter] | None = None,
        *,
        max_tool_calls: int = 5,
        project_service: Any = None,
    ) -> None:
        self._adapters: dict[str, ToolAdapter] = tool_adapters or {}
        self._max_tool_calls = max_tool_calls
        self._project_service = project_service

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
        user: str = "user",
    ) -> dict[str, Any]:
        """Full turn orchestration: gateway -> decision -> tools -> result.

        Returns dict with results and, when tools require confirmation,
        a ``pending_confirmations`` list containing plaintext tokens.
        """
        # Build message history from prior messages + current user message
        prior_messages = repo.get_messages(session.id)
        messages: list[dict[str, Any]] = []
        for msg in prior_messages:
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": user_message.content})

        # Build tools list for gateway
        tool_defs = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in registry.list_tools()
        ]

        request = AgentModelRequest(
            system_prompt=SYSTEM_PROMPT_V1,
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
        confirmations: list[AgentConfirmation] = []
        confirmation_tokens: list[dict[str, Any]] = []
        confirmation_required = False
        turn_failed = False

        if decision.decision_type == DecisionType.PROPOSE_TOOLS:
            if len(decision.tool_requests) > self._max_tool_calls:
                raise ToolCallLimitExceededError(self._max_tool_calls)

            for tool_req in decision.tool_requests:
                if not registry.is_registered(tool_req.tool_name):
                    raise UnregisteredToolError(tool_req.tool_name)

                # --- Authorization enforcement (Fix #5) ---
                tool_def = registry.get(tool_req.tool_name)
                self._enforce_authorization(
                    tool_def,
                    session=session,
                    gateway_metadata=gateway.get_metadata()
                    if hasattr(gateway, "get_metadata")
                    else None,
                    user=user,
                    repo=repo,
                )

                registry.validate_arguments(tool_req.tool_name, tool_req.arguments)

                tc = AgentToolCall(
                    session_id=session.id,
                    turn_id=turn.id,
                    tool_name=tool_req.tool_name,
                    tool_version=tool_def.version,
                    authorization_level=tool_def.authorization_level,
                    arguments=tool_req.arguments,
                    arguments_sha256=sha256_json(tool_req.arguments),
                )

                if tool_def.requires_confirmation:
                    # --- Create confirmation with token (Fix #2) ---
                    tc = AgentToolCall(
                        **{
                            **asdict(tc),
                            "status": ToolCallStatus.AWAITING_CONFIRMATION,
                        }
                    )
                    confirmation_required = True

                    # Generate one-time confirmation token
                    token = secrets.token_urlsafe(32)
                    token_hash = sha256_json(token)
                    now = datetime.now(UTC)
                    confirmation = AgentConfirmation(
                        tool_call_id=tc.id,
                        session_id=session.id,
                        confirmation_token_hash=token_hash,
                        arguments_sha256=tc.arguments_sha256,
                        confirmed_by=session.created_by,
                        expires_at=now + _CONFIRMATION_TOKEN_TTL,
                        created_at=now,
                    )
                    confirmations.append(confirmation)
                    confirmation_tokens.append(
                        {
                            "tool_call_id": tc.id,
                            "confirmation_token": token,
                            "expires_at": (now + _CONFIRMATION_TOKEN_TTL).isoformat(),
                            "arguments_sha256": tc.arguments_sha256,
                        }
                    )
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
                        turn_failed = True
                        # Stop on failure
                        break

                repo.add_tool_call(tc)
                tool_calls.append(tc)

            # Persist confirmations
            for conf in confirmations:
                repo.add_confirmation(conf)

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

        # Update session (CAS to prevent lost updates)
        updated_session = AgentSession(
            **{
                **asdict(session),
                "next_message_sequence": session.next_message_sequence + 1,
                "updated_at": now,
                "version": session.version + 1,
            }
        )
        cas_ok = repo.update_session_cas(updated_session, expected_version=session.version)
        if not cas_ok:
            from cold_storage.modules.planning_agent.domain.errors import ConcurrentTurnError

            raise ConcurrentTurnError(session.id)

        # Build full request SHA-256 for audit (Fix #11)
        full_request_for_audit = {
            "system_prompt": SYSTEM_PROMPT_V1,
            "messages": messages,
            "tools": tool_defs,
        }
        request_sha256 = sha256_json(full_request_for_audit)

        # Use gateway metadata for provider (Fix #11)
        metadata: GatewayMetadata | None = (
            gateway.get_metadata() if hasattr(gateway, "get_metadata") else None
        )
        model_provider = metadata.provider if metadata else "unknown"
        model_name_str = metadata.model_name if metadata else ""

        # Fix #6: Complete turn — handle failure
        if turn_failed:
            failed_tc = next((tc for tc in tool_calls if tc.status == ToolCallStatus.FAILED), None)
            failure_content = (
                f"\u5de5\u5177 {failed_tc.tool_name} \u6267\u884c\u5931\u8d25:"
                f" {failed_tc.error_message}"
                if failed_tc
                else "\u5de5\u5177\u6267\u884c\u5931\u8d25"
            )
            failure_msg = AgentMessage(
                session_id=session.id,
                sequence=session.next_message_sequence + 1,
                role=MessageRole.TOOL,
                content=failure_content,
                created_at=now,
            )
            repo.add_message(failure_msg)
            turn_status = TurnStatus.FAILED
        else:
            turn_status = (
                TurnStatus.AWAITING_CONFIRMATION if confirmation_required else TurnStatus.COMPLETED
            )

        completed_turn = AgentTurn(
            **{
                **asdict(turn),
                "status": turn_status,
                "assistant_message_id": assistant_msg.id,
                "model_provider": model_provider,
                "model_name": model_name_str,
                "prompt_version": PROMPT_VERSION,
                "request_sha256": request_sha256,
                "decision_snapshot": {
                    "decision_type": decision.decision_type.value,
                    "tool_calls": [
                        {
                            "tool_name": tc.tool_name,
                            "arguments": tc.arguments,
                            "status": tc.status.value,
                        }
                        for tc in tool_calls
                    ],
                    "missing_parameters": decision.missing_parameters,
                    "citations": decision.citations,
                    "warnings": decision.warnings,
                },
                "warning_messages": decision.warnings,
                "requires_review": decision.requires_review
                or any(tc.requires_review for tc in tool_calls),
                "completed_at": now,
                **(
                    {
                        "error_code": (failed_tc.error_code if turn_failed and failed_tc else None),
                        "error_message": (
                            failed_tc.error_message if turn_failed and failed_tc else None
                        ),
                    }
                    if turn_failed
                    else {}
                ),
            }
        )
        repo.update_turn(completed_turn)

        # Update session status if awaiting confirmation (CAS)
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
            cas_ok = repo.update_session_cas(awaiting, expected_version=updated_session.version)
            if not cas_ok:
                from cold_storage.modules.planning_agent.domain.errors import ConcurrentTurnError

                raise ConcurrentTurnError(session.id)

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
            "pending_confirmations": confirmation_tokens,
            "missing_parameters": decision.missing_parameters,
            "requires_review": decision.requires_review,
            "warnings": decision.warnings,
            "prompt_version": PROMPT_VERSION,
            "model_metadata": asdict(metadata) if metadata else {},
        }

    def _enforce_authorization(
        self,
        tool_def: Any,
        *,
        session: AgentSession,
        gateway_metadata: GatewayMetadata | None,
        user: str = "user",
        repo: Any = None,
    ) -> None:
        """Fix #5: Enforce tool-level authorization, project/version binding.

        Validates:
        - Session owner matches current actor
        - Project and version exist (if required by tool)
        - Version belongs to the bound project
        - Version status is in allowed_version_statuses
        - Approved versions cannot be modified
        """
        from cold_storage.modules.planning_agent.domain.authorization import (
            check_authorization,
        )
        from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel

        # Validate session owner matches current actor
        is_owner = session.created_by == user
        check_authorization(
            tool_def.authorization_level,
            is_session_owner=is_owner,
        )

        # Check project binding
        if tool_def.requires_project and not session.project_id:
            raise UnauthorizedError(f"Tool {tool_def.name} requires a bound project")

        # Check version binding
        if tool_def.requires_project_version and not session.project_version_id:
            raise UnauthorizedError(f"Tool {tool_def.name} requires a bound project version")

        # Fix #3: Validate project/version existence and status — fail closed
        if tool_def.requires_project_version and session.project_id and session.project_version_id:
            if self._project_service is None:
                raise UnauthorizedError(
                    "Project service not configured — cannot validate version status"
                )
            assert session.project_id is not None  # guarded by outer if
            try:
                versions = self._project_service.list_versions(session.project_id)
            except Exception as exc:
                raise UnauthorizedError(f"Failed to query project versions: {exc}") from exc
            version_obj = None
            for v in versions:
                if v.id == session.project_version_id or str(v.version_number) == str(
                    session.project_version_id
                ):
                    version_obj = v
                    break
            if version_obj is None:
                raise UnauthorizedError(f"Project version {session.project_version_id} not found")
            # Check version status is in allowed statuses
            if version_obj.status not in tool_def.allowed_version_statuses:
                raise UnauthorizedError(
                    f"Version status '{version_obj.status}' not in allowed "
                    f"{tool_def.allowed_version_statuses} for tool {tool_def.name}"
                )
            # Check approved version write rejection
            if (
                tool_def.authorization_level
                in (AuthorizationLevel.WRITE, AuthorizationLevel.CALCULATE)
                and version_obj.status == "approved"
            ):
                raise UnauthorizedError("Cannot modify an approved version")

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
