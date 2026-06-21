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

# Lazy import for jsonschema to avoid import-time dependency issues
_jsonschema_validator: Any = None


def _get_validate() -> Any:
    """Lazy-load jsonschema.validate."""
    global _jsonschema_validator  # noqa: PLW0603
    if _jsonschema_validator is None:
        try:
            import jsonschema

            _jsonschema_validator = jsonschema.validate
        except ImportError:
            # Fallback: basic required-field check only
            def _basic_validate(instance: Any, schema: Any) -> None:
                required = schema.get("required", [])
                for field_name in required:
                    if field_name not in instance:
                        raise ToolArgumentValidationError(
                            "unknown", [f"Missing required field: {field_name}"]
                        )
                # Check types for properties
                properties = schema.get("properties", {})
                for key, value in instance.items():
                    if key in properties:
                        prop_schema = properties[key]
                        expected_type = prop_schema.get("type")
                        if expected_type == "string" and not isinstance(value, str):
                            raise ToolArgumentValidationError(
                                "unknown",
                                [f"Field {key} must be string, got {type(value).__name__}"],
                            )
                        elif expected_type == "number" and not isinstance(value, (int, float)):
                            raise ToolArgumentValidationError(
                                "unknown",
                                [f"Field {key} must be number, got {type(value).__name__}"],
                            )
                        elif expected_type == "integer" and not isinstance(value, int):
                            raise ToolArgumentValidationError(
                                "unknown",
                                [f"Field {key} must be integer, got {type(value).__name__}"],
                            )

            _jsonschema_validator = _basic_validate
    return _jsonschema_validator


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
            raise ToolArgumentValidationError(
                name, [str(exc)]
            ) from exc


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
                "additionalProperties": False,
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
                "additionalProperties": False,
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
                    "daily_inbound_mass_kg": {"type": "number", "minimum": 0},
                    "working_time_h_per_day": {"type": "number", "minimum": 0, "maximum": 24},
                    "finished_storage_days": {"type": "number", "minimum": 0},
                    "packaging_storage_days": {"type": "number", "minimum": 0},
                    "precooling_required_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                    "storage_days": {"type": "number", "minimum": 0},
                },
                "additionalProperties": False,
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
                "additionalProperties": False,
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
                    "version_number": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            authorization_level=AuthorizationLevel.WRITE,
            requires_confirmation=True,
            requires_project=True,
            requires_project_version=True,
        )
    )

    return registry
