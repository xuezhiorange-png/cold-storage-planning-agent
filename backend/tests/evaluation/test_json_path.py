"""Tests for JSONPath grammar and canonical round-trips."""

from __future__ import annotations

import pytest

from cold_storage.evaluation.errors import JsonPathInvalidError
from cold_storage.evaluation.json_path import parse_json_path, render_json_path


class TestParseJsonPath:
    """P0-4: ASCII-only array index grammar and canonical round-trips."""

    # ── Accepted paths ──────────────────────────────────────────────

    @pytest.mark.parametrize(
        "path",
        [
            "$",
            "$.field",
            "$._field",
            "$.field_1",
            "$[0]",
            "$[1]",
            "$[10]",
            "$.items[0]",
            "$.matrix[0][1]",
            "$.items[10]",
        ],
    )
    def test_canonical_round_trip(self, path: str) -> None:
        """Every accepted path must round-trip via parse/render."""
        parsed = parse_json_path(path)
        assert parsed.raw == path
        assert render_json_path(parsed) == path

    # ── Rejected: Unicode digits ───────────────────────────────────

    @pytest.mark.parametrize(
        "path",
        [
            "$[\uff10]",  # FULLWIDTH DIGIT ZERO
            "$[\uff11]",  # FULLWIDTH DIGIT ONE
            "$[\uff12]",  # FULLWIDTH DIGIT TWO
            "$[\u0661]",  # ARABIC-INDIC DIGIT ONE
            "$[\u0967]",  # DEVANAGARI DIGIT ONE
        ],
    )
    def test_rejects_unicode_digits(self, path: str) -> None:
        """Unicode digits must be rejected as array indexes."""
        with pytest.raises(JsonPathInvalidError) as exc:
            parse_json_path(path)
        assert exc.value.code == "EVAL_JSON_PATH_INVALID"

    # ── Rejected: leading zeros and signs ───────────────────────────

    @pytest.mark.parametrize(
        "path",
        [
            "$[01]",
            "$[001]",
            "$[+1]",
            "$[-1]",
        ],
    )
    def test_rejects_leading_zero_and_signs(self, path: str) -> None:
        """Leading zeros and signs must be rejected as array indexes."""
        with pytest.raises(JsonPathInvalidError) as exc:
            parse_json_path(path)
        assert exc.value.code == "EVAL_JSON_PATH_INVALID"

    # ── Rejected: non-canonical forms ───────────────────────────────

    @pytest.mark.parametrize(
        "path",
        [
            "$[ 1]",
            "$[1 ]",
            "$.*",
            "$.-field",
            "$.1field",
            "$.field-name",
            "$.field name",
            "$..field",
            "$.",
        ],
    )
    def test_rejects_non_canonical_forms(self, path: str) -> None:
        """Various non-canonical JSONPath forms must be rejected."""
        with pytest.raises(JsonPathInvalidError):
            parse_json_path(path)

    # ── Rejected: non-string input ──────────────────────────────────

    @pytest.mark.parametrize("bad_input", [None, 123, True, [], {}])
    def test_rejects_non_string_input(self, bad_input: object) -> None:
        """Non-string inputs must be rejected."""
        with pytest.raises(JsonPathInvalidError) as exc:
            parse_json_path(bad_input)  # type: ignore[arg-type]
        assert exc.value.code == "EVAL_JSON_PATH_INVALID"
