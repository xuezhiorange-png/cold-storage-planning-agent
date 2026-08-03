"""Tests for JSON structured logging."""

from __future__ import annotations

import logging

from cold_storage.bootstrap.logging import (
    configure_logging,
    get_correlation_id,
    get_request_id,
    set_correlation_id,
    set_request_id,
)


class TestConfigureLogging:
    def test_configure_logging_idempotent(self) -> None:
        """Multiple calls should not duplicate handlers."""
        configure_logging()
        root = logging.getLogger()
        handler_count = len([h for h in root.handlers if hasattr(h, "stream")])
        configure_logging()
        handler_count_after = len([h for h in root.handlers if hasattr(h, "stream")])
        assert handler_count == handler_count_after

    def test_configure_logging_runs(self) -> None:
        """configure_logging should not raise."""
        configure_logging()


class TestCorrelationId:
    def test_set_get_correlation_id(self) -> None:
        set_correlation_id("test-id-123")
        assert get_correlation_id() == "test-id-123"

    def test_set_get_request_id(self) -> None:
        set_request_id("req-id-456")
        assert get_request_id() == "req-id-456"

    def test_default_correlation_id(self) -> None:
        set_correlation_id(None)
        cid = get_correlation_id()
        assert cid is None or isinstance(cid, str)

    def test_default_request_id(self) -> None:
        set_request_id(None)
        rid = get_request_id()
        assert rid is None or isinstance(rid, str)
