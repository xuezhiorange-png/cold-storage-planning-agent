"""Tool adapters for report render/export tools → ReportRenderService.

P0-12: Agent Tool Adapters for report rendering operations.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from cold_storage.modules.planning_agent.domain.errors import PlanningAgentError
from cold_storage.modules.planning_agent.domain.models import AgentToolResult

if TYPE_CHECKING:
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderService,
    )


class ReportRenderAdapter:
    """Adapts report.render → ReportRenderService.render().

    WRITE + requires_confirmation.
    """

    def __init__(self, render_service: ReportRenderService) -> None:
        self._service = render_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if self._service is None:
            raise PlanningAgentError("ReportRenderService not configured — cannot execute render")

        report_id = arguments["report_id"]
        revision_number = arguments["revision_number"]
        format_val = arguments.get("format", "docx")
        mode = arguments.get("mode", "draft")
        template_version = arguments.get("template_version")
        idempotency_key = arguments.get("idempotency_key")
        actor = arguments.get("actor", "system")

        try:
            artifact = self._service.render(
                report_id=report_id,
                revision_number=revision_number,
                format=format_val,
                template_version=template_version,
                mode=mode,
                actor=actor,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            raise PlanningAgentError(f"Render failed: {exc}") from exc

        warnings: list[str] = []
        if mode == "draft":
            warnings.append("Draft export — not suitable for official use")

        output = {
            "source_tool": "report.render",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {
                "artifact_id": artifact.id,
                "status": artifact.status.value,
                "format": artifact.format.value,
                "file_name": artifact.file_name,
                "file_size_bytes": artifact.file_size_bytes,
                "file_sha256": artifact.file_sha256,
            },
            "warnings": warnings,
            "requires_review": True,
        }
        return AgentToolResult(
            tool_name="report.render",
            output=output,
        )


class ReportListExportsAdapter:
    """Adapts report.list_exports → ReportRenderService.list_artifacts().

    READ only.
    """

    def __init__(self, render_service: ReportRenderService) -> None:
        self._service = render_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if self._service is None:
            raise PlanningAgentError("ReportRenderService not configured — cannot list exports")

        report_id = arguments["report_id"]
        actor = arguments.get("actor", "system")

        try:
            artifacts = self._service.list_artifacts(report_id, actor)
        except Exception as exc:
            raise PlanningAgentError(f"List exports failed: {exc}") from exc

        output = {
            "source_tool": "report.list_exports",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {
                "exports": [
                    {
                        "artifact_id": a.id,
                        "status": a.status.value,
                        "format": a.format.value,
                        "file_name": a.file_name,
                        "file_size_bytes": a.file_size_bytes,
                        "revision_number": a.revision_number,
                        "generated_at": (
                            a.generated_at.isoformat()
                            if hasattr(a.generated_at, "isoformat")
                            else str(a.generated_at)
                        ),
                    }
                    for a in artifacts
                ],
            },
            "warnings": [],
            "requires_review": False,
        }
        return AgentToolResult(
            tool_name="report.list_exports",
            output=output,
        )


class ReportGetExportAdapter:
    """Adapts report.get_export → ReportRenderService.get_artifact().

    READ only.
    """

    def __init__(self, render_service: ReportRenderService) -> None:
        self._service = render_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if self._service is None:
            raise PlanningAgentError("ReportRenderService not configured — cannot get export")

        report_id = arguments["report_id"]
        artifact_id = arguments["artifact_id"]
        actor = arguments.get("actor", "system")

        try:
            artifact = self._service.get_artifact(report_id, artifact_id, actor)
        except Exception as exc:
            raise PlanningAgentError(f"Get export failed: {exc}") from exc

        output = {
            "source_tool": "report.get_export",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {
                "artifact_id": artifact.id,
                "status": artifact.status.value,
                "format": artifact.format.value,
                "file_name": artifact.file_name,
                "file_size_bytes": artifact.file_size_bytes,
                "file_sha256": artifact.file_sha256,
                "revision_number": artifact.revision_number,
                "template_version": artifact.template_version,
            },
            "warnings": [],
            "requires_review": False,
        }
        return AgentToolResult(
            tool_name="report.get_export",
            output=output,
        )
