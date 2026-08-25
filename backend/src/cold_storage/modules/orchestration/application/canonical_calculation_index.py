"""Shared canonical calculation run indexing for downstream consumers (V0.5 P3).

Indexes persisted calculation rows by canonical calculator identity or stage
using last-write-wins ordering on ``(created_at, id)``, independent of input
order.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    resolve_canonical_calculator_name,
    stage_for_canonical_calculator,
)


def _normalize_created_at(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _record_sort_key(record: Any) -> tuple[str, str]:
    if isinstance(record, dict):
        record_id = str(record.get("calculation_id") or record.get("id", ""))
        created_at = record.get("created_at")
    else:
        record_id = str(getattr(record, "id", ""))
        created_at = getattr(record, "created_at", None)
    return (_normalize_created_at(created_at), record_id)


def _is_newer_than(candidate: Any, incumbent: Any) -> bool:
    return _record_sort_key(candidate) > _record_sort_key(incumbent)


def _matches_project_context(
    record: Any,
    *,
    project_id: str,
    project_version_id: str,
) -> bool:
    if isinstance(record, dict):
        record_project_id = str(record.get("project_id", ""))
        record_version_id = str(record.get("project_version_id", ""))
    else:
        record_project_id = str(getattr(record, "project_id", ""))
        record_version_id = str(getattr(record, "project_version_id", ""))
    if record_project_id and record_project_id != project_id:
        return False
    return not (record_version_id and record_version_id != project_version_id)


def index_canonical_calculation_runs(
    calculations: list[dict[str, Any]],
    *,
    project_id: str,
    project_version_id: str,
) -> dict[str, dict[str, Any]]:
    """Index latest canonical calculation runs keyed by calculator identity."""
    indexed: dict[str, dict[str, Any]] = {}
    for record in calculations:
        if not _matches_project_context(
            record,
            project_id=project_id,
            project_version_id=project_version_id,
        ):
            continue

        raw_name = str(record.get("calculator_name", ""))
        canonical_name = resolve_canonical_calculator_name(raw_name)
        if canonical_name is None:
            continue

        existing = indexed.get(canonical_name)
        if existing is None or _is_newer_than(record, existing):
            indexed[canonical_name] = record
    return indexed


def index_canonical_calculation_records(
    records: list[Any],
    *,
    project_id: str,
    project_version_id: str,
) -> dict[str, Any]:
    """Index latest canonical calculation ORM rows keyed by orchestration stage."""
    indexed: dict[str, Any] = {}
    for record in records:
        if str(getattr(record, "project_id", "")) != project_id:
            continue
        if str(getattr(record, "project_version_id", "")) != project_version_id:
            continue

        canonical_name = resolve_canonical_calculator_name(str(record.calculator_name))
        if canonical_name is None:
            continue
        stage = stage_for_canonical_calculator(canonical_name)
        if stage is None:
            continue

        existing = indexed.get(stage)
        if existing is None or _is_newer_than(record, existing):
            indexed[stage] = record
    return indexed
