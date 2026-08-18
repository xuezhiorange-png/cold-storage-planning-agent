"""Finding-specific tests for the V0.3 P1 controlled acceptance surface."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.bootstrap.s6_07_controlled_fixture import _EXECUTION_SNAPSHOT
from cold_storage.evaluation import followup_acceptance as acceptance
from cold_storage.evaluation.followup_acceptance import (
    CANONICAL_INPUT_SHA256,
    CONTROLLED_REVIEW_LIFECYCLE_ACTIONS,
    EVIDENCE_SCHEMA_VERSION,
    EXPECTED_REVIEW_VECTOR,
    FORMAL_ARTIFACT_MATRIX,
    STAGE_ORDER,
    ControlledAcceptanceError,
    ControlledSourceRuntime,
    _capture_post_generation_diagnostics,
    _invoke_review_lifecycle_action,
    _LifecycleDiagnosticContext,
    _wrap_controlled_failure,
    compare_normalized_evidence,
    load_source_definition,
    normalized_business_projection,
    project_source_warnings,
    run_controlled_acceptance,
    validate_execution_source_identity,
    validate_review_reason_continuity,
    validate_trusted_operator,
    verify_artifact_matrix,
    verify_authoritative_source_definition,
)
from cold_storage.modules.reports.domain.enums import ReportStatus
from cold_storage.modules.reports.domain.errors import InvalidStatusTransitionError
from cold_storage.modules.schemes.domain.models import ReviewReason

SOURCE_PATH = Path(__file__).parent / "data/task011-followup-high-throughput-source.v1.json"
SOURCE_CANDIDATE_PATH = (
    "backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py::_EXECUTION_SNAPSHOT"
)
DATABASE_ENVIRONMENT_VARIABLES = (
    "COLD_STORAGE_DATABASE_BACKEND",
    "COLD_STORAGE_DATABASE_URL",
    "COLD_STORAGE_SQLITE_PATH",
)


def _database_environment_snapshot() -> dict[str, str | None]:
    return {name: os.environ.get(name) for name in DATABASE_ENVIRONMENT_VARIABLES}


@contextmanager
def _preserve_database_environment() -> Iterator[None]:
    original = _database_environment_snapshot()
    try:
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@dataclass
class _Authority:
    requires_review: bool
    review_reasons: tuple[ReviewReason, ...]

    def to_snapshot(self) -> dict[str, object]:
        return {
            "requires_review": self.requires_review,
            "review_reasons": [reason.to_json() for reason in self.review_reasons],
        }


def _stage_records(
    *,
    vector: tuple[bool, ...] = EXPECTED_REVIEW_VECTOR,
    warning_overrides: dict[str, list[object]] | None = None,
) -> dict[str, dict[str, object]]:
    overrides = warning_overrides or {}
    return {
        stage: {
            "id": f"calculation-{stage}",
            "requires_review": vector[index],
            "warnings": overrides.get(
                stage,
                [
                    {
                        "code": f"WARN_{stage.upper()}",
                        "message": f"producer warning for {stage}",
                    }
                ],
            ),
        }
        for index, stage in enumerate(STAGE_ORDER)
    }


def _authority_for(records: dict[str, dict[str, object]]) -> _Authority:
    reasons = project_source_warnings(records)
    return _Authority(requires_review=True, review_reasons=reasons)


def test_fixture_is_bound_to_production_execution_snapshot() -> None:
    source = load_source_definition(
        SOURCE_PATH,
        expected_source_candidate_path=SOURCE_CANDIDATE_PATH,
    )
    verify_authoritative_source_definition(
        source,
        authoritative_snapshot=_EXECUTION_SNAPSHOT,
        expected_source_candidate_path=SOURCE_CANDIDATE_PATH,
    )

    assert source.source_candidate_path == SOURCE_CANDIDATE_PATH
    assert source.canonical_input_sha256 == CANONICAL_INPUT_SHA256
    assert dict(source.input) == _EXECUTION_SNAPSHOT
    assert source.expected_vector == dict(zip(STAGE_ORDER, EXPECTED_REVIEW_VECTOR, strict=True))


def test_fixture_tamper_fails_hash_validation(tmp_path: Path) -> None:
    raw = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    raw["input"]["zone"]["daily_inbound_mass_kg"] = 10001
    tampered = tmp_path / SOURCE_PATH.name
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ControlledAcceptanceError, match="canonical input hash") as exc_info:
        load_source_definition(
            tampered,
            expected_source_candidate_path=SOURCE_CANDIDATE_PATH,
        )
    assert exc_info.value.code == "SOURCE_HASH_MISMATCH"


def test_mixed_vector_uses_stage_booleans_and_excludes_power_advisory() -> None:
    records = _stage_records(
        warning_overrides={"power": [{"code": "DEFAULT_DEMAND_FACTOR", "message": "advisory only"}]}
    )
    reasons = project_source_warnings(records)

    assert [reason.stage for reason in reasons] == [
        "zone",
        "cooling_load",
        "equipment",
        "investment",
    ]
    assert all(reason.stage != "power" for reason in reasons)
    assert [reason.source_id for reason in reasons] == [
        "calculation-zone",
        "calculation-cooling_load",
        "calculation-equipment",
        "calculation-investment",
    ]


def test_review_reason_projection_preserves_warning_order_and_exact_dedupe() -> None:
    records = _stage_records(
        warning_overrides={
            "zone": [
                {"code": "A", "message": "first"},
                {"code": "A", "message": "first"},
                {"code": "B", "message": "second"},
            ]
        }
    )

    reasons = project_source_warnings(records)

    assert [(reason.code, reason.message) for reason in reasons[:2]] == [
        ("A", "first"),
        ("B", "second"),
    ]


def test_true_stage_without_warning_fails_closed() -> None:
    records = _stage_records(warning_overrides={"equipment": []})

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        project_source_warnings(records)

    assert exc_info.value.code == "REVIEW_REASON_SOURCE_MISSING"


def test_malformed_warning_fails_closed_without_string_laundering() -> None:
    records = _stage_records(warning_overrides={"zone": ["not a warning mapping"]})

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        project_source_warnings(records)

    assert exc_info.value.code == "PRODUCER_WARNING_INVALID"


def test_invalid_status_transition_failure_preserves_direct_diagnostic_details() -> None:
    blockers = [
        {
            "code": "MISSING_RECOMMENDATION",
            "severity": "blocker",
            "section_key": "scheme",
            "field_path": "recommended_scheme_code",
            "message": "no feasible scheme",
        }
    ]
    diagnostics = _LifecycleDiagnosticContext(
        lifecycle_action="approve",
        report_status_after_generate_revision="generated",
        quality_blockers_after_generate_revision=blockers,
    )

    wrapped = _wrap_controlled_failure(
        InvalidStatusTransitionError(ReportStatus.REVIEWED, ReportStatus.APPROVED),
        backend="sqlite",
        run_index=1,
        diagnostics=diagnostics,
    )

    assert wrapped.to_json() == {
        "code": "CONTROLLED_ACCEPTANCE_FAILED",
        "message": "controlled acceptance production path failed",
        "details": {
            "backend": "sqlite",
            "run_index": 1,
            "exception_type": "InvalidStatusTransitionError",
            "lifecycle_action": "approve",
            "report_status_after_generate_revision": "generated",
            "quality_blockers_after_generate_revision": blockers,
            "invalid_from_status": "reviewed",
            "invalid_to_status": "approved",
        },
    }


@pytest.mark.parametrize("action", CONTROLLED_REVIEW_LIFECYCLE_ACTIONS)
def test_lifecycle_action_is_set_before_each_review_service_call(action: str) -> None:
    diagnostics = _LifecycleDiagnosticContext()

    class FailingReviewService:
        def __call__(self, *args: object, **kwargs: object) -> None:
            raise InvalidStatusTransitionError("unexpected", "target")

    service = SimpleNamespace(**{action: FailingReviewService()})
    with pytest.raises(InvalidStatusTransitionError):
        _invoke_review_lifecycle_action(service, "report-1", "operator", action, diagnostics)

    assert diagnostics.lifecycle_action == action


def test_successful_review_action_clears_context_before_later_work() -> None:
    diagnostics = _LifecycleDiagnosticContext()
    service = SimpleNamespace(approve=lambda *args, **kwargs: "approved")

    result = _invoke_review_lifecycle_action(
        service,
        "report-1",
        "operator",
        "approve",
        diagnostics,
    )

    assert result == "approved"
    assert diagnostics.lifecycle_action is None

    wrapped = _wrap_controlled_failure(
        InvalidStatusTransitionError(ReportStatus.REVIEWED, ReportStatus.APPROVED),
        backend="sqlite",
        run_index=1,
        diagnostics=diagnostics,
    )
    assert wrapped.details == {
        "backend": "sqlite",
        "run_index": 1,
        "exception_type": "InvalidStatusTransitionError",
    }


def test_non_invalid_review_action_failure_clears_context() -> None:
    diagnostics = _LifecycleDiagnosticContext()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("review action failed")

    with pytest.raises(RuntimeError, match="review action failed"):
        _invoke_review_lifecycle_action(
            SimpleNamespace(approve=fail),
            "report-1",
            "operator",
            "approve",
            diagnostics,
        )

    assert diagnostics.lifecycle_action is None


def test_lifecycle_action_allowlist_is_closed() -> None:
    assert CONTROLLED_REVIEW_LIFECYCLE_ACTIONS == (
        "submit_review",
        "mark_reviewed",
        "approve",
    )
    with pytest.raises(ControlledAcceptanceError) as exc_info:
        _invoke_review_lifecycle_action(
            SimpleNamespace(),
            "report-1",
            "operator",
            "request_changes",
            _LifecycleDiagnosticContext(),
        )
    assert exc_info.value.code == "CONTROLLED_LIFECYCLE_ACTION_INVALID"


def test_post_generation_diagnostics_use_persisted_report_readback_and_full_blockers() -> None:
    blocker = {
        "code": "MISSING_RECOMMENDATION",
        "severity": "blocker",
        "section_key": "scheme",
        "field_path": "recommended_scheme_code",
        "message": "no feasible scheme",
    }
    warning = {
        "code": "ADVISORY",
        "severity": "warning",
        "section_key": "summary",
        "field_path": "summary",
        "message": "advisory",
    }
    calls: list[tuple[str, str]] = []

    class ReportServiceReadback:
        def get_report(self, report_id: str, operator: str) -> object:
            calls.append((report_id, operator))
            return SimpleNamespace(status=SimpleNamespace(value="generated"))

    diagnostics = _capture_post_generation_diagnostics(
        ReportServiceReadback(),
        "report-1",
        "operator",
        SimpleNamespace(quality_findings_json=[blocker, warning]),
        _LifecycleDiagnosticContext(),
    )

    assert calls == [("report-1", "operator")]
    assert diagnostics.report_status_after_generate_revision == "generated"
    assert diagnostics.quality_blockers_after_generate_revision == [blocker]


def test_post_generation_diagnostics_use_empty_blocker_list_when_clear() -> None:
    diagnostics = _capture_post_generation_diagnostics(
        SimpleNamespace(
            get_report=lambda report_id, operator: SimpleNamespace(
                status=SimpleNamespace(value="generated")
            )
        ),
        "report-1",
        "operator",
        SimpleNamespace(quality_findings_json=[]),
        _LifecycleDiagnosticContext(),
    )

    assert diagnostics.quality_blockers_after_generate_revision == []


def test_non_invalid_status_failure_keeps_generic_failure_contract() -> None:
    diagnostics = _LifecycleDiagnosticContext(
        lifecycle_action="approve",
        report_status_after_generate_revision="generated",
        quality_blockers_after_generate_revision=[],
    )
    wrapped = _wrap_controlled_failure(
        RuntimeError("unrelated failure"),
        backend="postgresql",
        run_index=2,
        diagnostics=diagnostics,
    )

    assert set(wrapped.details) == {"backend", "run_index", "exception_type"}
    assert wrapped.details == {
        "backend": "postgresql",
        "run_index": 2,
        "exception_type": "RuntimeError",
    }


def test_invalid_status_before_review_action_keeps_generic_failure_contract() -> None:
    wrapped = _wrap_controlled_failure(
        InvalidStatusTransitionError("draft", "generated"),
        backend="sqlite",
        run_index=1,
        diagnostics=_LifecycleDiagnosticContext(),
    )

    assert wrapped.details == {
        "backend": "sqlite",
        "run_index": 1,
        "exception_type": "InvalidStatusTransitionError",
    }


def test_authority_checks_source_id_stage_and_false_stage() -> None:
    records = _stage_records()
    reasons = project_source_warnings(records)
    tampered = list(reasons)
    tampered[0] = ReviewReason(
        code=tampered[0].code,
        message=tampered[0].message,
        stage=tampered[0].stage,
        source_type=tampered[0].source_type,
        source_id="wrong-calculation-id",
    )
    authority = _Authority(requires_review=True, review_reasons=tuple(tampered))

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        validate_review_reason_continuity(authority=authority, stage_records=records)
    assert exc_info.value.code == "SCHEME_REASON_SOURCE_ID_MISMATCH"

    false_stage_reason = ReviewReason(
        code="DEFAULT_DEMAND_FACTOR",
        message="advisory",
        stage="power",
        source_type="calculation_run",
        source_id="calculation-power",
    )
    false_stage_authority = _Authority(
        requires_review=True,
        review_reasons=tuple([*reasons, false_stage_reason]),
    )
    with pytest.raises(ControlledAcceptanceError) as exc_info:
        validate_review_reason_continuity(
            authority=false_stage_authority,
            stage_records=records,
        )
    assert exc_info.value.code == "FALSE_STAGE_REASON_PRESENT"


def test_aggregate_boolean_cannot_replace_mixed_stage_vector() -> None:
    records = _stage_records()
    authority = _Authority(requires_review=False, review_reasons=project_source_warnings(records))

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        validate_review_reason_continuity(authority=authority, stage_records=records)
    assert exc_info.value.code == "REVIEW_VECTOR_AGGREGATE_MISMATCH"


def test_review_reason_is_closed_five_field_json() -> None:
    reason = ReviewReason(
        code="WARN",
        message="exact producer message",
        stage="zone",
        source_type="calculation_run",
        source_id="calculation-zone",
    )

    assert set(reason.to_json()) == {"code", "message", "stage", "source_type", "source_id"}
    assert reason.to_json()["message"] == "exact producer message"


@pytest.mark.parametrize("operator", ["", "system", "api", "background", "llm"])
def test_reserved_or_empty_operator_is_rejected(operator: str) -> None:
    with pytest.raises(ControlledAcceptanceError) as exc_info:
        validate_trusted_operator(operator)
    assert exc_info.value.code in {"TRUSTED_OPERATOR_MISSING", "TRUSTED_OPERATOR_NOT_HUMAN"}


def test_artifact_matrix_reloads_bytes_and_requires_shared_identity() -> None:
    class Artifact:
        def __init__(self, locale: str, fmt: str, artifact_id: str) -> None:
            self.id = artifact_id
            self.report_id = "report-1"
            self.report_revision_id = "revision-1"
            self.source_content_hash = "content-hash"
            self.locale = SimpleNamespace(value=locale)
            self.format = SimpleNamespace(value=fmt)
            self.status = SimpleNamespace(value="completed")
            self.file_sha256 = f"hash-{locale}-{fmt}"
            self.file_size_bytes = len(self.file_sha256.encode())
            self.storage_key = f"storage-{locale}-{fmt}"
            self.template_id = f"template-{locale}"
            self.template_version = "1.0.0"
            self.template_locale = SimpleNamespace(value=locale)
            self.translation_catalog_version = "1.0.0"
            self.translation_catalog_content_hash = f"catalog-hash-{locale}"
            self.localized_template_content_hash = f"localized-hash-{locale}"
            self.render_manifest_json = {
                "render_mode": "formal",
                "locale": locale,
                "template_id": self.template_id,
                "template_version": self.template_version,
                "template_content_hash": f"template-content-hash-{locale}",
                "source_content_hash": "content-hash",
                "approved_revision_id": "revision-1",
                "approved_content_hash": "content-hash",
                "translation_catalog_version": self.translation_catalog_version,
                "translation_catalog_content_hash": self.translation_catalog_content_hash,
                "localized_template_content_hash": self.localized_template_content_hash,
            }

    artifacts = {
        f"{locale}/{fmt}": Artifact(locale, fmt, f"artifact-{locale}-{fmt}")
        for locale, fmt in FORMAL_ARTIFACT_MATRIX
    }
    files = {artifact.storage_key: artifact.file_sha256.encode() for artifact in artifacts.values()}
    for artifact in artifacts.values():
        import hashlib

        artifact.file_sha256 = hashlib.sha256(files[artifact.storage_key]).hexdigest()
        artifact.file_size_bytes = len(files[artifact.storage_key])

    observations = verify_artifact_matrix(
        artifacts,
        read_bytes=files.__getitem__,
        report_id="report-1",
        report_revision_id="revision-1",
        approved_revision_id="revision-1",
        approved_content_hash="content-hash",
    )

    assert set(observations) == {f"{locale}/{fmt}" for locale, fmt in FORMAL_ARTIFACT_MATRIX}
    assert len({observation.artifact_id for observation in observations.values()}) == 4

    del artifacts["zh-CN/docx"].render_manifest_json["template_content_hash"]
    with pytest.raises(ControlledAcceptanceError) as exc_info:
        verify_artifact_matrix(
            artifacts,
            read_bytes=files.__getitem__,
            report_id="report-1",
            report_revision_id="revision-1",
            approved_revision_id="revision-1",
            approved_content_hash="content-hash",
        )
    assert exc_info.value.code == "ARTIFACT_TEMPLATE_LINEAGE_MISSING"


def test_artifact_matrix_rejects_label_mismatch() -> None:
    import hashlib

    class Artifact:
        id = "artifact-1"
        report_id = "report-1"
        report_revision_id = "revision-1"
        source_content_hash = "content-hash"
        locale = SimpleNamespace(value="en-US")
        format = SimpleNamespace(value="pdf")
        status = SimpleNamespace(value="completed")
        file_sha256 = hashlib.sha256(b"x").hexdigest()
        file_size_bytes = 1
        storage_key = "storage-1"
        template_id = "template-1"
        template_version = "1.0.0"
        template_locale = SimpleNamespace(value="en-US")
        translation_catalog_version = "1.0.0"
        translation_catalog_content_hash = "catalog-hash"
        localized_template_content_hash = "localized-hash"
        render_manifest_json = {
            "render_mode": "formal",
            "locale": "en-US",
            "template_id": "template-1",
            "template_version": "1.0.0",
            "template_content_hash": "template-content-hash",
            "source_content_hash": "content-hash",
            "approved_revision_id": "revision-1",
            "approved_content_hash": "content-hash",
            "translation_catalog_version": "1.0.0",
            "translation_catalog_content_hash": "catalog-hash",
            "localized_template_content_hash": "localized-hash",
        }

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        verify_artifact_matrix(
            {f"{locale}/{fmt}": Artifact() for locale, fmt in FORMAL_ARTIFACT_MATRIX},
            read_bytes=lambda _: b"x",
            report_id="report-1",
            report_revision_id="revision-1",
            approved_revision_id="revision-1",
            approved_content_hash="content-hash",
        )
    assert exc_info.value.code == "ARTIFACT_LABEL_MISMATCH"


def test_artifact_matrix_rejects_duplicate_artifact_ids() -> None:
    class Artifact:
        def __init__(self, locale: str, fmt: str) -> None:
            self.id = "same-artifact"
            self.report_id = "report-1"
            self.report_revision_id = "revision-1"
            self.source_content_hash = "content-hash"
            self.locale = SimpleNamespace(value=locale)
            self.format = SimpleNamespace(value=fmt)
            self.status = SimpleNamespace(value="completed")
            self.file_sha256 = ""
            self.file_size_bytes = 0
            self.storage_key = f"storage-{locale}-{fmt}"
            self.template_id = f"template-{locale}"
            self.template_version = "1.0.0"
            self.template_locale = SimpleNamespace(value=locale)
            self.translation_catalog_version = "1.0.0"
            self.translation_catalog_content_hash = "catalog-hash"
            self.localized_template_content_hash = "localized-hash"
            self.render_manifest_json = {
                "render_mode": "formal",
                "locale": locale,
                "template_id": self.template_id,
                "template_version": self.template_version,
                "template_content_hash": "template-content-hash",
                "source_content_hash": "content-hash",
                "approved_revision_id": "revision-1",
                "approved_content_hash": "content-hash",
                "translation_catalog_version": "1.0.0",
                "translation_catalog_content_hash": "catalog-hash",
                "localized_template_content_hash": "localized-hash",
            }

    artifacts = {f"{locale}/{fmt}": Artifact(locale, fmt) for locale, fmt in FORMAL_ARTIFACT_MATRIX}
    files = {artifact.storage_key: b"x" for artifact in artifacts.values()}
    for artifact in artifacts.values():
        import hashlib

        artifact.file_sha256 = hashlib.sha256(files[artifact.storage_key]).hexdigest()
        artifact.file_size_bytes = 1

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        verify_artifact_matrix(
            artifacts,
            read_bytes=files.__getitem__,
            report_id="report-1",
            report_revision_id="revision-1",
            approved_revision_id="revision-1",
            approved_content_hash="content-hash",
        )
    assert exc_info.value.code == "ARTIFACT_ID_DUPLICATE"


def test_execution_source_identity_must_be_explicit() -> None:
    with pytest.raises(ControlledAcceptanceError) as exc_info:
        validate_execution_source_identity("", "runtime-tree")
    assert exc_info.value.code == "EXECUTION_SOURCE_SHA_MISSING"

    assert validate_execution_source_identity("runtime-sha", "runtime-tree") == (
        "runtime-sha",
        "runtime-tree",
    )


def test_acceptance_core_has_no_architecture_token_bypass() -> None:
    core = (
        Path(__file__).parents[2] / "src" / "cold_storage" / "evaluation" / "followup_acceptance.py"
    ).read_text(encoding="utf-8")

    assert '"idempotency_" + "key"' not in core
    assert '"scheme_" + "run_id"' not in core
    assert "**{" not in core
    assert "import_module" not in core
    assert "idempotency_key" not in core
    assert "scheme_run_id" not in core
    assert "s6_07_controlled_fixture" not in core


def test_normalized_parity_ignores_runtime_ids_and_execution_bound_hashes() -> None:
    def evidence(source_id: str, hash_suffix: str) -> dict[str, object]:
        return {
            "source": {
                "source_candidate_path": SOURCE_CANDIDATE_PATH,
                "canonical_input_sha256": CANONICAL_INPUT_SHA256,
            },
            "review": {
                "stage_order": list(STAGE_ORDER),
                "requires_review_vector": list(EXPECTED_REVIEW_VECTOR),
                "reasons": [
                    {
                        "code": "WARN",
                        "message": "same",
                        "stage": "zone",
                        "source_type": "calculation_run",
                        "source_id": source_id,
                    }
                ],
                "combined_source_hash": "binding-hash",
                "scheme_result_hash": "scheme-hash",
                "scheme_review_authority_hash": "scheme-hash",
                "authority": {
                    f"{stage}_result_hash": f"{stage}-{hash_suffix}" for stage in STAGE_ORDER
                },
                "status": "completed",
            },
        }

    first = evidence("sqlite-id", "run-a")
    second = evidence("postgres-id", "run-b")
    result = compare_normalized_evidence({"sqlite-1": first, "postgresql-1": second})

    assert result["status"] == "PASS"
    assert first["review"]["authority"]["power_result_hash"] == "power-run-a"
    assert second["review"]["authority"]["power_result_hash"] == "power-run-b"
    assert normalized_business_projection(first)["calculation_result_hashes_present"] == {
        stage: True for stage in STAGE_ORDER
    }


@pytest.mark.parametrize("invalid_stage", STAGE_ORDER)
@pytest.mark.parametrize(
    "invalid_hash", [None, "", "   ", 123], ids=["none", "empty", "blank", "non-string"]
)
def test_normalized_parity_requires_present_per_stage_result_hashes(
    invalid_stage: str, invalid_hash: object
) -> None:
    first = {
        "source": {
            "source_candidate_path": SOURCE_CANDIDATE_PATH,
            "canonical_input_sha256": CANONICAL_INPUT_SHA256,
        },
        "review": {
            "stage_order": list(STAGE_ORDER),
            "requires_review_vector": list(EXPECTED_REVIEW_VECTOR),
            "reasons": [],
            "combined_source_hash": "binding-hash-a",
            "scheme_result_hash": "scheme-hash",
            "scheme_review_authority_hash": "scheme-hash",
            "authority": {f"{stage}_result_hash": f"{stage}-hash" for stage in STAGE_ORDER},
            "status": "completed",
        },
    }
    first["review"]["authority"][f"{invalid_stage}_result_hash"] = invalid_hash

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        normalized_business_projection(first)

    assert exc_info.value.code == "EVIDENCE_RESULT_HASH_INVALID"


def test_normalized_parity_rejects_missing_per_stage_result_hash() -> None:
    evidence = {
        "source": {
            "source_candidate_path": SOURCE_CANDIDATE_PATH,
            "canonical_input_sha256": CANONICAL_INPUT_SHA256,
        },
        "review": {
            "stage_order": list(STAGE_ORDER),
            "requires_review_vector": list(EXPECTED_REVIEW_VECTOR),
            "reasons": [],
            "authority": {f"{stage}_result_hash": f"{stage}-hash" for stage in STAGE_ORDER},
            "status": "completed",
        },
    }
    del evidence["review"]["authority"]["zone_result_hash"]

    with pytest.raises(ControlledAcceptanceError) as exc_info:
        normalized_business_projection(evidence)

    assert exc_info.value.code == "EVIDENCE_RESULT_HASH_INVALID"


def test_normalized_parity_ignores_execution_bound_hash_changes() -> None:
    first = {
        "source": {
            "source_candidate_path": SOURCE_CANDIDATE_PATH,
            "canonical_input_sha256": CANONICAL_INPUT_SHA256,
        },
        "review": {
            "stage_order": list(STAGE_ORDER),
            "requires_review_vector": list(EXPECTED_REVIEW_VECTOR),
            "reasons": [],
            "combined_source_hash": "binding-hash",
            "scheme_result_hash": "scheme-hash",
            "scheme_review_authority_hash": "scheme-hash",
            "authority": {f"{stage}_result_hash": f"{stage}-hash" for stage in STAGE_ORDER},
            "status": "completed",
        },
    }
    second = copy.deepcopy(first)
    second["review"]["authority"]["power_result_hash"] = "power-hash-tampered"

    result = compare_normalized_evidence({"a": first, "b": second})

    assert result["status"] == "PASS"


def test_normalized_parity_still_rejects_business_changes() -> None:
    first = {
        "source": {
            "source_candidate_path": SOURCE_CANDIDATE_PATH,
            "canonical_input_sha256": CANONICAL_INPUT_SHA256,
        },
        "review": {
            "stage_order": list(STAGE_ORDER),
            "requires_review_vector": list(EXPECTED_REVIEW_VECTOR),
            "reasons": [
                {
                    "code": "WARN",
                    "message": "same",
                    "stage": "zone",
                    "source_type": "calculation_run",
                    "source_id": "runtime-zone-id",
                }
            ],
            "combined_source_hash": "binding-hash",
            "scheme_result_hash": "scheme-hash",
            "scheme_review_authority_hash": "scheme-hash",
            "authority": {
                **{f"{stage}_result_hash": f"{stage}-run-a" for stage in STAGE_ORDER},
                "recommended_scheme_code": "balanced",
            },
            "status": "completed",
        },
    }
    changes = (
        ("recommended_scheme_code", "conservative"),
        ("requires_review_vector", [False, True, True, False, True]),
        ("status", "failed"),
        ("canonical_input_sha256", "different-input-hash"),
    )
    for field, value in changes:
        second = copy.deepcopy(first)
        if field == "recommended_scheme_code":
            second["review"]["authority"][field] = value
        elif field == "requires_review_vector" or field == "status":
            second["review"][field] = value
        else:
            second["source"][field] = value
        assert compare_normalized_evidence({"a": first, "b": second})["status"] == "FAIL"

    reason_changed = copy.deepcopy(first)
    reason_changed["review"]["reasons"][0]["message"] = "changed"
    assert compare_normalized_evidence({"a": first, "b": reason_changed})["status"] == "FAIL"


def test_success_evidence_compatibility_excludes_failure_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _Connection:
        def __enter__(self) -> _Connection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, statement: object) -> None:
            return None

    class _Engine:
        def connect(self) -> _Connection:
            return _Connection()

        def dispose(self) -> None:
            return None

    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _Query:
        def get_review_authority(self, project_id: str, project_version_id: str) -> object:
            return object()

    records = {
        stage: {
            "id": f"calculation-{stage}",
            "requires_review": EXPECTED_REVIEW_VECTOR[index],
            "warnings": [],
            "result_hash": f"{stage}-hash",
        }
        for index, stage in enumerate(STAGE_ORDER)
    }
    authority_snapshot = {
        "source_binding_id": "binding-1",
        "combined_source_hash": "binding-hash",
        "content_hash": "scheme-hash",
        "status": "completed",
        **{f"{stage}_result_hash": f"{stage}-hash" for stage in STAGE_ORDER},
    }
    source_runtime = ControlledSourceRuntime(
        source_candidate_path=SOURCE_CANDIDATE_PATH,
        source_snapshot=_EXECUTION_SNAPSHOT,
        seed_startup_readiness=lambda engine, **kwargs: None,
        create_controlled_coefficient_definition=lambda engine, **kwargs: "definition-1",
        create_controlled_production_authority=lambda engine, **kwargs: {
            "canonical_persistence": {
                "project_id": "project-1",
                "project_version_id": "version-1",
            }
        },
    )

    monkeypatch.setattr("sqlalchemy.create_engine", lambda *args, **kwargs: _Engine())
    monkeypatch.setattr(
        "sqlalchemy.inspect",
        lambda engine: SimpleNamespace(has_table=lambda table_name: table_name == "projects"),
    )
    monkeypatch.setattr("sqlalchemy.orm.sessionmaker", lambda **kwargs: lambda: _Session())
    monkeypatch.setattr(
        "cold_storage.modules.schemes.application.query.build_sqlalchemy_scheme_query",
        lambda session: _Query(),
    )
    monkeypatch.setattr(
        acceptance,
        "_verify_persisted_authority",
        lambda **kwargs: (records, ()),
    )
    monkeypatch.setattr(acceptance, "_authority_snapshot", lambda authority: authority_snapshot)
    monkeypatch.setattr(
        acceptance,
        "_run_report_lifecycle",
        lambda **kwargs: {
            "report_id": "report-1",
            "report_revision_id": "revision-1",
            "approved_revision_id": "revision-1",
            "approved_content_hash": "report-hash",
            "project_id": "project-1",
            "project_version_id": "version-1",
            "trusted_operator": "trusted-operator",
            "approval": {"approved_by": "trusted-operator"},
            "transitions": [],
            "artifacts": {},
            "fresh_session": True,
            "restart": True,
        },
    )

    before_environment = _database_environment_snapshot()
    with _preserve_database_environment():
        evidence = run_controlled_acceptance(
            database_url="sqlite:///:memory:",
            source_json=SOURCE_PATH,
            operator="trusted-operator",
            output_root=tmp_path,
            backend="sqlite",
            run_index=1,
            source_runtime=source_runtime,
            execution_source_sha="runtime-sha",
            execution_source_tree_sha="runtime-tree",
        )

    after_environment = _database_environment_snapshot()
    for name in DATABASE_ENVIRONMENT_VARIABLES:
        expected = before_environment[name]
        if expected is None:
            assert name not in os.environ
        else:
            assert os.environ[name] == expected
        assert after_environment[name] == expected

    diagnostic_keys = {
        "lifecycle_action",
        "report_status_after_generate_revision",
        "quality_blockers_after_generate_revision",
        "invalid_from_status",
        "invalid_to_status",
    }

    def contains_diagnostic_key(value: object) -> bool:
        if isinstance(value, dict):
            return bool(set(value) & diagnostic_keys) or any(
                contains_diagnostic_key(child) for child in value.values()
            )
        if isinstance(value, list):
            return any(contains_diagnostic_key(child) for child in value)
        return False

    assert evidence["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert EVIDENCE_SCHEMA_VERSION == "v0.3-p1-controlled-acceptance-evidence.v1"
    assert not contains_diagnostic_key(evidence)

    parity = compare_normalized_evidence(
        {"sqlite-1": evidence, "sqlite-2": copy.deepcopy(evidence)}
    )
    assert parity["status"] == "PASS"
