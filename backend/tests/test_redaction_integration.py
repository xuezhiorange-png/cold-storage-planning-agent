"""Tests for redaction integration."""

from __future__ import annotations

from cold_storage.bootstrap.configuration_redactor import (
    EMIT_POINT_ENUM,
    SECRET_TYPE_ENUM,
    redact_exception_for_logging,
    redact_for_logging,
)


class TestRedactForLogging:
    def test_database_url(self) -> None:
        result = redact_for_logging("postgresql://user:pass@host/db")
        assert "pass" not in result or "***" in result

    def test_redis_url(self) -> None:
        result = redact_for_logging("redis://:secret@localhost:6379")
        assert "secret" not in result or "***" in result

    def test_password(self) -> None:
        result = redact_for_logging("password=mysecret123")
        assert "mysecret123" not in result

    def test_token(self) -> None:
        result = redact_for_logging("token=abc123xyz")
        assert "abc123xyz" not in result

    def test_api_key(self) -> None:
        result = redact_for_logging("api_key=sk-live-12345")
        assert "sk-live-12345" not in result

    def test_cookie(self) -> None:
        result = redact_for_logging("Cookie: session=abc123")
        assert "abc123" not in result or "REDACTED" in result

    def test_authorization_header(self) -> None:
        result = redact_for_logging("Authorization: Bearer token123")
        assert "token123" not in result or "REDACTED" in result

    def test_signed_url(self) -> None:
        result = redact_for_logging("https://example.com/file?signature=abc123")
        assert "abc123" not in result or "REDACTED" in result

    def test_clean_text_unchanged(self) -> None:
        result = redact_for_logging("normal log message without secrets")
        # Clean text should pass through (may have minor formatting changes)
        assert "normal" in result


class TestSecretTypeEnum:
    def test_all_11_types(self) -> None:
        assert len(SECRET_TYPE_ENUM) == 11


class TestEmitPointEnum:
    def test_all_5_points(self) -> None:
        assert len(EMIT_POINT_ENUM) == 5


class TestRedactExceptionForLogging:
    def test_exception_redaction(self) -> None:
        exc = ValueError("connection failed: postgresql://user:pass@host")
        result = redact_exception_for_logging(exc)
        assert "pass" not in result or "***" in result
