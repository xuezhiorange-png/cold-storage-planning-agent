"""Tests for canonical JSON serialization and snapshot hashing."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from cold_storage.modules.schemes.application.service import _canonical_json


class TestCanonicalJsonDictKeyOrder:
    """Verify dict key order is invariant in canonical output."""

    def test_dict_key_order_invariant(self) -> None:
        """{"b": 1, "a": 2} and {"a": 2, "b": 1} produce identical canonical JSON."""
        d1 = {"b": 1, "a": 2}
        d2 = {"a": 2, "b": 1}
        assert _canonical_json(d1) == _canonical_json(d2)

    def test_nested_dict_key_order_invariant(self) -> None:
        """Nested dicts with different insertion orders produce identical canonical JSON."""
        d1 = {"z": {"b": 1, "a": 2}, "a": 1}
        d2 = {"a": 1, "z": {"a": 2, "b": 1}}
        assert _canonical_json(d1) == _canonical_json(d2)


class TestCanonicalJsonDataChanges:
    """Verify data changes are reflected in canonical output."""

    def test_data_change_changes_hash(self) -> None:
        """Different data produces different canonical JSON."""
        h1 = _canonical_json({"a": 1})
        h2 = _canonical_json({"a": 2})
        assert h1 != h2

    def test_list_order_preserved(self) -> None:
        """Same list order produces same output; different order differs."""
        j1 = _canonical_json([1, 2, 3])
        j2 = _canonical_json([1, 2, 3])
        j3 = _canonical_json([3, 2, 1])
        assert j1 == j2
        assert j1 != j3


class TestCanonicalJsonTypes:
    """Verify special type serialization in canonical JSON."""

    def test_decimal_serialization(self) -> None:
        """Decimal('3.14') serializes as '3.14'."""
        result = _canonical_json({"val": Decimal("3.14")})
        assert "3.14" in result

    def test_uuid_serialization(self) -> None:
        """UUID objects serialize as their string form."""
        uid = uuid4()
        result = _canonical_json({"id": uid})
        assert str(uid) in result

    def test_datetime_serialization(self) -> None:
        """datetime objects serialize as ISO format."""
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = _canonical_json({"ts": dt})
        assert "2025-01-15T10:30:00" in result


class TestCanonicalJsonFormatting:
    """Verify canonical JSON formatting rules."""

    def test_no_whitespace(self) -> None:
        """Output has no spaces after separators."""
        result = _canonical_json({"a": 1, "b": [2, 3], "c": {"d": 4}})
        # Canonical JSON uses compact separators — no spaces after commas or colons
        assert ", " not in result
        assert ": " not in result


class TestCanonicalJsonHash:
    """Verify deterministic hashing of canonical JSON."""

    def test_same_data_different_input_order_same_hash(self) -> None:
        """Canonical JSON of two dicts with same data but different order produces same hash."""
        d1 = {"b": 1, "a": 2}
        d2 = {"a": 2, "b": 1}
        c1 = _canonical_json(d1)
        c2 = _canonical_json(d2)
        h1 = hashlib.sha256(c1.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(c2.encode("utf-8")).hexdigest()
        assert h1 == h2
