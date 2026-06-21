"""SQLAlchemy ORM models for the planning agent persistence layer."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AgentSessionRecord(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    project_version_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="active")
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False, server_default="")
    created_by: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    closed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    next_message_sequence: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    next_turn_sequence: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))


class AgentMessageRecord(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")
    structured_content: Mapped[str | None] = mapped_column(sa.JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class AgentTurnRecord(Base):
    __tablename__ = "agent_turns"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "turn_number", name="uq_agent_turns_session_turn"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="processing")
    user_message_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    assistant_message_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    model_provider: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    model_name: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    prompt_version: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    request_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    decision_snapshot: Mapped[str | None] = mapped_column(sa.JSON, nullable=True)
    warning_messages: Mapped[str | None] = mapped_column(sa.JSON, nullable=True)
    requires_review: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("0")
    )
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    completed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class AgentToolCallRecord(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_turns.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="1.0.0")
    authorization_level: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="read"
    )
    arguments: Mapped[str] = mapped_column(sa.JSON, nullable=False, server_default="{}")
    arguments_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="proposed")
    result: Mapped[str | None] = mapped_column(sa.JSON, nullable=True)
    result_reference: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    warning_messages: Mapped[str | None] = mapped_column(sa.JSON, nullable=True)
    requires_review: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("0")
    )
    proposed_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    confirmed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    executed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class AgentConfirmationRecord(Base):
    __tablename__ = "agent_confirmations"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    tool_call_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_tool_calls.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False
    )
    confirmation_token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    arguments_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    confirmed_by: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="active")
    expires_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    used_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
