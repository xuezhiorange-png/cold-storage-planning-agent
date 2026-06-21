"""Explicit allow-list tool registry for the planning agent.

Each tool declares its name, version, schema, authorization level, and
whether it requires confirmation or a bound project/version.

Fix #8: validate_arguments uses jsonschema for strict type/range/nested validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel
from cold_storage.modules.planning_agent.domain.errors import (
    ToolArgumentValidationError,
    UnregisteredToolError,
)

# jsonschema is a hard requirement — no fallback allowed (fail-closed).
try:
    import jsonschema

    _jsonschema_validate = jsonschema.validate
except ImportError as _exc:
    raise ImportError(
        "jsonschema is required for tool output validation. Install with: pip install jsonschema"
    ) from _exc


def _get_validate() -> Any:
    """Return jsonschema.validate. Raises at import time if missing."""
    return _jsonschema_validate


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
    allowed_version_statuses: list[str] = field(
        default_factory=lambda: ["draft", "generated", "under_review", "reviewed"]
    )


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
        """Validate arguments against the tool input_schema using jsonschema.

        Checks: required fields, types, nested objects, additional properties.
        """
        tool = self.get(name)
        schema = tool.input_schema
        if not schema:
            return

        validate = _get_validate()
        try:
            validate(instance=arguments, schema=schema)
        except Exception as exc:
            if isinstance(exc, ToolArgumentValidationError):
                raise
            raise ToolArgumentValidationError(name, [str(exc)]) from exc


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
                    "source_tool": {"const": "knowledge.search"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["results", "count"],
                        "properties": {
                            "results": {"type": "array"},
                            "count": {"type": "integer"},
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
            allowed_version_statuses=[
                "draft",
                "generated",
                "under_review",
                "reviewed",
                "approved",
                "archived",
            ],
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
                    "source_tool": {"const": "project.get"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["project"],
                        "properties": {
                            "project": {"type": "object"},
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
            requires_project=True,
            allowed_version_statuses=[
                "draft",
                "generated",
                "under_review",
                "reviewed",
                "approved",
                "archived",
            ],
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
                    "source_tool": {"const": "project_version.get"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["version"],
                        "properties": {
                            "version": {"type": "object"},
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
            requires_project=True,
            requires_project_version=True,
            allowed_version_statuses=[
                "draft",
                "generated",
                "under_review",
                "reviewed",
                "approved",
                "archived",
            ],
        )
    )

    registry.register(
        ToolDefinition(
            name="planning.calculate_throughput_inventory_area",
            description="Calculate throughput, inventory, precooling, and zone areas",
            input_schema={
                "type": "object",
                "required": ["daily_inbound_mass", "mass_unit", "working_time_h_per_day"],
                "properties": {
                    "daily_inbound_mass": {"type": "number", "minimum": 0},
                    "mass_unit": {"type": "string", "enum": ["kg", "tons"]},
                    "working_time_h_per_day": {"type": "number", "minimum": 0, "maximum": 24},
                    "finished_storage_days": {"type": "number", "minimum": 0},
                    "packaging_storage_days": {"type": "number", "minimum": 0},
                    "precooling_required_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                    "storage_days": {"type": "number", "minimum": 0},
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
                    "source_tool": {"const": "planning.calculate_throughput_inventory_area"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["zone_plan"],
                        "properties": {
                            "zone_plan": {
                                "type": "object",
                                "required": [
                                    "throughput_t_per_day",
                                    "throughput_unit",
                                    "required_inventory_t",
                                    "inventory_unit",
                                    "precooling_area_m2",
                                    "finished_area_m2",
                                    "packaging_area_m2",
                                ],
                                "properties": {
                                    "throughput_t_per_day": {"type": "number"},
                                    "throughput_unit": {
                                        "type": "string",
                                        "enum": ["t/day", "kg/day"],
                                    },
                                    "required_inventory_t": {"type": "number"},
                                    "inventory_unit": {"type": "string", "enum": ["t", "kg"]},
                                    "precooling_area_m2": {"type": "number"},
                                    "finished_area_m2": {"type": "number"},
                                    "packaging_area_m2": {"type": "number"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.CALCULATE,
            requires_confirmation=False,
            requires_project_version=True,
            allowed_version_statuses=["draft", "generated"],
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
                    "source_tool": {"const": "planning.calculate_cooling_load_and_equipment"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["result"],
                        "properties": {
                            "result": {
                                "type": "object",
                                "required": [
                                    "total_cooling_load_kw",
                                    "total_cooling_load_unit",
                                    "equipment_list",
                                    "total_equipment_capacity_kw",
                                    "total_equipment_capacity_unit",
                                ],
                                "properties": {
                                    "total_cooling_load_kw": {"type": "number"},
                                    "total_cooling_load_unit": {
                                        "type": "string",
                                        "enum": ["kW", "BTU/h"],
                                    },
                                    "equipment_list": {"type": "array"},
                                    "total_equipment_capacity_kw": {"type": "number"},
                                    "total_equipment_capacity_unit": {
                                        "type": "string",
                                        "enum": ["kW", "BTU/h"],
                                    },
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_review": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.CALCULATE,
            requires_confirmation=False,
            requires_project_version=True,
            allowed_version_statuses=["draft", "generated"],
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
                    "version_number": {"type": "integer", "minimum": 1},
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
                    "source_tool": {"const": "scheme.generate_and_compare"},
                    "tool_version": {"const": "1.0.0"},
                    "result_id": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "required": ["scheme_result"],
                        "properties": {
                            "scheme_result": {"type": "object"},
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
            requires_project=True,
            requires_project_version=True,
            allowed_version_statuses=["draft", "generated"],
        )
    )

    return registry
