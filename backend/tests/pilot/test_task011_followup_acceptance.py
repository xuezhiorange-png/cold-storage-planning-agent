"""Finding-specific tests for the V0.3 P1 controlled acceptance surface."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.bootstrap.s6_07_controlled_fixture import _EXECUTION_SNAPSHOT
from cold_storage.evaluation.followup_acceptance import (
    CANONICAL_INPUT_SHA256,
    EXPECTED_REVIEW_VECTOR,
    FORMAL_ARTIFACT_MATRIX,
    STAGE_ORDER,
    ControlledAcceptanceError,
    _controlled_scheme_candidate_evidence,
    _lifecycle_failure_diagnostic,
    compare_normalized_evidence,
    load_source_definition,
    project_source_warnings,
    validate_execution_source_identity,
    validate_review_reason_continuity,
    validate_trusted_operator,
    verify_artifact_matrix,
    verify_authoritative_source_definition,
)
from cold_storage.modules.reports.domain.errors import InvalidStatusTransitionError
from cold_storage.modules.schemes.domain.models import ReviewReason

SOURCE_PATH = Path(__file__).parent / "data/task011-followup-high-throughput-source.v1.json"
SOURCE_CANDIDATE_PATH = (
    "backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py::_EXECUTION_SNAPSHOT"
)


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


def test_normalized_parity_ignores_runtime_source_ids() -> None:
    def evidence(source_id: str) -> dict[str, object]:
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
                "authority": {f"{stage}_result_hash": f"{stage}-hash" for stage in STAGE_ORDER},
                "status": "completed",
            },
        }

    result = compare_normalized_evidence(
        {"sqlite-1": evidence("sqlite-id"), "postgresql-1": evidence("postgres-id")}
    )

    assert result["status"] == "PASS"


def test_normalized_parity_does_not_ignore_business_hash_changes() -> None:
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
    second = copy.deepcopy(first)
    second["review"]["authority"]["power_result_hash"] = "power-hash-tampered"

    result = compare_normalized_evidence({"a": first, "b": second})

    assert result["status"] == "FAIL"


def test_lifecycle_failure_diagnostic_preserves_production_root_cause() -> None:
    revision = SimpleNamespace(
        id="revision-1",
        revision_number=1,
        quality_status=SimpleNamespace(value="draft"),
        quality_findings_json=[
            {
                "code": "EMPTY_REQUIRED_ENGINEERING_RESULT",
                "severity": "blocker",
                "section_key": "scheme_comparison",
                "field_path": "scheme_comparison.recommended_scheme",
                "message": "recommended scheme is empty",
            }
        ],
    )
    authority = {
        "scheme_run_id": "scheme-run-1",
        "recommended_scheme_code": "",
        "requires_review": True,
        "content_hash": "scheme-hash",
        "source_binding_id": "binding-1",
    }
    candidates = _controlled_scheme_candidate_evidence(
        [
            {
                "scheme_code": "balanced",
                "feasible": False,
                "rank": None,
                "constraint_results": [{"code": "cooling_capacity_adequacy", "passed": False}],
            },
        ],
        recommended_scheme_code=authority["recommended_scheme_code"],
    )

    details = _lifecycle_failure_diagnostic(
        exception=InvalidStatusTransitionError("draft", "under_review"),
        report_status_after_generate=SimpleNamespace(value="draft"),
        revision=revision,
        scheme_review_authority=authority,
        scheme_candidate_evidence=candidates,
    )

    assert details["exception_type"] == "InvalidStatusTransitionError"
    assert details["from_status"] == "draft"
    assert details["to_status"] == "under_review"
    assert details["report_status_after_generate_revision"] == "draft"
    assert details["revision_quality_status"] == "draft"
    assert details["quality_blocker_fields"] == [
        {
            "code": "EMPTY_REQUIRED_ENGINEERING_RESULT",
            "section_key": "scheme_comparison",
            "field_path": "scheme_comparison.recommended_scheme",
        }
    ]
    assert details["scheme_review_authority"] == authority
    assert details["controlled_scheme_candidates"] == [
        {
            "scheme_code": "balanced",
            "feasible": False,
            "rank": None,
            "constraint_results": [{"code": "cooling_capacity_adequacy", "passed": False}],
            "recommendation_status": "no_persisted_recommendation",
        }
    ]
