"""Unit tests for the threading helpers (Phase 2).

These tests cover:

* ``assert_identity_complete`` — fail-closed on empty fields
* ``assert_database_backend_supported`` — fail-closed on unknown
  dialects
* ``compute_content_hash`` — deterministic across key orderings
* ``canonical_json`` — stable serialisation
"""

from __future__ import annotations

import pytest

from cold_storage.modules.orchestration.application.production_calculation.errors import (
    InvalidProjectInputError,
)
from cold_storage.modules.orchestration.application.production_calculation.threading import (
    REQUIRED_IDENTITY_FIELDS,
    assert_database_backend_supported,
    assert_identity_complete,
    canonical_json,
    compute_content_hash,
)


class TestAssertIdentityComplete:
    def test_all_complete(self) -> None:
        # Should not raise.
        assert_identity_complete(
            actor="actor-1",
            correlation_id="corr-1",
            database_backend="sqlite",
        )

    @pytest.mark.parametrize("empty_actor", ["", None])
    def test_empty_actor_raises(self, empty_actor: str | None) -> None:
        with pytest.raises(InvalidProjectInputError) as exc:
            assert_identity_complete(
                actor=empty_actor or "",
                correlation_id="corr",
                database_backend="sqlite",
            )
        assert exc.value.field == "actor"

    @pytest.mark.parametrize("empty_corr", ["", None])
    def test_empty_correlation_id_raises(self, empty_corr: str | None) -> None:
        with pytest.raises(InvalidProjectInputError) as exc:
            assert_identity_complete(
                actor="actor",
                correlation_id=empty_corr or "",
                database_backend="sqlite",
            )
        assert exc.value.field == "correlation_id"

    @pytest.mark.parametrize("empty_db", ["", None])
    def test_empty_database_backend_raises(self, empty_db: str | None) -> None:
        with pytest.raises(InvalidProjectInputError) as exc:
            assert_identity_complete(
                actor="actor",
                correlation_id="corr",
                database_backend=empty_db or "",
            )
        assert exc.value.field == "database_backend"

    def test_required_fields_constant(self) -> None:
        # The three fields are part of the frozen contract.
        assert REQUIRED_IDENTITY_FIELDS == (
            "actor",
            "correlation_id",
            "database_backend",
        )


class TestAssertDatabaseBackendSupported:
    @pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
    def test_supported_backends_pass(self, backend: str) -> None:
        # Should not raise.
        assert_database_backend_supported(backend)

    @pytest.mark.parametrize(
        "backend",
        ["mysql", "oracle", "mssql", "duckdb", "SQLITE", ""],
    )
    def test_unsupported_backends_fail_closed(self, backend: str) -> None:
        with pytest.raises(InvalidProjectInputError) as exc:
            assert_database_backend_supported(backend)
        assert exc.value.field == "database_backend"


class TestContentHash:
    def test_hash_is_64_hex(self) -> None:
        h = compute_content_hash({"a": 1, "b": 2})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_key_order_does_not_change_hash(self) -> None:
        h1 = compute_content_hash({"a": 1, "b": 2, "c": 3})
        h2 = compute_content_hash({"c": 3, "b": 2, "a": 1})
        assert h1 == h2

    def test_nested_key_order_does_not_change_hash(self) -> None:
        h1 = compute_content_hash({"outer": {"a": 1, "b": 2}})
        h2 = compute_content_hash({"outer": {"b": 2, "a": 1}})
        assert h1 == h2

    def test_different_payloads_yield_different_hashes(self) -> None:
        h1 = compute_content_hash({"a": 1})
        h2 = compute_content_hash({"a": 2})
        assert h1 != h2

    def test_empty_payload_hash_is_stable(self) -> None:
        # Two empty dicts hash identically.
        assert compute_content_hash({}) == compute_content_hash({})


class TestCanonicalJson:
    def test_sorted_keys(self) -> None:
        s1 = canonical_json({"b": 2, "a": 1})
        assert s1 == '{"a":1,"b":2}'

    def test_rejects_non_serialisable(self) -> None:
        with pytest.raises(TypeError):
            canonical_json({"a": object()})

    def test_supports_datetime_like(self) -> None:
        class _DateTime:
            def isoformat(self) -> str:
                return "2026-07-05T00:00:00"

        s = canonical_json({"when": _DateTime()})
        assert "2026-07-05T00:00:00" in s
