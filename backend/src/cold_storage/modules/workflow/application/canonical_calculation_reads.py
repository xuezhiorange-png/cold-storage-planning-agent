"""Anti-corruption helpers for workflow canonical calculation reads (V0.5 P3)."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_CALCULATOR_NAMES,
    CANONICAL_STAGE_ORDER,
    STAGE_TO_CALCULATOR_NAME,
    resolve_canonical_calculator_name,
    stage_for_canonical_calculator,
)
from cold_storage.modules.orchestration.domain.dag import STAGE_UPSTREAM_PROVENANCE_KEYS

REQUIRED_SCHEME_CALCULATOR_NAMES = CANONICAL_CALCULATOR_NAMES


def index_canonical_calculation_runs(
    calculations: list[dict[str, Any]],
    *,
    project_id: str,
    project_version_id: str,
) -> dict[str, dict[str, Any]]:
    """Index latest canonical calculation runs keyed by calculator identity.

    Rows with project/version mismatch are ignored. Supplemental calculators
    such as ``power_configuration`` are never indexed as canonical slots.
    """
    indexed: dict[str, dict[str, Any]] = {}
    for record in calculations:
        record_project_id = str(record.get("project_id", ""))
        record_version_id = str(record.get("project_version_id", ""))
        if record_project_id and record_project_id != project_id:
            continue
        if record_version_id and record_version_id != project_version_id:
            continue

        raw_name = str(record.get("calculator_name", ""))
        canonical_name = resolve_canonical_calculator_name(raw_name)
        if canonical_name is None:
            continue
        if canonical_name not in indexed:
            indexed[canonical_name] = record
    return indexed


def missing_canonical_calculator_names(
    indexed: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(REQUIRED_SCHEME_CALCULATOR_NAMES - set(indexed))


def canonical_runs_requiring_review(
    indexed: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(
        name for name, record in indexed.items() if bool(record.get("requires_review"))
    )


def detect_canonical_lineage_stale_reasons(
    indexed: dict[str, dict[str, Any]],
) -> list[str]:
    """Detect upstream calculation_id / result_hash drift per P0 §4.4."""
    by_stage: dict[str, dict[str, Any]] = {}
    for calculator_name, record in indexed.items():
        stage = stage_for_canonical_calculator(calculator_name)
        if stage is not None:
            by_stage[stage] = record

    reasons: list[str] = []
    for stage in CANONICAL_STAGE_ORDER:
        if stage == "zone":
            continue
        record = by_stage.get(stage)
        if record is None:
            continue
        upstream_ids = record.get("upstream_calculation_ids")
        if not isinstance(upstream_ids, dict):
            continue
        expected_upstream = STAGE_UPSTREAM_PROVENANCE_KEYS.get(stage, frozenset())
        for upstream_stage in expected_upstream:
            upstream_record = by_stage.get(upstream_stage)
            if upstream_record is None:
                continue
            upstream_calc_id = str(upstream_record.get("calculation_id") or upstream_record.get("id", ""))
            bound_id = str(upstream_ids.get(upstream_stage, ""))
            if bound_id and upstream_calc_id and bound_id != upstream_calc_id:
                reasons.append(f"calculation_upstream_id_mismatch:{stage}:{upstream_stage}")
            upstream_hash = str(upstream_record.get("result_hash", ""))
            bound_hash = str(upstream_ids.get(f"{upstream_stage}_result_hash", ""))
            if bound_hash and upstream_hash and bound_hash != upstream_hash:
                reasons.append(f"calculation_upstream_hash_mismatch:{stage}:{upstream_stage}")
    return reasons


def canonical_stage_calculator_names() -> dict[str, str]:
    return dict(STAGE_TO_CALCULATOR_NAME)
