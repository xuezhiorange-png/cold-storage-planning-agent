"""Tests for JSON structured logging."""

from __future__ import annotations

import io
import json
import logging

from cold_storage.bootstrap.logging import (
    _JSONFormatter,
    configure_logging,
    get_capability_tags,
    get_correlation_id,
    get_request_id,
    set_capability_tags,
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

    def test_json_formatter_emits_canonical_application_fields(self) -> None:
        correlation_id = "11111111-1111-4111-8111-111111111111"
        set_correlation_id(correlation_id)
        set_request_id(correlation_id)
        set_capability_tags(["strict_runtime"])
        record = logging.LogRecord(
            name="cold_storage.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="runtime ready",
            args=(),
            exc_info=None,
        )
        payload = json.loads(_JSONFormatter().format(record))
        assert payload["timestamp"]
        assert payload["level"] == "INFO"
        assert payload["name"] == "cold_storage.test"
        assert payload["correlation_id"] == correlation_id
        assert payload["request_id"] == correlation_id
        assert payload["capability_tags"] == ["strict_runtime"]
        assert payload["message"] == "runtime ready"
        set_capability_tags([])

    def test_configure_logging_emits_application_record_through_root_handler(self) -> None:
        configure_logging()
        root = logging.getLogger()
        handlers = [
            handler
            for handler in root.handlers
            if isinstance(handler, logging.StreamHandler)
            and getattr(handler, "cold_storage_bootstrap_logging_configured", False)
        ]
        assert len(handlers) == 1

        handler = handlers[0]
        stream = io.StringIO()
        original_stream = handler.stream
        logger = logging.getLogger("cold_storage.r8_test")
        original_level = logger.level
        original_propagate = logger.propagate
        original_correlation_id = get_correlation_id()
        original_request_id = get_request_id()
        original_capability_tags = get_capability_tags()
        correlation_id = "22222222-2222-4222-8222-222222222222"
        try:
            handler.setStream(stream)
            logger.setLevel(logging.INFO)
            logger.propagate = True
            set_correlation_id(correlation_id)
            set_request_id(correlation_id)
            set_capability_tags(["strict_runtime"])
            logger.info("runtime ready")
            handler.flush()
            payload = json.loads(stream.getvalue().strip())
        finally:
            handler.setStream(original_stream)
            logger.setLevel(original_level)
            logger.propagate = original_propagate
            set_correlation_id(original_correlation_id)
            set_request_id(original_request_id)
            set_capability_tags(original_capability_tags)

        assert payload["timestamp"]
        assert payload["level"] == "INFO"
        assert payload["name"] == "cold_storage.r8_test"
        assert payload["correlation_id"] == correlation_id
        assert payload["request_id"] == correlation_id
        assert payload["capability_tags"] == ["strict_runtime"]
        assert payload["message"] == "runtime ready"


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
