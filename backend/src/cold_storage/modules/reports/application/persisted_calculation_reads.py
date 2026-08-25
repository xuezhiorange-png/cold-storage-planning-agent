"""Read persisted canonical calculation rows for report assembly (V0.5 P3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cold_storage.modules.orchestration.application.canonical_calculation_index import (
    index_canonical_calculation_runs,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_STAGE_ORDER,
    STAGE_TO_CALCULATOR_NAME,
    resolve_canonical_calculator_name,
    stage_for_canonical_calculator,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    BUNDLE_SCHEMA_ID,
)

CANONICAL_STAGE_TO_REPORT_ATTR: dict[str, str] = {
    "zone": "throughput_result",
    "cooling_load": "cooling_load_result",
    "equipment": "equipment_result",
    "power": "power_result",
    "investment": "investment_result",
}

CANONICAL_CALCULATOR_TO_REPORT_SECTION: dict[str, str] = {
    "cold_room_zone_plan": "throughput_inventory_area",
    "cooling_load": "cooling_load",
    "equipment": "equipment_selection",
    "installed_power": "electrical_and_energy",
    "investment_estimate": "investment_estimate",
}


@dataclass(frozen=True, slots=True)
class ReportEngineeringContext:
    """Persisted engineering authority for report input/assumption sections."""

    input_conditions: dict[str, Any] | None
    assumptions: dict[str, Any] | None
    indexed_calculator_names: frozenset[str]
    stale_lineage_reasons: tuple[str, ...]


class PersistedCalculationQueryPort(Protocol):
    def get_orchestrated_result(
        self, project_id: str, project_version_id: str
    ) -> OrchestratedCalculationResult | None:
        """Return canonical persisted calculation sections for report assembly."""

    def get_report_engineering_context(
        self, project_id: str, project_version_id: str
    ) -> ReportEngineeringContext | None:
        """Return persisted engineering input/assumption authority for assembly."""


@dataclass
class CalculationSectionView:
    id: str
    calculator_name: str
    calculator_version: str
    result: dict[str, Any]
    content_hash: str | None = None
    tool_call_status: str | None = None


@dataclass
class OrchestratedCalculationResult:
    throughput_result: CalculationSectionView | None = None
    cooling_load_result: CalculationSectionView | None = None
    equipment_result: CalculationSectionView | None = None
    power_result: CalculationSectionView | None = None
    investment_result: CalculationSectionView | None = None


class ProjectServicePersistedCalculationQuery:
    """Application query port backed by ProjectService list_calculations."""

    def __init__(self, project_service: Any) -> None:
        self._project_service = project_service

    def get_orchestrated_result(
        self, project_id: str, project_version_id: str
    ) -> OrchestratedCalculationResult | None:
        version = self._resolve_version(project_id, project_version_id)
        if version is None:
            return None
        calculations = self._project_service.list_calculations(
            project_id,
            int(version.version_number),
        )
        indexed = index_canonical_calculation_runs(
            calculations,
            project_id=project_id,
            project_version_id=project_version_id,
        )
        return build_orchestrated_result_from_indexed(indexed)

    def get_report_engineering_context(
        self, project_id: str, project_version_id: str
    ) -> ReportEngineeringContext | None:
        version = self._resolve_version(project_id, project_version_id)
        if version is None:
            return None
        calculations = self._project_service.list_calculations(
            project_id,
            int(version.version_number),
        )
        indexed = index_canonical_calculation_runs(
            calculations,
            project_id=project_id,
            project_version_id=project_version_id,
        )
        if not indexed:
            return None
        from cold_storage.modules.workflow.application.canonical_calculation_reads import (
            detect_canonical_lineage_stale_reasons,
        )

        input_conditions = _input_conditions_from_version_snapshot(
            dict(getattr(version, "input_snapshot", {}) or {})
        )
        assumptions = _assumptions_from_persisted_sources(
            version_assumption_snapshot=dict(getattr(version, "assumption_snapshot", {}) or {}),
            indexed_calculations=indexed,
        )
        return ReportEngineeringContext(
            input_conditions=input_conditions,
            assumptions=assumptions,
            indexed_calculator_names=frozenset(indexed),
            stale_lineage_reasons=tuple(detect_canonical_lineage_stale_reasons(indexed)),
        )

    def _resolve_version(self, project_id: str, project_version_id: str) -> Any | None:
        project = self._project_service.get_project(project_id)
        for version in project.versions:
            if version.id == project_version_id:
                return version
        current = getattr(project, "current_version", None)
        if current is not None and current.id == project_version_id:
            return current
        return None


def build_orchestrated_result_from_indexed(
    indexed: dict[str, dict[str, Any]],
) -> OrchestratedCalculationResult | None:
    if not indexed:
        return None

    sections: dict[str, CalculationSectionView | None] = {
        "throughput_result": None,
        "cooling_load_result": None,
        "equipment_result": None,
        "power_result": None,
        "investment_result": None,
    }
    for stage in CANONICAL_STAGE_ORDER:
        calculator_name = STAGE_TO_CALCULATOR_NAME[stage]
        record = indexed.get(calculator_name)
        attr_name = CANONICAL_STAGE_TO_REPORT_ATTR[stage]
        if record is None:
            sections[attr_name] = None
            continue
        snapshot = record.get("result_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        sections[attr_name] = CalculationSectionView(
            id=str(record.get("calculation_id") or record.get("id", "")),
            calculator_name=calculator_name,
            calculator_version=str(record.get("calculator_version", "1.0.0")),
            result=snapshot,
            content_hash=str(record.get("result_hash")) if record.get("result_hash") else None,
            tool_call_status=None,
        )
    return OrchestratedCalculationResult(**sections)


def resolve_report_stage_for_calculator(calculator_name: str) -> str | None:
    stage = stage_for_canonical_calculator(
        resolve_canonical_calculator_name(calculator_name) or calculator_name
    )
    if stage is None:
        return None
    return stage


def _input_conditions_from_version_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if snapshot.get("schema_id") == BUNDLE_SCHEMA_ID:
        return _input_conditions_from_engineering_bundle(snapshot)
    return _input_conditions_from_execution_snapshot(snapshot)


def _input_conditions_from_engineering_bundle(bundle: dict[str, Any]) -> dict[str, Any] | None:
    cooling_section = bundle.get("cooling_load_inputs")
    if not isinstance(cooling_section, dict):
        return None
    raw_zones = cooling_section.get("zones")
    if not isinstance(raw_zones, list) or not raw_zones:
        return None

    zones: list[dict[str, Any]] = []
    temperature_levels: dict[str, dict[str, str]] = {}
    for zone in raw_zones:
        if not isinstance(zone, dict):
            continue
        projected_zone = _project_bundle_object_leaves(zone)
        if projected_zone:
            zones.append(projected_zone)
            level = projected_zone.get("temperature_level")
            if isinstance(level, str) and level:
                temperature_levels[level] = {"level": level}

    coefficients_used = _collect_coefficient_codes_from_bundle(bundle)
    if not zones and not coefficients_used:
        return None
    return {
        "zones": zones,
        "temperature_levels": list(temperature_levels.values()),
        "coefficients_used": coefficients_used,
    }


def _input_conditions_from_execution_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    cooling_stage = snapshot.get("cooling_load")
    if not isinstance(cooling_stage, dict):
        return None
    raw_zones = cooling_stage.get("zones")
    if not isinstance(raw_zones, list) or not raw_zones:
        return None

    zones: list[dict[str, Any]] = []
    temperature_levels: dict[str, dict[str, str]] = {}
    for zone in raw_zones:
        if not isinstance(zone, dict):
            continue
        zones.append(dict(zone))
        level = zone.get("temperature_level")
        if isinstance(level, str) and level:
            temperature_levels[level] = {"level": level}

    coefficients_used: list[str] = []
    for stage_payload in snapshot.values():
        if not isinstance(stage_payload, dict):
            continue
        coefficients = stage_payload.get("coefficients")
        if isinstance(coefficients, dict):
            for revision_ids in coefficients.values():
                if isinstance(revision_ids, dict):
                    for code in revision_ids:
                        if isinstance(code, str) and code:
                            coefficients_used.append(code)

    if not zones and not coefficients_used:
        return None
    return {
        "zones": zones,
        "temperature_levels": list(temperature_levels.values()),
        "coefficients_used": sorted(set(coefficients_used)),
    }


def _project_bundle_object_leaves(section: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key, leaf in section.items():
        if isinstance(leaf, dict) and "value" in leaf and "state" in leaf:
            value = leaf.get("value")
            if value is not None:
                projected[key] = value
        elif not isinstance(leaf, (dict, list)):
            projected[key] = leaf
    return projected


def _collect_coefficient_codes_from_bundle(bundle: dict[str, Any]) -> list[str]:
    codes: set[str] = set()
    coefficient_context = bundle.get("coefficient_context")
    if isinstance(coefficient_context, dict):
        demo_leaves = coefficient_context.get("demo_coefficient_leaves")
        if isinstance(demo_leaves, list):
            for leaf in demo_leaves:
                if isinstance(leaf, dict):
                    code = leaf.get("code")
                    if isinstance(code, str) and code:
                        codes.add(code)
    for section_name in ("cooling_load_inputs", "equipment_inputs", "zone_planning_inputs"):
        section = bundle.get(section_name)
        if not isinstance(section, dict):
            continue
        for key, leaf in section.items():
            if (
                isinstance(leaf, dict)
                and leaf.get("requires_review") is True
                and isinstance(key, str)
                and key not in {"zones", "systems", "coefficients"}
            ):
                codes.add(key)
    return sorted(codes)


def _assumptions_from_persisted_sources(
    *,
    version_assumption_snapshot: dict[str, Any],
    indexed_calculations: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def _append_item(description: object, source: str) -> None:
        if not isinstance(description, str):
            return
        text = description.strip()
        if not text or text in seen:
            return
        items.append({"description": text, "source": source})
        seen.add(text)

    snapshot_items = version_assumption_snapshot.get("items")
    if isinstance(snapshot_items, list):
        for entry in snapshot_items:
            if isinstance(entry, dict):
                _append_item(entry.get("description"), "project_version_assumption_snapshot")
            elif isinstance(entry, str):
                _append_item(entry, "project_version_assumption_snapshot")

    for calculator_name, record in indexed_calculations.items():
        assumptions = record.get("assumptions")
        if isinstance(assumptions, list):
            for assumption in assumptions:
                _append_item(assumption, f"calculation:{calculator_name}")

        coefficients = record.get("coefficients")
        if isinstance(coefficients, list):
            for coefficient in coefficients:
                if not isinstance(coefficient, dict):
                    continue
                requires_review = coefficient.get("requires_review")
                source_type = coefficient.get("source_type")
                validity_status = coefficient.get("validity_status")
                if (
                    requires_review is True
                    or source_type == "demo"
                    or validity_status in {"unverified", "conflict"}
                ):
                    description = coefficient.get("notes") or coefficient.get("name")
                    if description is None:
                        code = coefficient.get("code")
                        if isinstance(code, str):
                            description = f"Coefficient {code} requires review"
                    _append_item(description, f"coefficient:{calculator_name}")

    if not items:
        return None
    return {"items": items}


def build_input_conditions_from_execution_snapshot_and_coefficients(
    execution_snapshot: dict[str, Any],
    coefficient_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build report input_conditions from persisted orchestration snapshots."""
    input_conditions = _input_conditions_from_execution_snapshot(execution_snapshot)
    if input_conditions is None:
        return None
    if coefficient_context is None:
        return input_conditions

    coeff_codes = _collect_coefficient_codes_from_context(coefficient_context)
    if coeff_codes:
        merged = sorted(set(input_conditions.get("coefficients_used", [])) | set(coeff_codes))
        input_conditions = dict(input_conditions)
        input_conditions["coefficients_used"] = merged
    return input_conditions


def _collect_coefficient_codes_from_context(coefficient_context: dict[str, Any]) -> list[str]:
    codes: set[str] = set()
    coefficients = coefficient_context.get("coefficients")
    if isinstance(coefficients, list):
        for coefficient in coefficients:
            if isinstance(coefficient, dict):
                code = coefficient.get("code")
                if isinstance(code, str) and code:
                    codes.add(code)
    return sorted(codes)
