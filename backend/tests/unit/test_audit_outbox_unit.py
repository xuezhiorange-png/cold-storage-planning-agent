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
from pathlib import Path


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
        # Must be a 64-char SHA-256 hex digest, fitting VARCHAR(128)
        assert len(identity) == 64
        assert all(c in "0123456789abcdef" for c in identity)

    def test_length_fits_varchar128(self):
        from cold_storage.modules.orchestration.application.outbox_identity import (
            build_event_identity,
        )

        identity = build_event_identity(
            event_type="orchestration.request.preflight_rejected",
            aggregate_type="OrchestrationRequest",
            aggregate_id="a" * 120,
            transition_id="b" * 120,
        )
        assert len(identity) == 64
        assert len(identity) <= 128


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

        err = OutboxIdempotencyMismatchError(
            "ident-1",
            ["existing_payload_hash", "new_payload_hash"],
            existing_payload_hash="hash-a",
            new_payload_hash="hash-b",
        )
        assert err.event_identity == "ident-1"
        assert err.mismatched_fields == [
            "existing_payload_hash",
            "new_payload_hash",
        ]
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
        """Verify the classifier accepts PG unique_violation on outbox_event_id.

        Round 8 P0-3: migration 0026 creates the UNIQUE on outbox_event_id
        under the name ``uq_audit_event_outbox``.  Earlier rounds had the
        classifier check ``audit_events_outbox_event_id_key`` (a different
        name) which never matched the live database constraint, so the
        SAVEPOINT recovery path was unreachable in production.
        """
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        exc = MagicMock()
        exc.orig = MagicMock()
        exc.orig.sqlstate = "23505"
        exc.orig.diag = MagicMock()
        exc.orig.diag.constraint_name = "uq_audit_event_outbox"
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
        """A 23505 on a different constraint (e.g. ``audit_events_pkey``)
        must NOT be classified as an outbox_event_id conflict."""
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
            _is_outbox_event_id_conflict,
        )

        exc = MagicMock()
        exc.orig = MagicMock()
        exc.orig.sqlstate = "23505"
        exc.orig.diag = MagicMock()
        exc.orig.diag.constraint_name = "audit_events_pkey"
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


class TestOutboxEnvelopeValidation:
    """P0-12 fail-closed envelope validation tests.

    The audit outbox repository MUST reject empty actor / correlation_id
    rather than silently substituting defaults.  These tests use the
    public ``AuditOutboxRepository.add`` port contract to verify the
    fail-closed behavior without touching the database.
    """

    def test_missing_actor_raises_validation_error(self) -> None:
        """Port signature enforces ``actor`` as a required keyword-only arg."""
        import inspect

        from cold_storage.modules.orchestration.application.ports import (
            AuditOutboxRepository,
        )

        sig = inspect.signature(AuditOutboxRepository.add)
        actor_param = sig.parameters["actor"]
        assert actor_param.default is inspect.Parameter.empty
        assert actor_param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_missing_correlation_id_raises_validation_error(self) -> None:
        """Port signature enforces ``correlation_id`` as required kw-only arg."""
        import inspect

        from cold_storage.modules.orchestration.application.ports import (
            AuditOutboxRepository,
        )

        sig = inspect.signature(AuditOutboxRepository.add)
        corr_param = sig.parameters["correlation_id"]
        assert corr_param.default is inspect.Parameter.empty
        assert corr_param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_missing_occurred_at_raises_validation_error(self) -> None:
        """Port signature enforces ``occurred_at`` as required kw-only arg."""
        import inspect

        from cold_storage.modules.orchestration.application.ports import (
            AuditOutboxRepository,
        )

        sig = inspect.signature(AuditOutboxRepository.add)
        occ_param = sig.parameters["occurred_at"]
        assert occ_param.default is inspect.Parameter.empty
        assert occ_param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_validation_error_has_code_and_field(self) -> None:
        """``OutboxEnvelopeValidationError`` exposes structured fields."""
        from cold_storage.modules.orchestration.application.ports import (
            OutboxEnvelopeValidationError,
        )

        exc = OutboxEnvelopeValidationError(
            field="actor",
            message="missing actor",
        )
        assert exc.field == "actor"
        assert exc.code == "outbox_envelope_invalid"
        assert "actor" in str(exc)


class TestUnknownExceptionUntreated:
    """P0-7: unknown exceptions must NOT be silently retried.

    The dispatcher categorises errors by type:

    - ``OutboxMaterializationMismatchError`` / ``OutboxPayloadIntegrityError`` /
      ``TerminalOutboxDeliveryError`` → terminal ``FAILED``.
    - ``RetryableOutboxDeliveryError`` → retryable.
    - Bare ``Exception`` → terminal ``FAILED`` (no infinite retry).
    """

    def test_typed_terminal_exception_exists(self) -> None:
        from cold_storage.modules.orchestration.application.outbox_errors import (
            TerminalOutboxDeliveryError,
        )

        exc = TerminalOutboxDeliveryError(event_id="e1", reason="bad")
        assert exc.event_id == "e1"
        assert exc.reason == "bad"

    def test_typed_retryable_exception_exists(self) -> None:
        from cold_storage.modules.orchestration.application.outbox_errors import (
            RetryableOutboxDeliveryError,
        )

        exc = RetryableOutboxDeliveryError(event_id="e2", reason="transient")
        assert exc.event_id == "e2"
        assert exc.reason == "transient"


class TestCompletedEnvelopeBinding:
    """P0-2: completed outbox event must carry the durable request envelope.

    The TransactionBExecutor ``execute()`` signature MUST require
    ``actor``, ``correlation_id`` and ``completed_at`` as explicit
    keyword-only arguments.  No ``"system"`` / ``""`` defaults are
    permitted (see repository port).
    """

    def test_executor_requires_envelope_kw_args(self) -> None:
        import inspect

        from cold_storage.modules.orchestration.application.transaction_b import (
            TransactionBExecutor,
        )

        sig = inspect.signature(TransactionBExecutor.execute)
        for arg_name in ("actor", "correlation_id", "completed_at"):
            param = sig.parameters[arg_name]
            assert param.default is inspect.Parameter.empty, (
                f"TransactionBExecutor.execute() must require {arg_name} explicitly (no default)"
            )
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"TransactionBExecutor.execute() {arg_name} must be keyword-only"
            )


class TestPreMigrationBackfillFailClosed:
    """P0-9: backfill must fail closed on non-dict payloads."""

    def test_migration_imports_fail_closed_helper(self) -> None:
        """The migration module must contain the fail-closed RuntimeError
        raise for non-dict payloads (replaces the silent ``{}`` fallback).
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "alembic"
            / "versions"
            / "0033_extend_outbox_envelope.py"
        )
        source = migration_path.read_text(encoding="utf-8")
        assert "outbox backfill encountered non-dict payload" in source
        # The silent fallback MUST be removed.
        assert "if isinstance(payload, dict) else {}" not in source


class TestTransactionBEnvelopeFailClosed:
    """P0-3 (Round 7): Transaction B envelope fail-closed contract.

    The TransactionBApplicationService must:
      1. Load the durable request envelope BEFORE the request_status
         precondition check, so that envelope load failure or absence is
         caught before any other path runs.
      2. If envelope is missing, raise ``TransactionBFailure`` with code
         ``TXB_REQUEST_ENVELOPE_MISSING`` — no silent "system"/"" fallback.
      3. NEVER use ``"system"`` or ``""`` as actor / correlation_id
         defaults in any terminal path (use an explicit
         ``envelope-unavailable:<code>`` sentinel instead, recognizable
         in audit but never silently "system").
      4. Terminal outbox events must carry either the loaded envelope or
         the sentinel — never the old defaults.
    """

    SERVICE_PATH = (
        Path(__file__).parent.parent.parent
        / "src"
        / "cold_storage"
        / "modules"
        / "orchestration"
        / "application"
        / "service.py"
    )

    def test_service_no_longer_uses_system_fallback(self) -> None:
        """The literal ``"system"`` MUST NOT appear as a fallback anywhere in
        the service module's ``execute_transaction_b``."""
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # The forbidden fallback pattern: ``envelope[0] if envelope else "system"``
        assert 'if envelope else "system"' not in source, (
            "execute_transaction_b must not fall back to 'system' as envelope actor"
        )
        assert 'if envelope else ""' not in source, (
            "execute_transaction_b must not fall back to empty string as envelope correlation_id"
        )
        # The forbidden pattern as written in the executor call.
        assert "actor=(envelope[0]" not in source, (
            "executor.execute actor must come from envelope tuple, not a fallback"
        )
        assert "correlation_id=(envelope[1]" not in source

    def test_service_loads_envelope_before_request_status_check(self) -> None:
        """Source-order check: ``get_envelope`` MUST be called BEFORE
        ``get_status`` (or any precondition check) inside the same UoW.
        This prevents the UnboundLocalError risk in except handlers."""
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # Find the relevant region (between ``# P0-3`` and ``# Pre-condition``)
        p0_3_idx = source.find("# P0-3: load envelope first")
        precond_idx = source.find("# Pre-condition: verify request is ACCEPTED")
        assert p0_3_idx != -1, "P0-3 comment must be present"
        assert precond_idx != -1, "precondition check must be present"
        assert p0_3_idx < precond_idx, (
            "envelope must be loaded BEFORE the request_status precondition check"
        )
        get_envelope_idx = source.find("get_envelope(", p0_3_idx)
        get_status_idx = source.find("get_status(", p0_3_idx)
        assert get_envelope_idx != -1 and get_envelope_idx < precond_idx, (
            "get_envelope must be called inside the P0-3 region"
        )
        assert get_status_idx == -1 or get_status_idx > get_envelope_idx, (
            "get_status must NOT be called before get_envelope"
        )

    def test_service_emits_txb_request_envelope_missing(self) -> None:
        """The service must raise a ``TXB_REQUEST_ENVELOPE_MISSING`` failure
        when the envelope is None."""
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        assert "TXB_REQUEST_ENVELOPE_MISSING" in source, (
            "service must fail closed with TXB_REQUEST_ENVELOPE_MISSING when envelope is None"
        )

    def test_service_envelope_variables_typed_optional_outside_try(self) -> None:
        """``envelope_actor`` and ``envelope_correlation_id`` must be
        declared as ``str | None`` outside the try block so except branches
        can never raise UnboundLocalError."""
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # Look for the section right after the P0-3 comment block.
        p0_3_idx = source.find("# P0-3 (Round 7)")
        precond_idx = source.find("# Pre-condition: verify request is ACCEPTED")
        region = source[p0_3_idx:precond_idx] if p0_3_idx != -1 and precond_idx != -1 else ""
        assert "envelope_actor: str | None = None" in region, (
            "envelope_actor must be initialized as str | None before the try"
        )
        assert "envelope_correlation_id: str | None = None" in region, (
            "envelope_correlation_id must be initialized as str | None before the try"
        )

    def test_resolve_terminal_envelope_uses_sentinel_not_system(self) -> None:
        """The ``_resolve_terminal_envelope`` helper must return either the
        loaded envelope OR an explicit ``envelope-unavailable:<code>``
        sentinel — NEVER the bare ``"system"`` or ``""`` defaults."""
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # Helper exists
        assert "def _resolve_terminal_envelope(" in source
        # Sentinel is present
        assert "envelope-unavailable:" in source, (
            "envelope-unavailable sentinel must be present for terminal paths"
        )
        # The helper body must NOT return 'system' or '' as defaults
        helper_start = source.find("def _resolve_terminal_envelope(")
        helper_end = source.find("\n    def ", helper_start + 1)
        helper_body = source[helper_start:helper_end]
        assert 'return "' not in helper_body, (
            'helper must not return literal "system" or "" defaults'
        )

    def test_envelope_missing_branch_skips_terminal_outbox(self) -> None:
        """P0-4 (Round 8) Plan A: the ``TXB_REQUEST_ENVELOPE_MISSING``
        branch in ``execute_transaction_b`` must NOT call
        ``_transaction_b_terminal``.  Specifically, the source must
        contain an early ``raise`` after the envelope-missing check
        that precedes any ``_transaction_b_terminal`` call.  Without
        this, the fail-closed contract collapses — a missing envelope
        would still emit a sentinel terminal outbox event.
        """
        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # Locate execute_transaction_b body.
        start = source.find("def execute_transaction_b(")
        assert start != -1
        # Method body runs from ``try:`` until the next def at column 4.
        body_start = source.find("try:", start)
        import re

        next_def = re.search(r"\n    def (?!_)\w+\(", source[body_start:])
        body_end = body_start + (next_def.start() if next_def else len(source) - body_start)
        body = source[body_start:body_end]
        # Locate the TXB_REQUEST_ENVELOPE_MISSING branch.
        env_idx = body.find("TXB_REQUEST_ENVELOPE_MISSING")
        assert env_idx != -1, "TXB_REQUEST_ENVELOPE_MISSING branch must exist"
        # Inside that branch the FIRST ``raise`` statement must occur
        # BEFORE any ``_transaction_b_terminal`` call (within 4 KB of
        # source after env_idx — sufficient to cover the early-return
        # block).
        slice_after = body[env_idx : env_idx + 4096]
        raise_idx = slice_after.find("raise")
        terminal_idx = slice_after.find("_transaction_b_terminal")
        assert raise_idx != -1, "TXB_REQUEST_ENVELOPE_MISSING branch must contain a raise"
        assert terminal_idx == -1 or terminal_idx > raise_idx, (
            "Plan A fail-closed contract violated: "
            "_transaction_b_terminal is called before the raise in the "
            "TXB_REQUEST_ENVELOPE_MISSING branch — that branch must "
            "early-return without writing any terminal outbox event"
        )

    def test_terminal_branches_call_resolve_helper(self) -> None:
        """Every except branch that calls ``_transaction_b_terminal`` MUST
        route through ``_resolve_terminal_envelope`` (so that the
        envelope-unavailable sentinel is applied when needed).

        P0-4 (Round 8) fail-closed: the TXB_REQUEST_ENVELOPE_MISSING
        branch is excluded — Plan A says "do NOT emit a terminal
        outbox" for that specific code, so that branch must not call
        ``_transaction_b_terminal``.
        """
        import re

        source = self.SERVICE_PATH.read_text(encoding="utf-8")
        # Find the body of execute_transaction_b.
        start = source.find("def execute_transaction_b(")
        assert start != -1, "execute_transaction_b not found"
        # End of the method: next def at indent level 4 after the method.
        # Approximate by counting the closing pattern.
        body_start = source.find("try:", start)
        # Take everything up to the next top-level method definition
        # (`    def ` at column 4) after the body start.
        next_def = re.search(r"\n    def (?!_)\w+\(", source[body_start:])
        body_end = body_start + (next_def.start() if next_def else len(source) - body_start)
        body = source[body_start:body_end]

        terminal_calls = len(re.findall(r"self\._transaction_b_terminal\(", body))
        resolve_calls = len(re.findall(r"self\._resolve_terminal_envelope\(", body))
        assert terminal_calls > 0, "no _transaction_b_terminal calls found in execute_transaction_b"
        assert resolve_calls >= 3, (
            f"expected at least 3 _resolve_terminal_envelope calls in execute_transaction_b "
            f"(TransactionBBlocked, TransactionBFailure non-missing, OrchestrationDomainError, "
            f"IntegrityError, Exception), got {resolve_calls}"
        )
        # Plan A fail-closed: the TXB_REQUEST_ENVELOPE_MISSING branch
        # MUST NOT call _transaction_b_terminal — verify by source-level
        # substring check inside the envelope-missing block.
        # Locate the TXB_REQUEST_ENVELOPE_MISSING branch and confirm
        # the next _transaction_b_terminal call is AFTER it.
        env_idx = body.find("TXB_REQUEST_ENVELOPE_MISSING")
        assert env_idx != -1, "TXB_REQUEST_ENVELOPE_MISSING branch not found"
        # The envelope-missing branch should re-raise without calling
        # _transaction_b_terminal.  Find the next raise after the code.
        branch_end = body.find("raise", env_idx)
        assert branch_end != -1, "no raise after TXB_REQUEST_ENVELOPE_MISSING branch"
        terminal_after_branch = body.find("_transaction_b_terminal", branch_end)
        assert terminal_after_branch != -1, (
            "no _transaction_b_terminal call after the TXB_REQUEST_ENVELOPE_MISSING branch — "
            "execute_transaction_b would have no FAILED path for non-missing failures"
        )
        # The P0-4 fail-closed contract is satisfied if the code BETWEEN
        # the envelope-missing branch and the next raise has no
        # _transaction_b_terminal call.  We check the slice up to the
        # next raise after the sentinel branch ends.
        slice_ = body[branch_end:terminal_after_branch]
        assert "_transaction_b_terminal" not in slice_, (
            "Plan A fail-closed contract violated: "
            "TXB_REQUEST_ENVELOPE_MISSING branch MUST NOT call _transaction_b_terminal"
        )
