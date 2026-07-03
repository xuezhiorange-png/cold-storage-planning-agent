"""Unit tests for the audit outbox subsystem.

Covers:
- Canonical event envelope
- Deterministic event identity
- Payload hash
- Retry policy
- Typed error mapping
- Exact unique-conflict classifier
- CLI summary format
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class TestCanonicalJson:
    def test_sort_keys(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            canonical_json,
        )

        result = canonical_json({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_compact_separators(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            canonical_json,
        )

        result = canonical_json({"x": "hello"})
        assert ": " not in result
        assert ", " not in result

    def test_nested_sort(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            canonical_json,
        )

        result = canonical_json({"z": {"b": 2, "a": 1}})
        assert '"a":1' in result
        assert '"b":2' in result


class TestEventIdentity:
    def test_deterministic(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            build_event_identity,
        )

        id1 = build_event_identity(
            event_type="orchestration.request.accepted",
            aggregate_type="OrchestrationRequest",
            aggregate_id="req-123",
            transition_id="trans-456",
        )
        id2 = build_event_identity(
            event_type="orchestration.request.accepted",
            aggregate_type="OrchestrationRequest",
            aggregate_id="req-123",
            transition_id="trans-456",
        )
        assert id1 == id2

    def test_different_transition_different_identity(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            build_event_identity,
        )

        id1 = build_event_identity(
            event_type="orchestration.request.accepted",
            aggregate_type="OrchestrationRequest",
            aggregate_id="req-123",
            transition_id="trans-A",
        )
        id2 = build_event_identity(
            event_type="orchestration.request.accepted",
            aggregate_type="OrchestrationRequest",
            aggregate_id="req-123",
            transition_id="trans-B",
        )
        assert id1 != id2

    def test_format(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            build_event_identity,
        )

        identity = build_event_identity(
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            transition_id="trans-1",
            schema_version="2.0",
        )
        assert identity == "2.0:test.event:TestAggregate:agg-1:trans-1"


class TestPayloadHash:
    def test_deterministic(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            compute_payload_hash,
        )

        payload = {"key": "value", "nested": {"a": 1}}
        h1 = compute_payload_hash(payload)
        h2 = compute_payload_hash(payload)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_different_payload_different_hash(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            compute_payload_hash,
        )

        h1 = compute_payload_hash({"a": 1})
        h2 = compute_payload_hash({"a": 2})
        assert h1 != h2

    def test_canonical_independence(self):
        """Same logical payload regardless of insertion order."""
        from cold_storage.modules.orchestration.application.outbox_identity import (
            compute_payload_hash,
        )

        h1 = compute_payload_hash({"b": 2, "a": 1})
        h2 = compute_payload_hash({"a": 1, "b": 2})
        assert h1 == h2


class TestRetryPolicy:
    def test_exponential_backoff(self):
        from cold_storage.modules.orchestration.application.outbox_retry import (
            ExponentialBackoffPolicy,
        )

        policy = ExponentialBackoffPolicy(base_seconds=10.0, cap_seconds=100.0)
        now = datetime(2026, 1, 1, tzinfo=UTC)

        r1 = policy.next_retry_at(attempt_count=1, now=now)
        assert r1 == now + timedelta(seconds=10)

        r2 = policy.next_retry_at(attempt_count=2, now=now)
        assert r2 == now + timedelta(seconds=20)

        r3 = policy.next_retry_at(attempt_count=3, now=now)
        assert r3 == now + timedelta(seconds=40)

    def test_cap(self):
        from cold_storage.modules.orchestration.application.outbox_retry import (
            ExponentialBackoffPolicy,
        )

        policy = ExponentialBackoffPolicy(base_seconds=10.0, cap_seconds=30.0)
        now = datetime(2026, 1, 1, tzinfo=UTC)

        r = policy.next_retry_at(attempt_count=10, now=now)
        assert r == now + timedelta(seconds=30)

    def test_deterministic(self):
        from cold_storage.modules.orchestration.application.outbox_retry import (
            ExponentialBackoffPolicy,
        )

        policy = ExponentialBackoffPolicy()
        now = datetime(2026, 1, 1, tzinfo=UTC)
        r1 = policy.next_retry_at(attempt_count=5, now=now)
        r2 = policy.next_retry_at(attempt_count=5, now=now)
        assert r1 == r2


class TestTypedErrors:
    def test_claim_lost(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxClaimLostError,
        )

        err = OutboxClaimLostError("evt-1", "worker-1", "token-1")
        assert err.event_id == "evt-1"
        assert err.worker_id == "worker-1"
        assert "worker-1" in str(err)

    def test_idempotency_mismatch(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxIdempotencyMismatchError,
        )

        err = OutboxIdempotencyMismatchError("ident-1", "hash-a", "hash-b")
        assert err.event_identity == "ident-1"
        assert err.existing_payload_hash == "hash-a"
        assert err.new_payload_hash == "hash-b"

    def test_materialization_mismatch(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxMaterializationMismatchError,
        )

        err = OutboxMaterializationMismatchError("ident-1", ["action", "actor"])
        assert err.mismatched_fields == ["action", "actor"]

    def test_payload_integrity(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxPayloadIntegrityError,
        )

        err = OutboxPayloadIntegrityError("evt-1", "expected", "actual")
        assert err.expected_hash == "expected"
        assert err.actual_hash == "actual"

    def test_retryable(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            RetryableOutboxDeliveryError,
        )

        err = RetryableOutboxDeliveryError("evt-1", "network timeout")
        assert err.reason == "network timeout"

    def test_terminal(self):
        from cold_storage.modules.orchestration.application.outbox_errors import (
            TerminalOutboxDeliveryError,
        )

        err = TerminalOutboxDeliveryError("evt-1", "schema invalid")
        assert err.reason == "schema invalid"


class TestConflictClassifier:
    def test_pg_23505_outbox_event_id(self):
        """Verify the classifier accepts PG unique_violation on outbox_event_id."""
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        exc = MagicMock()
        exc.orig = MagicMock()
        exc.orig.sqlstate = "23505"
        exc.orig.diag = MagicMock()
        exc.orig.diag.constraint_name = "uq_audit_events_outbox_event_id"
        assert _is_outbox_event_id_conflict(exc) is True

    def test_rejects_non_23505(self):
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        exc = MagicMock()
        exc.orig = MagicMock()
        exc.orig.sqlstate = "23503"  # FK violation
        assert _is_outbox_event_id_conflict(exc) is False

    def test_rejects_wrong_constraint(self):
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        exc = MagicMock()
        exc.orig = MagicMock()
        exc.orig.sqlstate = "23505"
        exc.orig.diag = MagicMock()
        exc.orig.diag.constraint_name = "some_other_constraint"
        assert _is_outbox_event_id_conflict(exc) is False

    def test_no_orig(self):
        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        assert _is_outbox_event_id_conflict(Exception("test")) is False


class TestAuditEventComparison:
    def test_identical_events_match(self):
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _compare_audit_events,
        )

        new = MagicMock()
        new.action = "test"
        new.entity_type = "TestEntity"
        new.entity_id = "id-1"
        new.actor = "actor-1"
        new.before_snapshot = {}
        new.after_snapshot = {"a": 1}
        new.event_metadata = {"key": "val"}

        existing = MagicMock()
        existing.action = "test"
        existing.entity_type = "TestEntity"
        existing.entity_id = "id-1"
        existing.actor = "actor-1"
        existing.before_snapshot = {}
        existing.after_snapshot = {"a": 1}
        existing.event_metadata = {"key": "val"}

        assert _compare_audit_events(new, existing) == []

    def test_different_action_mismatches(self):
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _compare_audit_events,
        )

        new = MagicMock()
        new.action = "new.action"
        new.entity_type = "T"
        new.entity_id = "id"
        new.actor = "a"
        new.before_snapshot = {}
        new.after_snapshot = {}
        new.event_metadata = {}

        existing = MagicMock()
        existing.action = "old.action"
        existing.entity_type = "T"
        existing.entity_id = "id"
        existing.actor = "a"
        existing.before_snapshot = {}
        existing.after_snapshot = {}
        existing.event_metadata = {}

        mismatches = _compare_audit_events(new, existing)
        assert "action" in mismatches
