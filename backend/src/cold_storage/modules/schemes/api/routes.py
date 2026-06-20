"""Scheme API routes — thin layer, delegates to SchemeService.

Status codes:
- 404: project, version, or scheme run not found
- 409: source calculation missing or version conflict
- 422: invalid profile, parameter, or weight set
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.domain.errors import (
    CompletedRunImmutabilityError,
    InvalidProfileError,
    InvalidProfileParameterError,
    MissingProfileParameterError,
    ProjectNotFoundError,
    ProjectVersionNotFoundError,
    SourceCalculationMissingError,
    VersionConflictError,
    WeightSetError,
)


class SchemeRunRequest(BaseModel):
    """Client only provides profile selection and weight set.
    All engineering data is read from the database by the service.
    """

    profile_codes: list[str]
    weight_set_id: str
    profile_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)


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
        except (SourceCalculationMissingError, VersionConflictError) as e:
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

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs")
    def list_scheme_runs(
        project_id: str,
        version: int,
    ) -> list[dict[str, Any]]:
        service: SchemeService = get_service()
        # Use version record ID for listing
        version_id = f"{project_id}-v{version}"
        return service.list_scheme_runs(version_id)

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs/{run_id}")
    def get_scheme_run(
        project_id: str,
        version: int,
        run_id: str,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        result = service.get_scheme_run(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Scheme run not found")
        return result

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs/{run_id}/comparison")
    def get_comparison(
        project_id: str,
        version: int,
        run_id: str,
    ) -> dict[str, Any]:
        service: SchemeService = get_service()
        result = service.get_comparison(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Scheme run not found")
        return result

    # ------------------------------------------------------------------
    # Demo endpoint — uses Application Service, not direct domain calls
    # ------------------------------------------------------------------

    @app.post("/api/v1/demo/scheme-comparison")
    def demo_scheme_comparison() -> dict[str, Any]:
        """Demo endpoint using the same Application Service as the formal API.

        Seeds a demo project/version/calculations and delegates to SchemeService.
        """
        service: SchemeService = get_service()
        try:
            # Seed demo data via the service
            return service.generate_scheme_run(
                project_id="demo-project",
                version=1,
                profile_codes=["balanced", "consolidated_large_rooms", "segmented_small_rooms"],
                weight_set_id="demo-weight-set-001",
                profile_parameters={
                    "segmented_small_rooms": {"max_positions_per_room": 50},
                },
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
