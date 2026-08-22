"""Workflow domain errors — no framework dependencies."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base workflow aggregation error."""


class ProjectNotFoundForWorkflowError(WorkflowError):
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"Project not found: {project_id}")


class ProjectVersionNotFoundForWorkflowError(WorkflowError):
    def __init__(self, project_id: str, version_number: int) -> None:
        self.project_id = project_id
        self.version_number = version_number
        super().__init__(
            f"Project version not found: project={project_id} version={version_number}"
        )
