"""Report domain tests — status machine, canonical hash, quality, diff, units."""

from __future__ import annotations

import pytest

from cold_storage.modules.reports.domain.canonical import canonical_json, content_hash
from cold_storage.modules.reports.domain.enums import (
    ReportStatus,
    ReviewAction,
)
from cold_storage.modules.reports.domain.errors import InvalidStatusTransitionError
from cold_storage.modules.reports.domain.models import (
    ReportRevision,
)
from cold_storage.modules.reports.domain.quality import (
    evaluate_quality,
    get_blockers,
    has_blockers,
)
from cold_storage.modules.reports.domain.revision_diff import diff_revisions
from cold_storage.modules.reports.domain.status_machine import apply_action, validate_transition

# ---------------------------------------------------------------------------
# Status machine tests
# ---------------------------------------------------------------------------


class TestStatusMachine:
    def test_draft_to_generated(self):
        validate_transition(ReportStatus.DRAFT, ReportStatus.GENERATED)

    def test_generated_to_under_review(self):
        validate_transition(ReportStatus.GENERATED, ReportStatus.UNDER_REVIEW)

    def test_under_review_to_reviewed(self):
        validate_transition(ReportStatus.UNDER_REVIEW, ReportStatus.REVIEWED)

    def test_under_review_to_draft(self):
        validate_transition(ReportStatus.UNDER_REVIEW, ReportStatus.DRAFT)

    def test_reviewed_to_approved(self):
        validate_transition(ReportStatus.REVIEWED, ReportStatus.APPROVED)

    def test_approved_to_archived(self):
        validate_transition(ReportStatus.APPROVED, ReportStatus.ARCHIVED)

    def test_archived_is_terminal(self):
        with pytest.raises(InvalidStatusTransitionError):
            validate_transition(ReportStatus.ARCHIVED, ReportStatus.DRAFT)

    def test_skip_level_rejected(self):
        with pytest.raises(InvalidStatusTransitionError):
            validate_transition(ReportStatus.DRAFT, ReportStatus.APPROVED)

    def test_approved_no_skip_to_draft(self):
        with pytest.raises(InvalidStatusTransitionError):
            validate_transition(ReportStatus.APPROVED, ReportStatus.DRAFT)

    def test_apply_action_submit_review(self):
        result = apply_action(ReportStatus.GENERATED, ReviewAction.SUBMIT_REVIEW)
        assert result == ReportStatus.UNDER_REVIEW

    def test_apply_action_request_changes(self):
        result = apply_action(ReportStatus.UNDER_REVIEW, ReviewAction.REQUEST_CHANGES)
        assert result == ReportStatus.DRAFT

    def test_apply_action_approve(self):
        result = apply_action(ReportStatus.REVIEWED, ReviewAction.APPROVE)
        assert result == ReportStatus.APPROVED

    def test_apply_action_wrong_status(self):
        with pytest.raises(InvalidStatusTransitionError):
            apply_action(ReportStatus.DRAFT, ReviewAction.APPROVE)


# ---------------------------------------------------------------------------
# Approved/archived revision immutability tests
# ---------------------------------------------------------------------------


class TestRevisionImmutability:
    def test_frozen_dataclass(self):
        rev = ReportRevision.create(
            report_id="r1",
            revision_number=1,
            schema_version="test@1.0.0",
            content_json={},
            canonical_content_json={},
            content_hash="abc",
            quality_status=ReportStatus.DRAFT,
            quality_findings_json=[],
            generated_by="test",
        )
        with pytest.raises(AttributeError):
            rev.content_hash = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Canonical JSON and SHA-256 stability
# ---------------------------------------------------------------------------


class TestCanonicalJson:
    def test_sorted_keys(self):
        data = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(data)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self):
        data = {"key": "value"}
        result = canonical_json(data)
        assert " " not in result

    def test_deterministic_hash(self):
        data = {"a": 1, "b": [1, 2, 3]}
        h1 = content_hash(data)
        h2 = content_hash(data)
        assert h1 == h2

    def test_different_data_different_hash(self):
        h1 = content_hash({"a": 1})
        h2 = content_hash({"a": 2})
        assert h1 != h2

    def test_key_order_invariant(self):
        h1 = content_hash({"x": 1, "y": 2})
        h2 = content_hash({"y": 2, "x": 1})
        assert h1 == h2

    def test_decimal_serialization(self):
        from decimal import Decimal

        data = {"value": Decimal("123.456")}
        result = canonical_json(data)
        assert '"123.456"' in result


# ---------------------------------------------------------------------------
# Quality findings
# ---------------------------------------------------------------------------


class TestQualityFindings:
    def test_empty_content_no_blockers(self):
        findings = evaluate_quality({}, [], required_sections=[])
        blockers = get_blockers(findings)
        assert len(blockers) == 0

    def test_missing_required_section(self):
        findings = evaluate_quality({}, [], required_sections=["cooling_load"])
        assert any(f["code"] == "MISSING_REQUIRED_SECTION" for f in findings)

    def test_not_calculated_detected(self):
        content = {"cooling_load": {"total": "not_calculated"}}
        findings = evaluate_quality(content, [])
        assert any(f["code"] == "NOT_CALCULATED_VALUE" for f in findings)

    def test_blocker_from_invalid_unit(self):
        content = {"cooling_load": {"load_unit": "BTU/h"}}
        findings = evaluate_quality(content, [])
        assert has_blockers(findings)

    def test_source_missing_result_id(self):
        refs = [
            {
                "section_key": "x",
                "field_path": "x",
                "source_type": "calculation_result",
                "result_id": "",
                "tool_version": "1.0",
                "content_hash": "abc",
            }
        ]
        findings = evaluate_quality({}, refs)
        assert any(f["code"] == "SOURCE_MISSING_RESULT_ID" for f in findings)


# ---------------------------------------------------------------------------
# Unit dimension isolation
# ---------------------------------------------------------------------------


class TestUnitDimensionIsolation:
    VALID_UNITS = {"kW(r)", "kW(e)", "kW(th)", "kWh"}

    def test_valid_units_pass(self):
        content = {"load": {"load_unit": "kW(r)"}, "power": {"power_unit": "kW(e)"}}
        findings = evaluate_quality(content, [])
        assert not any(f["code"] == "INVALID_UNIT" for f in findings)

    def test_fuzzy_kw_rejected(self):
        content = {"load": {"load_unit": "kW"}}
        findings = evaluate_quality(content, [])
        assert has_blockers(findings)

    def test_btu_rejected(self):
        content = {"load": {"load_unit": "BTU/h"}}
        findings = evaluate_quality(content, [])
        assert has_blockers(findings)


# ---------------------------------------------------------------------------
# Revision diff
# ---------------------------------------------------------------------------


class TestRevisionDiff:
    def test_no_changes(self):
        d = diff_revisions({"a": 1}, {"a": 1})
        assert len(d) == 0

    def test_added_field(self):
        d = diff_revisions({}, {"a": 1})
        assert len(d) == 1
        assert d[0]["change_type"] == "added"

    def test_removed_field(self):
        d = diff_revisions({"a": 1}, {})
        assert len(d) == 1
        assert d[0]["change_type"] == "removed"

    def test_modified_field(self):
        d = diff_revisions({"a": 1}, {"a": 2})
        assert len(d) == 1
        assert d[0]["change_type"] == "modified"
        assert d[0]["before"] == 1
        assert d[0]["after"] == 2

    def test_nested_changes(self):
        before = {"section": {"nested": "old"}}
        after = {"section": {"nested": "new"}}
        d = diff_revisions(before, after)
        assert len(d) == 1
        assert d[0]["field_path"] == "section.nested"

    def test_unit_change_detected(self):
        before = {"load_unit": "kW(r)", "load_value": 100}
        after = {"load_unit": "kW(e)", "load_value": 100}
        d = diff_revisions(before, after)
        # load_unit changed
        unit_changes = [c for c in d if c["field_path"] == "load_unit"]
        assert len(unit_changes) == 1
        assert unit_changes[0].get("unit_changed") is True


# ---------------------------------------------------------------------------
# Quality gate: empty sections → blocker
# ---------------------------------------------------------------------------


class TestQualityGateEmptySections:
    """An empty section dict {} for a required calc field should produce
    EMPTY_REQUIRED_ENGINEERING_RESULT blocker."""

    def test_empty_section_is_blocker(self):
        content = {"equipment_selection": {}}
        findings = evaluate_quality(
            content,
            [],
            required_calc_fields=["equipment_selection.total_compressor_capacity"],
        )
        blockers = get_blockers(findings)
        assert any(f["code"] == "EMPTY_REQUIRED_ENGINEERING_RESULT" for f in blockers)

    def test_non_empty_section_passes(self):
        content = {
            "equipment_selection": {
                "total_compressor_capacity": {
                    "value": 120.0,
                    "unit": "kW(r)",
                    "source_result_id": "calc-001",
                    "source_tool": "equipment_selector",
                    "source_tool_version": "1.0.0",
                }
            }
        }
        findings = evaluate_quality(
            content,
            [],
            required_calc_fields=["equipment_selection.total_compressor_capacity"],
        )
        assert not any(f["code"] == "EMPTY_REQUIRED_ENGINEERING_RESULT" for f in findings)


# ---------------------------------------------------------------------------
# Quality gate: measured-value unit dimension check
# ---------------------------------------------------------------------------


class TestQualityGateUnits:
    """Measured-value objects with wrong unit dimension should produce
    WRONG_UNIT_DIMENSION blocker."""

    def test_measured_value_wrong_unit_is_blocker(self):
        # total_compressor_capacity expects kW(r) but gets kW(e)
        content = {
            "equipment_selection": {
                "total_compressor_capacity": {
                    "value": 120.0,
                    "unit": "kW(e)",  # WRONG — should be kW(r)
                    "source_result_id": "calc-001",
                    "source_tool": "equipment_selector",
                    "source_tool_version": "1.0.0",
                }
            }
        }
        findings = evaluate_quality(content, [])
        blockers = get_blockers(findings)
        assert any(f["code"] == "WRONG_UNIT_DIMENSION" for f in blockers)

    def test_measured_value_correct_unit_passes(self):
        content = {
            "equipment_selection": {
                "total_compressor_capacity": {
                    "value": 120.0,
                    "unit": "kW(r)",  # correct
                    "source_result_id": "calc-001",
                    "source_tool": "equipment_selector",
                    "source_tool_version": "1.0.0",
                }
            }
        }
        findings = evaluate_quality(content, [])
        assert not any(f["code"] == "WRONG_UNIT_DIMENSION" for f in findings)


# ---------------------------------------------------------------------------
# Quality gate: findings schema — source_ids
# ---------------------------------------------------------------------------


class TestQualityGateFindingsSourceIds:
    """Validate that findings objects conform to the JSON Schema, including
    proper handling of source_ids (optional property)."""

    def test_findings_with_source_ids_validate(self):
        """Findings containing source_ids should pass schema validation."""
        import jsonschema

        from cold_storage.modules.reports.domain.schema import get_schema

        schema = get_schema("cold_storage_concept_design", "1.0.0")
        content = {
            "report_metadata": {
                "schema_version": "cold_storage_concept_design@1.0.0",
                "report_id": "r1",
                "project_id": "p1",
                "project_version_id": "v1",
                "generated_at": "2024-01-01T00:00:00Z",
            },
            "quality_summary": {
                "total_findings": 1,
                "blocker_count": 0,
                "warning_count": 0,
                "info_count": 1,
                "findings": [
                    {
                        "code": "TEST",
                        "severity": "info",
                        "message": "test finding",
                        "source_ids": ["src-1", "src-2"],
                    }
                ],
            },
        }
        # Should not raise
        jsonschema.validate(instance=content, schema=schema)

    def test_finding_with_unknown_property_fails_schema(self):
        """additionalProperties: False ensures findings don't smuggle
        extra fields not defined in the schema."""
        import jsonschema

        from cold_storage.modules.reports.domain.schema import get_schema

        schema = get_schema("cold_storage_concept_design", "1.0.0")
        content = {
            "report_metadata": {
                "schema_version": "cold_storage_concept_design@1.0.0",
                "report_id": "r1",
                "project_id": "p1",
                "project_version_id": "v1",
                "generated_at": "2024-01-01T00:00:00Z",
            },
            "quality_summary": {
                "total_findings": 1,
                "blocker_count": 0,
                "warning_count": 0,
                "info_count": 1,
                "findings": [
                    {
                        "code": "TEST",
                        "severity": "info",
                        "message": "test finding",
                        "unknown_field": "should_fail",
                    }
                ],
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=content, schema=schema)


# ---------------------------------------------------------------------------
# Minimum required engineering results
# ---------------------------------------------------------------------------


class TestMinimumEngineeringResults:
    """Missing or empty key engineering result fields must produce BLOCKERs."""

    def test_missing_compressor_capacity_is_blocker(self):
        content = {
            "equipment_selection": {
                "some_other_field": "value",
            }
        }
        findings = evaluate_quality(
            content,
            [],
            required_calc_fields=["equipment_selection.total_compressor_capacity"],
        )
        blockers = get_blockers(findings)
        assert any(f["code"] == "MISSING_REQUIRED_ENGINEERING_RESULT" for f in blockers)

    def test_missing_installed_power_is_blocker(self):
        content = {
            "electrical_and_energy": {
                "some_other_field": "value",
            }
        }
        findings = evaluate_quality(
            content,
            [],
            required_calc_fields=["electrical_and_energy.total_installed_power"],
        )
        blockers = get_blockers(findings)
        assert any(f["code"] == "MISSING_REQUIRED_ENGINEERING_RESULT" for f in blockers)

    def test_empty_equipment_section_is_blocker(self):
        content = {"equipment_selection": {}}
        findings = evaluate_quality(
            content,
            [],
            required_calc_fields=["equipment_selection.total_compressor_capacity"],
        )
        blockers = get_blockers(findings)
        assert any(f["code"] == "EMPTY_REQUIRED_ENGINEERING_RESULT" for f in blockers)


# -----------------------------------------------------------------------
# Scheme source authenticity — no hardcoded tool_call_status
# -----------------------------------------------------------------------


class TestSchemeSourceAuthenticity:
    def test_scheme_source_ref_has_no_hardcoded_status(self):
        """Scheme source ref should not have hardcoded tool_call_status."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        ref = _make_source_ref(
            section_key="scheme_comparison",
            source_type=SourceType.SCHEME_RESULT,
            source_id="run-123",
            data={"run_id": "run-123", "status": "completed"},
        )
        assert "tool_call_status" not in ref  # Not hardcoded
        assert ref["source_id"] == "run-123"

    def test_scheme_source_ref_includes_verification_when_present(self):
        """tool_call_status only appears when genuinely present in data."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        ref = _make_source_ref(
            section_key="scheme_comparison",
            source_type=SourceType.SCHEME_RESULT,
            source_id="run-456",
            data={"run_id": "run-456", "tool_call_status": "completed"},
        )
        assert ref["tool_call_status"] == "completed"


# -----------------------------------------------------------------------
# Knowledge per-revision provenance
# -----------------------------------------------------------------------


class TestKnowledgePerRevisionProvenance:
    def test_knowledge_source_refs_are_per_revision(self):
        """Each knowledge revision should have its own source ref."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        knowledge_data = [
            {
                "id": "doc-1",
                "approved_revisions": [
                    {"id": "rev-1", "content_sha256": "abc123"},
                    {"id": "rev-2", "content_sha256": "def456"},
                ],
            },
        ]
        refs = []
        for doc in knowledge_data:
            for rev in doc.get("approved_revisions", []):
                refs.append(
                    _make_source_ref(
                        section_key="knowledge_references",
                        source_type=SourceType.KNOWLEDGE_REVISION,
                        source_id=rev["id"],
                        data={
                            "knowledge_status": "approved",
                            "persisted_content_hash": rev.get("content_sha256", ""),
                        },
                    )
                )
        assert len(refs) == 2
        assert refs[0]["source_id"] == "rev-1"
        assert refs[1]["source_id"] == "rev-2"
        assert refs[0]["content_hash"] == "abc123"
        assert refs[1]["content_hash"] == "def456"

    def test_knowledge_ref_without_persisted_hash_is_empty(self):
        """Without persisted_content_hash, content_hash should be empty string."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        ref = _make_source_ref(
            section_key="knowledge_references",
            source_type=SourceType.KNOWLEDGE_REVISION,
            source_id="rev-3",
            data={"knowledge_status": "approved"},
        )
        assert ref["content_hash"] == ""  # No fallback to computed hash


# -----------------------------------------------------------------------
# Missing hash generates blocker
# -----------------------------------------------------------------------


class TestMissingHashGeneratesBlocker:
    def test_empty_content_hash_is_blocker(self):
        """Source ref with empty content_hash should trigger SOURCE_MISSING_CONTENT_HASH."""
        content = {
            "report_metadata": {
                "schema_version": "test@1.0",
                "report_id": "r1",
                "project_id": "p1",
                "project_version_id": "v1",
                "generated_at": "2026-01-01T00:00:00",
                "generated_by": "test",
                "revision_number": 1,
            },
            "quality_summary": {
                "total_findings": 0,
                "blocker_count": 0,
                "warning_count": 0,
                "info_count": 0,
            },
        }
        source_refs = [
            {
                "section_key": "cooling_load",
                "field_path": "cooling_load",
                "source_type": "calculation_result",
                "source_id": "calc-001",
                "result_id": "calc-001",
                "tool_version": "1.0.0",
                "content_hash": "",  # Empty — no persisted hash
            }
        ]
        findings = evaluate_quality(content, source_refs)
        blocker_codes = [f["code"] for f in findings if f["severity"] == "blocker"]
        assert "SOURCE_MISSING_CONTENT_HASH" in blocker_codes

    def test_nonempty_content_hash_passes(self):
        """Source ref with valid content_hash should not trigger blocker."""
        content = {
            "cooling_load": {"total_design_refrigeration_load": {"value": 100, "unit": "kW(r)"}}
        }
        source_refs = [
            {
                "section_key": "cooling_load",
                "field_path": "cooling_load",
                "source_type": "calculation_result",
                "source_id": "calc-001",
                "result_id": "calc-001",
                "tool_version": "1.0.0",
                "content_hash": "abc123def456",
            }
        ]
        findings = evaluate_quality(content, source_refs)
        blocker_codes = [f["code"] for f in findings if f["severity"] == "blocker"]
        assert "SOURCE_MISSING_CONTENT_HASH" not in blocker_codes


# ---------------------------------------------------------------------------
# Scheme version filtering — assembler omits scheme_comparison when None
# ---------------------------------------------------------------------------


class TestSchemeVersionFilter:
    def test_cross_version_scheme_rejection(self):
        """Scheme data from wrong project version should not appear in report."""
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
            ReportDataProvider,
        )
        from cold_storage.modules.reports.domain.enums import ReportType

        class _NoSchemeProvider(ReportDataProvider):
            def get_project(self, project_id):
                return {"name": "P"}

            def get_project_version(self, version_id, project_id=None):
                return {"id": version_id, "version_number": 1}

            def get_calculation_results(self, project_id, version_id):
                return []

            def get_scheme_results(self, project_id, version_id):
                return None  # No scheme for this version

            def get_agent_sessions(self, project_id, version_id):
                return []

            def get_knowledge_documents(self):
                return []

        assembler = ReportAssembler(_NoSchemeProvider())
        result = assembler.assemble(
            report_id="r1",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="test",
        )
        assert "scheme_comparison" not in result.content


# ---------------------------------------------------------------------------
# Canonical hash stability — engineering inputs determine the hash
# ---------------------------------------------------------------------------


class TestCanonicalHashStability:
    def test_same_inputs_same_hash(self):
        """Same engineering inputs with same report_id should produce same canonical hash."""
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
            ReportDataProvider,
        )
        from cold_storage.modules.reports.domain.enums import ReportType

        class _StableProvider(ReportDataProvider):
            def get_project(self, pid):
                return {"name": "P"}

            def get_project_version(self, vid, *, project_id=None):
                return None

            def get_calculation_results(self, pid, vid):
                return []

            def get_scheme_results(self, pid, vid):
                return None

            def get_agent_sessions(self, pid, vid):
                return []

            def get_knowledge_documents(self):
                return []

        p = _StableProvider()
        a = ReportAssembler(p)
        r1 = a.assemble(
            report_id="report-A",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="alice",
        )
        r2 = a.assemble(
            report_id="report-A",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=2,
            generated_by="bob",
        )
        assert r1.content_hash == r2.content_hash, (
            f"Canonical hash differs: {r1.content_hash} != {r2.content_hash}"
        )

    def test_different_report_id_same_hash(self):
        """Different report_ids should produce same canonical hashes
        because report_id is excluded from the canonical content."""
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
            ReportDataProvider,
        )
        from cold_storage.modules.reports.domain.enums import ReportType

        class _StableProvider(ReportDataProvider):
            def get_project(self, pid):
                return {"name": "P"}

            def get_project_version(self, vid, *, project_id=None):
                return None

            def get_calculation_results(self, pid, vid):
                return []

            def get_scheme_results(self, pid, vid):
                return None

            def get_agent_sessions(self, pid, vid):
                return []

            def get_knowledge_documents(self):
                return []

        p = _StableProvider()
        a = ReportAssembler(p)
        r1 = a.assemble(
            report_id="report-A",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="alice",
        )
        r2 = a.assemble(
            report_id="report-B",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="alice",
        )
        assert r1.content_hash == r2.content_hash, (
            "Canonical hash should be the same when only report_id differs "
            "(report_id is excluded from canonical hash)"
        )


# ---------------------------------------------------------------------------
# Agent session provenance — sessions produce source refs
# ---------------------------------------------------------------------------


class TestAgentTurnProvenance:
    def test_completed_tool_calls_generate_tool_call_refs(self):
        """Successful tool calls should produce AGENT_TOOL_CALL source refs."""
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
            ReportDataProvider,
        )
        from cold_storage.modules.reports.domain.enums import ReportType, SourceType

        class _TurnProvider(ReportDataProvider):
            def get_project(self, pid):
                return {"name": "P"}

            def get_project_version(self, vid, *, project_id=None):
                return None

            def get_calculation_results(self, pid, vid):
                return []

            def get_scheme_results(self, pid, vid):
                return None

            def get_agent_sessions(self, pid, vid):
                return [
                    {
                        "session_id": "s1",
                        "turns": [
                            {"id": "t1", "status": "completed"},
                            {"id": "t2", "status": "failed"},
                        ],
                        "tool_calls": [
                            {"id": "tc1", "tool_call_status": "succeeded"},
                            {"id": "tc2", "tool_call_status": "failed"},
                            {"id": "tc3", "tool_call_status": "confirmed"},
                        ],
                    }
                ]

            def get_knowledge_documents(self):
                return []

        a = ReportAssembler(_TurnProvider())
        result = a.assemble(
            report_id="r1",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="test",
        )
        # Should have 1 AGENT_SESSION ref
        session_refs = [
            r for r in result.source_refs if r["source_type"] == SourceType.AGENT_SESSION.value
        ]
        assert len(session_refs) == 1
        assert session_refs[0]["source_id"] == "s1"

        # Should have 1 AGENT_TOOL_CALL ref (only succeeded, not confirmed or failed)
        tool_call_refs = [
            r for r in result.source_refs if r["source_type"] == SourceType.AGENT_TOOL_CALL.value
        ]
        assert len(tool_call_refs) == 1
        tc_ids = {r["source_id"] for r in tool_call_refs}
        assert tc_ids == {"tc1"}

    def test_empty_tool_calls_produces_session_ref_only(self):
        """Session with no tool calls should produce only an AGENT_SESSION ref."""
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
            ReportDataProvider,
        )
        from cold_storage.modules.reports.domain.enums import ReportType, SourceType

        class _EmptyToolCallsProvider(ReportDataProvider):
            def get_project(self, pid):
                return {"name": "P"}

            def get_project_version(self, vid, *, project_id=None):
                return None

            def get_calculation_results(self, pid, vid):
                return []

            def get_scheme_results(self, pid, vid):
                return None

            def get_agent_sessions(self, pid, vid):
                return [
                    {
                        "session_id": "s2",
                        "turns": [{"id": "t1", "status": "completed"}],
                        "tool_calls": [],
                    }
                ]

            def get_knowledge_documents(self):
                return []

        a = ReportAssembler(_EmptyToolCallsProvider())
        result = a.assemble(
            report_id="r1",
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            revision_number=1,
            generated_by="test",
        )
        session_refs = [
            r for r in result.source_refs if r["source_type"] == SourceType.AGENT_SESSION.value
        ]
        tool_call_refs = [
            r for r in result.source_refs if r["source_type"] == SourceType.AGENT_TOOL_CALL.value
        ]
        assert len(session_refs) == 1
        assert len(tool_call_refs) == 0


# ---------------------------------------------------------------------------
# Scheme source ref — persisted_content_hash propagation
# ---------------------------------------------------------------------------


class TestSchemePersistedHash:
    def test_scheme_source_ref_has_persisted_hash(self):
        """Scheme source ref should carry persisted_content_hash from run."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        ref = _make_source_ref(
            section_key="scheme_comparison",
            source_type=SourceType.SCHEME_RESULT,
            source_id="run-1",
            data={"run_id": "run-1", "persisted_content_hash": "abc123"},
        )
        assert ref["content_hash"] == "abc123"

    def test_scheme_source_ref_empty_hash_when_missing(self):
        """Scheme source ref without persisted hash should have empty content_hash."""
        from cold_storage.modules.reports.application.assembler import _make_source_ref
        from cold_storage.modules.reports.domain.enums import SourceType

        ref = _make_source_ref(
            section_key="scheme_comparison",
            source_type=SourceType.SCHEME_RESULT,
            source_id="run-1",
            data={"run_id": "run-1"},
        )
        assert ref["content_hash"] == ""
