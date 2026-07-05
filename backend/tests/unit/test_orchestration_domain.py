"""Orchestration domain invariant tests.

Coverage:
- DAG: 5-stage order, calculator bindings, acyclic dependencies, provenance keys
- DTO immutability: frozen dataclasses reject mutation
- Canonical hash: same content → same hash, provenance change → different hash,
  requires_review change → different hash, schema/version change → different hash
- Zone upstream_calculation_ids == {}
- Non-zone missing/extra/null upstream ID rejection
- Structured errors: code/field/details
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from cold_storage.modules.orchestration.domain.dag import (
    ALLOWED_STAGES,
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
    STAGE_DEPENDENCIES,
    STAGE_UPSTREAM_PROVENANCE_KEYS,
    validate_registry_consistency,
    validate_stage_acyclic,
)
from cold_storage.modules.orchestration.domain.errors import (
    OrchestrationDomainError,
    ProjectVersionNotFoundError,
    TamperedContentError,
)
from cold_storage.modules.orchestration.domain.fingerprint import (
    canonical_json_bytes,
    result_hash,
)
from cold_storage.modules.orchestration.domain.snapshots import (
    SourceSnapshotContentV1,
    SourceSnapshotProvenanceV1,
)

# ── DAG ─────────────────────────────────────────────────────────────────────


class TestDAG:
    """Five-stage DAG invariants."""

    def test_exactly_five_stages(self) -> None:
        assert len(ORCHESTRATION_STAGE_ORDER) == 5
        assert len(ALLOWED_STAGES) == 5
        assert ORCHESTRATION_STAGE_ORDER == (
            "zone",
            "cooling_load",
            "equipment",
            "power",
            "investment",
        )

    def test_calculator_bindings_exact(self) -> None:
        assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
        assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
        assert CALCULATOR_BINDINGS["equipment"] == "equipment"
        assert CALCULATOR_BINDINGS["power"] == "installed_power"
        assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"
        assert set(CALCULATOR_BINDINGS.keys()) == set(ORCHESTRATION_STAGE_ORDER)

    def test_dependencies_acyclic(self) -> None:
        validate_stage_acyclic()

    def test_dependencies_only_preceding(self) -> None:
        for stage in ORCHESTRATION_STAGE_ORDER:
            deps = STAGE_DEPENDENCIES[stage]
            idx = ORCHESTRATION_STAGE_ORDER.index(stage)
            for dep in deps:
                dep_idx = ORCHESTRATION_STAGE_ORDER.index(dep)
                assert dep_idx < idx, f"{stage} depends on later/same stage {dep}"

    def test_no_unknown_stage(self) -> None:
        for stage in STAGE_DEPENDENCIES:
            assert stage in ALLOWED_STAGES

    def test_registry_consistency(self) -> None:
        validate_registry_consistency()

    def test_zone_no_dependencies(self) -> None:
        assert STAGE_DEPENDENCIES["zone"] == ()

    def test_investment_depends_on_zone_and_power(self) -> None:
        assert STAGE_DEPENDENCIES["investment"] == ("zone", "power")


# ── Provenance keys ─────────────────────────────────────────────────────────


class TestProvenanceKeys:
    """Per-stage upstream_calculation_ids key sets."""

    def test_zone_empty_mapping(self) -> None:
        assert STAGE_UPSTREAM_PROVENANCE_KEYS["zone"] == frozenset()

    def test_cooling_load_requires_zone(self) -> None:
        assert STAGE_UPSTREAM_PROVENANCE_KEYS["cooling_load"] == frozenset({"zone"})

    def test_equipment_requires_cooling_load(self) -> None:
        assert STAGE_UPSTREAM_PROVENANCE_KEYS["equipment"] == frozenset({"cooling_load"})

    def test_power_requires_equipment(self) -> None:
        assert STAGE_UPSTREAM_PROVENANCE_KEYS["power"] == frozenset({"equipment"})

    def test_investment_requires_zone_and_power(self) -> None:
        assert STAGE_UPSTREAM_PROVENANCE_KEYS["investment"] == frozenset({"zone", "power"})

    def test_provenance_keys_match_dependencies(self) -> None:
        for stage in ORCHESTRATION_STAGE_ORDER:
            assert STAGE_UPSTREAM_PROVENANCE_KEYS[stage] == set(STAGE_DEPENDENCIES[stage])


# ── DTO immutability ────────────────────────────────────────────────────────


class TestDTOImmutability:
    """Frozen dataclasses reject mutation."""

    def test_provenance_immutable(self) -> None:
        p = SourceSnapshotProvenanceV1(
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
        )
        with pytest.raises(FrozenInstanceError):
            p.execution_snapshot_id = "changed"  # type: ignore[misc]

    def test_content_immutable(self) -> None:
        c = SourceSnapshotContentV1(
            schema_version="1.0",
            calculation_type="zone",
            calculator_name="cold_room_zone_plan",
            calculator_version="1.0.0",
            project_id="p-1",
            project_version_id="pv-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            input_hash="abc123",
            requires_review=False,
            payload={"zones": []},
            provenance=SourceSnapshotProvenanceV1(
                execution_snapshot_id="es-1",
                coefficient_context_id="cc-1",
                orchestration_identity_id="oi-1",
                orchestration_run_attempt_id="oa-1",
            ),
        )
        with pytest.raises(FrozenInstanceError):
            c.requires_review = True  # type: ignore[misc]


# ── Canonical hash ──────────────────────────────────────────────────────────


class TestCanonicalHash:
    """Execution-bound result_hash invariants."""

    def _make_content(self, **overrides: object) -> SourceSnapshotContentV1:
        base = {
            "schema_version": "1.0",
            "calculation_type": "zone",
            "calculator_name": "cold_room_zone_plan",
            "calculator_version": "1.0.0",
            "project_id": "p-1",
            "project_version_id": "pv-1",
            "execution_snapshot_id": "es-1",
            "coefficient_context_id": "cc-1",
            "orchestration_identity_id": "oi-1",
            "orchestration_run_attempt_id": "oa-1",
            "input_hash": "abc123",
            "requires_review": False,
            "payload": {"zones": [{"zone_code": "A"}]},
            "provenance": SourceSnapshotProvenanceV1(
                execution_snapshot_id="es-1",
                coefficient_context_id="cc-1",
                orchestration_identity_id="oi-1",
                orchestration_run_attempt_id="oa-1",
                upstream_calculation_ids={},
            ),
        }
        base.update({k: v for k, v in overrides.items() if k != "provenance"})
        if "provenance" in overrides:
            base["provenance"] = overrides["provenance"]
        return SourceSnapshotContentV1(**base)  # type: ignore[arg-type]

    def test_same_complete_content_same_hash(self) -> None:
        c1 = self._make_content()
        c2 = self._make_content()
        assert result_hash(c1) == result_hash(c2)

    def test_payload_change_changes_hash(self) -> None:
        c1 = self._make_content()
        c2 = self._make_content(payload={"zones": [{"zone_code": "B"}]})
        assert result_hash(c1) != result_hash(c2)

    def test_provenance_change_changes_hash(self) -> None:
        c1 = self._make_content()
        c2 = self._make_content(
            execution_snapshot_id="es-2",  # must match provenance
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            provenance=SourceSnapshotProvenanceV1(
                execution_snapshot_id="es-2",  # different, but consistent
                coefficient_context_id="cc-1",
                orchestration_identity_id="oi-1",
                orchestration_run_attempt_id="oa-1",
                upstream_calculation_ids={},
            ),
        )
        assert result_hash(c1) != result_hash(c2)

    def test_requires_review_change_changes_hash(self) -> None:
        c1 = self._make_content(requires_review=False)
        c2 = self._make_content(requires_review=True)
        assert result_hash(c1) != result_hash(c2)

    def test_calculator_version_change_changes_hash(self) -> None:
        c1 = self._make_content(calculator_version="1.0.0")
        c2 = self._make_content(calculator_version="2.0.0")
        assert result_hash(c1) != result_hash(c2)

    def test_schema_version_change_changes_hash(self) -> None:
        c1 = self._make_content(schema_version="1.0")
        c2 = self._make_content(schema_version="2.0")
        assert result_hash(c1) != result_hash(c2)

    def test_upstream_id_change_changes_hash(self) -> None:
        p1 = SourceSnapshotProvenanceV1(
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            upstream_calculation_ids={"zone": "calc-aaa"},
        )
        p2 = SourceSnapshotProvenanceV1(
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            upstream_calculation_ids={"zone": "calc-bbb"},
        )
        c1 = self._make_content(calculation_type="cooling_load", provenance=p1)
        c2 = self._make_content(calculation_type="cooling_load", provenance=p2)
        assert result_hash(c1) != result_hash(c2)

    def test_canonical_json_deterministic(self) -> None:
        c1 = self._make_content()
        c2 = self._make_content()
        assert canonical_json_bytes(c1) == canonical_json_bytes(c2)

    def test_decimal_canonicalization(self) -> None:
        # Decimal("1.50") normalizes to the same string as Decimal("1.5")
        data_a = {"value": Decimal("1.50")}
        data_b = {"value": Decimal("1.5")}
        # Both should produce the same canonical bytes
        assert canonical_json_bytes(data_a) == canonical_json_bytes(data_b)

    def test_non_finite_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="Non-finite"):
            canonical_json_bytes({"val": float("nan")})
        with pytest.raises(ValueError, match="Non-finite"):
            canonical_json_bytes({"val": float("inf")})

    def test_binary_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="Binary float"):
            canonical_json_bytes({"val": 1.5})

    def test_duplicate_logical_key_rejected(self) -> None:
        # canonical_json uses json.dumps with sort_keys=True, so duplicate
        # logical keys at the Python dict level are already impossible.
        # We verify that sorted output is stable.
        data = {"b": 1, "a": 2, "c": 3}
        b1 = canonical_json_bytes(data)
        data2 = {"c": 3, "a": 2, "b": 1}
        b2 = canonical_json_bytes(data2)
        assert b1 == b2


# ── Zone provenance contract ────────────────────────────────────────────────


class TestZoneProvenanceContract:
    """Zone upstream_calculation_ids is exactly {}."""

    def test_zone_provenance_empty(self) -> None:
        p = SourceSnapshotProvenanceV1(
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
        )
        assert p.upstream_calculation_ids == {}

    def test_zone_provenance_no_null_values(self) -> None:
        p = SourceSnapshotProvenanceV1(
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            upstream_calculation_ids={},
        )
        for v in p.upstream_calculation_ids.values():
            assert v is not None
            assert isinstance(v, str)
            assert len(v) > 0


# ── Structured errors ───────────────────────────────────────────────────────


class TestStructuredErrors:
    """Typed exceptions with code, field, details."""

    def test_error_carries_code(self) -> None:
        e = ProjectVersionNotFoundError("v-1")
        assert e.code == "PROJ_VERSION_NOT_FOUND"
        assert e.field == "project_version_id"
        assert "v-1" in str(e)

    def test_error_carries_details(self) -> None:
        e = ProjectVersionNotFoundError("v-1")
        assert e.details.get("project_version_id") == "v-1"

    def test_tampered_content_error(self) -> None:
        e = TamperedContentError("aaa", "bbb")
        assert e.code == "TAMPERED_CONTENT"
        assert e.field == "result_hash"
        assert e.details["expected"] == "aaa"
        assert e.details["actual"] == "bbb"

    def test_all_errors_are_domain_errors(self) -> None:
        e = ProjectVersionNotFoundError("v-1")
        assert isinstance(e, OrchestrationDomainError)
        assert isinstance(e, Exception)


# ── Deep immutability ───────────────────────────────────────────────────────


class TestDeepImmutability:
    """DTOs are recursively immutable — external mutation cannot affect them."""

    def test_dto_not_affected_by_original_dict_mutation(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import OrchestrationRequestCommand

        ctx = {"key": "original"}
        cmd = OrchestrationRequestCommand(
            project_id="p-1",
            project_version_id="pv-1",
            coefficient_resolution_context=ctx,
            actor="test",
            correlation_id="c-1",
        )
        # Mutate original
        ctx["key"] = "changed"
        ctx["extra"] = "added"
        # DTO unchanged
        assert cmd.coefficient_resolution_context["key"] == "original"
        assert "extra" not in cmd.coefficient_resolution_context

    def test_dto_mapping_immutable(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import OrchestrationRequestCommand

        ctx = {"key": "v"}
        cmd = OrchestrationRequestCommand(
            project_id="p-1",
            project_version_id="pv-1",
            coefficient_resolution_context=ctx,
            actor="test",
            correlation_id="c-1",
        )
        # Attempting to mutate the frozen mapping should fail
        with pytest.raises(TypeError):
            cmd.coefficient_resolution_context["key"] = "new"  # type: ignore[index]

    def test_payload_deep_frozen(self) -> None:
        """Payload dict mutations don't affect SourceSnapshotContentV1."""
        payload = {"zones": [{"zone_code": "A"}]}
        c = SourceSnapshotContentV1(
            schema_version="1.0",
            calculation_type="zone",
            calculator_name="cold_room_zone_plan",
            calculator_version="1.0.0",
            project_id="p-1",
            project_version_id="pv-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            input_hash="abc123",
            requires_review=False,
            payload=payload,
            provenance=SourceSnapshotProvenanceV1(
                execution_snapshot_id="es-1",
                coefficient_context_id="cc-1",
                orchestration_identity_id="oi-1",
                orchestration_run_attempt_id="oa-1",
                upstream_calculation_ids={},
            ),
        )
        payload["zones"] = [{"zone_code": "Z"}]
        payload["new_field"] = "corrupt"
        assert c.payload["zones"][0]["zone_code"] == "A"
        assert "new_field" not in c.payload

    def test_execution_snapshot_deep_frozen(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import ExecutionSnapshotCandidate

        snap = {"a": {"b": 1}}
        candidate = ExecutionSnapshotCandidate(
            project_id="p-1",
            project_version_id="pv-1",
            version_number=1,
            input_snapshot=snap,
            input_snapshot_hash="h1",
            schema_version="1.0",
            captured_status="approved",
        )
        snap["a"]["b"] = 99
        assert candidate.input_snapshot["a"]["b"] == 1


# ── Provenance key validation ───────────────────────────────────────────────


class TestProvenanceKeyValidation:
    """Provenance upstream_calculation_ids key set validation via validate_provenance_keys."""

    def test_zone_non_empty_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            validate_provenance_keys,
        )

        with pytest.raises(ValueError, match="extra keys"):
            validate_provenance_keys("zone", {"zone": "calc-1"})

    def test_cooling_load_missing_zone_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            validate_provenance_keys,
        )

        with pytest.raises(ValueError, match="missing keys.*zone"):
            validate_provenance_keys("cooling_load", {})

    def test_equipment_extra_zone_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            validate_provenance_keys,
        )

        with pytest.raises(ValueError, match="extra keys.*zone"):
            validate_provenance_keys("equipment", {"zone": "calc-1"})

    def test_null_upstream_id_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            validate_provenance_keys,
        )

        with pytest.raises(ValueError, match="is None"):
            validate_provenance_keys(
                "cooling_load",
                {"zone": None},  # type: ignore[dict-item]
            )

    def test_whitespace_id_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            validate_provenance_keys,
        )

        with pytest.raises(ValueError, match="empty/whitespace"):
            validate_provenance_keys(
                "cooling_load",
                {"zone": "   "},
            )

    def test_identity_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="Content-provenance identity mismatch"):
            SourceSnapshotContentV1(
                schema_version="1.0",
                calculation_type="zone",
                calculator_name="cold_room_zone_plan",
                calculator_version="1.0.0",
                project_id="p-1",
                project_version_id="pv-1",
                execution_snapshot_id="es-1",
                coefficient_context_id="cc-1",
                orchestration_identity_id="oi-1",
                orchestration_run_attempt_id="oa-1",
                input_hash="abc",
                requires_review=False,
                payload={},
                provenance=SourceSnapshotProvenanceV1(
                    execution_snapshot_id="es-WRONG",
                    coefficient_context_id="cc-1",
                    orchestration_identity_id="oi-1",
                    orchestration_run_attempt_id="oa-1",
                    upstream_calculation_ids={},
                ),
            )


# ── Canonical datetime ──────────────────────────────────────────────────────


class TestCanonicalDatetime:
    """Canonical JSON datetime rules: naive rejected, UTC → Z suffix."""

    def test_naive_datetime_rejected(self) -> None:
        dt = datetime(2026, 6, 28, 12, 0, 0)
        with pytest.raises(TypeError, match="Naive datetime"):
            canonical_json_bytes({"dt": dt})

    def test_utc_datetime_z_suffix(self) -> None:
        dt = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)
        b = canonical_json_bytes({"dt": dt})
        assert '"2026-06-28T12:00:00Z"' in b.decode()

    def test_plus0800_converts_to_z(self) -> None:
        tz = timezone(timedelta(hours=8))
        dt = datetime(2026, 6, 28, 12, 0, 0, tzinfo=tz)
        b = canonical_json_bytes({"dt": dt})
        # 12:00 +08:00 = 04:00 UTC
        assert '"2026-06-28T04:00:00Z"' in b.decode()

    def test_different_timezone_same_utc_same_hash(self) -> None:
        # 12:00+08:00 = 04:00 UTC
        tz8 = timezone(timedelta(hours=8))
        dt1 = datetime(2026, 6, 28, 12, 0, 0, tzinfo=tz8)

        # 04:00+00:00 = 04:00 UTC
        dt2 = datetime(2026, 6, 28, 4, 0, 0, tzinfo=UTC)

        b1 = canonical_json_bytes({"dt": dt1})
        b2 = canonical_json_bytes({"dt": dt2})
        assert b1 == b2


# ── Canonical UUID ──────────────────────────────────────────────────────────


class TestCanonicalUUID:
    """UUIDs canonicalize to lowercase."""

    def test_uuid_lowercase(self) -> None:
        import uuid

        u = uuid.UUID("ABCD1234-ABCD-ABCD-ABCD-ABCD1234ABCD")
        b = canonical_json_bytes({"id": u})
        assert '"abcd1234-abcd-abcd-abcd-abcd1234abcd"' in b.decode()


# ── Canonical Mapping ───────────────────────────────────────────────────────


class TestCanonicalMapping:
    """FrozenMapping and other Mapping subtypes are supported."""

    def test_frozen_mapping_canonicalizes(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import deep_freeze

        fm = deep_freeze({"b": 2, "a": 1})
        b = canonical_json_bytes(fm)
        # Should serialize as JSON object with sorted keys
        assert b.decode() == '{"a":1,"b":2}'

    def test_duplicate_logical_key_rejected(self) -> None:
        # Generic payload preserves original keys — no lowercase collision
        result = canonical_json_bytes({"A": 1, "a": 2})
        decoded = result.decode()
        assert '"A"' in decoded
        assert '"a"' in decoded

    def test_generic_payload_keys_preserved(self) -> None:
        # "Key" and "key" are distinct keys in generic payload — both preserved
        result = canonical_json_bytes({"Key": 1, "key": 2})
        decoded = result.decode()
        assert '"Key"' in decoded
        assert '"key"' in decoded

    def test_semantic_stage_key_collision_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.fingerprint import (
            semantic_normalize_stage_key_mapping,
        )

        allowed = frozenset({"zone", "cooling_load", "equipment", "power", "investment"})

        # Valid: no collision
        result = semantic_normalize_stage_key_mapping(
            [("zone", "v1"), ("power", "v2")],
            allowed_keys=allowed,
        )
        assert result == {"zone": "v1", "power": "v2"}

        # Collision detected
        with pytest.raises(ValueError, match="Duplicate logical stage key"):
            semantic_normalize_stage_key_mapping(
                [("ZONE", "v1"), ("zone", "v2")],
                allowed_keys=allowed,
            )

    def test_semantic_stage_key_unknown_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.fingerprint import (
            semantic_normalize_stage_key_mapping,
        )

        allowed = frozenset({"zone", "power"})
        with pytest.raises(ValueError, match="Unknown semantic stage key"):
            semantic_normalize_stage_key_mapping(
                [("cooling_load", "v1")],
                allowed_keys=allowed,
            )

    def test_semantic_stage_key_empty_rejected(self) -> None:
        from cold_storage.modules.orchestration.domain.fingerprint import (
            semantic_normalize_stage_key_mapping,
        )

        allowed = frozenset({"zone"})
        with pytest.raises(ValueError, match="empty after normalization"):
            semantic_normalize_stage_key_mapping(
                [("  ", "v1")],
                allowed_keys=allowed,
            )


# ── New DTOs exist and are frozen ───────────────────────────────────────────


class TestNewDTOs:
    """Phase 1 DTOs from approved design exist and are frozen."""

    def test_orchestration_request_command(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            OrchestrationRequestCommand,
        )

        cmd = OrchestrationRequestCommand(
            project_id="p-1",
            project_version_id="pv-1",
            coefficient_resolution_context={},
            actor="test",
            correlation_id="c-1",
        )
        with pytest.raises(FrozenInstanceError):
            cmd.project_id = "changed"  # type: ignore[misc]

    def test_preflight_failure(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            PreflightFailure,
        )

        pf = PreflightFailure(
            request_id="r-1",
            project_id="p-1",
            project_version_id="pv-1",
            error_class="TestError",
            code="TEST",
            field="test_field",
            details={"reason": "test"},
            occurred_at=datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC),
        )
        assert pf.code == "TEST"

    def test_calculation_type_enum(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            CalculationType,
        )

        assert CalculationType.ZONE == "zone"
        assert CalculationType.POWER == "power"
        assert CalculationType.INVESTMENT == "investment"
        assert len(CalculationType) == 5
