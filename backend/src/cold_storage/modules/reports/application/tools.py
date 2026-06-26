"""Report tool definitions for the planning agent tool registry.

tools:
- report.create (WRITE, requires_confirmation)
- report.generate (WRITE, requires_confirmation)
- report.get (READ)
- report.compare_revisions (READ)
- report.render (WRITE, requires_confirmation) — Task 9B
- report.list_exports (READ) — Task 9B
- report.get_export (READ) — Task 9B
"""

from __future__ import annotations

from cold_storage.modules.planning_agent.application.tool_registry import (
    ToolDefinition,
    ToolRegistry,
)
from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel


def register_report_tools(registry: ToolRegistry) -> None:
    """Register the 7 report tools in the given registry."""

    registry.register(
        ToolDefinition(
            name="report.create",
            description="Create a new report shell for a project version",
            input_schema={
                "type": "object",
                "required": ["project_id", "project_version_id", "report_type"],
                "properties": {
                    "project_id": {"type": "string"},
                    "project_version_id": {"type": "string"},
                    "report_type": {
                        "type": "string",
                        "enum": ["cold_storage_concept_design"],
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.create"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["report_id", "status"],
                        "properties": {
                            "report_id": {"type": "string"},
                            "status": {"const": "draft"},
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.WRITE,
            requires_confirmation=True,
            requires_project_version=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="report.generate",
            description="Generate a new revision of an existing report from persisted data",
            input_schema={
                "type": "object",
                "required": ["report_id"],
                "properties": {
                    "report_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.generate"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["revision_number", "content_hash"],
                        "properties": {
                            "revision_number": {"type": "integer", "minimum": 1},
                            "content_hash": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.WRITE,
            requires_confirmation=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="report.get",
            description="Get a report and its latest revision summary",
            input_schema={
                "type": "object",
                "required": ["report_id"],
                "properties": {
                    "report_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.get"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["report_id", "status", "revision_number"],
                        "properties": {
                            "report_id": {"type": "string"},
                            "status": {"type": "string"},
                            "revision_number": {"type": "integer"},
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="report.compare_revisions",
            description="Compare two revisions of a report and return structured diff",
            input_schema={
                "type": "object",
                "required": ["report_id", "revision_a", "revision_b"],
                "properties": {
                    "report_id": {"type": "string"},
                    "revision_a": {"type": "integer", "minimum": 1},
                    "revision_b": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.compare_revisions"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["changes"],
                        "properties": {
                            "changes": {"type": "array", "items": {"type": "object"}},
                            "revision_a": {"type": "integer"},
                            "revision_b": {"type": "integer"},
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
        )
    )

    # --- Task 9B: Render / Export tools ---

    registry.register(
        ToolDefinition(
            name="report.render",
            description="Render a report revision to DOCX or PDF format",
            input_schema={
                "type": "object",
                "required": ["report_id", "revision_number", "format", "mode", "locale"],
                "properties": {
                    "report_id": {"type": "string"},
                    "revision_number": {"type": "integer", "minimum": 1},
                    "format": {"type": "string", "enum": ["docx", "pdf"]},
                    "mode": {"type": "string", "enum": ["draft", "formal"]},
                    "template_version": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                    "locale": {
                        "type": "string",
                        "enum": ["zh-CN", "en-US"],
                        "description": "Report locale for localized rendering",
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.render"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": [
                            "artifact_id",
                            "status",
                            "format",
                            "file_name",
                            "file_size_bytes",
                            "file_sha256",
                            "locale",
                            "template_locale",
                            "translation_catalog_version",
                            "translation_catalog_content_hash",
                            "localized_template_content_hash",
                        ],
                        "properties": {
                            "artifact_id": {"type": "string"},
                            "status": {"type": "string"},
                            "format": {"type": "string"},
                            "file_name": {"type": "string"},
                            "file_size_bytes": {"type": "integer"},
                            "file_sha256": {"type": "string"},
                            "locale": {
                                "type": "string",
                                "description": "Report locale (e.g. zh-CN, en-US)",
                            },
                            "template_locale": {"type": "string", "description": "Template locale"},
                            "translation_catalog_version": {
                                "type": "string",
                                "description": "Catalog version",
                            },
                            "translation_catalog_content_hash": {
                                "type": "string",
                                "description": "Catalog content hash",
                            },
                            "localized_template_content_hash": {
                                "type": "string",
                                "description": "Localized template hash",
                            },
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.WRITE,
            requires_confirmation=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="report.list_exports",
            description="List all export artifacts for a report",
            input_schema={
                "type": "object",
                "required": ["report_id"],
                "properties": {
                    "report_id": {"type": "string"},
                    "locale": {
                        "type": "string",
                        "enum": ["zh-CN", "en-US"],
                        "description": "Filter exports by locale",
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.list_exports"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["exports"],
                        "properties": {
                            "exports": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": [
                                        "artifact_id",
                                        "status",
                                        "format",
                                        "file_name",
                                        "file_size_bytes",
                                        "revision_number",
                                        "generated_at",
                                        "locale",
                                        "template_locale",
                                        "translation_catalog_version",
                                        "translation_catalog_content_hash",
                                        "localized_template_content_hash",
                                    ],
                                    "properties": {
                                        "artifact_id": {"type": "string"},
                                        "status": {"type": "string"},
                                        "format": {"type": "string"},
                                        "file_name": {"type": "string"},
                                        "file_size_bytes": {"type": "integer"},
                                        "revision_number": {"type": "integer"},
                                        "generated_at": {"type": "string"},
                                        "locale": {"type": "string"},
                                        "template_locale": {"type": "string"},
                                        "translation_catalog_version": {"type": "string"},
                                        "translation_catalog_content_hash": {"type": "string"},
                                        "localized_template_content_hash": {"type": "string"},
                                    },
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="report.get_export",
            description="Get details of a specific export artifact",
            input_schema={
                "type": "object",
                "required": ["report_id", "artifact_id"],
                "properties": {
                    "report_id": {"type": "string"},
                    "artifact_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "source_tool",
                    "tool_version",
                    "result_id",
                    "payload",
                    "warnings",
                    "requires_review",
                ],
                "properties": {
                    "source_tool": {"const": "report.get_export"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": [
                            "artifact_id",
                            "status",
                            "format",
                            "file_name",
                            "file_size_bytes",
                            "file_sha256",
                            "revision_number",
                            "template_version",
                            "locale",
                            "template_locale",
                            "translation_catalog_version",
                            "translation_catalog_content_hash",
                            "localized_template_content_hash",
                        ],
                        "properties": {
                            "artifact_id": {"type": "string"},
                            "status": {"type": "string"},
                            "format": {"type": "string"},
                            "file_name": {"type": "string"},
                            "file_size_bytes": {"type": "integer"},
                            "file_sha256": {"type": "string"},
                            "revision_number": {"type": "integer"},
                            "template_version": {"type": "string"},
                            "locale": {"type": "string"},
                            "template_locale": {"type": "string"},
                            "translation_catalog_version": {"type": "string"},
                            "translation_catalog_content_hash": {"type": "string"},
                            "localized_template_content_hash": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
        )
    )
