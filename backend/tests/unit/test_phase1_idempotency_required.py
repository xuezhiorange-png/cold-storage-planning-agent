"""Phase 1 (P1-2) repository-level invariant for new writes.

The ``orchestration_run_attempts.idempotency_key`` column is
NULLABLE at the schema layer so legacy rows (pre-Phase-1) can
carry NULL without breaking the upgrade path. But for any
NEW write — application, repository, fixture, or migration —
a NULL ``idempotency_key`` is an invariant violation: it
defeats the unique index ``uq_attempt_idempotency_key_db`` and
silently corrupts the deduplication contract.

The repository helper ``_require_idempotency_key`` enforces
this invariant at the call site. These tests pin its
behaviour:

- NULL → raises ``ValueError`` (no silent insert).
- Empty string → raises ``ValueError``.
- Non-str type → raises ``TypeError``.
- Valid non-empty str → returned as-is (round-trip).
"""

from __future__ import annotations

import pytest

from cold_storage.modules.orchestration.infrastructure.repositories import (
    _require_idempotency_key,
)


class TestRequireIdempotencyKey:
    """The repository-level invariant for new attempt writes."""

    def test_none_raises_value_error(self) -> None:
        """NULL idempotency_key is a Phase 1 invariant violation."""
        with pytest.raises(ValueError) as exc:
            _require_idempotency_key(None)
        assert "idempotency_key is required" in str(exc.value)

    def test_empty_string_raises_value_error(self) -> None:
        """Empty string is also rejected — the schema-level
        ``uq_attempt_idempotency_key_db`` unique index only
        constrains the (database_backend, idempotency_key)
        tuple when key IS NOT NULL. An empty string would
        therefore also bypass deduplication. We reject it
        explicitly to keep the invariant strict."""
        with pytest.raises(ValueError) as exc:
            _require_idempotency_key("")
        assert "non-empty" in str(exc.value)

    def test_non_string_type_raises_type_error(self) -> None:
        """Non-str types (int, bool, dict, list) are rejected
        at the type boundary. ``bool`` is a special case (it's
        a subclass of int in Python) — still rejected."""
        for bad in [123, 1.5, True, False, ["x"], {"k": "v"}]:
            with pytest.raises(TypeError) as exc:
                _require_idempotency_key(bad)  # type: ignore[arg-type]
            assert "must be str" in str(exc.value)

    def test_valid_string_round_trips(self) -> None:
        """A non-empty str is returned unchanged — the helper
        does not normalize, mangle, or alter the value. The
        application layer owns canonicalization (see design
        contract §4.4)."""
        for good in [
            "idem-1",
            "idempotency-uuid-12345",
            "x",  # single-char is acceptable
            "  spaced  ",  # whitespace-padded is acceptable; CHECK on
            # correlation_id is strict, but idempotency_key
            # is the application contract, not a hard
            # identity contract.
        ]:
            assert _require_idempotency_key(good) == good
