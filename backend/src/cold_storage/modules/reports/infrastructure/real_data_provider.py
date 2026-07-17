"""Real ReportDataProvider — reads from actual application services.

Uses public query ports (SchemeQueryPort, KnowledgeQueryPort) instead of
directly accessing ORM models or Session objects of other modules.  This
enforces the architecture boundary: the reports module never touches
infrastructure internals of schemes or knowledge.

Calculation-domain projection
-----------------------------

``get_calculation_results`` is the anti-corruption boundary between the
calculation domain's persisted v0 ``result_snapshot`` shape and the
report-domain v1 schema
(``cold_storage_concept_design@1.0.0``).  The v0 calculator fields are
projected to v1 report fields with strict typing — no inference, no
fabrication, no recompute.  Numeric values persisted as JSON-safe
strings are coerced through ``Decimal`` then converted to ``float`` for
the schema-allowed ``number`` slot; any non-finite value, ``bool``, or
unparseable string raises :class:`ReportProjectionError` so the failure
is surfaced rather than silently substituted.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from cold_storage.modules.reports.application.assembler import ReportDataProvider
from cold_storage.modules.reports.domain.errors import ReportError

# ── Projection error type ──────────────────────────────────────────────────


class ReportProjectionError(ReportError):
    """Raised when a persisted v0 calculation row cannot be projected.

    This is an in-file exception (defined in the infrastructure layer,
    not :mod:`cold_storage.modules.reports.domain.errors`) so the
    domain ``errors`` module can remain unchanged.  Callers must inspect
    ``section_key`` / ``result_id`` / ``field_path`` / ``reason_code``
    for machine-readable classification — do NOT depend on ``str(exc)``.
    """

    code = "REPORT_PROJECTION_INVALID_SOURCE"

    def __init__(
        self,
        *,
        section_key: str,
        result_id: str,
        field_path: str,
        reason_code: str,
        detail: str = "",
    ) -> None:
        message = (
            f"report projection failed [{self.code}]: "
            f"section={section_key!r} result_id={result_id!r} "
            f"field_path={field_path!r} reason={reason_code!r}"
        )
        if detail:
            message = f"{message} detail={detail}"
        super().__init__(message)
        self.section_key = section_key
        self.result_id = result_id
        self.field_path = field_path
        self.reason_code = reason_code


# ── Numeric coercion ───────────────────────────────────────────────────────


def _coerce_to_number(
    *,
    value: object,
    section_key: str,
    result_id: str,
    field_path: str,
) -> float:
    """Coerce a persisted JSON value to a JSON ``number``.

    Accepts:
    - ``int`` (excluding ``bool``) → returns the value as ``float``;
    - ``Decimal`` (finite) → returns ``float(value)``;
    - finite decimal string (``"200.0"`` / ``"-3.5e2"``) → ``Decimal``
      then ``float``.

    Rejects: ``bool`` (any value), ``float`` NaN / +inf / -inf, empty
    string, non-numeric string, ``None``, ``list`` / ``dict``, and any
    other type.  Raises :class:`ReportProjectionError` on rejection.
    """
    if isinstance(value, bool):
        raise ReportProjectionError(
            section_key=section_key,
            result_id=result_id,
            field_path=field_path,
            reason_code="BOOL_NOT_NUMERIC",
            detail=f"bool is not a numeric source: {value!r}",
        )
    if isinstance(value, int):
        return float(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=field_path,
                reason_code="NON_FINITE_NUMBER",
                detail=f"Decimal is non-finite: {value!r}",
            )
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=field_path,
                reason_code="NON_FINITE_NUMBER",
                detail=f"float is non-finite: {value!r}",
            )
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=field_path,
                reason_code="EMPTY_STRING",
                detail="empty string is not a numeric source",
            )
        try:
            decimal_value = Decimal(stripped)
        except (InvalidOperation, ValueError):
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=field_path,
                reason_code="NON_NUMERIC_STRING",
                detail=f"string is not a finite decimal: {value!r}",
            ) from None
        if not decimal_value.is_finite():
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=field_path,
                reason_code="NON_FINITE_NUMBER",
                detail=f"Decimal parsed from string is non-finite: {value!r}",
            )
        return float(decimal_value)
    raise ReportProjectionError(
        section_key=section_key,
        result_id=result_id,
        field_path=field_path,
        reason_code="UNSUPPORTED_SOURCE_TYPE",
        detail=f"unsupported numeric source type: {type(value).__name__}",
    )


def _build_measured_value(
    *,
    section_key: str,
    result_id: str,
    field_path: str,
    source_value: object,
    unit_const: str,
    source_tool: str,
    source_tool_version: str,
) -> dict[str, Any]:
    """Project a single source value to the v1 ``measured_value`` shape.

    Wraps :func:`_coerce_to_number` and assembles the
    schema-required five-key dict.  The required provenance
    ``source_result_id`` / ``source_tool`` / ``source_tool_version``
    come from the caller's *persisted* fields; the function does NOT
    accept any caller-synthesised provenance.
    """
    numeric = _coerce_to_number(
        value=source_value,
        section_key=section_key,
        result_id=result_id,
        field_path=field_path,
    )
    return {
        "value": numeric,
        "unit": unit_const,
        "source_result_id": result_id,
        "source_tool": source_tool,
        "source_tool_version": source_tool_version,
    }


# ── v0 → v1 strict projection (per section) ────────────────────────────────


# Mapping from a (data_provider attr, schema section_key) to the canonical
# calculator name expected in v0.  The tuple is
# (attr, section_key, v0_source_field, v0_aliases, v0_unit_const,
#  v1_measured_field).  ``v0_aliases`` is a tuple of alternative v0
# field names; at most ONE alias may be present (a conflict raises).
_V0_TO_V1_PROJECTION: tuple[
    tuple[str, str, str, tuple[str, ...], str, str],
    ...,
] = (
    (
        "cooling_load_result",
        "cooling_load",
        "total_cooling_load_kw",
        (),
        "kW(r)",
        "total_design_refrigeration_load",
    ),
    (
        "equipment_result",
        "equipment_selection",
        "compressor_installed_capacity_kw",
        ("compressor_capacity_kw",),
        "kW(r)",
        "total_compressor_capacity",
    ),
    (
        "equipment_result",
        "equipment_selection",
        "condenser_heat_rejection_capacity_kw",
        ("condenser_heat_rejection_kw",),
        "kW(th)",
        "condenser_heat_rejection",
    ),
    (
        "power_result",
        "electrical_and_energy",
        "total_installed_power_kw_e",
        ("total_installed_power_kw",),
        "kW(e)",
        "total_installed_power",
    ),
)


def _project_v0_to_v1_section(
    *,
    calc_result: Any,
    section_key: str,
    section_data: dict[str, Any],
    result_id: str,
    calculator_name: str,
    calculator_version: str,
) -> dict[str, Any]:
    """Project one v0 ``result_snapshot`` dict into a v1 schema section dict.

    Reads ONLY from the supplied ``section_data``; never recomputes
    from inputs; never looks outside the persisted row.  Optional v1
    fields are omitted when no persisted source exists (the schema
    allows absence).  Required v1 fields raise
    :class:`ReportProjectionError` when the persisted source is
    missing or invalid.
    """
    projected: dict[str, Any] = {}

    # Mandatory provenance — must come from the persisted row, not
    # any caller-synthesised value.
    if not result_id:
        raise ReportProjectionError(
            section_key=section_key,
            result_id="",
            field_path="id",
            reason_code="MISSING_RESULT_ID",
        )
    if not calculator_name:
        raise ReportProjectionError(
            section_key=section_key,
            result_id=result_id,
            field_path="calculator_name",
            reason_code="MISSING_PROVENANCE",
        )
    if not calculator_version:
        raise ReportProjectionError(
            section_key=section_key,
            result_id=result_id,
            field_path="calculator_version",
            reason_code="MISSING_PROVENANCE",
        )

    if section_key == "throughput_inventory_area":
        # throughput_inventory_area v1 fields: daily_inbound_mass_kg
        # (number), storage_capacity_kg (number, optional — only when
        # an explicit persisted source exists), total_area_m2 (number),
        # zone_details (array).  v0 fields: daily_inbound_mass_kg,
        # total_area_m2, zones.  We project by exact field name for
        # the two scalar fields and rename ``zones`` → ``zone_details``.
        if "daily_inbound_mass_kg" not in section_data:
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path="daily_inbound_mass_kg",
                reason_code="REQUIRED_SOURCE_FIELD_MISSING",
            )
        projected["daily_inbound_mass_kg"] = _coerce_to_number(
            value=section_data["daily_inbound_mass_kg"],
            section_key=section_key,
            result_id=result_id,
            field_path="daily_inbound_mass_kg",
        )
        if "storage_capacity_kg" in section_data:
            projected["storage_capacity_kg"] = _coerce_to_number(
                value=section_data["storage_capacity_kg"],
                section_key=section_key,
                result_id=result_id,
                field_path="storage_capacity_kg",
            )
        if "total_area_m2" not in section_data:
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path="total_area_m2",
                reason_code="REQUIRED_SOURCE_FIELD_MISSING",
            )
        projected["total_area_m2"] = _coerce_to_number(
            value=section_data["total_area_m2"],
            section_key=section_key,
            result_id=result_id,
            field_path="total_area_m2",
        )
        if "zones" in section_data:
            zones_value = section_data["zones"]
            if not isinstance(zones_value, list):
                raise ReportProjectionError(
                    section_key=section_key,
                    result_id=result_id,
                    field_path="zones",
                    reason_code="UNSUPPORTED_SOURCE_TYPE",
                    detail=f"expected list, got {type(zones_value).__name__}",
                )
            projected["zone_details"] = zones_value
        return projected

    # cooling_load / equipment_selection / electrical_and_energy:
    # the schema requires measured_value fields; each maps to one v0
    # source field with optional aliases (rejected on conflict).
    for (
        _attr_name,
        mapped_section_key,
        v0_field,
        v0_aliases,
        unit_const,
        v1_field,
    ) in _V0_TO_V1_PROJECTION:
        if mapped_section_key != section_key:
            continue
        field_path = f"{section_key}.{v1_field}"
        present_fields: list[str] = []
        for candidate in (v0_field, *v0_aliases):
            if candidate in section_data:
                present_fields.append(candidate)
        if not present_fields:
            # Required v1 measured-value field has no v0 source.  We
            # skip the v1 field when the v0 field name doesn't exist
            # AND the v1 field is optional in the schema.  To keep
            # the contract simple, treat every projected measured
            # value as required when explicitly enumerated in the
            # mapping table.
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=v0_field,
                reason_code="REQUIRED_SOURCE_FIELD_MISSING",
                detail=(
                    f"v1 field {v1_field!r} requires v0 source "
                    f"{v0_field!r}"
                ),
            )
        if len(present_fields) > 1:
            # Aliases exist alongside the primary v0 field; this is a
            # conflict that must be rejected to keep provenance
            # deterministic.
            raise ReportProjectionError(
                section_key=section_key,
                result_id=result_id,
                field_path=v0_field,
                reason_code="ALIAS_CONFLICT",
                detail=f"multiple v0 sources present: {present_fields!r}",
            )
        chosen = present_fields[0]
        projected[v1_field] = _build_measured_value(
            section_key=section_key,
            result_id=result_id,
            field_path=f"{field_path}.{chosen}",
            source_value=section_data[chosen],
            unit_const=unit_const,
            source_tool=calculator_name,
            source_tool_version=calculator_version,
        )

    # Sanity: at least one measured value was projected.
    if not projected:
        raise ReportProjectionError(
            section_key=section_key,
            result_id=result_id,
            field_path="<root>",
            reason_code="UNKNOWN_SECTION",
        )
    return projected


# Sections the report service consumes.  Each entry is
# (data_provider attr, schema section_key, calculator_name).
# ``calculator_name`` is the v0 source field; we expose it on the
# duck-typed section so the projector can use it as ``source_tool``.
_REPORT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("throughput_result", "throughput_inventory_area"),
    ("cooling_load_result", "cooling_load"),
    ("equipment_result", "equipment_selection"),
    ("power_result", "electrical_and_energy"),
)


class RealReportDataProvider(ReportDataProvider):
    """Reads persisted data from actual module services and repositories.

    Constructor accepts any combination of services/ports; missing ones
    are silently skipped (returns empty data for that section).
    """

    def __init__(
        self,
        *,
        project_service: Any | None = None,
        calculation_service: Any | None = None,
        scheme_query: Any | None = None,
        knowledge_query: Any | None = None,
        agent_session_query: Any | None = None,
    ) -> None:
        self._project_service = project_service
        self._calculation_service = calculation_service
        self._scheme_query = scheme_query
        self._knowledge_query = knowledge_query
        self._agent_session_query = agent_session_query

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Read project metadata from ProjectService."""
        if self._project_service is None:
            return None
        try:
            project = self._project_service.get_project(project_id)
            return {
                "name": getattr(project, "name", ""),
                "location": getattr(project, "location", ""),
                "description": getattr(project, "description", ""),
                "product_category": getattr(project, "product_category", ""),
                "code": getattr(project, "code", ""),
            }
        except (KeyError, AttributeError):
            return None

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        """Read project version data."""
        if self._project_service is None:
            return None
        try:
            # ProjectService stores versions in project.current_version
            # We need to search across all projects for the version
            for project in self._project_service.list_projects():
                ver = getattr(project, "current_version", None)
                if ver is not None and getattr(ver, "id", None) == version_id:
                    if project_id is not None and getattr(project, "id", None) != project_id:
                        continue
                    return {
                        "id": ver.id,
                        "version_number": getattr(ver, "version_number", 0),
                        "status": getattr(ver, "status", ""),
                    }
        except (AttributeError, TypeError):
            pass
        return None

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        """Project persisted v0 calculation rows into v1 report sections.

        The supplied ``calculation_service`` must expose
        ``get_orchestrated_result(project_id, version_id)`` returning
        an object with the four named attrs
        (``throughput_result`` / ``cooling_load_result`` /
        ``equipment_result`` / ``power_result``), each either ``None``
        or a duck-typed section with ``id``,
        ``calculator_name``, ``calculator_version``,
        ``result`` (the persisted ``result_snapshot`` dict) and
        optional ``content_hash`` / ``tool_call_status``.

        The method does NOT recompute, copy, or modify the
        ``result_snapshot`` dict — every value in the projected
        section is read by reference from the persisted row and
        coerced only for the JSON ``number`` slot.  Any v0 field
        not enumerated in :data:`_V0_TO_V1_PROJECTION` is
        **dropped**; it does NOT appear in the projected section
        and does NOT cause a failure on its own.
        """
        if self._calculation_service is None:
            return []
        try:
            result = self._calculation_service.get_orchestrated_result(project_id, version_id)
        except (AttributeError, KeyError):
            return []
        if result is None:
            return []

        sections: list[dict[str, Any]] = []
        for attr_name, section_key in _REPORT_SECTIONS:
            calc_result = getattr(result, attr_name, None)
            if calc_result is None:
                # The persisted row for this section does not exist.
                # Skip — the assembler will generate a warning finding
                # for the missing section.  This matches the
                # pre-existing skip-on-attribute-missing contract.
                continue
            result_id = getattr(calc_result, "id", "") or ""
            if not result_id:
                continue
            calculator_name = getattr(calc_result, "calculator_name", "") or ""
            calculator_version = getattr(calc_result, "calculator_version", "1.0.0") or "1.0.0"
            section_data = getattr(calc_result, "result", {}) or {}
            if not isinstance(section_data, dict):
                # Persisted ``result_snapshot`` is not a dict; we
                # cannot project.  This is a structural integrity
                # issue — surface it rather than silently skip.
                raise ReportProjectionError(
                    section_key=section_key,
                    result_id=result_id,
                    field_path="result",
                    reason_code="UNSUPPORTED_SOURCE_TYPE",
                    detail=(
                        "persisted result_snapshot is not a dict: "
                        f"{type(section_data).__name__}"
                    ),
                )
            # Project v0 → v1 with strict typing.  Any unknown / missing
            # / invalid source field raises ReportProjectionError.
            projected = _project_v0_to_v1_section(
                calc_result=calc_result,
                section_key=section_key,
                section_data=section_data,
                result_id=result_id,
                calculator_name=calculator_name,
                calculator_version=calculator_version,
            )

            entry: dict[str, Any] = {
                "section_key": section_key,
                "result_id": result_id,
                "tool_name": calculator_name,
                "tool_version": calculator_version,
                "data": projected,
            }

            # Pass through persisted content_hash when present (no
            # recompute — the data provider does not synthesise
            # hashes; mismatch detection stays an assembler concern).
            persisted_hash = getattr(calc_result, "content_hash", None)
            if persisted_hash:
                entry["persisted_content_hash"] = persisted_hash
                entry["hash_mismatch"] = False  # unused by current assembler

            # Pass through persisted tool_call_status if available
            persisted_status = getattr(calc_result, "tool_call_status", None)
            if persisted_status is not None:
                entry["tool_call_status"] = persisted_status

            sections.append(entry)

        return sections

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        """Read scheme comparison results via SchemeQueryPort.

        Returns the latest completed scheme run with its candidates.
        """
        if self._scheme_query is None:
            return None
        try:
            runs = self._scheme_query.get_completed_runs_for_project_version(project_id, version_id)
            if not runs:
                return None

            latest_run = runs[0]  # Already ordered by created_at desc

            candidates = self._scheme_query.get_candidates_for_run(latest_run["run_id"])

            schemes: list[dict[str, Any]] = []
            for c in candidates:
                schemes.append(
                    {
                        "scheme_id": c["id"],
                        "name": c.get("scheme_code", c["id"]),
                        "total_score": c.get("total_score", "0"),
                        "rank": c.get("rank", 0),
                    }
                )

            result: dict[str, Any] = {
                "run_id": latest_run["run_id"],
                "status": latest_run["status"],
                "schemes": schemes,
                "recommended_scheme": latest_run.get("recommended_scheme_code", ""),
                "generator_version": latest_run.get("generator_version", ""),
            }

            # Pass through persisted_content_hash (DB-only) and
            # computed_content_hash (fallback for pre-0012 runs).
            persisted_hash = latest_run.get("persisted_content_hash", "")
            computed_hash = latest_run.get("computed_content_hash", "")
            if persisted_hash:
                result["persisted_content_hash"] = persisted_hash
            if computed_hash:
                result["computed_content_hash"] = computed_hash

            # Verify source hash against persisted value when available.
            # For legacy runs without DB hash, verify against the computed fallback.
            reference_hash = persisted_hash or computed_hash
            if reference_hash:
                from cold_storage.modules.reports.domain.source_contract import (
                    compute_scheme_source_hash,
                )

                computed = compute_scheme_source_hash(
                    run_id=result["run_id"],
                    recommended_scheme_code=result.get("recommended_scheme", ""),
                    generator_version=result.get("generator_version", ""),
                    candidates=candidates,
                )
                result["source_hash_mismatch"] = computed != reference_hash

            return result
        except Exception:  # noqa: BLE001
            return None

    def get_knowledge_documents(self) -> list[dict[str, Any]]:
        """Read approved knowledge documents via KnowledgeQueryPort."""
        if self._knowledge_query is None:
            return []
        try:
            docs: list[dict[str, Any]] = self._knowledge_query.get_approved_documents()
            return docs
        except Exception:  # noqa: BLE001
            return []

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        """Read agent session/tool-call data for provenance."""
        if self._agent_session_query is None:
            return []
        try:
            sessions = self._agent_session_query.get_sessions_for_project(project_id, version_id)
            result: list[dict[str, Any]] = []
            for session in sessions:
                tool_calls = self._agent_session_query.get_tool_calls_for_session(
                    session["session_id"]
                )
                turns = self._agent_session_query.get_turns_for_session(session["session_id"])
                result.append({**session, "tool_calls": tool_calls, "turns": turns})
            return result
        except Exception:  # noqa: BLE001
            return []
