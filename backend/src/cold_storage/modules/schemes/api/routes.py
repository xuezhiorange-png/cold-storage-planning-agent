"""Scheme API routes — thin layer, delegates to SchemeService."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from cold_storage.modules.schemes.application.service import SchemeService

router = APIRouter(prefix="/api/v1", tags=["schemes"])


class SchemeRunRequest(BaseModel):
    profile_codes: list[str]
    weight_set_id: str
    profile_parameters: dict[str, dict[str, Any]] = {}
    source_calculation_ids: dict[str, str] = {}
    source_snapshot_hashes: dict[str, str] = {}
    zone_results: list[dict[str, Any]]
    investment_result: dict[str, Any]
    cooling_load_result: dict[str, Any]
    equipment_result: dict[str, Any]
    total_daily_throughput_kg_day: float
    total_storage_capacity_kg: float
    total_position_count: int


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
                project_version_id=f"{project_id}-v{version}",
                profile_codes=request.profile_codes,
                weight_set_id=request.weight_set_id,
                profile_parameters=request.profile_parameters,
                source_calculation_ids=request.source_calculation_ids,
                source_snapshot_hashes=request.source_snapshot_hashes,
                zone_results_raw=request.zone_results,
                investment_raw=request.investment_result,
                cooling_load_raw=request.cooling_load_result,
                equipment_raw=request.equipment_result,
                total_daily_throughput_kg_day=request.total_daily_throughput_kg_day,
                total_storage_capacity_kg=request.total_storage_capacity_kg,
                total_position_count=request.total_position_count,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    @app.get("/api/v1/projects/{project_id}/versions/{version}/scheme-runs")
    def list_scheme_runs(
        project_id: str,
        version: int,
    ) -> list[dict[str, Any]]:
        service: SchemeService = get_service()
        return service.list_scheme_runs(f"{project_id}-v{version}")

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
