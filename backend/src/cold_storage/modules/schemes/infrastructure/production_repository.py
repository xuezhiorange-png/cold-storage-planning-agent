"""Infrastructure implementation of ProductionSchemeRunRepository.

Persists production scheme runs and candidates within the caller's session.
MUST NOT commit, rollback, close, or create sessions.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    PersistedSchemeRun,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeCandidateRecord,
    SchemeRunRecord,
)


class SqlAlchemyProductionSchemeRunRepository:
    """Persist production scheme runs using SQLAlchemy within caller's session."""

    def save_production_run(
        self,
        session: Any,
        /,
        *,
        run_id: str,
        project_id: str,
        project_version_id: str,
        weight_set_id: str,
        status: str,
        generator_version: str,
        source_snapshot_hash: str,
        input_snapshot: dict[str, Any],
        assumption_snapshot: dict[str, Any],
        comparison_snapshot: dict[str, Any],
        candidates_snapshot: dict[str, Any],
        requires_review: bool,
        recommended_scheme_code: str | None,
        warning_messages: list[str],
        content_hash: str,
        source_mode: str,
        source_binding_id: str,
        source_contract_version: str,
        binding_schema_version: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        authoritative_attempt_id: str,
        orchestration_fingerprint: str,
        zone_calculation_id: str,
        cooling_load_calculation_id: str,
        equipment_calculation_id: str,
        power_calculation_id: str,
        investment_calculation_id: str,
        zone_result_hash: str,
        cooling_load_result_hash: str,
        equipment_result_hash: str,
        power_result_hash: str,
        investment_result_hash: str,
        combined_source_hash: str,
        weight_set_revision_id: str,
        weight_set_content_hash: str,
        weight_set_generator_compatibility_version: str,
        profile_codes: tuple[str, ...],
        profile_parameters: dict[str, dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> PersistedSchemeRun:
        run_rec = SchemeRunRecord(
            id=run_id,
            project_id=project_id,
            project_version_id=project_version_id,
            weight_set_id=weight_set_id,
            status=status,
            generator_version=generator_version,
            source_snapshot_hash=source_snapshot_hash,
            input_snapshot=input_snapshot,
            assumption_snapshot={
                **assumption_snapshot,
                "profile_codes": list(profile_codes),
                "profile_parameters": dict(profile_parameters),
            },
            comparison_snapshot=comparison_snapshot,
            candidates_snapshot=candidates_snapshot,
            requires_review=requires_review,
            recommended_scheme_code=recommended_scheme_code,
            warning_messages=warning_messages,
            content_hash=content_hash,
            source_mode=source_mode,
            source_binding_id=source_binding_id,
            source_contract_version=source_contract_version,
            weight_set_revision_id=weight_set_revision_id,
            weight_set_content_hash=weight_set_content_hash,
            weight_set_generator_compatibility_version=(weight_set_generator_compatibility_version),
            combined_source_hash=combined_source_hash,
            binding_schema_version=binding_schema_version,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            authoritative_attempt_id=authoritative_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            zone_calculation_id=zone_calculation_id,
            cooling_load_calculation_id=cooling_load_calculation_id,
            equipment_calculation_id=equipment_calculation_id,
            power_calculation_id=power_calculation_id,
            investment_calculation_id=investment_calculation_id,
            zone_result_hash=zone_result_hash,
            cooling_load_result_hash=cooling_load_result_hash,
            equipment_result_hash=equipment_result_hash,
            power_result_hash=power_result_hash,
            investment_result_hash=investment_result_hash,
        )
        session.add(run_rec)

        for cand_data in candidates:
            cand_rec = SchemeCandidateRecord(
                id=cand_data["id"],
                scheme_run_id=run_id,
                scheme_code=cand_data["scheme_code"],
                profile_code=cand_data["profile_code"],
                feasible=cand_data["feasible"],
                rank=cand_data.get("rank"),
                total_score=cand_data.get("total_score"),
                score_breakdown_snapshot=cand_data.get("score_breakdown_snapshot", {}),
                constraint_results=cand_data.get("constraint_results", []),
                result_snapshot=cand_data.get("result_snapshot", {}),
            )
            session.add(cand_rec)

        return PersistedSchemeRun(
            id=run_id,
            project_id=project_id,
            project_version_id=project_version_id,
            content_hash=content_hash,
            source_mode=source_mode,
            source_binding_id=source_binding_id,
            source_contract_version=source_contract_version,
            binding_schema_version=binding_schema_version,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            authoritative_attempt_id=authoritative_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            zone_calculation_id=zone_calculation_id,
            cooling_load_calculation_id=cooling_load_calculation_id,
            equipment_calculation_id=equipment_calculation_id,
            power_calculation_id=power_calculation_id,
            investment_calculation_id=investment_calculation_id,
            zone_result_hash=zone_result_hash,
            cooling_load_result_hash=cooling_load_result_hash,
            equipment_result_hash=equipment_result_hash,
            power_result_hash=power_result_hash,
            investment_result_hash=investment_result_hash,
            combined_source_hash=combined_source_hash,
            weight_set_id=weight_set_id,
            weight_set_revision_id=weight_set_revision_id,
            weight_set_content_hash=weight_set_content_hash,
            weight_set_generator_compatibility_version=(weight_set_generator_compatibility_version),
            generator_version=generator_version,
            profile_codes=profile_codes,
            profile_parameters=profile_parameters,
            candidates_count=len(candidates),
        )
