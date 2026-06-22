"""Versioned JSON Schemas for report content contracts.

V1: cold_storage_concept_design@1.0.0
"""

from __future__ import annotations

from typing import Any


def _unit_enum() -> dict[str, Any]:
    return {"type": "string", "enum": ["kW(r)", "kW(e)", "kW(th)", "kWh"]}


def _measured_value_with_unit(unit_const: str) -> dict[str, Any]:
    """A measured engineering value with a fixed unit constraint."""
    return {
        "type": "object",
        "required": ["value", "unit", "source_result_id", "source_tool", "source_tool_version"],
        "properties": {
            "value": {"type": "number"},
            "unit": {"const": unit_const},
            "source_result_id": {"type": "string"},
            "source_tool": {"type": "string"},
            "source_tool_version": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _measured_value(extra_props: dict[str, Any] | None = None) -> dict[str, Any]:
    """A measured engineering value: value + unit + source provenance."""
    props: dict[str, Any] = {
        "value": {"type": "number"},
        "unit": _unit_enum(),
        "source_result_id": {"type": "string"},
        "source_tool": {"type": "string"},
        "source_tool_version": {"type": "string"},
    }
    if extra_props:
        props.update(extra_props)
    return {
        "type": "object",
        "required": ["value", "unit", "source_result_id", "source_tool", "source_tool_version"],
        "properties": props,
        "additionalProperties": False,
    }


COLD_STORAGE_CONCEPT_DESIGN_V1: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "cold_storage_concept_design@1.0.0",
    "title": "Cold Storage Concept Design Report",
    "type": "object",
    "required": [
        "report_metadata",
        "quality_summary",
    ],
    "properties": {
        "report_metadata": {
            "type": "object",
            "required": [
                "schema_version",
                "report_id",
                "project_id",
                "project_version_id",
                "generated_at",
            ],
            "properties": {
                "schema_version": {"const": "cold_storage_concept_design@1.0.0"},
                "report_id": {"type": "string"},
                "project_id": {"type": "string"},
                "project_version_id": {"type": "string"},
                "generated_at": {"type": "string"},
                "generated_by": {"type": "string"},
                "revision_number": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "project_summary": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "project_location": {"type": "string"},
                "design_capacity_tons_per_day": {"type": "number"},
                "description": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "input_conditions": {
            "type": "object",
            "properties": {
                "zones": {"type": "array", "items": {"type": "object"}},
                "temperature_levels": {"type": "array", "items": {"type": "object"}},
                "coefficients_used": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "assumptions": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description"],
                        "properties": {
                            "description": {"type": "string"},
                            "source": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "throughput_inventory_area": {
            "type": "object",
            "properties": {
                "daily_inbound_mass_kg": {"type": "number"},
                "storage_capacity_kg": {"type": "number"},
                "total_area_m2": {"type": "number"},
                "zone_details": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        "cooling_load": {
            "type": "object",
            "properties": {
                "total_design_refrigeration_load": _measured_value_with_unit("kW(r)"),
                "zone_loads": {"type": "array", "items": {"type": "object"}},
                "level_summaries": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        "equipment_selection": {
            "type": "object",
            "properties": {
                "total_compressor_capacity": _measured_value_with_unit("kW(r)"),
                "total_compressor_input_power": _measured_value_with_unit("kW(e)"),
                "condenser_heat_rejection": _measured_value_with_unit("kW(th)"),
                "systems": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        "electrical_and_energy": {
            "type": "object",
            "properties": {
                "total_installed_power": _measured_value_with_unit("kW(e)"),
                "refrigeration_power": _measured_value_with_unit("kW(e)"),
                "process_power": _measured_value_with_unit("kW(e)"),
                "lighting_power": _measured_value_with_unit("kW(e)"),
                "auxiliary_power": _measured_value_with_unit("kW(e)"),
            },
            "additionalProperties": False,
        },
        "scheme_comparison": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "schemes": {"type": "array", "items": {"type": "object"}},
                "recommended_scheme": {"type": "string"},
                "generator_version": {"type": "string"},
                "persisted_content_hash": {"type": "string"},
                "comparison_metrics": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        "investment_estimate": {
            "type": "object",
            "properties": {
                "total_investment": {"type": "number"},
                "breakdown": {"type": "object"},
            },
            "additionalProperties": False,
        },
        "risks_and_missing_information": {
            "type": "object",
            "properties": {
                "risks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description", "severity"],
                        "properties": {
                            "description": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                            "mitigation": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                "missing_information": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description"],
                        "properties": {
                            "description": {"type": "string"},
                            "impact": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "quality_summary": {
            "type": "object",
            "required": ["total_findings", "blocker_count", "warning_count", "info_count"],
            "properties": {
                "total_findings": {"type": "integer", "minimum": 0},
                "blocker_count": {"type": "integer", "minimum": 0},
                "warning_count": {"type": "integer", "minimum": 0},
                "info_count": {"type": "integer", "minimum": 0},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["code", "severity", "message"],
                        "properties": {
                            "code": {"type": "string"},
                            "severity": {"type": "string", "enum": ["info", "warning", "blocker"]},
                            "section_key": {"type": "string"},
                            "field_path": {"type": "string"},
                            "message": {"type": "string"},
                            "remediation": {"type": "string"},
                            "source_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["section_key", "field_path", "source_type", "source_id"],
                "properties": {
                    "section_key": {"type": "string"},
                    "field_path": {"type": "string"},
                    "source_type": {"type": "string"},
                    "source_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "tool_version": {"type": "string"},
                    "result_id": {"type": "string"},
                    "content_hash": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "provenance": {
            "type": "object",
            "required": ["content_hash", "canonical_hash"],
            "properties": {
                "content_hash": {"type": "string"},
                "canonical_hash": {"type": "string"},
                "selection_rules": {"type": "object"},
                "assembly_timestamp": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


def get_schema(report_type: str, version: str = "1.0.0") -> dict[str, Any]:
    """Return the JSON Schema for the given report type and version."""
    key = f"{report_type}@{version}"
    schemas: dict[str, dict[str, Any]] = {
        "cold_storage_concept_design@1.0.0": COLD_STORAGE_CONCEPT_DESIGN_V1,
    }
    if key not in schemas:
        raise ValueError(f"Unknown report schema: {key}")
    return schemas[key]
