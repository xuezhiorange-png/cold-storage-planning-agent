"""Workflow API routes — read-only aggregation."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request

from cold_storage.modules.workflow.application.service import WorkflowAggregateService
from cold_storage.modules.workflow.domain.errors import (
    ProjectNotFoundForWorkflowError,
    ProjectVersionNotFoundForWorkflowError,
)
from cold_storage.modules.workflow.domain.steps import (
    WORKFLOW_GOAL_FORMAL_REPORT,
    WORKFLOW_GOAL_PLANNING_PREVIEW,
)


def register_workflow_routes(app: FastAPI, get_service: Any) -> None:
    """Register workflow routes on the FastAPI app."""

    @app.get("/api/v1/projects/{project_id}/versions/{version}/workflow")
    def get_workflow_aggregate(
        project_id: str,
        version: int,
        request: Request,
        workflow_goal: str = WORKFLOW_GOAL_FORMAL_REPORT,
    ) -> dict[str, Any]:
        if workflow_goal not in {WORKFLOW_GOAL_FORMAL_REPORT, WORKFLOW_GOAL_PLANNING_PREVIEW}:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported workflow_goal: {workflow_goal}",
            )
        service: WorkflowAggregateService = get_service(request)
        try:
            return service.get_workflow_aggregate(
                project_id,
                version,
                workflow_goal=workflow_goal,
            )
        except ProjectNotFoundForWorkflowError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ProjectVersionNotFoundForWorkflowError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
