"""Unit tests for Aily connector transport shared-secret auth."""

from __future__ import annotations

import pytest

from cold_storage.modules.aily.application.connector_auth import (
    CONNECTOR_KEY_HEADER,
    UNAUTHORIZED_CODE,
    connector_secret_configured,
    verify_connector_key,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError


def test_connector_secret_unset_or_blank_is_not_configured() -> None:
    assert connector_secret_configured(None) is False
    assert connector_secret_configured("") is False
    assert connector_secret_configured("   ") is False


def test_connector_secret_non_blank_is_configured() -> None:
    assert connector_secret_configured("connector-test-secret") is True


def test_verify_skips_when_secret_unset() -> None:
    verify_connector_key(None, None)
    verify_connector_key(None, "")
    verify_connector_key("any-value", None)


def test_verify_rejects_missing_header_when_secret_set() -> None:
    with pytest.raises(AilyConnectorError) as exc_info:
        verify_connector_key(None, "connector-test-secret")
    err = exc_info.value
    assert err.code == UNAUTHORIZED_CODE
    assert err.field_path == f"headers.{CONNECTOR_KEY_HEADER}"


def test_verify_rejects_wrong_header_when_secret_set() -> None:
    with pytest.raises(AilyConnectorError) as exc_info:
        verify_connector_key("wrong-key", "connector-test-secret")
    assert exc_info.value.code == UNAUTHORIZED_CODE


def test_verify_accepts_matching_header() -> None:
    verify_connector_key("connector-test-secret", "connector-test-secret")


def test_verify_strips_configured_secret_whitespace() -> None:
    verify_connector_key("connector-test-secret", "  connector-test-secret  ")


def test_verify_rejects_empty_header_with_whitespace_secret() -> None:
    with pytest.raises(AilyConnectorError) as exc_info:
        verify_connector_key("", "  connector-test-secret  ")
    assert exc_info.value.code == UNAUTHORIZED_CODE
