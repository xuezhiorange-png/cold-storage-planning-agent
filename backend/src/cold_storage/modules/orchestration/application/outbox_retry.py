"""Deterministic retry policy for outbox event delivery failures.

The policy is injectable and fully deterministic (no real sleep),
enabling predictable test behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class RetryPolicy(Protocol):
    """Protocol for backoff calculation."""

    def next_retry_at(
        self,
        *,
        attempt_count: int,
        now: datetime,
    ) -> datetime:
        """Compute the next retry timestamp based on attempt count."""
        ...


class ExponentialBackoffPolicy:
    """Exponential backoff with configurable base delay and cap.

    Default: base=30s, cap=3600s (1 hour).
    Formula: min(base * 2^(attempt_count-1), cap)
    """

    def __init__(
        self,
        *,
        base_seconds: float = 30.0,
        cap_seconds: float = 3600.0,
    ) -> None:
        self._base = timedelta(seconds=base_seconds)
        self._cap = timedelta(seconds=cap_seconds)

    def next_retry_at(
        self,
        *,
        attempt_count: int,
        now: datetime,
    ) -> datetime:
        delay = self._base * (2 ** max(0, attempt_count - 1))
        if delay > self._cap:
            delay = self._cap
        result: datetime = now.astimezone(UTC) + delay
        return result


# Module-level default for convenience
DEFAULT_RETRY_POLICY = ExponentialBackoffPolicy()
