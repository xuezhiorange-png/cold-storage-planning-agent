"""Quality gate evaluation for report revisions.

Checks the assembled report content and source references against a
structured set of rules.  Returns machine-readable findings.
"""

from __future__ import annotations

import re
from typing import Any

from cold_storage.modules.reports.domain.enums import QualitySeverity


def _finding(
    code: str,
    severity: QualitySeverity,
    section_key: str,
    field_path: str,
    message: str,
    source_ids: list[str] | None = None,
    remediation: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity.value,
        "section_key": section_key,
        "field_path": field_path,
        "message": message,
        "source_ids": source_ids or [],
        "remediation": remediation,
    }


def evaluate_quality(
    content: dict[str, Any],
    source_refs: list[dict[str, Any]],
    *,
    required_sections: list[str] | tuple[str, ...] | None = None,
    required_calc_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate report content and return quality findings."""
    findings: list[dict[str, Any]] = []

    # 1. Required sections check — missing section is a BLOCKER
    if required_sections:
        for section in required_sections:
            if section not in content or content[section] is None:
                findings.append(
                    _finding(
                        code="MISSING_REQUIRED_SECTION",
                        severity=QualitySeverity.BLOCKER,
                        section_key=section,
                        field_path=section,
                        message=f"Required section '{section}' is missing or null",
                        remediation=f"Provide data for section '{section}'",
                    )
                )

    # 2. Required engineering result fields — missing key calculations → BLOCKER
    if required_calc_fields:
        _check_required_calc_fields(content, required_calc_fields, findings)

    # 3. Check for not_calculated / placeholder / default / estimated values
    _check_not_calculated(content, "", findings)

    # 4. Unit dimension isolation
    _check_units(content, "", findings)

    # 5. Source reference completeness + verification
    _check_source_refs(source_refs, findings)

    return findings


# ---------------------------------------------------------------------------
# Required engineering result fields
# ---------------------------------------------------------------------------


def _check_required_calc_fields(
    content: dict[str, Any],
    required_fields: list[str],
    findings: list[dict[str, Any]],
) -> None:
    """Check that key engineering result fields are present and non-empty.

    Each required field is a dotted path like 'cooling_load.total_design_refrigeration_load'.
    Missing path → BLOCKER.
    """
    for field_path in required_fields:
        parts = field_path.split(".")
        obj: Any = content
        found = True
        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                found = False
                break
        section = parts[0] if parts else "root"
        if not found or obj is None:
            findings.append(
                _finding(
                    code="MISSING_REQUIRED_ENGINEERING_RESULT",
                    severity=QualitySeverity.BLOCKER,
                    section_key=section,
                    field_path=field_path,
                    message=f"Required engineering result '{field_path}' is missing",
                    remediation=f"Ensure calculation result for '{field_path}' is present",
                )
            )


def _check_not_calculated(obj: Any, path: str, findings: list[dict[str, Any]]) -> None:
    """Recursively check for not_calculated/placeholder/default/estimated values."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            cur = f"{path}.{key}" if path else key
            _blocker_values = ("not_calculated", "placeholder", "default", "estimated")
            if isinstance(val, str) and val in _blocker_values:
                findings.append(
                    _finding(
                        code="NOT_CALCULATED_VALUE",
                        severity=QualitySeverity.BLOCKER,
                        section_key=path.split(".")[0] if path else "root",
                        field_path=cur,
                        message=f"Field contains '{val}' which is not a real calculated result",
                    )
                )
            elif isinstance(val, dict):
                _check_not_calculated(val, cur, findings)
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    _check_not_calculated(item, f"{cur}[{i}]", findings)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_not_calculated(item, f"{path}[{i}]", findings)


# ---------------------------------------------------------------------------
# Field-level unit dimension constraints
# ---------------------------------------------------------------------------

# Maps a regex (matched against the *base* field name, i.e. without the
# trailing ``_unit`` suffix) to the expected unit string.
_FIELD_UNIT_CONSTRAINTS: dict[str, str] = {
    r"total_design_refrigeration_load": "kW(r)",
    r"compressor_capacity": "kW(r)",
    r"compressor_input(?:_power)?": "kW(e)",
    r"installed_power": "kW(e)",
    r"process_power": "kW(e)",
    r"lighting_power": "kW(e)",
    r"auxiliary_power": "kW(e)",
    r"refrigeration_power": "kW(e)",
    r"condenser_heat_rejection": "kW(th)",
}

_ENERGY_FIELD_PATTERNS: list[str] = [
    r"energy$",
    r"consumption$",
    r"_kwh$",
]


def _expected_unit_for_field(field_path: str) -> str | None:
    """Return the expected unit for a given base field path, or None."""
    for pattern, unit in _FIELD_UNIT_CONSTRAINTS.items():
        if re.search(pattern, field_path):
            return unit
    for pattern in _ENERGY_FIELD_PATTERNS:
        if re.search(pattern, field_path):
            return "kWh"
    return None


def _check_units(obj: Any, path: str, findings: list[dict[str, Any]]) -> None:
    """Check that unit fields use correct dimension-specific units."""
    if not isinstance(obj, dict):
        return
    VALID_UNITS = {"kW(r)", "kW(e)", "kW(th)", "kWh"}
    for key, val in obj.items():
        cur = f"{path}.{key}" if path else key
        if key.endswith("_unit") and isinstance(val, str):
            if val not in VALID_UNITS:
                findings.append(
                    _finding(
                        code="INVALID_UNIT",
                        severity=QualitySeverity.BLOCKER,
                        section_key=path.split(".")[0] if path else "root",
                        field_path=cur,
                        message=f"Invalid unit '{val}'; must be one of {VALID_UNITS}",
                    )
                )
            else:
                # Check field-level dimension constraint
                # Strip the trailing _unit to get the base field name
                base_field = cur[: -len("_unit")] if cur.endswith("_unit") else cur
                expected = _expected_unit_for_field(base_field)
                if expected is not None and val != expected:
                    findings.append(
                        _finding(
                            code="WRONG_UNIT_DIMENSION",
                            severity=QualitySeverity.BLOCKER,
                            section_key=path.split(".")[0] if path else "root",
                            field_path=cur,
                            message=(
                                f"Unit mismatch: field '{cur}' expects '{expected}' but got '{val}'"
                            ),
                        )
                    )
        elif isinstance(val, dict):
            _check_units(val, cur, findings)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                _check_units(item, f"{cur}[{i}]", findings)


# ---------------------------------------------------------------------------
# Source reference completeness + verification
# ---------------------------------------------------------------------------


def _check_source_refs(
    source_refs: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    """Check source references have required provenance fields.

    For calculation_result, scheme_result, knowledge_revision, agent_tool_call:
      - result_id → BLOCKER if missing
      - tool_version → BLOCKER if missing
      - content_hash → BLOCKER if missing

    Source verification data (if present) is also checked:
      - tool_call_status: must be confirmed/completed/success → BLOCKER otherwise
      - knowledge_status: must be approved → BLOCKER otherwise
      - source_exists: False → BLOCKER
      - hash_mismatch: True → BLOCKER
    """
    VERIFIED_TYPES = {
        "calculation_result",
        "scheme_result",
        "knowledge_revision",
        "agent_tool_call",
    }
    for ref in source_refs:
        source_type = ref.get("source_type", "")
        section = ref.get("section_key", "unknown")
        field_path = ref.get("field_path", "")

        if source_type in VERIFIED_TYPES:
            # result_id required
            if not ref.get("result_id"):
                findings.append(
                    _finding(
                        code="SOURCE_MISSING_RESULT_ID",
                        severity=QualitySeverity.BLOCKER,
                        section_key=section,
                        field_path=field_path,
                        message=f"Source '{source_type}' missing result_id",
                    )
                )
            # tool_version required
            if not ref.get("tool_version"):
                findings.append(
                    _finding(
                        code="SOURCE_MISSING_TOOL_VERSION",
                        severity=QualitySeverity.BLOCKER,
                        section_key=section,
                        field_path=field_path,
                        message=f"Source '{source_type}' missing tool_version",
                    )
                )
            # content_hash required (BLOCKER, not warning)
            if not ref.get("content_hash"):
                findings.append(
                    _finding(
                        code="SOURCE_MISSING_CONTENT_HASH",
                        severity=QualitySeverity.BLOCKER,
                        section_key=section,
                        field_path=field_path,
                        message=f"Source '{source_type}' missing content_hash",
                    )
                )

        # Source verification checks (when verification data is attached)
        tool_call_status = ref.get("tool_call_status")
        if tool_call_status is not None and tool_call_status not in (
            "confirmed",
            "completed",
            "success",
        ):
            findings.append(
                _finding(
                    code="SOURCE_TOOL_CALL_INVALID_STATUS",
                    severity=QualitySeverity.BLOCKER,
                    section_key=section,
                    field_path=field_path,
                    message=(
                        f"Source tool call has invalid status '{tool_call_status}'; "
                        "must be confirmed/completed/success"
                    ),
                )
            )

        knowledge_status = ref.get("knowledge_status")
        if knowledge_status is not None and knowledge_status != "approved":
            findings.append(
                _finding(
                    code="SOURCE_KNOWLEDGE_NOT_APPROVED",
                    severity=QualitySeverity.BLOCKER,
                    section_key=section,
                    field_path=field_path,
                    message=(
                        f"Source knowledge revision has status '{knowledge_status}'; "
                        "must be approved"
                    ),
                )
            )

        source_exists = ref.get("source_exists")
        if source_exists is False:
            findings.append(
                _finding(
                    code="SOURCE_DELETED_OR_UNREADABLE",
                    severity=QualitySeverity.BLOCKER,
                    section_key=section,
                    field_path=field_path,
                    message="Source no longer exists or is unreadable",
                )
            )

        hash_mismatch = ref.get("hash_mismatch")
        if hash_mismatch is True:
            findings.append(
                _finding(
                    code="SOURCE_HASH_MISMATCH",
                    severity=QualitySeverity.BLOCKER,
                    section_key=section,
                    field_path=field_path,
                    message="Stored source hash does not match report citation hash",
                )
            )

    # Non-verified types (project, project_version, agent_session, agent_turn)
    # only need content_hash
    for ref in source_refs:
        source_type = ref.get("source_type", "")
        if source_type not in VERIFIED_TYPES:
            section = ref.get("section_key", "unknown")
            field_path = ref.get("field_path", "")
            if not ref.get("content_hash"):
                findings.append(
                    _finding(
                        code="SOURCE_MISSING_CONTENT_HASH",
                        severity=QualitySeverity.WARNING,
                        section_key=section,
                        field_path=field_path,
                        message=f"Source '{source_type}' missing content_hash",
                    )
                )


def has_blockers(findings: list[dict[str, Any]]) -> bool:
    """Return True if any finding has severity=blocker."""
    return any(f.get("severity") == QualitySeverity.BLOCKER.value for f in findings)


def get_blockers(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in findings if f.get("severity") == QualitySeverity.BLOCKER.value]
