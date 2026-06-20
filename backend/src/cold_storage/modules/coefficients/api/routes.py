"""FastAPI routes for the coefficient registry."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from cold_storage.modules.coefficients.application.service import CoefficientService
from cold_storage.modules.coefficients.domain.exceptions import (
    CoefficientNotFoundError,
    DuplicateCoefficientCodeError,
    InvalidRevisionTransitionError,
    RevisionImmutabilityError,
    SupersedesCrossDefinitionError,
)
from cold_storage.modules.coefficients.domain.models import (
    CoefficientDefinition,
    CoefficientRevision,
    CoefficientSet,
)

router = APIRouter(prefix="/api/v1/coefficients", tags=["coefficients"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CoefficientDefinitionCreateRequest(BaseModel):
    code: str
    name: str
    description: str
    category: str
    canonical_unit: str
    value_type: str = "decimal"
    scope_type: str = "global"
    is_active: bool = True


class CoefficientRevisionCreateRequest(BaseModel):
    value_decimal: str | None = None
    value_json: dict[str, Any] | None = None
    unit: str | None = None
    source_type: str = "demo"
    source_title: str | None = None
    source_reference: str | None = None
    source_page: str | None = None
    applicable_product_type: str | None = None
    applicable_zone_type: str | None = None
    applicable_process_type: str | None = None
    supersedes_revision_id: str | None = None
    change_reason: str | None = None
    created_by: str = "system"


class CoefficientResolveRequest(BaseModel):
    codes: list[str] | None = None
    product_type: str | None = None
    zone_type: str | None = None
    process_type: str | None = None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _definition_to_dict(d: CoefficientDefinition) -> dict[str, Any]:
    return {
        "id": d.id,
        "code": d.code,
        "name": d.name,
        "description": d.description,
        "category": d.category,
        "canonical_unit": d.canonical_unit,
        "value_type": d.value_type,
        "scope_type": d.scope_type,
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


def _revision_to_dict(r: CoefficientRevision) -> dict[str, Any]:
    return {
        "id": r.id,
        "coefficient_definition_id": r.coefficient_definition_id,
        "revision_number": r.revision_number,
        "value_decimal": str(r.value_decimal) if r.value_decimal is not None else None,
        "value_json": r.value_json,
        "unit": r.unit,
        "status": r.status,
        "source_type": r.source_type,
        "source_title": r.source_title,
        "source_reference": r.source_reference,
        "source_page": r.source_page,
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "applicable_product_type": r.applicable_product_type,
        "applicable_zone_type": r.applicable_zone_type,
        "applicable_process_type": r.applicable_process_type,
        "supersedes_revision_id": r.supersedes_revision_id,
        "change_reason": r.change_reason,
        "created_by": r.created_by,
        "reviewed_by": r.reviewed_by,
        "approved_by": r.approved_by,
        "created_at": r.created_at.isoformat(),
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
    }


def _coefficient_value_to_dict(v: Any) -> dict[str, Any]:
    return {
        "code": v.code,
        "revision_id": v.revision_id,
        "revision_number": v.revision_number,
        "value": str(v.value),
        "unit": v.unit,
        "status": v.status,
        "source_type": v.source_type,
        "source_reference": v.source_reference,
        "requires_review": v.requires_review,
    }


def _coefficient_set_to_dict(s: CoefficientSet) -> dict[str, Any]:
    return {
        "schema_version": s.schema_version,
        "captured_at": s.captured_at.isoformat(),
        "items": {code: _coefficient_value_to_dict(v) for code, v in s.items.items()},
        "count": len(s.items),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def register_coefficient_routes(
    app: FastAPI, coefficient_service: CoefficientService
) -> None:
    """Register coefficient routes on the FastAPI app.

    This function is called from the app factory to inject the service dependency.
    """

    @app.get("/api/v1/coefficients")
    def list_coefficients(
        category: str | None = None,
        is_active: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List coefficient definitions with optional filters."""
        definitions = coefficient_service.list_definitions(category=category, is_active=is_active)
        return [_definition_to_dict(d) for d in definitions]

    @app.post("/api/v1/coefficients")
    def create_coefficient(request: CoefficientDefinitionCreateRequest) -> dict[str, Any]:
        """Create a new coefficient definition."""
        try:
            definition = coefficient_service.create_definition(
                code=request.code,
                name=request.name,
                description=request.description,
                category=request.category,
                canonical_unit=request.canonical_unit,
                value_type=request.value_type,
                scope_type=request.scope_type,
                is_active=request.is_active,
            )
            return _definition_to_dict(definition)
        except DuplicateCoefficientCodeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/coefficients/{definition_id}")
    def get_coefficient(definition_id: str) -> dict[str, Any]:
        """Get a coefficient definition by ID."""
        try:
            definition = coefficient_service.get_definition(definition_id)
            return _definition_to_dict(definition)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/coefficients/{definition_id}/revisions")
    def list_revisions(definition_id: str) -> list[dict[str, Any]]:
        """List all revisions for a coefficient definition."""
        try:
            revisions = coefficient_service.list_revisions(definition_id)
            return [_revision_to_dict(r) for r in revisions]
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/coefficients/{definition_id}/revisions")
    def create_revision(
        definition_id: str, request: CoefficientRevisionCreateRequest
    ) -> dict[str, Any]:
        """Create a new revision for a coefficient definition."""
        try:
            value_decimal = Decimal(request.value_decimal) if request.value_decimal else None
            revision = coefficient_service.create_revision(
                definition_id=definition_id,
                value_decimal=value_decimal,
                value_json=request.value_json,
                unit=request.unit,
                source_type=request.source_type,
                source_title=request.source_title,
                source_reference=request.source_reference,
                source_page=request.source_page,
                applicable_product_type=request.applicable_product_type,
                applicable_zone_type=request.applicable_zone_type,
                applicable_process_type=request.applicable_process_type,
                supersedes_revision_id=request.supersedes_revision_id,
                change_reason=request.change_reason,
                created_by=request.created_by,
            )
            return _revision_to_dict(revision)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SupersedesCrossDefinitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/coefficients/{definition_id}/revisions/{revision_id}")
    def get_revision(definition_id: str, revision_id: str) -> dict[str, Any]:
        """Get a specific revision."""
        try:
            revision = coefficient_service.get_revision(definition_id, revision_id)
            return _revision_to_dict(revision)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/coefficients/{definition_id}/revisions/{revision_id}/review")
    def review_revision(definition_id: str, revision_id: str) -> dict[str, Any]:
        """Mark a revision as reviewed."""
        try:
            revision = coefficient_service.mark_revision_reviewed(
                definition_id, revision_id, reviewer="api"
            )
            return _revision_to_dict(revision)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (InvalidRevisionTransitionError, RevisionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/coefficients/{definition_id}/revisions/{revision_id}/approve")
    def approve_revision(definition_id: str, revision_id: str) -> dict[str, Any]:
        """Approve a reviewed revision."""
        try:
            revision = coefficient_service.approve_revision(
                definition_id, revision_id, approver="api"
            )
            return _revision_to_dict(revision)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (InvalidRevisionTransitionError, RevisionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/coefficients/{definition_id}/revisions/{revision_id}/withdraw")
    def withdraw_revision(definition_id: str, revision_id: str) -> dict[str, Any]:
        """Withdraw an approved revision."""
        try:
            revision = coefficient_service.withdraw_revision(
                definition_id, revision_id, actor="api"
            )
            return _revision_to_dict(revision)
        except CoefficientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (InvalidRevisionTransitionError, RevisionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/coefficients/resolve")
    def resolve_coefficients(request: CoefficientResolveRequest) -> dict[str, Any]:
        """Resolve coefficient set for calculations."""
        coefficient_set = coefficient_service.resolve_coefficient_set(
            codes=request.codes,
            product_type=request.product_type,
            zone_type=request.zone_type,
            process_type=request.process_type,
        )
        return _coefficient_set_to_dict(coefficient_set)
