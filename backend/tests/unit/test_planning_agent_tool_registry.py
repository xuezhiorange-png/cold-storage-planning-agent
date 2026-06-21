"""Tests for the planning agent tool registry."""

from __future__ import annotations

import pytest

from cold_storage.modules.planning_agent.application.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    build_default_registry,
)
from cold_storage.modules.planning_agent.domain.enums import AuthorizationLevel
from cold_storage.modules.planning_agent.domain.errors import (
    ToolArgumentValidationError,
    UnregisteredToolError,
)


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        t = ToolDefinition(name="test.tool", description="A test tool")
        reg.register(t)
        assert reg.get("test.tool") is t

    def test_get_unregistered(self):
        reg = ToolRegistry()
        with pytest.raises(UnregisteredToolError):
            reg.get("nonexistent")

    def test_is_registered(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a"))
        assert reg.is_registered("a") is True
        assert reg.is_registered("b") is False

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a"))
        reg.register(ToolDefinition(name="b"))
        assert len(reg.list_tools()) == 2

    def test_validate_arguments_missing_required(self):
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="test",
                input_schema={"required": ["x", "y"]},
            )
        )
        with pytest.raises(ToolArgumentValidationError) as exc:
            reg.validate_arguments("test", {"x": 1})
        assert "y" in str(exc.value)

    def test_validate_arguments_pass(self):
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="test",
                input_schema={"required": ["x"]},
            )
        )
        reg.validate_arguments("test", {"x": 1})


class TestDefaultRegistry:
    def test_has_all_v1_tools(self):
        reg = build_default_registry()
        names = reg.list_tool_names()
        assert "knowledge.search" in names
        assert "project.get" in names
        assert "project_version.get" in names
        assert "planning.calculate_throughput_inventory_area" in names
        assert "planning.calculate_cooling_load_and_equipment" in names
        assert "scheme.generate_and_compare" in names

    def test_read_tools_no_confirmation(self):
        reg = build_default_registry()
        assert reg.get("knowledge.search").requires_confirmation is False
        assert reg.get("project.get").requires_confirmation is False

    def test_write_tools_require_confirmation(self):
        reg = build_default_registry()
        assert reg.get("scheme.generate_and_compare").requires_confirmation is True

    def test_authorization_levels(self):
        reg = build_default_registry()
        assert reg.get("knowledge.search").authorization_level == AuthorizationLevel.READ
        assert (
            reg.get("scheme.generate_and_compare").authorization_level == AuthorizationLevel.WRITE
        )

    def test_all_tools_have_schemas(self):
        reg = build_default_registry()
        for tool in reg.list_tools():
            assert "required" in tool.input_schema or "properties" in tool.input_schema
