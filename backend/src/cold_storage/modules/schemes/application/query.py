"""Scheme query port - public read-only interface for scheme data.

This module defines the architecture boundary between the reports module
and the schemes module.  Reports consume scheme data through this port
without touching ORM models, Session objects, or infrastructure internals.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from cold_storage.modules.schemes.domain.models import (
    ReviewReason,
    review_reasons_to_json,
)

STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)


@dataclass(frozen=True, slots=True)
class SchemeReviewAuthority:
    """Typed, persisted SchemeRun review authority exposed to applications.

    The report module consumes this value as a snapshot.  It never receives a
    Scheme ORM record or a database session, and it cannot reconstruct review
    state from warning text.  The optional provenance fields are populated by
    the production readback adapter and are retained in the report revision
    lineage when present.
    """

    scheme_run_id: str
    project_id: str
    project_version_id: str
    requires_review: bool
    review_reasons: tuple[ReviewReason, ...]
    source_binding_id: str
    combined_source_hash: str
    content_hash: str
    status: str = "completed"
    recommended_scheme_code: str = ""
    source_contract_version: str = ""
    binding_schema_version: str = ""
    execution_snapshot_id: str = ""
    coefficient_context_id: str = ""
    orchestration_identity_id: str = ""
    authoritative_attempt_id: str = ""
    orchestration_fingerprint: str = ""
    zone_calculation_id: str = ""
    cooling_load_calculation_id: str = ""
    equipment_calculation_id: str = ""
    power_calculation_id: str = ""
    investment_calculation_id: str = ""
    zone_result_hash: str = ""
    cooling_load_result_hash: str = ""
    equipment_result_hash: str = ""
    power_result_hash: str = ""
    investment_result_hash: str = ""
    weight_set_id: str = ""
    weight_set_revision_id: str = ""
    weight_set_content_hash: str = ""
    weight_set_generator_compatibility_version: str = ""
    generator_version: str = ""
    database_backend: str = ""

    def __post_init__(self) -> None:
        if type(self.requires_review) is not bool:
            raise TypeError("SchemeReviewAuthority.requires_review must be bool")
        if not all(isinstance(reason, ReviewReason) for reason in self.review_reasons):
            raise TypeError("SchemeReviewAuthority.review_reasons must contain ReviewReason")
        if not self.requires_review and self.review_reasons:
            raise ValueError("review_required=false cannot carry review reasons")
        if self.requires_review and not self.review_reasons:
            raise ValueError("review_required=true requires at least one review reason")

    def to_snapshot(self) -> dict[str, Any]:
        """Return the closed JSON projection used in report revision lineage."""
        return {
            "scheme_run_id": self.scheme_run_id,
            "project_id": self.project_id,
            "project_version_id": self.project_version_id,
            "status": self.status,
            "recommended_scheme_code": self.recommended_scheme_code,
            "requires_review": self.requires_review,
            "review_reasons": review_reasons_to_json(self.review_reasons),
            "source_binding_id": self.source_binding_id,
            "combined_source_hash": self.combined_source_hash,
            "content_hash": self.content_hash,
            "source_contract_version": self.source_contract_version,
            "binding_schema_version": self.binding_schema_version,
            "execution_snapshot_id": self.execution_snapshot_id,
            "coefficient_context_id": self.coefficient_context_id,
            "orchestration_identity_id": self.orchestration_identity_id,
            "authoritative_attempt_id": self.authoritative_attempt_id,
            "orchestration_fingerprint": self.orchestration_fingerprint,
            "zone_calculation_id": self.zone_calculation_id,
            "cooling_load_calculation_id": self.cooling_load_calculation_id,
            "equipment_calculation_id": self.equipment_calculation_id,
            "power_calculation_id": self.power_calculation_id,
            "investment_calculation_id": self.investment_calculation_id,
            "zone_result_hash": self.zone_result_hash,
            "cooling_load_result_hash": self.cooling_load_result_hash,
            "equipment_result_hash": self.equipment_result_hash,
            "power_result_hash": self.power_result_hash,
            "investment_result_hash": self.investment_result_hash,
            "weight_set_id": self.weight_set_id,
            "weight_set_revision_id": self.weight_set_revision_id,
            "weight_set_content_hash": self.weight_set_content_hash,
            "weight_set_generator_compatibility_version": (
                self.weight_set_generator_compatibility_version
            ),
            "generator_version": self.generator_version,
            "database_backend": self.database_backend,
        }


class SchemeReviewAuthorityReader(ABC):
    """Application-side reader for strict persisted SchemeRun readback."""

    @abstractmethod
    def get_for_run(self, run_id: str) -> SchemeReviewAuthority:
        """Return one exact authority or raise on invalid persisted state."""
        ...


def _run_content_hash(run: Any, candidates: list[dict[str, Any]] | None = None) -> str:
    """Stable hash of scheme run content for provenance."""
    payload: dict[str, Any] = {
        "run_id": run.id,
        "recommended_scheme_code": run.recommended_scheme_code or "",
        "generator_version": run.generator_version or "",
    }
    if candidates:
        payload["candidates"] = [
            {
                "id": c.get("id", ""),
                "scheme_code": c.get("scheme_code", ""),
                "total_score": c.get("total_score"),
                "rank": c.get("rank"),
            }
            for c in sorted(candidates, key=lambda x: x.get("id", ""))
        ]
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class SchemeQueryPort(ABC):
    """Public read-only port for scheme data — no ORM/Session exposure."""

    @abstractmethod
    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        """Return completed scheme runs for a project, newest first."""
        ...

    @abstractmethod
    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        """Return completed scheme runs for a specific project version, newest first."""
        ...

    @abstractmethod
    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return candidate records for a given run."""
        ...

    def get_review_authority(
        self, project_id: str, version_id: str
    ) -> SchemeReviewAuthority | None:
        """Return the latest strict persisted review authority for a version.

        Implementations that expose report-facing scheme data must implement
        this method.  It deliberately is not abstract so older, non-report
        query adapters can continue to serve their legacy dictionary API while
        the production composition supplies the strict reader below.
        """
        raise NotImplementedError("Scheme review authority reader is not configured")


class SchemeQueryService(SchemeQueryPort):
    """Implementation backed by SchemeRepository."""

    def __init__(
        self,
        repository: Any,
        *,
        review_authority_reader: SchemeReviewAuthorityReader | None = None,
    ) -> None:
        self._repo = repository
        self._review_authority_reader = review_authority_reader

    def _serialize_run(
        self, run: Any, candidates: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "project_version_id": run.project_version_id,
            "status": run.status,
            "weight_set_id": run.weight_set_id,
            "generator_version": run.generator_version,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "recommended_scheme_code": run.recommended_scheme_code,
            "warning_messages": run.warning_messages,
            # persisted_content_hash is ONLY the DB-stored value.
            # A separate computed_content_hash field carries the fallback
            # so consumers can distinguish real persistence from on-the-fly computation.
            "persisted_content_hash": run.content_hash or "",
            "computed_content_hash": _run_content_hash(run, candidates),
        }

    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        runs = self._repo.get_completed_runs_for_project(project_id)
        result: list[dict[str, Any]] = []
        for run in runs:
            # Always load candidates so hash fallback (when content_hash is NULL)
            # uses the same inputs as generation-time computation.
            candidate_records = self._repo.get_candidates(run.id)
            candidate_dicts = [
                {
                    "id": c.scheme_code,
                    "scheme_code": c.scheme_code,
                    "total_score": str(c.total_score) if c.total_score else None,
                    "rank": c.rank,
                }
                for c in candidate_records
            ]
            result.append(self._serialize_run(run, candidate_dicts))
        return result

    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        runs = self._repo.get_completed_runs_for_project(project_id)
        filtered = [r for r in runs if r.project_version_id == version_id]
        result: list[dict[str, Any]] = []
        for run in filtered:
            candidate_records = self._repo.get_candidates(run.id)
            # Use scheme_code as hash id for consistency with service.py
            # (SchemeCandidate domain model has no id, only scheme_code)
            candidate_dicts = [
                {
                    "id": c.scheme_code,
                    "scheme_code": c.scheme_code,
                    "total_score": str(c.total_score) if c.total_score else None,
                    "rank": c.rank,
                }
                for c in candidate_records
            ]
            result.append(self._serialize_run(run, candidate_dicts))
        return result

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        candidate_records = self._repo.get_candidates(run_id)
        return [
            {
                # Use scheme_code as the candidate ID for hash consistency.
                # Hash computation (compute_scheme_source_hash / _run_content_hash)
                # expects scheme_code, not DB UUIDs.  Using c.id here would cause
                # a permanent mismatch with the stored content_hash.
                "id": c.scheme_code,
                "scheme_code": c.scheme_code,
                "profile_code": c.profile_code,
                "feasible": c.feasible,
                "rank": c.rank,
                "total_score": str(c.total_score) if c.total_score is not None else None,
                "score_breakdown_snapshot": c.score_breakdown_snapshot,
                "constraint_results": c.constraint_results,
                "result_snapshot": c.result_snapshot,
            }
            for c in candidate_records
        ]

    def get_review_authority(
        self, project_id: str, version_id: str
    ) -> SchemeReviewAuthority | None:
        """Read the newest completed run through strict production readback."""
        if self._review_authority_reader is None:
            raise RuntimeError("Scheme review authority reader is not configured")
        runs = self._repo.get_completed_runs_for_project(project_id)
        matching = [run for run in runs if run.project_version_id == version_id]
        if not matching:
            return None
        return self._review_authority_reader.get_for_run(matching[0].id)


_SCHEME_QUERY_SERVICE_IMPLEMENTATION = SchemeQueryService


class SqlAlchemySchemeReviewAuthorityReader(SchemeReviewAuthorityReader):
    """Strict production readback adapter hidden behind the app query port."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get_for_run(self, run_id: str) -> SchemeReviewAuthority:
        # Imports stay inside the adapter so reports and this application
        # boundary never expose schemes infrastructure to consumers.
        from cold_storage.modules.schemes.application.production_service import (
            read_verified_production_scheme_run,
        )
        from cold_storage.modules.schemes.domain.generator import GENERATOR_VERSION
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemyProductionSchemeRunReadPort,
            SqlAlchemySourceBindingReadPort,
            SqlAlchemyWeightRevisionReadPort,
        )

        persisted_port = SqlAlchemyProductionSchemeRunReadPort()
        persisted = persisted_port.load_production_run(self._session, run_id=run_id)
        if persisted is None:
            raise ValueError(f"SchemeRun {run_id!r} not found")

        verified = read_verified_production_scheme_run(
            persisted_port,
            SqlAlchemySourceBindingReadPort(),
            SqlAlchemyWeightRevisionReadPort(),
            self._session,
            run_id=run_id,
            generator_version=GENERATOR_VERSION,
        )
        reasons_list: list[ReviewReason] = []
        for reason in verified.warning_messages:
            if not isinstance(reason, ReviewReason):
                raise ValueError(f"SchemeRun {run_id!r} contains non-canonical review reasons")
            reasons_list.append(reason)
        reasons = tuple(reasons_list)

        def required(value: Any, field_name: str) -> str:
            if not isinstance(value, str) or not value:
                raise ValueError(f"SchemeRun {run_id!r} missing authority field {field_name}")
            return value

        return SchemeReviewAuthority(
            scheme_run_id=required(persisted.id, "scheme_run_id"),
            project_id=required(persisted.project_id, "project_id"),
            project_version_id=required(persisted.project_version_id, "project_version_id"),
            requires_review=persisted.requires_review,
            review_reasons=reasons,
            source_binding_id=required(persisted.source_binding_id, "source_binding_id"),
            combined_source_hash=required(persisted.combined_source_hash, "combined_source_hash"),
            content_hash=required(persisted.content_hash, "content_hash"),
            status=required(persisted.status, "status"),
            recommended_scheme_code=persisted.recommended_scheme_code or "",
            source_contract_version=required(
                persisted.source_contract_version, "source_contract_version"
            ),
            binding_schema_version=required(
                persisted.binding_schema_version, "binding_schema_version"
            ),
            execution_snapshot_id=required(
                persisted.execution_snapshot_id, "execution_snapshot_id"
            ),
            coefficient_context_id=required(
                persisted.coefficient_context_id, "coefficient_context_id"
            ),
            orchestration_identity_id=required(
                persisted.orchestration_identity_id, "orchestration_identity_id"
            ),
            authoritative_attempt_id=required(
                persisted.authoritative_attempt_id, "authoritative_attempt_id"
            ),
            orchestration_fingerprint=required(
                persisted.orchestration_fingerprint, "orchestration_fingerprint"
            ),
            zone_calculation_id=required(persisted.zone_calculation_id, "zone_calculation_id"),
            cooling_load_calculation_id=required(
                persisted.cooling_load_calculation_id, "cooling_load_calculation_id"
            ),
            equipment_calculation_id=required(
                persisted.equipment_calculation_id, "equipment_calculation_id"
            ),
            power_calculation_id=required(persisted.power_calculation_id, "power_calculation_id"),
            investment_calculation_id=required(
                persisted.investment_calculation_id, "investment_calculation_id"
            ),
            zone_result_hash=required(persisted.zone_result_hash, "zone_result_hash"),
            cooling_load_result_hash=required(
                persisted.cooling_load_result_hash, "cooling_load_result_hash"
            ),
            equipment_result_hash=required(
                persisted.equipment_result_hash, "equipment_result_hash"
            ),
            power_result_hash=required(persisted.power_result_hash, "power_result_hash"),
            investment_result_hash=required(
                persisted.investment_result_hash, "investment_result_hash"
            ),
            weight_set_id=required(persisted.weight_set_id, "weight_set_id"),
            weight_set_revision_id=required(
                persisted.weight_set_revision_id, "weight_set_revision_id"
            ),
            weight_set_content_hash=required(
                persisted.weight_set_content_hash, "weight_set_content_hash"
            ),
            weight_set_generator_compatibility_version=required(
                persisted.weight_set_generator_compatibility_version,
                "weight_set_generator_compatibility_version",
            ),
            generator_version=required(persisted.generator_version, "generator_version"),
            database_backend=required(persisted.database_backend, "database_backend"),
        )


def build_sqlalchemy_scheme_query(session: Any) -> SchemeQueryService:
    """Compose the public scheme query and strict production reader."""
    from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository

    # Keep composition bound to the concrete implementation.  A legacy pilot
    # test temporarily replaces the public module symbol while exercising its
    # own lifecycle seam; production composition must still retain the strict
    # persisted-authority reader.
    concrete_query_type = _SCHEME_QUERY_SERVICE_IMPLEMENTATION
    return concrete_query_type(
        SchemeRepository(session),
        review_authority_reader=SqlAlchemySchemeReviewAuthorityReader(session),
    )
