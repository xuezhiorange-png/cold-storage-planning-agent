"""Scheme API routes — thin layer, delegates to SchemeService.

Status codes:
- 404: project, version, or scheme run not found
- 409: source calculation missing or version conflict
- 422: invalid profile, parameter, or weight set
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from cold_storage.bootstrap.dependencies import (
    get_production_scheme_service,
    get_production_session_factory,
)
from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.application.production_service import ProductionSchemeError
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.domain.errors import (
    CompletedRunImmutabilityError,
    InvalidProfileError,
    InvalidProfileParameterError,
    MissingProfileParameterError,
    ProjectNotFoundError,
    ProjectVersionNotFoundError,
    SchemeDomainError,
    SourceCalculationMissingError,
    SourceSnapshotInvalidError,
    VersionConflictError,
    WeightSetError,
)
from cold_storage.modules.schemes.domain.models import (
    ReviewReason,
    SchemeRun,
    review_reasons_to_json,
)


class SchemeRunRequest(BaseModel):
    """Client only provides profile selection and weight set.
    All engineering data is read from the database by the service.
    """

    profile_codes: list[str]
    weight_set_id: str
    profile_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProductionSchemeRunRequest(BaseModel):
    """Production scheme generation bound to five-stage SourceBinding.

    Engineering inputs are read from persisted orchestration results.
    The client supplies scoring policy (approved revision) and profiles only.
    """

    profile_codes: list[str]
    weight_set_revision_id: str
    profile_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _resolve_five_stage_source_binding_id(
    *,
    project_id: str,
    project_version_id: str,
) -> str:
    session_factory = get_production_session_factory()
    with session_factory() as session:
        binding = session.scalar(
            select(SourceBindingRecord)
            .where(
                SourceBindingRecord.project_id == project_id,
                SourceBindingRecord.project_version_id == project_version_id,
            )
            .order_by(SourceBindingRecord.created_at.desc())
        )
    if binding is None:
        raise SourceCalculationMissingError(
            "Five-stage SourceBinding is missing for this project version",
        )
    return str(binding.id)


def _serialize_production_scheme_run(
    run: SchemeRun,
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
) -> dict[str, Any]:
    canonical_reasons = [
        reason for reason in run.warning_messages if isinstance(reason, ReviewReason)
    ]
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "project_version_id": run.project_version_id,
        "source_mode": "production",
        "source_binding_id": source_binding_id,
        "weight_set_revision_id": weight_set_revision_id,
        "status": run.status,
        "generator_version": run.generator_version,
        "recommended_scheme_code": run.recommended_scheme_code,
        "requires_review": run.requires_review,
        "review_reasons": review_reasons_to_json(canonical_reasons),
        "combined_source_hash": run.source_snapshot_hash,
        "content_hash": run.content_hash,
    }


def _http_status_for_production_scheme_error(exc: ProductionSchemeError) -> int:
    governance_codes = {
        "revision_not_found",
        "revision_not_approved",
        "revision_content_hash_mismatch",
        "generator_version_incompatible",
        "criteria_invalid",
        "criteria_sum_invalid",
        "criteria_negative_weight",
        "duplicate_criterion_code",
    }
    if exc.code in governance_codes:
        return 422
    return 409


def register_scheme_routes(app: FastAPI, get_service: Any) -> None:
    """Register scheme routes on the FastAPI app."""

    @app.post("/api/v1/projects/{project_id}/versions/{version}/scheme-runs")
    def create_scheme_run(
        project_id: str,
        version: int,
        request: SchemeRunRequest,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        try:
            return service.generate_scheme_run(
                project_id=project_id,
                version=version,
                profile_codes=request.profile_codes,
                weight_set_id=request.weight_set_id,
                profile_parameters=request.profile_parameters,
            )
        except (ProjectNotFoundError, ProjectVersionNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (
            SourceCalculationMissingError,
            VersionConflictError,
            SourceSnapshotInvalidError,
        ) as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except (
            InvalidProfileError,
            InvalidProfileParameterError,
            MissingProfileParameterError,
            WeightSetError,
        ) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except CompletedRunImmutabilityError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @app.post(
        "/api/v1/projects/{project_id}/versions/{version}/production-scheme-runs",
    )
    def create_production_scheme_run(
        project_id: str,
        version: int,
        request: ProductionSchemeRunRequest,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        try:
            project_version_id = service.resolve_version_id(project_id, version)
        except ProjectNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ProjectVersionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        try:
            source_binding_id = _resolve_five_stage_source_binding_id(
                project_id=project_id,
                project_version_id=project_version_id,
            )
        except SourceCalculationMissingError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

        production_service = get_production_scheme_service()
        command = GenerateProductionSchemeCommand(
            source_binding_id=source_binding_id,
            weight_set_revision_id=request.weight_set_revision_id,
            profile_codes=tuple(request.profile_codes),
            profile_parameters=request.profile_parameters,
            actor="",
            correlation_id=f"api-prod-scheme-{uuid.uuid4().hex}",
            database_backend=get_settings().database_backend,
        )
        try:
            run = production_service.generate_production_scheme_run(command)
        except ProductionSchemeError as e:
            raise HTTPException(
                status_code=_http_status_for_production_scheme_error(e),
                detail=str(e),
            ) from e
        except SchemeDomainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        return _serialize_production_scheme_run(
            run,
            source_binding_id=source_binding_id,
            weight_set_revision_id=request.weight_set_revision_id,
        )

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs")
    def list_scheme_runs(
        project_id: str,
        version: int,
    ) -> list[dict[str, Any]]:
        service: SchemeService = get_service()
        try:
            version_id = service.resolve_version_id(project_id, version)
        except ProjectVersionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return service.list_scheme_runs(version_id)

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs/{run_id}")
    def get_scheme_run(
        project_id: str,
        version: int,
        run_id: str,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        try:
            version_id = service.resolve_version_id(project_id, version)
        except ProjectVersionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        result = service.get_scheme_run(run_id)
        if result is None or result.get("project_version_id") != version_id:
            raise HTTPException(status_code=404, detail="Scheme run not found")
        return result

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs/{run_id}/comparison")
    def get_comparison(
        project_id: str,
        version: int,
        run_id: str,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        try:
            version_id = service.resolve_version_id(project_id, version)
        except ProjectVersionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        result = service.get_comparison(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Scheme run not found")
        # Verify the run belongs to this version
        run_result = service.get_scheme_run(run_id)
        if run_result is None or run_result.get("project_version_id") != version_id:
            raise HTTPException(status_code=404, detail="Scheme run not found")
        return result

    # ------------------------------------------------------------------
    # Demo endpoint — uses Application Service, not direct domain calls
    # ------------------------------------------------------------------

    @app.get("/api/v1/demo/scheme-comparison")
    def demo_scheme_comparison() -> dict[str, Any]:
        """Demo endpoint using the same Application Service as the formal API.

        Seeds a demo project/version/calculations and delegates to SchemeService.
        """
        service: SchemeService = get_service()
        try:
            return service.generate_demo_scheme_comparison()
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
