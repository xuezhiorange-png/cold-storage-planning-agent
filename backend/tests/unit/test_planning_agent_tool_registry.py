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


class TestCoolingLoadOutputUnitValidation:
    """Verify that the cooling load output schema enforces strict engineering
    units: kW(r) for refrigeration, kW(e) for electrical, kW(th) for condenser,
    kWh for energy.  Fuzzy/incorrect units must be rejected by jsonschema const."""

    @pytest.fixture()
    def cooling_output_schema(self):
        reg = build_default_registry()
        tool = reg.get("planning.calculate_cooling_load_and_equipment")
        return tool.output_schema

    def _make_output(self, **unit_overrides):
        """Build a valid cooling load output dict, with optional unit overrides.
        Condenser and energy are omitted by default (optional)."""
        base = {
            "source_tool": "planning.calculate_cooling_load_and_equipment",
            "tool_version": "1.0.0",
            "result_id": "test-id",
            "payload": {
                "result": {
                    "total_cooling_load_kw": 100.0,
                    "total_cooling_load_unit": "kW(r)",
                    "equipment_list": [],
                    "total_equipment_capacity_kw": 110.0,
                    "total_equipment_capacity_unit": "kW(r)",
                    "total_electrical_input_kw": 40.0,
                    "total_electrical_input_unit": "kW(e)",
                },
            },
            "warnings": [],
            "requires_review": True,
        }
        for key, val in unit_overrides.items():
            base["payload"]["result"][key] = val
        return base

    def _make_full_output(self, **unit_overrides):
        """Build output with all optional fields present."""
        base = self._make_output(
            condenser_heat_rejection_kw=125.0,
            condenser_heat_rejection_unit="kW(th)",
            daily_energy_kwh=400.0,
            daily_energy_unit="kWh",
        )
        for key, val in unit_overrides.items():
            base["payload"]["result"][key] = val
        return base

    def test_valid_output_passes(self, cooling_output_schema):
        import jsonschema

        output = self._make_output()
        jsonschema.validate(output, cooling_output_schema)

    def test_valid_full_output_passes(self, cooling_output_schema):
        import jsonschema

        output = self._make_full_output()
        jsonschema.validate(output, cooling_output_schema)

    def test_optional_condenser_absent_passes(self, cooling_output_schema):
        """Condenser field is optional — absence should not fail validation."""
        import jsonschema

        output = self._make_output()
        assert "condenser_heat_rejection_kw" not in output["payload"]["result"]
        jsonschema.validate(output, cooling_output_schema)

    def test_optional_energy_absent_passes(self, cooling_output_schema):
        """Daily energy field is optional — absence should not fail validation."""
        import jsonschema

        output = self._make_output()
        assert "daily_energy_kwh" not in output["payload"]["result"]
        jsonschema.validate(output, cooling_output_schema)

    def test_fuzzy_kw_rejected(self, cooling_output_schema):
        """Plain 'kW' without suffix must be rejected."""
        import jsonschema

        output = self._make_output(total_cooling_load_unit="kW")
        with pytest.raises(jsonschema.ValidationError, match="kW"):
            jsonschema.validate(output, cooling_output_schema)

    def test_btu_rejected(self, cooling_output_schema):
        """'BTU/h' must not be accepted as a cooling unit."""
        import jsonschema

        output = self._make_output(total_cooling_load_unit="BTU/h")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(output, cooling_output_schema)

    def test_cooling_vs_electrical_mixed(self, cooling_output_schema):
        """kW(r) must not appear in electrical fields, kW(e) not in cooling."""
        import jsonschema

        output = self._make_output(total_electrical_input_unit="kW(r)")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(output, cooling_output_schema)

    def test_condenser_not_kw_r(self, cooling_output_schema):
        """Condenser heat rejection must be kW(th), not kW(r)."""
        import jsonschema

        output = self._make_full_output(condenser_heat_rejection_unit="kW(r)")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(output, cooling_output_schema)

    def test_missing_unit_rejected(self, cooling_output_schema):
        """A missing required unit field must fail validation."""
        import jsonschema

        output = self._make_output()
        del output["payload"]["result"]["total_cooling_load_unit"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(output, cooling_output_schema)
