"""Configuration redaction contract tests."""

from __future__ import annotations

from cold_storage.bootstrap.configuration_redactor import redact, redact_text


def test_recursive_mapping_redaction() -> None:
    value = {"password": "secret", "nested": ["postgresql+psycopg2://u:p@db/x", {"token": "abc"}]}
    result = redact(value)
    assert result["password"] == "***"
    assert "p@db" not in str(result)
    assert result["nested"][1]["token"] == "***"


def test_dsn_and_assignment_redaction() -> None:
    assert "secret" not in redact_text("postgresql+psycopg2://user:secret@host/db")
    assert "abc" not in redact_text("token=abc")
