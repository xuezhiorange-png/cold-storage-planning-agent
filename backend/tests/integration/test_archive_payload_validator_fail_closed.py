"""Round-9 P1-1 fail-closed tests for archive_payload schema validator.

The new ``validate_archive_payload_v1`` is the single application-side
enforcement point for the SchemeSourceArchiveV1 payload shape.  The
two guarantees are:

* exactly the 19 required keys (``REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1``);
* ``source_slots`` is the canonical ordered sequence in
  ``SOURCE_SLOT_ORDER_V1`` order.

Any deviation MUST raise ``SourceArchiveBuildError`` BEFORE the hash
recomputation runs.  These tests cover three structural failures plus
the success path; the resolver wire-up test exercises the integrity
flood on the read side.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.sqlite


def _full_payload(**overrides):
    """Build a canonical archive_payload with one field overridable."""
    from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
        assemble_archive_payload,
    )

    payload = assemble_archive_payload(
        source_slots=[
            ("zone", {"calculation_id": "zone-run-1", "result_hash": "rh-zone"}),
            ("cooling_load", {"calculation_id": "cool-run-1", "result_hash": "rh-cool"}),
            ("equipment", {"calculation_id": "equip-run-1", "result_hash": "rh-equip"}),
            ("power", {"calculation_id": "power-run-1", "result_hash": "rh-power"}),
            ("investment", {"calculation_id": "inv-run-1", "result_hash": "rh-inv"}),
        ],
        scheme_run_id="sr-001",
        source_binding_id="b-001",
        source_contract_version="SVC-1.0",
        binding_schema_version="BSV-1.0",
        combined_source_hash="combined-h",
        weight_set_revision_id="rev-001",
        weight_set_content_hash="weight-h",
        weight_set_generator_compatibility_version="WG-1.0",
        execution_snapshot_id="snap-001",
        coefficient_context_id="ctx-001",
        orchestration_identity_id="ident-001",
        authoritative_attempt_id="att-001",
        orchestration_fingerprint="fp-001",
        project_id="proj-001",
        project_version_id="pver-001",
        generator_compatibility_version="GCV-1.0",
        captured_at=datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC),
    )
    payload.update(overrides)
    return payload


class TestArchivePayloadValidatorHappyPath:
    """Round-9 P1-1 success path: canonical payload is accepted."""

    def test_canonical_payload_is_accepted(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            compute_archive_hash_v1,
            validate_archive_payload_v1,
        )

        payload = _full_payload()
        validated = validate_archive_payload_v1(payload)
        # Validator returns the same dict (identity over contract).
        assert validated is payload
        # Hash computation completes cleanly afterwards.
        assert len(compute_archive_hash_v1(payload)) == 64

    def test_validator_returns_same_dict_after_validation(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )

        payload = _full_payload()
        result = validate_archive_payload_v1(payload)
        assert result is payload


class TestArchivePayloadValidatorMissingKey:
    """Removing any of the 19 required keys MUST be rejected."""

    @pytest.mark.parametrize(
        "missing_key",
        [
            "schema",
            "scheme_run_id",
            "source_binding_id",
            "source_contract_version",
            "binding_schema_version",
            "combined_source_hash",
            "weight_set_revision_id",
            "weight_set_content_hash",
            "weight_set_generator_compatibility_version",
            "execution_snapshot_id",
            "coefficient_context_id",
            "orchestration_identity_id",
            "authoritative_attempt_id",
            "orchestration_fingerprint",
            "source_slots",
            "project_id",
            "project_version_id",
            "generator_compatibility_version",
            "captured_at",
        ],
    )
    def test_missing_required_key_raises(self, missing_key: str) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1,
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        assert missing_key in REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1, (
            f"test author missed updating REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1; key {missing_key!r}"
        )
        payload = _full_payload()
        payload.pop(missing_key, None)

        with pytest.raises(SourceArchiveBuildError) as exc_info:
            validate_archive_payload_v1(payload)

        msg = str(exc_info.value)
        assert "missing" in msg, f"error message should report missing keys, got: {msg!r}"
        assert missing_key in msg, (
            f"error message should name the missing key {missing_key!r}; got: {msg!r}"
        )


class TestArchivePayloadValidatorExtraKey:
    """Adding any key outside the 19 required MUST be rejected."""

    def test_single_extra_key_is_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        payload = _full_payload(extra_field_not_allowed=True)

        with pytest.raises(SourceArchiveBuildError) as exc_info:
            validate_archive_payload_v1(payload)

        msg = str(exc_info.value)
        assert "extra" in msg, f"error should report extras, got: {msg!r}"
        assert "extra_field_not_allowed" in msg, f"error must name the offending key; got: {msg!r}"

    def test_multiple_extra_keys_are_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        payload = _full_payload()
        payload["rogue_one"] = "rogue"
        payload["rogue_two"] = 99

        with pytest.raises(SourceArchiveBuildError) as exc_info:
            validate_archive_payload_v1(payload)

        msg = str(exc_info.value)
        assert "rogue_one" in msg
        assert "rogue_two" in msg

    def test_both_missing_and_extra_are_reported(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        payload = _full_payload()
        payload.pop("captured_at", None)
        payload["rogue"] = "x"

        with pytest.raises(SourceArchiveBuildError) as exc_info:
            validate_archive_payload_v1(payload)

        msg = str(exc_info.value)
        assert "captured_at" in msg
        assert "rogue" in msg
        assert "missing" in msg and "extra" in msg


class TestArchivePayloadValidatorMalformedSourceSlots:
    """``source_slots`` MUST be the canonical ordered sequence."""

    def test_source_slots_wrong_order_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        # Reverse the canonical order; same five slots, wrong order.
        reversed_slots = [
            ["investment", {"calculation_id": "inv-run", "result_hash": "rh-inv"}],
            ["power", {"calculation_id": "power-run", "result_hash": "rh-power"}],
            ["equipment", {"calculation_id": "equip-run", "result_hash": "rh-equip"}],
            ["cooling_load", {"calculation_id": "cool-run", "result_hash": "rh-cool"}],
            ["zone", {"calculation_id": "zone-run", "result_hash": "rh-zone"}],
        ]
        payload = _full_payload(source_slots=reversed_slots)

        with pytest.raises(SourceArchiveBuildError) as exc_info:
            validate_archive_payload_v1(payload)
        assert "order" in str(exc_info.value).lower()

    def test_source_slots_missing_slot_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        # Drop the investment slot.
        slots = [
            ["zone", {"calculation_id": "z", "result_hash": "rh-z"}],
            ["cooling_load", {"calculation_id": "c", "result_hash": "rh-c"}],
            ["equipment", {"calculation_id": "e", "result_hash": "rh-e"}],
            ["power", {"calculation_id": "p", "result_hash": "rh-p"}],
        ]
        payload = _full_payload(source_slots=slots)

        with pytest.raises(SourceArchiveBuildError):
            validate_archive_payload_v1(payload)

    def test_source_slots_extra_slot_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        slots = [
            ["zone", {"calculation_id": "z", "result_hash": "rh-z"}],
            ["cooling_load", {"calculation_id": "c", "result_hash": "rh-c"}],
            ["equipment", {"calculation_id": "e", "result_hash": "rh-e"}],
            ["power", {"calculation_id": "p", "result_hash": "rh-p"}],
            ["investment", {"calculation_id": "i", "result_hash": "rh-i"}],
            ["rogue_slot", {"calculation_id": "r", "result_hash": "rh-r"}],
        ]
        payload = _full_payload(source_slots=slots)

        with pytest.raises(SourceArchiveBuildError):
            validate_archive_payload_v1(payload)

    def test_source_slots_dict_shape_rejected(self) -> None:
        """Dict-shaped ``source_slots`` (legacy v0) MUST be rejected by v1 validator.

        The canonical five-slot list shape is required; ``assemble_archive_payload``
        would already reject this on its own validation path, but the validator
        serves as a backstop for payloads handed in directly.
        """
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        slots_dict = {
            "zone": {"calculation_id": "z", "result_hash": "rh-z"},
            "cooling_load": {"calculation_id": "c", "result_hash": "rh-c"},
            "equipment": {"calculation_id": "e", "result_hash": "rh-e"},
            "power": {"calculation_id": "p", "result_hash": "rh-p"},
            "investment": {"calculation_id": "i", "result_hash": "rh-i"},
        }
        payload = _full_payload(source_slots=slots_dict)

        with pytest.raises(SourceArchiveBuildError):
            validate_archive_payload_v1(payload)

    def test_source_slots_slot_payload_missing_result_hash_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        slots = [
            ["zone", {"calculation_id": "z"}],  # missing result_hash
            ["cooling_load", {"calculation_id": "c", "result_hash": "rh-c"}],
            ["equipment", {"calculation_id": "e", "result_hash": "rh-e"}],
            ["power", {"calculation_id": "p", "result_hash": "rh-p"}],
            ["investment", {"calculation_id": "i", "result_hash": "rh-i"}],
        ]
        payload = _full_payload(source_slots=slots)

        with pytest.raises(SourceArchiveBuildError):
            validate_archive_payload_v1(payload)


class TestArchivePayloadValidatorTypeErrors:
    """Type errors on the top-level payload must reject."""

    def test_non_dict_payload_rejected(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            validate_archive_payload_v1,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        for bad in [None, "string", 123, 1.5, ["a", "b"], ("a", "b")]:
            with pytest.raises(SourceArchiveBuildError) as exc_info:
                validate_archive_payload_v1(bad)
            assert "must be dict" in str(exc_info.value) or "must be" in str(exc_info.value), (
                f"rejection {exc_info.value!r} did not name type contract"
            )


class TestArchivePayloadValidatorRequiredKeySet:
    """The 19-key required set is itself part of the contract."""

    def test_required_key_set_size_is_19(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1,
        )

        assert len(REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1) == 19, (
            "Public contract declares 19 required keys; if this fails, "
            "update validate_archive_payload_v1 and required_key_set_size_is_19 "
            "in lockstep."
        )

    def test_required_key_set_includes_canonical_keys(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1,
        )

        must_have = {
            "schema",
            "scheme_run_id",
            "source_binding_id",
            "source_contract_version",
            "binding_schema_version",
            "combined_source_hash",
            "weight_set_revision_id",
            "weight_set_content_hash",
            "weight_set_generator_compatibility_version",
            "execution_snapshot_id",
            "coefficient_context_id",
            "orchestration_identity_id",
            "authoritative_attempt_id",
            "orchestration_fingerprint",
            "source_slots",
            "project_id",
            "project_version_id",
            "generator_compatibility_version",
            "captured_at",
        }
        assert must_have == REQUIRED_ARCHIVE_PAYLOAD_KEYS_V1
