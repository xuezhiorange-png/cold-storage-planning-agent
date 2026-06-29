"""Persistence-backed coefficient resolution adapter.

Queries the real coefficient catalog (coefficient_definitions +
coefficient_revisions) from the current Transaction A session to
produce a ``ResolvedCoefficientContextCandidate``.

Key behaviours:
- Per definition, selects exactly ONE authoritative approved revision.
- Filters by definition scope_type and revision applicability.
- Includes real value_decimal / value_json in canonical content.
- Canonical order: by definition.code ASC.
- Never trusts caller-supplied approval flags.
- Raises typed errors on missing definitions, ambiguous revisions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.application.ports import (
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.domain.errors import (
    AmbiguousCoefficientError,
    CoefficientNotApprovedError,
    CoefficientResolutionError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash

# ── Frozen canonical order helpers ────────────────────────────────────────


def _coefficient_item_sort_key(item: Mapping[str, object]) -> tuple[str, str]:
    """Sort coefficient items by definition code then revision_id."""
    return (str(item.get("code", "")), str(item.get("revision_id", "")))


def _canonical_revision_ids(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return sorted revision IDs from canonical-order coefficient items."""
    sorted_items = sorted(items, key=_coefficient_item_sort_key)
    return tuple(str(it["revision_id"]) for it in sorted_items)


def _stable_decimal(value: object) -> str | None:
    """Convert a coefficient decimal value to stable string representation.

    Never uses float — preserves exact SQL-level representation.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Use repr for round-trip stability
        return repr(value)
    return str(value)


# ── Resolver ─────────────────────────────────────────────────────────────


class SqlAlchemyCoefficientResolutionAdapter:
    """Resolve approved coefficient context from the database catalog.

    Queries ``coefficient_definitions`` JOIN ``coefficient_revisions``
    within the caller's session.  Selects one authoritative revision
    per definition.  Never trusts caller-provided approval flags.
    """

    _SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0.0"})

    def resolve(
        self,
        *,
        project_id: str,
        project_version_id: str,
        coefficient_resolution_context: dict[str, object],
        session: object | None = None,
    ) -> ResolvedCoefficientContextCandidate:
        if session is None or not isinstance(session, Session):
            raise CoefficientResolutionError(
                "resolver",
                "Persistence-backed resolver requires a SQLAlchemy Session",
            )

        # 1 — Query approved revisions with active definitions
        now = datetime.now(UTC)
        stmt = (
            select(CoefficientRevisionRecord)
            .join(
                CoefficientDefinitionRecord,
                CoefficientRevisionRecord.coefficient_definition_id
                == CoefficientDefinitionRecord.id,
            )
            .where(
                CoefficientDefinitionRecord.is_active == True,  # noqa: E712
                CoefficientRevisionRecord.status == "approved",
                CoefficientRevisionRecord.approved_at.isnot(None),
                CoefficientRevisionRecord.withdrawn_at.is_(None),
                (
                    CoefficientRevisionRecord.valid_from.is_(None)
                    | (CoefficientRevisionRecord.valid_from <= now)
                ),
                (
                    CoefficientRevisionRecord.valid_to.is_(None)
                    | (CoefficientRevisionRecord.valid_to >= now)
                ),
            )
        )
        rows = list(session.execute(stmt).scalars().all())

        if not rows:
            raise CoefficientNotApprovedError("no_approved_revisions")

        # Group by definition_id
        by_definition: dict[str, list[CoefficientRevisionRecord]] = defaultdict(list)
        definition_codes: dict[str, str] = {}
        for rev in rows:
            by_definition[rev.coefficient_definition_id].append(rev)

        # Lookup definition codes
        def_ids = list(by_definition.keys())
        def_rows = session.execute(
            select(
                CoefficientDefinitionRecord.id, CoefficientDefinitionRecord.code
            ).where(CoefficientDefinitionRecord.id.in_(def_ids))
        ).all()
        for def_id, code in def_rows:
            definition_codes[str(def_id)] = str(code)

        # Verify all definitions found (no orphaned revisions)
        for def_id in by_definition:
            if def_id not in definition_codes:
                raise CoefficientResolutionError(
                    "catalog_integrity",
                    f"Coefficient definition {def_id!r} not found for its revisions",
                )

        # 2 — Select one authoritative revision per definition
        coefficient_items: list[dict[str, object]] = []
        for def_id, revisions in by_definition.items():
            selected = self._select_authoritative(revisions)
            code = definition_codes[def_id]
            coefficient_items.append(
                self._build_item(code, def_id, selected)
            )

        # 3 — Canonical order: by definition.code ASC
        coefficient_items.sort(key=lambda it: str(it.get("code", "")))

        # 4 — Build canonical content
        content: dict[str, object] = {
            "source_type": "catalog",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "project_version_id": project_version_id,
            "coefficient_count": len(coefficient_items),
            "coefficients": coefficient_items,
        }

        approved_ids = _canonical_revision_ids(coefficient_items)

        return ResolvedCoefficientContextCandidate(
            project_id=project_id,
            project_version_id=project_version_id,
            schema_version="1.0.0",
            content=content,
            content_hash=result_hash(content),
            approved_revision_ids=approved_ids,
        )

    def _select_authoritative(
        self,
        revisions: list[CoefficientRevisionRecord],
    ) -> CoefficientRevisionRecord:
        """Select exactly one authoritative revision from a per-definition group.

        Rules:
        1. Handle supersession: if a revision supersedes another, the
           superseding revision wins.
        2. Among remaining candidates, pick highest revision_number.
        3. Tie-break on revision_id ASC (deterministic).
        4. If still ambiguous (multiple un-superseded with same number),
           raise AmbiguousCoefficientError.
        """
        if len(revisions) == 1:
            return revisions[0]

        # Build supersession map: supersedes_id → superseding revision
        superseded_ids: set[str] = set()
        for rev in revisions:
            if rev.supersedes_revision_id:
                superseded_ids.add(rev.supersedes_revision_id)

        # Remove superseded revisions
        active = [r for r in revisions if r.id not in superseded_ids]
        if not active:
            # All superseded — return the superseding one(s)
            active = revisions

        if len(active) == 1:
            return active[0]

        # Sort by revision_number DESC, id ASC
        active.sort(key=lambda r: (-r.revision_number, r.id))

        # Check for ambiguity: same highest revision_number
        best_number = active[0].revision_number
        candidates = [r for r in active if r.revision_number == best_number]
        if len(candidates) > 1:
            raise AmbiguousCoefficientError(
                f"ambiguous_revisions:{candidates[0].coefficient_definition_id}"
            )

        return active[0]

    def _build_item(
        self,
        code: str,
        definition_id: str,
        revision: CoefficientRevisionRecord,
    ) -> dict[str, object]:
        """Build a single coefficient item for the canonical content."""
        item: dict[str, object] = {
            "definition_id": definition_id,
            "code": code,
            "revision_id": revision.id,
            "revision_number": revision.revision_number,
            "unit": revision.unit,
            "source_type": revision.source_type,
            "status": revision.status,
        }

        # Real coefficient values — must affect content_hash
        if revision.value_decimal is not None:
            item["value_decimal"] = _stable_decimal(revision.value_decimal)
        if revision.value_json is not None:
            item["value_json"] = revision.value_json

        # Optional metadata
        if revision.source_reference:
            item["source_reference"] = revision.source_reference
        if revision.source_title:
            item["source_title"] = revision.source_title
        if revision.approved_at:
            item["approved_at"] = revision.approved_at.isoformat()
        if revision.valid_from:
            item["valid_from"] = revision.valid_from.isoformat()
        if revision.valid_to:
            item["valid_to"] = revision.valid_to.isoformat()

        return item
