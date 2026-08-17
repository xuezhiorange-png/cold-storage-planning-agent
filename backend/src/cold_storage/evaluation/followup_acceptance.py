"""V0.3 P1 controlled-acceptance orchestration and evidence verification.

This module is an acceptance boundary, not a second calculation engine.  It
calls the existing production fixture/orchestration/report services, reads
their persisted output through fresh sessions, and fails closed when an
identity, review reason, lifecycle action, or artifact is missing or stale.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from cold_storage.modules.orchestration.domain.fingerprint import canonical_json_bytes
from cold_storage.modules.reports.domain.errors import InvalidStatusTransitionError
from cold_storage.modules.reports.domain.quality import get_blockers
from cold_storage.modules.schemes.domain.models import ReviewReason

STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)
EXPECTED_REVIEW_VECTOR: tuple[bool, ...] = (True, True, True, False, True)
# These identify the accepted source-definition baseline.  They are not the
# source identity of the checkout that executes a controlled run.
ACCEPTED_SOURCE_DEFINITION_BASE_SHA = "c6903d80089291c81bace737f6245da174825b70"
ACCEPTED_SOURCE_DEFINITION_BASE_TREE_SHA = "5f0239f5804499ca857250a39af38f61c039530b"
CANONICAL_INPUT_SHA256 = "6a3ccd82852d8aa908a8bedcaab6437fbb68ff8ee3a305f9451c84b738d5f5d4"
SOURCE_SCHEMA_VERSION = "v0.3-p1-high-throughput-source.v1"
EVIDENCE_SCHEMA_VERSION = "v0.3-p1-controlled-acceptance-evidence.v1"
FORMAL_ARTIFACT_MATRIX: tuple[tuple[str, str], ...] = (
    ("zh-CN", "docx"),
    ("zh-CN", "pdf"),
    ("en-US", "docx"),
    ("en-US", "pdf"),
)
REJECTED_OPERATOR_NAMES = frozenset({"system", "api", "background", "llm"})
CONTROLLED_REVIEW_LIFECYCLE_ACTIONS: tuple[str, ...] = (
    "submit_review",
    "mark_reviewed",
    "approve",
)


class ControlledAcceptanceError(RuntimeError):
    """A machine-readable fail-closed acceptance error."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_json(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ControlledSourceDefinition:
    """The immutable source-definition projection used by Stage25/26."""

    schema_version: str
    source_label: str
    source_candidate_path: str
    canonical_input_sha256: str
    stage_order: tuple[str, ...]
    expected_requires_review: tuple[bool, ...]
    input: Mapping[str, object]

    @property
    def expected_vector(self) -> dict[str, bool]:
        return dict(zip(self.stage_order, self.expected_requires_review, strict=True))

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_label": self.source_label,
            "source_candidate_path": self.source_candidate_path,
            "canonical_input_sha256": self.canonical_input_sha256,
            "stage_order": list(self.stage_order),
            "expected_requires_review": self.expected_vector,
            "input": self.input,
        }


@dataclass(frozen=True, slots=True)
class ControlledSourceRuntime:
    """Explicit pilot-owned access to the accepted production support surface."""

    source_candidate_path: str
    source_snapshot: Mapping[str, object]
    seed_startup_readiness: Callable[..., object]
    create_controlled_coefficient_definition: Callable[..., object]
    create_controlled_production_authority: Callable[..., object]


@dataclass(frozen=True, slots=True)
class ArtifactObservation:
    """Persisted artifact metadata plus the independently read file hash."""

    artifact_id: str
    report_id: str
    report_revision_id: str
    approved_revision_id: str
    approved_content_hash: str
    locale: str
    format: str
    status: str
    file_sha256: str
    observed_file_sha256: str
    file_size_bytes: int
    storage_key: str
    template_id: str
    template_version: str
    template_content_hash: str
    template_locale: str
    translation_catalog_version: str
    translation_catalog_content_hash: str
    localized_template_content_hash: str

    def to_json(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "report_id": self.report_id,
            "report_revision_id": self.report_revision_id,
            "approved_revision_id": self.approved_revision_id,
            "approved_content_hash": self.approved_content_hash,
            "locale": self.locale,
            "format": self.format,
            "status": self.status,
            "file_sha256": self.file_sha256,
            "observed_file_sha256": self.observed_file_sha256,
            "file_size_bytes": self.file_size_bytes,
            "storage_key": self.storage_key,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "template_content_hash": self.template_content_hash,
            "template_locale": self.template_locale,
            "translation_catalog_version": self.translation_catalog_version,
            "translation_catalog_content_hash": self.translation_catalog_content_hash,
            "localized_template_content_hash": self.localized_template_content_hash,
        }


@dataclass(slots=True)
class _LifecycleDiagnosticContext:
    lifecycle_action: str | None = None
    report_status_after_generate_revision: str | None = None
    quality_blockers_after_generate_revision: list[dict[str, Any]] | None = None


def _capture_post_generation_diagnostics(
    report_service: Any,
    report_id: str,
    operator: str,
    revision: Any,
    diagnostics: _LifecycleDiagnosticContext,
) -> _LifecycleDiagnosticContext:
    """Read the persisted report state and complete quality findings once."""

    generated_report = report_service.get_report(report_id, operator)
    diagnostics.report_status_after_generate_revision = generated_report.status.value
    diagnostics.quality_blockers_after_generate_revision = get_blockers(
        revision.quality_findings_json
    )
    return diagnostics


def _invoke_review_lifecycle_action(
    report_service: Any,
    report_id: str,
    operator: str,
    action: str,
    diagnostics: _LifecycleDiagnosticContext,
) -> Any:
    """Set the exact action before invoking the existing report service."""

    if action not in CONTROLLED_REVIEW_LIFECYCLE_ACTIONS:
        raise ControlledAcceptanceError(
            "CONTROLLED_LIFECYCLE_ACTION_INVALID",
            "controlled acceptance lifecycle action is not supported",
            lifecycle_action=action,
        )
    diagnostics.lifecycle_action = action
    try:
        result = getattr(report_service, action)(
            report_id,
            operator,
            comment="controlled acceptance",
        )
    except InvalidStatusTransitionError:
        # Preserve the targeted action for the outer diagnostic wrapper.
        raise
    except Exception:
        # Other failures must not leave a stale review-action context behind.
        diagnostics.lifecycle_action = None
        raise
    else:
        diagnostics.lifecycle_action = None
        return result


def _status_detail(value: object) -> str:
    """Serialize a status attribute without parsing the exception message."""

    normalized = getattr(value, "value", value)
    return normalized if isinstance(normalized, str) else str(normalized)


def _wrap_controlled_failure(
    exc: Exception,
    *,
    backend: str,
    run_index: int,
    diagnostics: _LifecycleDiagnosticContext,
) -> ControlledAcceptanceError:
    details: dict[str, object] = {
        "backend": backend,
        "run_index": run_index,
        "exception_type": type(exc).__name__,
    }
    if (
        isinstance(exc, InvalidStatusTransitionError)
        and diagnostics.lifecycle_action in CONTROLLED_REVIEW_LIFECYCLE_ACTIONS
    ):
        details.update(
            {
                "lifecycle_action": diagnostics.lifecycle_action,
                "report_status_after_generate_revision": (
                    diagnostics.report_status_after_generate_revision
                ),
                "quality_blockers_after_generate_revision": (
                    diagnostics.quality_blockers_after_generate_revision or []
                ),
                "invalid_from_status": _status_detail(exc.from_status),
                "invalid_to_status": _status_detail(exc.to_status),
            }
        )
    return ControlledAcceptanceError(
        "CONTROLLED_ACCEPTANCE_FAILED",
        "controlled acceptance production path failed",
        **details,
    )


def _require(condition: bool, code: str, message: str, **details: object) -> None:
    if not condition:
        raise ControlledAcceptanceError(code, message, **details)


def _as_bool(value: object, *, stage: str) -> bool:
    _require(
        type(value) is bool,
        "STAGE_REVIEW_BOOLEAN_INVALID",
        "producer requires_review must be a real boolean",
        stage=stage,
        observed_type=type(value).__name__,
    )
    return bool(value)


def validate_trusted_operator(operator: str) -> str:
    """Validate the explicit operator seam; never infer it from CI identity."""

    value = operator.strip()
    _require(bool(value), "TRUSTED_OPERATOR_MISSING", "trusted operator is required")
    _require(
        value.lower() not in REJECTED_OPERATOR_NAMES,
        "TRUSTED_OPERATOR_NOT_HUMAN",
        "system/api/background/llm actors are not controlled human proof",
        operator=value,
    )
    return value


def validate_execution_source_identity(
    source_sha: str,
    source_tree_sha: str,
) -> tuple[str, str]:
    """Require the workflow/runner to provide the actual executing checkout."""

    _require(
        isinstance(source_sha, str) and bool(source_sha.strip()),
        "EXECUTION_SOURCE_SHA_MISSING",
        "controlled execution source commit must be supplied explicitly",
    )
    _require(
        isinstance(source_tree_sha, str) and bool(source_tree_sha.strip()),
        "EXECUTION_SOURCE_TREE_SHA_MISSING",
        "controlled execution source tree must be supplied explicitly",
    )
    return source_sha, source_tree_sha


def _source_definition_from_mapping(raw: Mapping[str, object]) -> ControlledSourceDefinition:
    stage_order_raw = raw.get("stage_order")
    vector_raw = raw.get("expected_requires_review")
    source_input = raw.get("input")
    _require(
        isinstance(stage_order_raw, list),
        "SOURCE_DEFINITION_INVALID",
        "stage_order must be a JSON list",
    )
    _require(
        isinstance(vector_raw, Mapping),
        "SOURCE_DEFINITION_INVALID",
        "expected_requires_review must be a JSON object",
    )
    _require(
        isinstance(source_input, Mapping),
        "SOURCE_DEFINITION_INVALID",
        "input must be a JSON object",
    )
    stage_order_values = cast(list[object], stage_order_raw)
    vector_mapping = cast(Mapping[str, object], vector_raw)
    source_input_mapping = cast(Mapping[str, object], source_input)
    stage_order = tuple(str(value) for value in stage_order_values)
    _require(
        stage_order == STAGE_ORDER,
        "SOURCE_STAGE_ORDER_MISMATCH",
        "controlled source stage order is not the frozen order",
        observed=list(stage_order),
        expected=list(STAGE_ORDER),
    )
    vector = tuple(_as_bool(vector_mapping.get(stage), stage=stage) for stage in STAGE_ORDER)
    _require(
        vector == EXPECTED_REVIEW_VECTOR,
        "SOURCE_REVIEW_VECTOR_MISMATCH",
        "controlled source review vector is not the accepted vector",
        observed=list(vector),
        expected=list(EXPECTED_REVIEW_VECTOR),
    )
    return ControlledSourceDefinition(
        schema_version=str(raw.get("schema_version", "")),
        source_label=str(raw.get("source_label", "")),
        source_candidate_path=str(raw.get("source_candidate_path", "")),
        canonical_input_sha256=str(raw.get("canonical_input_sha256", "")),
        stage_order=stage_order,
        expected_requires_review=vector,
        input=source_input_mapping,
    )


def load_source_definition(
    path: str | Path,
    *,
    expected_source_candidate_path: str,
) -> ControlledSourceDefinition:
    """Load and hash the fixture with the production canonicalizer."""

    source_path = Path(path)
    try:
        raw_value = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlledAcceptanceError(
            "SOURCE_DEFINITION_UNREADABLE",
            "controlled source definition could not be loaded",
            path=str(source_path),
        ) from exc
    _require(
        isinstance(raw_value, Mapping),
        "SOURCE_DEFINITION_INVALID",
        "controlled source definition must be a JSON object",
    )
    source = _source_definition_from_mapping(raw_value)
    _require(
        source.schema_version == SOURCE_SCHEMA_VERSION,
        "SOURCE_SCHEMA_VERSION_MISMATCH",
        "controlled source schema version is not accepted",
        observed=source.schema_version,
    )
    _require(
        source.source_label == "high_throughput_review",
        "SOURCE_LABEL_MISMATCH",
        "source label is not the frozen high-throughput scenario",
    )
    _require(
        source.source_candidate_path == expected_source_candidate_path,
        "SOURCE_CANDIDATE_MISMATCH",
        "source candidate is not the accepted production snapshot",
        observed=source.source_candidate_path,
        expected=expected_source_candidate_path,
    )
    actual_hash = hashlib.sha256(canonical_json_bytes(source.input)).hexdigest()
    _require(
        actual_hash == source.canonical_input_sha256 == CANONICAL_INPUT_SHA256,
        "SOURCE_HASH_MISMATCH",
        "controlled source canonical input hash is not accepted",
        declared=source.canonical_input_sha256,
        actual=actual_hash,
        expected=CANONICAL_INPUT_SHA256,
    )
    return source


def verify_authoritative_source_definition(
    source: ControlledSourceDefinition,
    *,
    authoritative_snapshot: Mapping[str, object],
    expected_source_candidate_path: str,
) -> None:
    """Bind the JSON fixture to the accepted production source snapshot."""

    _require(
        source.source_candidate_path == expected_source_candidate_path,
        "SOURCE_CANDIDATE_MISMATCH",
        "source candidate is not the accepted production snapshot",
        observed=source.source_candidate_path,
        expected=expected_source_candidate_path,
    )

    authoritative_hash = hashlib.sha256(canonical_json_bytes(authoritative_snapshot)).hexdigest()
    _require(
        authoritative_hash == CANONICAL_INPUT_SHA256,
        "AUTHORITATIVE_SOURCE_DRIFT",
        "the read-only production source snapshot changed its accepted hash",
        actual=authoritative_hash,
        expected=CANONICAL_INPUT_SHA256,
    )
    _require(
        source.input == authoritative_snapshot,
        "SOURCE_FIXTURE_NOT_BOUND",
        "controlled source JSON does not equal the accepted production snapshot",
    )


def _record_value(record: object, field_name: str) -> object:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _record_warnings(record: object) -> list[object]:
    warnings = _record_value(record, "warnings")
    if warnings is None:
        return []
    _require(
        isinstance(warnings, list),
        "PRODUCER_WARNINGS_INVALID",
        "persisted producer warnings must be a JSON list",
    )
    return list(cast(list[object], warnings))


def _reason_from_warning(*, warning: object, stage: str, source_id: str) -> ReviewReason:
    _require(
        isinstance(warning, Mapping),
        "PRODUCER_WARNING_INVALID",
        "producer warning must be a structured mapping",
        stage=stage,
    )
    warning_mapping = cast(Mapping[str, object], warning)
    code = warning_mapping.get("code")
    message = warning_mapping.get("message")
    _require(
        isinstance(code, str) and bool(code),
        "PRODUCER_WARNING_INVALID",
        "producer warning code must be a non-empty string",
        stage=stage,
    )
    _require(
        isinstance(message, str) and bool(message),
        "PRODUCER_WARNING_INVALID",
        "producer warning message must be a non-empty string",
        stage=stage,
    )
    return ReviewReason(
        code=cast(str, code),
        message=cast(str, message),
        stage=stage,
        source_type="calculation_run",
        source_id=source_id,
    )


def project_source_warnings(stage_records: Mapping[str, object]) -> tuple[ReviewReason, ...]:
    """Project producer warnings using persisted booleans as the authority.

    Warning presence never sets ``requires_review``.  It only supplies the
    source evidence for a stage whose persisted producer boolean is already
    true.  Exact five-field duplicates retain their first occurrence.
    """

    result: list[ReviewReason] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for stage in STAGE_ORDER:
        record = stage_records.get(stage)
        _require(
            record is not None,
            "CALCULATION_RUN_MISSING",
            "stage CalculationRun is missing",
            stage=stage,
        )
        requires_review = _as_bool(_record_value(record, "requires_review"), stage=stage)
        source_id = _record_value(record, "id")
        _require(
            isinstance(source_id, str) and bool(source_id),
            "CALCULATION_RUN_ID_MISSING",
            "stage CalculationRun id is missing",
            stage=stage,
        )
        if not requires_review:
            continue
        warnings = _record_warnings(record)
        _require(
            bool(warnings),
            "REVIEW_REASON_SOURCE_MISSING",
            "review-required stage has no producer warning source",
            stage=stage,
            source_id=source_id,
        )
        source_id_value = cast(str, source_id)
        for warning in warnings:
            reason = _reason_from_warning(
                warning=warning,
                stage=stage,
                source_id=source_id_value,
            )
            key = (
                reason.code,
                reason.message,
                reason.stage,
                reason.source_type,
                reason.source_id,
            )
            if key not in seen:
                seen.add(key)
                result.append(reason)
    return tuple(result)


def _authority_snapshot(authority: object) -> Mapping[str, object]:
    to_snapshot = getattr(authority, "to_snapshot", None)
    _require(
        callable(to_snapshot),
        "SCHEME_AUTHORITY_UNTYPED",
        "Scheme authority has no typed snapshot",
    )
    snapshot = cast(Callable[[], object], to_snapshot)()
    _require(
        isinstance(snapshot, Mapping),
        "SCHEME_AUTHORITY_UNTYPED",
        "Scheme authority snapshot is not a mapping",
    )
    return cast(Mapping[str, object], snapshot)


def validate_review_reason_continuity(
    *,
    authority: object,
    stage_records: Mapping[str, object],
    expected_vector: Mapping[str, bool] | None = None,
) -> tuple[ReviewReason, ...]:
    """Validate the complete persisted CalculationRun -> SchemeRun chain."""

    vector = expected_vector or dict(zip(STAGE_ORDER, EXPECTED_REVIEW_VECTOR, strict=True))
    observed: dict[str, bool] = {}
    calculation_ids: dict[str, str] = {}
    for stage in STAGE_ORDER:
        record = stage_records.get(stage)
        _require(
            record is not None,
            "CALCULATION_RUN_MISSING",
            "stage CalculationRun is missing",
            stage=stage,
        )
        observed[stage] = _as_bool(_record_value(record, "requires_review"), stage=stage)
        source_id = _record_value(record, "id")
        _require(
            isinstance(source_id, str) and bool(source_id),
            "CALCULATION_RUN_ID_MISSING",
            "stage CalculationRun id is missing",
            stage=stage,
        )
        calculation_ids[stage] = cast(str, source_id)
    _require(
        observed == dict(vector),
        "REVIEW_VECTOR_MISMATCH",
        "persisted CalculationRun review vector does not match the source",
        observed=observed,
        expected=dict(vector),
    )
    authority_requires_review = _authority_snapshot(authority).get("requires_review")
    authority_requires_review = _as_bool(authority_requires_review, stage="aggregate")
    _require(
        authority_requires_review == any(observed.values()),
        "REVIEW_VECTOR_AGGREGATE_MISMATCH",
        "aggregate SchemeRun review boolean does not equal stage vector",
        aggregate=authority_requires_review,
        stage_vector=observed,
    )

    expected_reasons = project_source_warnings(stage_records)
    raw_reasons = getattr(authority, "review_reasons", None)
    _require(
        isinstance(raw_reasons, tuple),
        "SCHEME_REASONS_UNTYPED",
        "Scheme authority reasons must be an immutable typed tuple",
    )
    typed_reasons: list[ReviewReason] = []
    for raw_reason in cast(tuple[object, ...], raw_reasons):
        _require(
            isinstance(raw_reason, ReviewReason),
            "SCHEME_REASON_UNTYPED",
            "Scheme authority contains a non-canonical ReviewReason",
        )
        typed_reasons.append(cast(ReviewReason, raw_reason))
    reasons = tuple(typed_reasons)
    for reason in reasons:
        _require(
            reason.stage in STAGE_ORDER,
            "SCHEME_REASON_STAGE_INVALID",
            "ReviewReason stage is outside the frozen stage set",
            stage=reason.stage,
        )
        _require(
            reason.source_type == "calculation_run",
            "SCHEME_REASON_SOURCE_TYPE_INVALID",
            "ReviewReason source_type is not calculation_run",
            stage=reason.stage,
        )
        _require(
            reason.source_id == calculation_ids[reason.stage],
            "SCHEME_REASON_SOURCE_ID_MISMATCH",
            "ReviewReason source_id is not the stage CalculationRun id",
            stage=reason.stage,
            observed=reason.source_id,
            expected=calculation_ids[reason.stage],
        )
        _require(
            observed[reason.stage],
            "FALSE_STAGE_REASON_PRESENT",
            "a false review stage cannot project a canonical ReviewReason",
            stage=reason.stage,
        )
    _require(
        tuple(reason.to_json() for reason in reasons)
        == tuple(reason.to_json() for reason in expected_reasons),
        "SCHEME_REASON_SET_MISMATCH",
        "persisted SchemeRun reasons differ from producer warning evidence",
    )
    for stage, requires_review in observed.items():
        count = sum(1 for reason in reasons if reason.stage == stage)
        _require(
            (count >= 1) if requires_review else (count == 0),
            "SCHEME_REASON_CARDINALITY_INVALID",
            "ReviewReason cardinality does not match the persisted stage boolean",
            stage=stage,
            requires_review=requires_review,
            count=count,
        )
    return reasons


def _load_stage_records(session: Any, authority: object) -> dict[str, object]:
    from sqlalchemy import select

    from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

    ids = {stage: getattr(authority, f"{stage}_calculation_id", "") for stage in STAGE_ORDER}
    rows = session.scalars(
        select(CalculationRunRecord).where(CalculationRunRecord.id.in_(list(ids.values())))
    ).all()
    by_id = {str(row.id): row for row in rows}
    records: dict[str, object] = {}
    for stage, calculation_id in ids.items():
        _require(
            isinstance(calculation_id, str) and bool(calculation_id),
            "SOURCE_BINDING_ID_MISSING",
            "Scheme authority is missing a stage CalculationRun id",
            stage=stage,
        )
        row = by_id.get(calculation_id)
        _require(
            row is not None,
            "CALCULATION_RUN_MISSING",
            "referenced CalculationRun is absent",
            stage=stage,
        )
        row_value = cast(Any, row)
        _require(
            row_value.calculation_type == stage,
            "CALCULATION_RUN_STAGE_MISMATCH",
            "CalculationRun calculation_type does not match its slot",
            stage=stage,
        )
        records[stage] = row_value
    return records


def _verify_persisted_authority(
    *,
    session: Any,
    authority: object,
    canonical_persistence: Mapping[str, object],
) -> tuple[dict[str, object], tuple[ReviewReason, ...]]:
    records = _load_stage_records(session, authority)
    reasons = validate_review_reason_continuity(
        authority=authority,
        stage_records=records,
    )
    binding = canonical_persistence.get("source_binding")
    _require(
        isinstance(binding, Mapping),
        "SOURCE_BINDING_MISSING",
        "canonical SourceBinding evidence is missing",
    )
    binding_mapping = cast(Mapping[str, object], binding)
    _require(
        binding_mapping.get("source_binding_id") == getattr(authority, "source_binding_id", None),
        "SOURCE_BINDING_ID_MISMATCH",
        "SchemeRun and SourceBinding identities differ",
    )
    _require(
        binding_mapping.get("content_sha256") == getattr(authority, "combined_source_hash", None),
        "SOURCE_BINDING_HASH_MISMATCH",
        "SchemeRun and SourceBinding combined hashes differ",
    )
    required_slot_ids = binding_mapping.get("required_slot_ids")
    _require(
        isinstance(required_slot_ids, list) and len(required_slot_ids) == len(STAGE_ORDER),
        "SOURCE_BINDING_SLOTS_INVALID",
        "SourceBinding required slot ids are not a complete stage list",
    )
    slot_ids = cast(list[object], required_slot_ids)
    persisted_hashes = binding_mapping.get("per_calculation_result_hashes")
    _require(
        isinstance(persisted_hashes, Mapping),
        "SOURCE_BINDING_HASHES_INVALID",
        "SourceBinding result hashes are not a mapping",
    )
    persisted_hash_mapping = cast(Mapping[str, object], persisted_hashes)
    for stage in STAGE_ORDER:
        persisted_id = slot_ids[STAGE_ORDER.index(stage)]
        authority_id = getattr(authority, f"{stage}_calculation_id", None)
        _require(
            persisted_id == authority_id,
            "SOURCE_BINDING_CALCULATION_ID_MISMATCH",
            "SourceBinding slot does not reference the authoritative CalculationRun",
            stage=stage,
        )
        _require(
            persisted_hash_mapping.get(stage) == getattr(authority, f"{stage}_result_hash", None),
            "SOURCE_BINDING_RESULT_HASH_MISMATCH",
            "SourceBinding result hash does not match SchemeRun authority",
            stage=stage,
        )
    return records, reasons


def normalized_business_projection(evidence: Mapping[str, object]) -> dict[str, object]:
    """Remove runtime IDs while retaining all business authority semantics."""

    source = evidence.get("source")
    _require(
        isinstance(source, Mapping),
        "EVIDENCE_SOURCE_MISSING",
        "evidence has no source projection",
    )
    source_mapping = cast(Mapping[str, object], source)
    review = evidence.get("review")
    _require(
        isinstance(review, Mapping),
        "EVIDENCE_REVIEW_MISSING",
        "evidence has no review projection",
    )
    review_mapping = cast(Mapping[str, object], review)
    reasons = review_mapping.get("reasons", [])
    normalized_reasons: list[dict[str, object]] = []
    _require(
        isinstance(reasons, list),
        "EVIDENCE_REASONS_INVALID",
        "evidence reasons must be a list",
    )
    for reason in cast(list[object], reasons):
        _require(isinstance(reason, Mapping), "EVIDENCE_REASON_INVALID", "reason is not an object")
        reason_mapping = cast(Mapping[str, object], reason)
        normalized_reasons.append(
            {
                "code": reason_mapping.get("code"),
                "message": reason_mapping.get("message"),
                "stage": reason_mapping.get("stage"),
                "source_type": reason_mapping.get("source_type"),
                "source_id": f"<calculation:{reason_mapping.get('stage')}>",
            }
        )
    authority = review_mapping.get("authority")
    authority_mapping = (
        cast(Mapping[str, object], authority) if isinstance(authority, Mapping) else {}
    )
    calculation_result_hashes = {
        stage: authority_mapping.get(f"{stage}_result_hash") for stage in STAGE_ORDER
    }
    projection: dict[str, object] = {
        "source": {
            "source_candidate_path": source_mapping.get("source_candidate_path"),
            "canonical_input_sha256": source_mapping.get("canonical_input_sha256"),
        },
        "stage_order": list(cast(list[object], review_mapping.get("stage_order", []))),
        "requires_review_vector": list(
            cast(list[object], review_mapping.get("requires_review_vector", []))
        ),
        "reasons": normalized_reasons,
        "recommended_scheme_code": authority_mapping.get("recommended_scheme_code"),
        "calculation_result_hashes": calculation_result_hashes,
        # These hashes bind runtime identities by contract.  Preserve their
        # presence in each raw run, but do not compare their raw values across
        # independent databases where those identities are intentionally new.
        "combined_source_hash_present": bool(review_mapping.get("combined_source_hash")),
        "scheme_result_hash_present": bool(review_mapping.get("scheme_result_hash")),
        "scheme_review_authority_hash_present": bool(
            review_mapping.get("scheme_review_authority_hash")
        ),
        "status": review_mapping.get("status"),
    }
    artifacts = evidence.get("artifacts")
    if isinstance(artifacts, Mapping):
        projection["artifact_semantics"] = {
            key: {
                "approved_content_hash": value.get("approved_content_hash"),
                "locale": value.get("locale"),
                "format": value.get("format"),
                "status": value.get("status"),
                "template_version": value.get("template_version"),
                "template_content_hash": value.get("template_content_hash"),
                "template_locale": value.get("template_locale"),
                "translation_catalog_version": value.get("translation_catalog_version"),
                "translation_catalog_content_hash": value.get("translation_catalog_content_hash"),
                "localized_template_content_hash": value.get("localized_template_content_hash"),
            }
            for key, value in artifacts.items()
            if isinstance(value, Mapping)
        }
    return projection


def compare_normalized_evidence(
    evidence_items: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Compare independent backend/run evidence without comparing raw UUIDs."""

    _require(
        len(evidence_items) >= 2,
        "PARITY_INPUT_TOO_SMALL",
        "at least two independent runs are required for parity",
    )
    projections = {
        key: normalized_business_projection(value) for key, value in evidence_items.items()
    }
    labels = list(projections)
    baseline = projections[labels[0]]
    mismatches: dict[str, list[str]] = {}
    for label in labels[1:]:
        if projections[label] != baseline:
            mismatches[label] = ["normalized business projection differs from baseline"]
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "baseline": labels[0],
        "compared_runs": labels,
        "mismatches": mismatches,
        "projections": projections,
    }


def verify_artifact_matrix(
    artifacts: Mapping[str, object],
    *,
    read_bytes: Callable[[str], bytes],
    report_id: str,
    report_revision_id: str,
    approved_revision_id: str,
    approved_content_hash: str,
) -> dict[str, ArtifactObservation]:
    """Read each formal artifact and verify its complete persisted lineage."""

    expected_keys = {f"{locale}/{fmt}" for locale, fmt in FORMAL_ARTIFACT_MATRIX}
    _require(
        set(artifacts) == expected_keys,
        "FORMAL_ARTIFACT_MATRIX_INCOMPLETE",
        "formal acceptance requires exactly four locale/format artifacts",
        observed=sorted(artifacts),
    )
    observations: dict[str, ArtifactObservation] = {}
    shared: tuple[str, str, str, str] | None = None
    seen_artifact_ids: set[str] = set()
    seen_storage_keys: set[str] = set()
    for key in sorted(artifacts):
        artifact = artifacts[key]
        expected_locale, expected_format = key.split("/", 1)
        artifact_id = getattr(artifact, "id", "")
        storage_key = getattr(artifact, "storage_key", "")
        declared_hash = getattr(artifact, "file_sha256", "")
        _require(bool(artifact_id), "ARTIFACT_ID_MISSING", "formal artifact id is missing", key=key)
        _require(
            isinstance(artifact_id, str),
            "ARTIFACT_ID_INVALID",
            "formal artifact id must be a string",
            key=key,
        )
        _require(
            isinstance(storage_key, str) and bool(storage_key),
            "ARTIFACT_STORAGE_KEY_MISSING",
            "formal artifact storage key is missing",
            key=key,
        )
        _require(
            isinstance(declared_hash, str) and bool(declared_hash),
            "ARTIFACT_FILE_HASH_MISSING",
            "formal artifact file hash is missing",
            key=key,
        )
        _require(
            artifact_id not in seen_artifact_ids,
            "ARTIFACT_ID_DUPLICATE",
            "formal artifact ids must be unique across the matrix",
            key=key,
            artifact_id=artifact_id,
        )
        _require(
            storage_key not in seen_storage_keys,
            "ARTIFACT_STORAGE_KEY_DUPLICATE",
            "formal artifact storage keys must be unique across the matrix",
            key=key,
            storage_key=storage_key,
        )
        seen_artifact_ids.add(artifact_id)
        seen_storage_keys.add(storage_key)
        file_bytes = read_bytes(storage_key)
        observed_hash = hashlib.sha256(file_bytes).hexdigest()
        locale = getattr(
            getattr(artifact, "locale", None), "value", getattr(artifact, "locale", "")
        )
        fmt = getattr(getattr(artifact, "format", None), "value", getattr(artifact, "format", ""))
        locale = locale if isinstance(locale, str) else ""
        fmt = fmt if isinstance(fmt, str) else ""
        _require(
            locale == expected_locale and fmt == expected_format,
            "ARTIFACT_LABEL_MISMATCH",
            "formal artifact metadata does not match its matrix label",
            key=key,
            observed=f"{locale}/{fmt}",
        )
        report_id_value = getattr(artifact, "report_id", "")
        report_revision_id_value = getattr(artifact, "report_revision_id", "")
        source_content_hash = getattr(artifact, "source_content_hash", "")
        template_id = getattr(artifact, "template_id", "")
        template_version = getattr(artifact, "template_version", "")
        template_locale = getattr(
            getattr(artifact, "template_locale", None),
            "value",
            getattr(artifact, "template_locale", ""),
        )
        catalog_version = getattr(artifact, "translation_catalog_version", "")
        catalog_hash = getattr(artifact, "translation_catalog_content_hash", "")
        localized_template_hash = getattr(artifact, "localized_template_content_hash", "")
        manifest = getattr(artifact, "render_manifest_json", None)
        _require(
            isinstance(manifest, Mapping),
            "ARTIFACT_TEMPLATE_LINEAGE_MISSING",
            "formal artifact render manifest is missing",
            key=key,
        )
        manifest_mapping = cast(Mapping[str, object], manifest)
        template_content_hash = manifest_mapping.get("template_content_hash")
        _require(
            isinstance(report_id_value, str) and bool(report_id_value),
            "ARTIFACT_REPORT_ID_MISSING",
            "formal artifact report id is missing",
            key=key,
        )
        _require(
            isinstance(report_revision_id_value, str) and bool(report_revision_id_value),
            "ARTIFACT_REVISION_ID_MISSING",
            "formal artifact revision id is missing",
            key=key,
        )
        for field_name, field_value in (
            ("source_content_hash", source_content_hash),
            ("template_id", template_id),
            ("template_version", template_version),
            ("template_content_hash", template_content_hash),
            ("template_locale", template_locale),
            ("translation_catalog_version", catalog_version),
            ("translation_catalog_content_hash", catalog_hash),
            ("localized_template_content_hash", localized_template_hash),
        ):
            _require(
                isinstance(field_value, str) and bool(field_value),
                "ARTIFACT_TEMPLATE_LINEAGE_MISSING",
                "formal artifact template/catalog lineage is incomplete",
                key=key,
                field=field_name,
            )
        template_content_hash = cast(str, template_content_hash)
        template_id = cast(str, template_id)
        template_version = cast(str, template_version)
        template_locale = cast(str, template_locale)
        catalog_version = cast(str, catalog_version)
        catalog_hash = cast(str, catalog_hash)
        localized_template_hash = cast(str, localized_template_hash)
        _require(
            template_locale == locale,
            "ARTIFACT_TEMPLATE_LOCALE_MISMATCH",
            "formal artifact template locale differs from artifact locale",
            key=key,
        )
        _require(
            manifest_mapping.get("template_id") == template_id
            and manifest_mapping.get("template_version") == template_version
            and manifest_mapping.get("template_content_hash") == template_content_hash
            and manifest_mapping.get("source_content_hash") == source_content_hash
            and manifest_mapping.get("approved_revision_id") == approved_revision_id
            and manifest_mapping.get("approved_content_hash") == approved_content_hash
            and manifest_mapping.get("render_mode") == "formal"
            and manifest_mapping.get("locale") == locale
            and manifest_mapping.get("translation_catalog_version") == catalog_version
            and manifest_mapping.get("translation_catalog_content_hash") == catalog_hash
            and manifest_mapping.get("localized_template_content_hash") == localized_template_hash,
            "ARTIFACT_FORMAL_LINEAGE_MISMATCH",
            "formal artifact manifest does not match persisted template/catalog/approval lineage",
            key=key,
        )
        observation = ArtifactObservation(
            artifact_id=artifact_id,
            report_id=report_id_value,
            report_revision_id=report_revision_id_value,
            approved_revision_id=approved_revision_id,
            approved_content_hash=source_content_hash,
            locale=locale,
            format=fmt,
            status=str(
                getattr(getattr(artifact, "status", None), "value", getattr(artifact, "status", ""))
            ),
            file_sha256=declared_hash,
            observed_file_sha256=observed_hash,
            file_size_bytes=int(getattr(artifact, "file_size_bytes", 0)),
            storage_key=storage_key,
            template_id=template_id,
            template_version=template_version,
            template_content_hash=template_content_hash,
            template_locale=template_locale,
            translation_catalog_version=catalog_version,
            translation_catalog_content_hash=catalog_hash,
            localized_template_content_hash=localized_template_hash,
        )
        _require(bool(file_bytes), "ARTIFACT_EMPTY", "formal artifact file is empty", key=key)
        _require(
            observation.status == "completed",
            "ARTIFACT_NOT_COMPLETED",
            "formal artifact is not completed",
            key=key,
        )
        _require(
            observation.report_id == report_id
            and observation.report_revision_id == report_revision_id,
            "ARTIFACT_LINEAGE_MISMATCH",
            "formal artifact is bound to the wrong report revision",
            key=key,
        )
        _require(
            observation.approved_revision_id == report_revision_id
            and approved_revision_id == report_revision_id,
            "ARTIFACT_APPROVED_REVISION_MISMATCH",
            "formal artifact is not bound to the approved revision",
            key=key,
        )
        _require(
            observation.approved_content_hash == approved_content_hash,
            "ARTIFACT_CONTENT_HASH_MISMATCH",
            "formal artifact source content hash is not the approved hash",
            key=key,
        )
        _require(
            declared_hash == observed_hash,
            "ARTIFACT_FILE_HASH_MISMATCH",
            "persisted artifact file hash differs from downloaded bytes",
            key=key,
        )
        _require(
            observation.file_size_bytes == len(file_bytes),
            "ARTIFACT_FILE_SIZE_MISMATCH",
            "persisted artifact file size differs from downloaded bytes",
            key=key,
        )
        identity = (
            observation.report_id,
            observation.report_revision_id,
            observation.approved_content_hash,
            observation.status,
        )
        if shared is None:
            shared = identity
        _require(
            identity == shared,
            "ARTIFACT_SHARED_IDENTITY_MISMATCH",
            "formal artifacts do not share the approved revision identity",
            key=key,
        )
        observations[key] = observation
    return observations


def _redact_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{host}{port}{path}"


def _configure_database_environment(database_url: str) -> None:
    os.environ["COLD_STORAGE_DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = (
        "postgresql" if database_url.startswith("postgres") else "sqlite"
    )
    if database_url.startswith("sqlite"):
        parsed = urlsplit(database_url)
        if parsed.path:
            os.environ["COLD_STORAGE_SQLITE_PATH"] = parsed.path


def _persisted_calculation_query(session_factory: Callable[[], Any]) -> object:
    """Create a read-only calculation projection for the report provider."""

    from sqlalchemy import select

    from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

    class PersistedSection:
        def __init__(self, row: Any) -> None:
            self.id = str(row.id)
            self.calculator_name = str(row.calculator_name or "")
            self.calculator_version = str(row.calculator_version or "1.0.0")
            self.result = row.result_snapshot or {}
            self.content_hash = row.result_hash
            self.tool_call_status = None

    class PersistedResult:
        def __init__(self, rows: Mapping[str, Any]) -> None:
            self.throughput_result = PersistedSection(rows["zone"])
            self.cooling_load_result = PersistedSection(rows["cooling_load"])
            self.equipment_result = PersistedSection(rows["equipment"])
            self.power_result = PersistedSection(rows["power"])

    class PersistedCalculationQuery:
        def get_orchestrated_result(self, project_id: str, version_id: str) -> object | None:
            with session_factory() as session:
                rows = {
                    str(row.calculation_type): row
                    for row in session.scalars(
                        select(CalculationRunRecord).where(
                            CalculationRunRecord.project_id == project_id,
                            CalculationRunRecord.project_version_id == version_id,
                        )
                    ).all()
                }
            required = {"cooling_load", "equipment", "power"}
            if not required.issubset(rows):
                return None
            return PersistedResult(rows)

    return PersistedCalculationQuery()


def _artifact_matrix_label(artifact: object) -> str:
    locale = getattr(getattr(artifact, "locale", None), "value", getattr(artifact, "locale", ""))
    fmt = getattr(getattr(artifact, "format", None), "value", getattr(artifact, "format", ""))
    _require(
        isinstance(locale, str) and isinstance(fmt, str) and bool(locale) and bool(fmt),
        "ARTIFACT_LABEL_INVALID",
        "formal artifact locale/format label is incomplete",
    )
    return f"{locale}/{fmt}"


def _index_artifacts_for_matrix(artifacts: Sequence[object]) -> dict[str, object]:
    indexed: dict[str, object] = {}
    for artifact in artifacts:
        label = _artifact_matrix_label(artifact)
        _require(
            label not in indexed,
            "ARTIFACT_LABEL_DUPLICATE",
            "formal artifact matrix contains duplicate locale/format labels",
            label=label,
        )
        indexed[label] = artifact
    return indexed


def _run_report_lifecycle(
    *,
    engine: Any,
    project_id: str,
    project_version_id: str,
    operator: str,
    output_root: Path,
    diagnostics: _LifecycleDiagnosticContext,
) -> dict[str, object]:
    """Run the existing report lifecycle and independently verify artifacts."""

    from sqlalchemy.orm import sessionmaker

    from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
    from cold_storage.modules.reports.application.assembler import ReportAssembler
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderService,
        ReportRenderUnitOfWork,
    )
    from cold_storage.modules.reports.application.service import (
        ReportService,
        _default_trusted_operator,
    )
    from cold_storage.modules.reports.domain.enums import ReportLocale, ReportType
    from cold_storage.modules.reports.infrastructure.artifact_storage import ReportArtifactStorage
    from cold_storage.modules.reports.infrastructure.real_data_provider import (
        RealReportDataProvider,
    )
    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.reports.infrastructure.template_seed import seed_default_templates
    from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        report_repo = SQLReportRepository(session)
        scheme_query = build_sqlalchemy_scheme_query(session)
        provider = RealReportDataProvider(
            project_service=DatabaseProjectService(engine),
            calculation_service=_persisted_calculation_query(session_factory),
            scheme_query=scheme_query,
        )
        assembler = ReportAssembler(data_provider=provider)
        report_service = ReportService(
            repository=report_repo,
            assembler=assembler,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )
        storage = ReportArtifactStorage(base_dir=str(output_root))
        render_uow = ReportRenderUnitOfWork(
            session,
            report_repo=report_repo,
            artifact_repo=report_repo,
            session_factory=session_factory,
        )
        render_service = ReportRenderService(
            uow=render_uow,
            storage=storage,
            template_repo=report_repo,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )
        seed_default_templates(report_repo)
        report_repo.commit()
        report = report_service.create_report(
            project_id=project_id,
            project_version_id=project_version_id,
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor=operator,
        )
        revision = report_service.generate_revision(report.id, operator)
        _capture_post_generation_diagnostics(
            report_service,
            report.id,
            operator,
            revision,
            diagnostics,
        )
        _invoke_review_lifecycle_action(
            report_service,
            report.id,
            operator,
            "submit_review",
            diagnostics,
        )
        _invoke_review_lifecycle_action(
            report_service,
            report.id,
            operator,
            "mark_reviewed",
            diagnostics,
        )
        approved = _invoke_review_lifecycle_action(
            report_service,
            report.id,
            operator,
            "approve",
            diagnostics,
        )
        artifacts: dict[str, object] = {}
        for locale_value, format_value in FORMAL_ARTIFACT_MATRIX:
            locale = ReportLocale(locale_value)
            artifact = render_service.render(
                report_id=report.id,
                revision_number=revision.revision_number,
                format=format_value,
                template_version=None,
                mode="formal",
                actor=operator,
                locale=locale,
            )
            artifacts[f"{locale_value}/{format_value}"] = render_service.verify_download(
                report.id, artifact.id, operator
            )
        report_id = approved.id
        revision_id = revision.id
        approved_revision_id = str(approved.approved_revision_id or "")
        approved_content_hash = revision.content_hash
        _require(
            approved_revision_id == revision_id
            and approved.approved_content_hash == approved_content_hash,
            "APPROVAL_IDENTITY_MISMATCH",
            "approval does not bind the exact rendered revision and content hash",
        )
        observations = verify_artifact_matrix(
            artifacts,
            read_bytes=storage.get,
            report_id=report_id,
            report_revision_id=revision_id,
            approved_revision_id=approved_revision_id,
            approved_content_hash=approved_content_hash,
        )
        actions = report_repo.list_review_actions(report_id)

    # Recreate every reader after the write session is closed.
    with session_factory() as fresh_session:
        fresh_repo = SQLReportRepository(fresh_session)
        fresh_report = fresh_repo.get_report(report_id)
        fresh_revision = fresh_repo.get_revision(report_id, revision.revision_number)
        fresh_actions = fresh_repo.list_review_actions(report_id)
        fresh_query = build_sqlalchemy_scheme_query(fresh_session)
        fresh_authority = fresh_query.get_review_authority(project_id, project_version_id)
    _require(
        fresh_report is not None, "FRESH_SESSION_REPORT_MISSING", "report disappeared after restart"
    )
    assert fresh_report is not None
    _require(
        fresh_revision is not None and fresh_revision.id == revision_id,
        "FRESH_SESSION_REVISION_MISSING",
        "approved revision disappeared after restart",
    )
    _require(
        fresh_report.status.value == "approved"
        and fresh_report.approved_revision_id == approved_revision_id
        and fresh_report.approved_content_hash == approved_content_hash,
        "FRESH_SESSION_APPROVAL_MISMATCH",
        "approval identity changed or disappeared after restart",
    )
    fresh_artifact_map = _index_artifacts_for_matrix(fresh_repo.list_artifacts(report_id))
    fresh_observations = verify_artifact_matrix(
        fresh_artifact_map,
        read_bytes=storage.get,
        report_id=report_id,
        report_revision_id=revision_id,
        approved_revision_id=approved_revision_id,
        approved_content_hash=approved_content_hash,
    )
    _require(
        {key: observation.to_json() for key, observation in fresh_observations.items()}
        == {key: observation.to_json() for key, observation in observations.items()},
        "FRESH_SESSION_ARTIFACT_MISMATCH",
        "formal artifact metadata changed after restart",
    )
    _require(
        len(fresh_actions) == len(actions)
        and any(action.action.value == "mark_reviewed" for action in fresh_actions),
        "FRESH_SESSION_REVIEW_ACTION_MISSING",
        "persisted mark_reviewed proof was not visible in a fresh session",
    )
    _require(
        fresh_authority is not None,
        "FRESH_SESSION_AUTHORITY_MISSING",
        "Scheme authority disappeared",
    )
    mark_reviewed_actions = [
        action for action in fresh_actions if action.action.value == "mark_reviewed"
    ]
    approval_actions = [action for action in fresh_actions if action.action.value == "approve"]
    _require(
        len(mark_reviewed_actions) == 1,
        "FRESH_SESSION_MARK_REVIEWED_AMBIGUOUS",
        "fresh-session readback must expose exactly one mark_reviewed proof",
    )
    _require(
        len(approval_actions) == 1,
        "FRESH_SESSION_APPROVAL_ACTION_MISSING",
        "fresh-session readback must expose exactly one approval action",
    )

    def action_to_json(action: Any) -> dict[str, object]:
        return {
            "action": action.action.value,
            "report_id": action.report_id,
            "report_revision_id": action.report_revision_id,
            "from_status": action.from_status.value,
            "to_status": action.to_status.value,
            "actor": action.actor,
            "created_at": action.created_at.isoformat(),
        }

    return {
        "report_id": report_id,
        "report_revision_id": revision_id,
        "approved_revision_id": approved_revision_id,
        "approved_content_hash": approved_content_hash,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "trusted_operator": operator,
        "mark_reviewed_action": action_to_json(mark_reviewed_actions[0]),
        "approval": {
            "report_id": fresh_report.id,
            "report_revision_id": fresh_report.approved_revision_id,
            "approved_revision_id": fresh_report.approved_revision_id,
            "approved_content_hash": fresh_report.approved_content_hash,
            "approved_by": fresh_report.approved_by,
            "approved_at": fresh_report.approved_at,
        },
        "transitions": [action_to_json(action) for action in fresh_actions],
        "artifacts": {
            key: observation.to_json() for key, observation in fresh_observations.items()
        },
        "fresh_session": True,
        "restart": True,
    }


def run_controlled_acceptance(
    *,
    database_url: str,
    source_json: str | Path,
    operator: str,
    output_root: str | Path,
    backend: str,
    run_index: int,
    source_runtime: ControlledSourceRuntime,
    execution_source_sha: str,
    execution_source_tree_sha: str,
) -> dict[str, object]:
    """Execute one isolated backend acceptance run.

    Database schema migration and database creation remain explicit workflow
    responsibilities.  This function only operates on the supplied isolated
    URL and never touches a production endpoint.
    """

    source = load_source_definition(
        source_json,
        expected_source_candidate_path=source_runtime.source_candidate_path,
    )
    verify_authoritative_source_definition(
        source,
        authoritative_snapshot=source_runtime.source_snapshot,
        expected_source_candidate_path=source_runtime.source_candidate_path,
    )
    trusted_operator = validate_trusted_operator(operator)
    execution_source_sha, execution_source_tree_sha = validate_execution_source_identity(
        execution_source_sha,
        execution_source_tree_sha,
    )
    _require(run_index > 0, "RUN_INDEX_INVALID", "run_index must be positive")
    _require(
        backend in {"sqlite", "postgresql"},
        "BACKEND_INVALID",
        "controlled acceptance backend must be sqlite or postgresql",
    )
    _configure_database_environment(database_url)
    from sqlalchemy import create_engine, inspect, select
    from sqlalchemy.orm import sessionmaker

    engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
    if backend == "sqlite":
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **engine_kwargs)
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)
    diagnostics = _LifecycleDiagnosticContext()
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
        _require(
            inspect(engine).has_table("projects"),
            "SCHEMA_NOT_READY",
            "acceptance database is not migrated to head",
        )
        token = f"p1-controlled-{backend}-{run_index}"
        source_runtime.seed_startup_readiness(engine, token=token)
        definition_id = source_runtime.create_controlled_coefficient_definition(engine, token=token)
        persistence_value = source_runtime.create_controlled_production_authority(
            engine,
            definition_id=definition_id,
            token=token,
        )
        _require(
            isinstance(persistence_value, Mapping),
            "SOURCE_RUNTIME_INVALID",
            "controlled source runtime returned no persistence mapping",
        )
        persistence = cast(Mapping[str, object], persistence_value)
        canonical_persistence = persistence["canonical_persistence"]
        _require(
            isinstance(canonical_persistence, Mapping),
            "SOURCE_RUNTIME_INVALID",
            "controlled source runtime omitted canonical persistence",
        )
        canonical_persistence_mapping = cast(Mapping[str, object], canonical_persistence)
        project_id = str(canonical_persistence_mapping["project_id"])
        project_version_id = str(canonical_persistence_mapping["project_version_id"])
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as session:
            from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

            query = build_sqlalchemy_scheme_query(session)
            authority = query.get_review_authority(project_id, project_version_id)
            _require(
                authority is not None,
                "SCHEME_AUTHORITY_MISSING",
                "persisted Scheme authority is missing",
            )
            records, reasons = _verify_persisted_authority(
                session=session,
                authority=authority,
                canonical_persistence=canonical_persistence_mapping,
            )
            authority_snapshot = dict(_authority_snapshot(authority))
        with session_factory() as fresh_session:
            from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

            fresh_query = build_sqlalchemy_scheme_query(fresh_session)
            fresh_authority = fresh_query.get_review_authority(project_id, project_version_id)
        _require(
            fresh_authority is not None
            and dict(_authority_snapshot(fresh_authority)) == authority_snapshot,
            "FRESH_SESSION_AUTHORITY_MISMATCH",
            "fresh-session Scheme authority differs from the persisted authority",
        )
        stage_records = {
            stage: {
                "id": str(_record_value(record, "id")),
                "requires_review": _record_value(record, "requires_review"),
                "warnings": _record_warnings(record),
                "result_hash": _record_value(record, "result_hash"),
            }
            for stage, record in records.items()
        }
        report = _run_report_lifecycle(
            engine=engine,
            project_id=project_id,
            project_version_id=project_version_id,
            operator=trusted_operator,
            output_root=output_path / "artifacts",
            diagnostics=diagnostics,
        )
        evidence: dict[str, object] = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "source": {
                "accepted_source_definition_sha": ACCEPTED_SOURCE_DEFINITION_BASE_SHA,
                "accepted_source_definition_tree_sha": ACCEPTED_SOURCE_DEFINITION_BASE_TREE_SHA,
                "execution_source_sha": execution_source_sha,
                "execution_source_tree_sha": execution_source_tree_sha,
                "source_candidate_path": source_runtime.source_candidate_path,
                "canonical_input_sha256": source.canonical_input_sha256,
                "source_definition": source.to_json(),
            },
            "environment": {
                "backend": backend,
                "run_index": run_index,
                "database_url": _redact_database_url(database_url),
            },
            "review": {
                "stage_order": list(STAGE_ORDER),
                "requires_review_vector": [
                    stage_records[stage]["requires_review"] for stage in STAGE_ORDER
                ],
                "reasons": [reason.to_json() for reason in reasons],
                "source_binding_id": authority_snapshot["source_binding_id"],
                "combined_source_hash": authority_snapshot["combined_source_hash"],
                "scheme_result_hash": authority_snapshot["content_hash"],
                "scheme_review_authority_hash": authority_snapshot["content_hash"],
                "status": authority_snapshot["status"],
                "authority": authority_snapshot,
            },
            "lifecycle": report,
            "persistence": {"fresh_session": True, "restart": True},
            "backends": {"backend": backend, "run_index": run_index},
            "result": {"status": "PASS", "blockers": []},
        }
        return evidence
    except ControlledAcceptanceError:
        raise
    except Exception as exc:
        raise _wrap_controlled_failure(
            exc,
            backend=backend,
            run_index=run_index,
            diagnostics=diagnostics,
        ) from exc
    finally:
        engine.dispose()


__all__ = [
    "ACCEPTED_SOURCE_DEFINITION_BASE_SHA",
    "ACCEPTED_SOURCE_DEFINITION_BASE_TREE_SHA",
    "CANONICAL_INPUT_SHA256",
    "ControlledAcceptanceError",
    "ControlledSourceRuntime",
    "ControlledSourceDefinition",
    "EVIDENCE_SCHEMA_VERSION",
    "EXPECTED_REVIEW_VECTOR",
    "FORMAL_ARTIFACT_MATRIX",
    "STAGE_ORDER",
    "compare_normalized_evidence",
    "load_source_definition",
    "normalized_business_projection",
    "project_source_warnings",
    "run_controlled_acceptance",
    "verify_authoritative_source_definition",
    "validate_review_reason_continuity",
    "validate_execution_source_identity",
    "validate_trusted_operator",
    "verify_artifact_matrix",
]
