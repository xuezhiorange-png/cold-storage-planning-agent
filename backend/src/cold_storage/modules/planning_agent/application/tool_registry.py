"""Explicit allow-list tool registry for the planning agent.

Each tool declares its name, version, schema, authorization level, and
whether it requires confirmation or a bound project/version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel
from cold_storage.modules.planning_agent.domain.errors import (
    ToolArgumentValidationError,
    UnregisteredToolError,
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    authorization_level: AuthorizationLevel = AuthorizationLevel.READ
    requires_confirmation: bool = False
    requires_project: bool = False
    requires_project_version: bool = False
    allowed_version_statuses: list[str] = field(default_factory=lambda: ["draft", "submitted"])


class ToolRegistry:
    """Strict allow-list registry of agent-callable tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise UnregisteredToolError(name)
        return self._tools[name]

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> None:
        """Validate arguments against the tool input_schema (basic required-field check)."""
        tool = self.get(name)
        required = tool.input_schema.get("required", [])
        errors: list[str] = []
        for field_name in required:
            if field_name not in arguments:
                errors.append(f"Missing required field: {field_name}")
        if errors:
            raise ToolArgumentValidationError(name, errors)


def build_default_registry() -> ToolRegistry:
    """Build the V1 tool registry with all registered planning tools."""
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="knowledge.search",
            description="Search the professional knowledge base by query text",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "default": 5},
                },
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="project.get",
            description="Get project details by ID",
            input_schema={
                "type": "object",
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                },
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
            requires_project=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="project_version.get",
            description="Get a specific project version",
            input_schema={
                "type": "object",
                "required": ["project_id", "version_number"],
                "properties": {
                    "project_id": {"type": "string"},
                    "version_number": {"type": "integer"},
                },
            },
            authorization_level=AuthorizationLevel.READ,
            requires_confirmation=False,
            requires_project=True,
            requires_project_version=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="planning.calculate_throughput_inventory_area",
            description="Calculate throughput, inventory, precooling, and zone areas",
            input_schema={
                "type": "object",
                "required": ["daily_inbound_mass_kg", "working_time_h_per_day"],
                "properties": {
                    "daily_inbound_mass_kg": {"type": "number"},
                    "working_time_h_per_day": {"type": "number"},
                    "finished_storage_days": {"type": "number"},
                    "packaging_storage_days": {"type": "number"},
                    "precooling_required_ratio": {"type": "number"},
                    "storage_days": {"type": "number"},
                },
            },
            authorization_level=AuthorizationLevel.CALCULATE,
            requires_confirmation=False,
            requires_project_version=True,
            allowed_version_statuses=["draft", "submitted"],
        )
    )

    registry.register(
        ToolDefinition(
            name="planning.calculate_cooling_load_and_equipment",
            description="Calculate cooling load and equipment capability",
            input_schema={
                "type": "object",
                "required": ["zone_areas", "temperature_levels"],
                "properties": {
                    "zone_areas": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "temperature_levels": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            },
            authorization_level=AuthorizationLevel.CALCULATE,
            requires_confirmation=False,
            requires_project_version=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="scheme.generate_and_compare",
            description="Generate and compare cold-room schemes",
            input_schema={
                "type": "object",
                "required": ["project_id", "version_number"],
                "properties": {
                    "project_id": {"type": "string"},
                    "version_number": {"type": "integer"},
                },
            },
            authorization_level=AuthorizationLevel.WRITE,
            requires_confirmation=True,
            requires_project=True,
            requires_project_version=True,
        )
    )

    return registry
