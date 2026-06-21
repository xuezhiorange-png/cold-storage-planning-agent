"""Add planning agent tables.

Revision ID: 0008_add_planning_agent
Revises: 0007_add_knowledge_base
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from alembic import op



# Fix #1: Dialect-aware JSON type — PostgreSQL uses JSONB, SQLite uses JSON
def _json_type():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql.JSONB
    return sqlite.JSON


revision = "0008_add_planning_agent"
down_revision = "0007_add_knowledge_base"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    bool_false = sa.text("0") if dialect == "sqlite" else sa.text("false")

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("project_version_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_message_sequence", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("next_turn_sequence", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_agent_sessions_project_id", "agent_sessions", ["project_id"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("structured_content", _json_type(), nullable=True),
        sa.Column("tool_call_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"])

    op.create_table(
        "agent_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("turn_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("user_message_id", sa.String(36), nullable=False),
        sa.Column("assistant_message_id", sa.String(36), nullable=True),
        sa.Column("model_provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("request_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("decision_snapshot", _json_type(), nullable=True),
        sa.Column("warning_messages", _json_type(), nullable=True),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default=bool_false),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.UniqueConstraint("session_id", "turn_number", name="uq_agent_turns_session_turn"),
    )
    op.create_index("ix_agent_turns_session_id", "agent_turns", ["session_id"])

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("turn_id", sa.String(36), sa.ForeignKey("agent_turns.id"), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("authorization_level", sa.String(32), nullable=False, server_default="read"),
        sa.Column("arguments", _json_type(), nullable=False, server_default="{}"),
        sa.Column("arguments_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("result", _json_type(), nullable=True),
        sa.Column("result_reference", sa.String(200), nullable=True),
        sa.Column("warning_messages", _json_type(), nullable=True),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default=bool_false),
        sa.Column(
            "proposed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_agent_tool_calls_session_id", "agent_tool_calls", ["session_id"])
    op.create_index("ix_agent_tool_calls_turn_id", "agent_tool_calls", ["turn_id"])
    op.create_index("ix_agent_tool_calls_status", "agent_tool_calls", ["status"])

    op.create_table(
        "agent_confirmations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tool_call_id", sa.String(36), sa.ForeignKey("agent_tool_calls.id"), nullable=False
        ),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=False),
        sa.Column("arguments_sha256", sa.String(64), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_confirmations_tool_call_id", "agent_confirmations", ["tool_call_id"])
    op.create_index("ix_agent_confirmations_session_id", "agent_confirmations", ["session_id"])


    # Fix #4: Idempotency tracking table
    op.create_table(
        "agent_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id", sa.String(36),
            sa.ForeignKey("agent_sessions.id"), nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("result_ref", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id", "idempotency_key",
            name="uq_agent_idempotency_session_key",
        ),
    )
    op.create_index(
        "ix_agent_idempotency_session_id",
        "agent_idempotency", ["session_id"],
    )

def downgrade() -> None:
    op.drop_table("agent_idempotency")
    op.drop_table("agent_confirmations")
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_turns")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
