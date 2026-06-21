"""Repository for agent session persistence — uses SQLAlchemy Session directly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from cold_storage.modules.planning_agent.domain.enums import (
    AuthorizationLevel,
    ConfirmationStatus,
    MessageRole,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import SessionNotFoundError
from cold_storage.modules.planning_agent.domain.models import (
    AgentConfirmation,
    AgentMessage,
    AgentSession,
    AgentToolCall,
    AgentTurn,
)
from cold_storage.modules.planning_agent.infrastructure.orm import (
    AgentConfirmationRecord,
    AgentIdempotencyRecord,
    AgentMessageRecord,
    AgentSessionRecord,
    AgentToolCallRecord,
    AgentTurnRecord,
)


class AgentRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    # ----- Sessions -----

    def create_session(self, s: AgentSession) -> AgentSession:
        rec = AgentSessionRecord(
            id=s.id,
            project_id=s.project_id,
            project_version_id=s.project_version_id,
            status=s.status.value,
            title=s.title,
            created_by=s.created_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
            closed_at=s.closed_at,
            next_message_sequence=s.next_message_sequence,
            next_turn_sequence=s.next_turn_sequence,
            version=s.version,
        )
        self._session.add(rec)
        self._session.flush()
        return s

    def get_session(self, session_id: str) -> AgentSession:
        rec = self._session.get(AgentSessionRecord, session_id)
        if rec is None:
            raise SessionNotFoundError(session_id)
        return self._to_session(rec)

    def update_session(self, s: AgentSession) -> AgentSession:
        rec = self._session.get(AgentSessionRecord, s.id)
        if rec is None:
            raise SessionNotFoundError(s.id)
        rec.status = s.status.value
        rec.updated_at = datetime.now(UTC)
        rec.closed_at = s.closed_at
        rec.next_message_sequence = s.next_message_sequence
        rec.next_turn_sequence = s.next_turn_sequence
        rec.version = s.version
        self._session.flush()
        return s

    def update_session_cas(self, s: AgentSession, expected_version: int) -> bool:
        """Fix #6: Atomic CAS on session version.

        UPDATE WHERE version=expected_version, returns True if updated.
        Prevents lost updates from concurrent requests.
        """
        stmt = (
            sa.update(AgentSessionRecord)
            .where(
                AgentSessionRecord.id == s.id,
                AgentSessionRecord.version == expected_version,
            )
            .values(
                status=s.status.value,
                updated_at=datetime.now(UTC),
                closed_at=s.closed_at,
                next_message_sequence=s.next_message_sequence,
                next_turn_sequence=s.next_turn_sequence,
                version=s.version,
            )
        )
        result = self._session.execute(stmt)
        self._session.flush()
        rowcount: int = result.rowcount or 0
        return rowcount == 1

    def list_sessions(self, limit: int = 50) -> list[AgentSession]:
        stmt = (
            sa.select(AgentSessionRecord)
            .order_by(AgentSessionRecord.created_at.desc())
            .limit(limit)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_session(r) for r in rows]

    # ----- Messages -----

    def add_message(self, m: AgentMessage) -> AgentMessage:
        rec = AgentMessageRecord(
            id=m.id,
            session_id=m.session_id,
            sequence=m.sequence,
            role=m.role.value,
            content=m.content,
            structured_content=m.structured_content,
            tool_call_id=m.tool_call_id,
            created_at=m.created_at,
        )
        self._session.add(rec)
        self._session.flush()
        return m

    def get_messages(self, session_id: str) -> list[AgentMessage]:
        stmt = (
            sa.select(AgentMessageRecord)
            .where(AgentMessageRecord.session_id == session_id)
            .order_by(AgentMessageRecord.sequence)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_message(r) for r in rows]

    # ----- Turns -----

    def add_turn(self, t: AgentTurn) -> AgentTurn:
        rec = AgentTurnRecord(
            id=t.id,
            session_id=t.session_id,
            turn_number=t.turn_number,
            status=t.status.value,
            user_message_id=t.user_message_id,
            assistant_message_id=t.assistant_message_id,
            model_provider=t.model_provider,
            model_name=t.model_name,
            prompt_version=t.prompt_version,
            request_sha256=t.request_sha256,
            decision_snapshot=t.decision_snapshot,
            warning_messages=t.warning_messages or [],
            requires_review=t.requires_review,
            created_at=t.created_at,
            completed_at=t.completed_at,
            error_code=t.error_code,
            error_message=t.error_message,
        )
        self._session.add(rec)
        self._session.flush()
        return t

    def update_turn(self, t: AgentTurn) -> AgentTurn:
        rec = self._session.get(AgentTurnRecord, t.id)
        if rec is None:
            return t
        rec.status = t.status.value
        rec.assistant_message_id = t.assistant_message_id
        rec.decision_snapshot = t.decision_snapshot
        rec.warning_messages = t.warning_messages or []
        rec.requires_review = t.requires_review
        rec.completed_at = t.completed_at
        rec.error_code = t.error_code
        rec.error_message = t.error_message
        self._session.flush()
        return t

    def get_turn(self, turn_id: str) -> AgentTurn | None:
        rec = self._session.get(AgentTurnRecord, turn_id)
        if rec is None:
            return None
        return self._to_turn(rec)

    def get_active_turn(self, session_id: str) -> AgentTurn | None:
        stmt = (
            sa.select(AgentTurnRecord)
            .where(
                AgentTurnRecord.session_id == session_id,
                AgentTurnRecord.status.in_(["processing", "awaiting_confirmation"]),
            )
            .order_by(AgentTurnRecord.turn_number.desc())
            .limit(1)
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        return self._to_turn(rec) if rec else None

    # ----- Tool calls -----

    def add_tool_call(self, tc: AgentToolCall) -> AgentToolCall:
        rec = AgentToolCallRecord(
            id=tc.id,
            session_id=tc.session_id,
            turn_id=tc.turn_id,
            tool_name=tc.tool_name,
            tool_version=tc.tool_version,
            authorization_level=tc.authorization_level.value,
            arguments=tc.arguments,
            arguments_sha256=tc.arguments_sha256,
            status=tc.status.value,
            result=tc.result,
            result_reference=tc.result_reference,
            warning_messages=tc.warning_messages or [],
            requires_review=tc.requires_review,
            proposed_at=tc.proposed_at,
            confirmed_at=tc.confirmed_at,
            executed_at=tc.executed_at,
            completed_at=tc.completed_at,
            error_code=tc.error_code,
            error_message=tc.error_message,
        )
        self._session.add(rec)
        self._session.flush()
        return tc

    def update_tool_call(self, tc: AgentToolCall) -> AgentToolCall:
        rec = self._session.get(AgentToolCallRecord, tc.id)
        if rec is None:
            return tc
        rec.status = tc.status.value
        rec.result = tc.result
        rec.result_reference = tc.result_reference
        rec.warning_messages = tc.warning_messages or []
        rec.requires_review = tc.requires_review
        rec.confirmed_at = tc.confirmed_at
        rec.executed_at = tc.executed_at
        rec.completed_at = tc.completed_at
        rec.error_code = tc.error_code
        rec.error_message = tc.error_message
        self._session.flush()
        return tc

    def get_tool_call(self, tool_call_id: str) -> AgentToolCall | None:
        rec = self._session.get(AgentToolCallRecord, tool_call_id)
        if rec is None:
            return None
        return self._to_tool_call(rec)

    def list_tool_calls(self, session_id: str) -> list[AgentToolCall]:
        stmt = (
            sa.select(AgentToolCallRecord)
            .where(AgentToolCallRecord.session_id == session_id)
            .order_by(AgentToolCallRecord.proposed_at)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_tool_call(r) for r in rows]

    # ----- Confirmations -----

    def add_confirmation(self, c: AgentConfirmation) -> AgentConfirmation:
        rec = AgentConfirmationRecord(
            id=c.id,
            tool_call_id=c.tool_call_id,
            session_id=c.session_id,
            confirmation_token_hash=c.confirmation_token_hash,
            arguments_sha256=c.arguments_sha256,
            confirmed_by=c.confirmed_by,
            status=c.status.value,
            expires_at=c.expires_at,
            created_at=c.created_at,
            used_at=c.used_at,
        )
        self._session.add(rec)
        self._session.flush()
        return c

    def get_confirmation_by_token_hash(self, token_hash: str) -> AgentConfirmation | None:
        stmt = sa.select(AgentConfirmationRecord).where(
            AgentConfirmationRecord.confirmation_token_hash == token_hash
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        if rec is None:
            return None
        return self._to_confirmation(rec)

    def update_confirmation(self, c: AgentConfirmation) -> AgentConfirmation:
        rec = self._session.get(AgentConfirmationRecord, c.id)
        if rec is None:
            return c
        rec.status = c.status.value
        rec.used_at = c.used_at
        rec.expires_at = c.expires_at
        self._session.flush()
        return c

    def claim_confirmation_atomic(
        self, confirmation_id: str, expected_status: str = "active"
    ) -> bool:
        """Fix #6: Atomic CAS — UPDATE WHERE status=expected, return success.

        Only one concurrent caller can succeed; others get False.
        """
        stmt = (
            sa.update(AgentConfirmationRecord)
            .where(
                AgentConfirmationRecord.id == confirmation_id,
                AgentConfirmationRecord.status == expected_status,
            )
            .values(status="used", used_at=sa.func.now())
        )
        result = self._session.execute(stmt)
        self._session.flush()
        rowcount: int = result.rowcount or 0
        return rowcount == 1

    # ----- Transaction boundary -----

    def commit(self) -> None:
        """Commit the current transaction. Fix #9: explicit transaction boundary."""
        self._session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self._session.rollback()

    # ----- Idempotency -----

    def get_idempotency_record(self, session_id: str, key: str) -> AgentIdempotencyRecord | None:
        """Indexed lookup for idempotency record."""
        stmt = sa.select(AgentIdempotencyRecord).where(
            AgentIdempotencyRecord.session_id == session_id,
            AgentIdempotencyRecord.idempotency_key == key,
        )
        record: AgentIdempotencyRecord | None = self._session.execute(stmt).scalar_one_or_none()
        return record

    def claim_idempotency(
        self,
        session_id: str,
        key: str,
        turn_id: str,
    ) -> bool:
        """Atomically insert idempotency record with status='processing'.

        Returns True if inserted (claim succeeded), False if duplicate exists.
        Uses the unique constraint for atomicity.
        Only catches IntegrityError (duplicate key); other DB errors propagate.
        """
        import uuid as _uuid

        from sqlalchemy.exc import IntegrityError

        rec = AgentIdempotencyRecord(
            id=str(_uuid.uuid4()),
            session_id=session_id,
            idempotency_key=key,
            status="processing",
            turn_id=turn_id,
        )
        self._session.add(rec)
        try:
            self._session.flush()
            return True
        except IntegrityError:
            self._session.rollback()
            return False

    def complete_idempotency(
        self,
        session_id: str,
        key: str,
        turn_id: str,
        result_payload: dict[str, Any],
    ) -> None:
        """Mark idempotency record as completed with the full result payload.

        Also updates the placeholder turn_id to the real turn_id.
        """
        stmt = (
            sa.update(AgentIdempotencyRecord)
            .where(
                AgentIdempotencyRecord.session_id == session_id,
                AgentIdempotencyRecord.idempotency_key == key,
            )
            .values(
                status="completed",
                turn_id=turn_id,
                result_payload=result_payload,
            )
        )
        self._session.execute(stmt)

    # ----- Serializers -----

    def _to_session(self, r: AgentSessionRecord) -> AgentSession:
        return AgentSession(
            id=r.id,
            project_id=r.project_id,
            project_version_id=r.project_version_id,
            status=SessionStatus(r.status),
            title=r.title,
            created_by=r.created_by,
            created_at=r.created_at,  # type: ignore[arg-type]
            updated_at=r.updated_at,  # type: ignore[arg-type]
            closed_at=r.closed_at,  # type: ignore[arg-type]
            next_message_sequence=r.next_message_sequence,
            next_turn_sequence=r.next_turn_sequence,
            version=r.version,
        )

    def _to_message(self, r: AgentMessageRecord) -> AgentMessage:
        return AgentMessage(
            id=r.id,
            session_id=r.session_id,
            sequence=r.sequence,
            role=MessageRole(r.role),
            content=r.content,
            structured_content=r.structured_content,
            tool_call_id=r.tool_call_id,
            created_at=r.created_at,  # type: ignore[arg-type]
        )

    def _to_turn(self, r: AgentTurnRecord) -> AgentTurn:
        return AgentTurn(
            id=r.id,
            session_id=r.session_id,
            turn_number=r.turn_number,
            status=TurnStatus(r.status),
            user_message_id=r.user_message_id,
            assistant_message_id=r.assistant_message_id,
            model_provider=r.model_provider,
            model_name=r.model_name,
            prompt_version=r.prompt_version,
            request_sha256=r.request_sha256,
            decision_snapshot=r.decision_snapshot,
            warning_messages=r.warning_messages or [],
            requires_review=r.requires_review,
            created_at=r.created_at,  # type: ignore[arg-type]
            completed_at=r.completed_at,  # type: ignore[arg-type]
            error_code=r.error_code,
            error_message=r.error_message,
        )

    def _to_tool_call(self, r: AgentToolCallRecord) -> AgentToolCall:
        return AgentToolCall(
            id=r.id,
            session_id=r.session_id,
            turn_id=r.turn_id,
            tool_name=r.tool_name,
            tool_version=r.tool_version,
            authorization_level=AuthorizationLevel(r.authorization_level),
            arguments=r.arguments or {},
            arguments_sha256=r.arguments_sha256,
            status=ToolCallStatus(r.status),
            result=r.result,
            result_reference=r.result_reference,
            warning_messages=r.warning_messages or [],
            requires_review=r.requires_review,
            proposed_at=r.proposed_at,  # type: ignore[arg-type]
            confirmed_at=r.confirmed_at,  # type: ignore[arg-type]
            executed_at=r.executed_at,  # type: ignore[arg-type]
            completed_at=r.completed_at,  # type: ignore[arg-type]
            error_code=r.error_code,
            error_message=r.error_message,
        )

    def _to_confirmation(self, r: AgentConfirmationRecord) -> AgentConfirmation:
        return AgentConfirmation(
            id=r.id,
            tool_call_id=r.tool_call_id,
            session_id=r.session_id,
            confirmation_token_hash=r.confirmation_token_hash,
            arguments_sha256=r.arguments_sha256,
            confirmed_by=r.confirmed_by,
            status=ConfirmationStatus(r.status),
            expires_at=r.expires_at,  # type: ignore[arg-type]
            created_at=r.created_at,  # type: ignore[arg-type]
            used_at=r.used_at,  # type: ignore[arg-type]
        )
