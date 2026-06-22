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
