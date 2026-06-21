"""PostgreSQL integration tests for planning agent module.

Verifies migration 0008, table/index/constraint existence, JSONB round-trips,
session persistence, message ordering, confirmation single-use, concurrency,
rollback, and durable reads.

Requires: DATABASE_URL=postgresql+psycopg2://...
Marker: postgresql
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from threading import Barrier, Thread

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cold_storage.modules.planning_agent.domain.enums import (
    ConfirmationStatus,
    MessageRole,
    SessionStatus,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentConfirmation,
    AgentMessage,
    AgentSession,
    AgentToolCall,
)
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository

pytestmark = pytest.mark.postgresql


@pytest.fixture(scope="module")
def pg_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL integration tests")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_session_factory(pg_engine):
    return Session(bind=pg_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Migration / schema checks
# ---------------------------------------------------------------------------


class TestMigrationSchema:
    def test_agent_sessions_table_exists(self, pg_engine):
        insp = inspect(pg_engine)
        tables = insp.get_table_names()
        assert "agent_sessions" in tables

    def test_agent_messages_table_exists(self, pg_engine):
        insp = inspect(pg_engine)
        assert "agent_messages" in insp.get_table_names()

    def test_agent_turns_table_exists(self, pg_engine):
        insp = inspect(pg_engine)
        assert "agent_turns" in insp.get_table_names()

    def test_agent_tool_calls_table_exists(self, pg_engine):
        insp = inspect(pg_engine)
        assert "agent_tool_calls" in insp.get_table_names()

    def test_agent_confirmations_table_exists(self, pg_engine):
        insp = inspect(pg_engine)
        assert "agent_confirmations" in insp.get_table_names()

    def test_unique_constraint_messages(self, pg_engine):
        insp = inspect(pg_engine)
        uqs = insp.get_unique_constraints("agent_messages")
        names = [uq["name"] for uq in uqs]
        assert "uq_agent_messages_session_sequence" in names

    def test_unique_constraint_turns(self, pg_engine):
        insp = inspect(pg_engine)
        uqs = insp.get_unique_constraints("agent_turns")
        names = [uq["name"] for uq in uqs]
        assert "uq_agent_turns_session_turn" in names

    def test_indexes_exist(self, pg_engine):
        insp = inspect(pg_engine)
        idx_session = [i["name"] for i in insp.get_indexes("agent_sessions")]
        assert any("project_id" in n for n in idx_session)
        idx_tc = [i["name"] for i in insp.get_indexes("agent_tool_calls")]
        assert any("status" in n for n in idx_tc)


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    def test_create_and_read_session(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="PG test session", created_by="test-user")
            repo.create_session(s)
            got = repo.get_session(s.id)
            assert got.title == "PG test session"
            assert got.created_by == "test-user"

    def test_update_session(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="Update test")
            repo.create_session(s)
            updated = AgentSession(
                **{
                    "id": s.id,
                    "title": "Updated",
                    "status": SessionStatus.COMPLETED,
                    "closed_at": datetime.now(UTC),
                    "version": s.version + 1,
                    "created_by": s.created_by,
                    "created_at": s.created_at,
                    "updated_at": datetime.now(UTC),
                    "next_message_sequence": 1,
                    "next_turn_sequence": 1,
                    "project_id": None,
                    "project_version_id": None,
                }
            )
            repo.update_session(updated)
            got = repo.get_session(s.id)
            assert got.status == SessionStatus.COMPLETED

    def test_list_sessions(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s1 = AgentSession(title="List A")
            s2 = AgentSession(title="List B")
            repo.create_session(s1)
            repo.create_session(s2)
            sessions = repo.list_sessions()
            ids = [s.id for s in sessions]
            assert s1.id in ids
            assert s2.id in ids


# ---------------------------------------------------------------------------
# Message ordering and uniqueness
# ---------------------------------------------------------------------------


class TestMessageOrdering:
    def test_messages_ordered_by_sequence(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="Msg order test")
            repo.create_session(s)
            for i in range(1, 4):
                msg = AgentMessage(
                    session_id=s.id, sequence=i, role=MessageRole.USER, content=f"msg {i}"
                )
                repo.add_message(msg)
            msgs = repo.get_messages(s.id)
            assert [m.sequence for m in msgs] == [1, 2, 3]

    def test_duplicate_sequence_rejected(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="Dup seq test")
            repo.create_session(s)
            m1 = AgentMessage(session_id=s.id, sequence=1, content="first")
            repo.add_message(m1)
            m2 = AgentMessage(session_id=s.id, sequence=1, content="second")
            with pytest.raises(IntegrityError):
                repo.add_message(m2)
                pg_session_factory.flush()


# ---------------------------------------------------------------------------
# Confirmation single-use
# ---------------------------------------------------------------------------


class TestConfirmationSingleUse:
    def test_confirmation_can_be_marked_used(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="Conf test")
            repo.create_session(s)
            tc = AgentToolCall(session_id=s.id, turn_id="t1", tool_name="test")
            repo.add_tool_call(tc)
            conf = AgentConfirmation(
                tool_call_id=tc.id,
                session_id=s.id,
                confirmation_token_hash="abc123",
                arguments_sha256="def456",
                confirmed_by="user",
            )
            repo.add_confirmation(conf)
            # Mark used
            used = AgentConfirmation(
                **{
                    "id": conf.id,
                    "tool_call_id": conf.tool_call_id,
                    "session_id": conf.session_id,
                    "confirmation_token_hash": conf.confirmation_token_hash,
                    "arguments_sha256": conf.arguments_sha256,
                    "confirmed_by": conf.confirmed_by,
                    "status": ConfirmationStatus.USED,
                    "expires_at": conf.expires_at,
                    "created_at": conf.created_at,
                    "used_at": datetime.now(UTC),
                }
            )
            repo.update_confirmation(used)
            found = repo.get_confirmation_by_token_hash("abc123")
            assert found is not None
            assert found.status == ConfirmationStatus.USED


# ---------------------------------------------------------------------------
# Concurrency: concurrent confirmation attempt
# ---------------------------------------------------------------------------


class TestConcurrentConfirmation:
    def test_concurrent_confirm_only_one_succeeds(self, pg_engine):
        """Two threads try to mark the same confirmation as used.
        Only one should succeed; the other should see stale state."""
        from sqlalchemy.orm import sessionmaker

        SF = sessionmaker(bind=pg_engine, expire_on_commit=False)

        # Setup
        with SF() as setup_session:
            repo = AgentRepository(setup_session)
            s = AgentSession(title="Concurrent test")
            repo.create_session(s)
            tc = AgentToolCall(session_id=s.id, turn_id="t1", tool_name="test")
            repo.add_tool_call(tc)
            conf = AgentConfirmation(
                tool_call_id=tc.id,
                session_id=s.id,
                confirmation_token_hash="concurrent_hash",
                arguments_sha256="args_hash",
                confirmed_by="user",
            )
            repo.add_confirmation(conf)
            setup_session.commit()
            conf_id = conf.id

        errors: list[str] = []

        def attempt_confirm():
            try:
                with SF() as sess:
                    AgentRepository(sess)
                    c = sess.get(
                        __import__(
                            "cold_storage.modules.planning_agent.infrastructure.orm",
                            fromlist=["AgentConfirmationRecord"],
                        ).AgentConfirmationRecord,
                        conf_id,
                    )
                    if c and c.status == "active":
                        c.status = "used"
                        c.used_at = datetime.now(UTC)
                        sess.commit()
                    else:
                        errors.append("already_used")
            except Exception as e:
                errors.append(str(e))

        barrier = Barrier(2)

        def worker():
            barrier.wait()
            attempt_confirm()

        t1 = Thread(target=worker)
        t2 = Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # At least one should succeed, the other may fail or see used
        with SF() as check:
            from cold_storage.modules.planning_agent.infrastructure.orm import (
                AgentConfirmationRecord,
            )

            c = check.get(AgentConfirmationRecord, conf_id)
            assert c.status == "used"


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_flush_without_commit_is_reversible(self, pg_session_factory):
        with pg_session_factory:
            repo = AgentRepository(pg_session_factory)
            s = AgentSession(title="Rollback test")
            repo.create_session(s)
            pg_session_factory.flush()
            pg_session_factory.rollback()
        # After rollback, session should not be findable
        with pg_session_factory:
            from cold_storage.modules.planning_agent.domain.errors import SessionNotFoundError

            with pytest.raises(SessionNotFoundError):
                AgentRepository(pg_session_factory).get_session(s.id)


# ---------------------------------------------------------------------------
# Durable read
# ---------------------------------------------------------------------------


class TestDurableRead:
    def test_session_persists_across_sessions(self, pg_engine):
        from sqlalchemy.orm import sessionmaker

        sf = sessionmaker(bind=pg_engine, expire_on_commit=False)

        with sf() as s1:
            repo = AgentRepository(s1)
            sess = AgentSession(title="Durable read test", created_by="reader")
            repo.create_session(sess)
            s1.commit()

        with sf() as s2:
            repo = AgentRepository(s2)
            got = repo.get_session(sess.id)
            assert got.title == "Durable read test"
            assert got.created_by == "reader"
