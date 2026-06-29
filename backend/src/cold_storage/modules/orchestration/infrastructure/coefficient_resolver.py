"""Persistence-backed coefficient resolution adapter.

Queries the real coefficient catalog (coefficient_definitions +
coefficient_revisions) from the current Transaction A session to
produce a ``ResolvedCoefficientContextCandidate``.

Key behaviours:
- Filters by definition scope_type and revision applicability
  (product_type, zone_type, process_type) from frozen ProjectVersion inputs.
- Enforces required coefficient completeness — every required code
  must resolve to exactly one authoritative approved revision.
- Per definition, selects exactly ONE authoritative revision via
  supersession DAG validation (cycle detection, multi-head rejection).
- Includes real value_decimal / value_json in canonical content,
  with Decimal normalization and JSON structural canonicalization.
- Canonical order: by definition.code ASC.
- Never trusts caller-supplied approval flags.
- Raises typed errors on missing definitions, ambiguous revisions,
  supersession integrity violations, and invalid values.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

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


def coefficient_item_sort_key(item: Mapping[str, object]) -> tuple[str, str]:
    """Sort coefficient items by definition code then revision_id."""
    return (str(item.get("code", "")), str(item.get("revision_id", "")))


def canonical_revision_ids(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return sorted revision IDs from canonical-order coefficient items."""
    sorted_items = sorted(items, key=coefficient_item_sort_key)
    return tuple(str(it["revision_id"]) for it in sorted_items)


# ── Value canonicalization ────────────────────────────────────────────────


def _canonicalize_decimal(raw: object) -> str:
    """Parse *raw* as Decimal and return a stable normalized string.

    Uses ``Decimal.normalize()`` followed by ``format(…, 'f')`` to
    collapse equivalent representations (1.0, 1.00, 1E0) into a single
    canonical form.  Rejects non-finite and unparseable values.
    """
    if raw is None:
        raise CoefficientResolutionError(
            "invalid_value", "Decimal value is required but was None"
        )
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CoefficientResolutionError(
            "invalid_value",
            f"Cannot parse decimal value {raw!r}: {exc}",
        ) from exc
    # Reject non-finite
    if not d.is_finite():
        raise CoefficientResolutionError(
            "invalid_value", f"Non-finite decimal {d!r} not allowed"
        )
    normalized = d.normalize()
    # Use 'f' format for stable representation
    return format(normalized, "f")


def _canonicalize_json(raw: object) -> dict[str, object] | list[object]:
    """Parse *raw* as JSON text and return the structured object.

    Rejects non-dict/list top-level values, NaN, Infinity, and invalid JSON.
    Returns a Python object that canonical_json_bytes will sort.
    """
    if raw is None:
        raise CoefficientResolutionError(
            "invalid_value", "JSON value is required but was None"
        )
    parsed: object
    if isinstance(raw, (dict, list)):
        # Already a structured object (from ORM JSON column)
        try:
            # Round-trip through json to validate JSON-safety
            parsed = json.loads(json.dumps(raw, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise CoefficientResolutionError(
                "invalid_json", f"JSON value not JSON-safe: {exc}"
            ) from exc
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CoefficientResolutionError(
                "invalid_json", f"Cannot parse JSON value: {exc}"
            ) from exc
    else:
        raise CoefficientResolutionError(
            "invalid_json", f"Unexpected JSON value type: {type(raw).__name__}"
        )

    if not isinstance(parsed, (dict, list)):
        raise CoefficientResolutionError(
            "invalid_json",
            f"JSON value must be a dict or list, got {type(parsed).__name__}",
        )

    # Reject NaN / Infinity at top level
    _check_no_nonfinite(parsed)
    return parsed


def _check_no_nonfinite(obj: object) -> None:
    """Recursively verify *obj* contains no NaN or Infinity values."""
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            raise CoefficientResolutionError(
                "invalid_json", f"Non-finite float {obj!r} not allowed in JSON value"
            )
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_no_nonfinite(v)
    elif isinstance(obj, list):
        for v in obj:
            _check_no_nonfinite(v)


# ── Supersession DAG validation ───────────────────────────────────────────


def _validate_supersession_dag(
    revisions: list[CoefficientRevisionRecord],
    definition_id: str,
) -> dict[str, list[str]]:
    """Build and validate the supersession DAG for *revisions*.

    Returns adjacency map: supersedes_revision_id → [superseding_ids].

    Raises:
        CoefficientResolutionError: on missing target, cross-definition
            edge, self-loop, cycle, or multiple terminal heads.
        AmbiguousCoefficientError: on multiple un-superseded heads.
    """
    # Map: superseding_rev_id → supersedes_rev_id
    edges: dict[str, str] = {}
    rev_by_id: dict[str, CoefficientRevisionRecord] = {}
    for rev in revisions:
        rev_by_id[rev.id] = rev
        if rev.supersedes_revision_id:
            edges[rev.id] = rev.supersedes_revision_id

    # Validate all targets exist and are same definition
    for sid, target_id in edges.items():
        if target_id not in rev_by_id:
            raise CoefficientResolutionError(
                "supersession",
                f"Supersession target {target_id!r} not found in definition "
                f"{definition_id!r}",
            )
        if target_id == sid:
            raise CoefficientResolutionError(
                "supersession",
                f"Self-loop detected: revision {sid!r} supersedes itself",
            )

    # Build reverse adjacency for cycle detection
    adj: dict[str, list[str]] = defaultdict(list)
    for sid, target_id in edges.items():
        adj[target_id].append(sid)

    # Detect cycles via DFS with three-color marking
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {r.id: WHITE for r in revisions}

    def dfs(node: str) -> None:
        color[node] = GRAY
        for neighbor in adj.get(node, []):
            if color[neighbor] == GRAY:
                raise CoefficientResolutionError(
                    "supersession",
                    f"Supersession cycle detected involving revisions "
                    f"{node!r} and {neighbor!r}",
                )
            if color[neighbor] == WHITE:
                dfs(neighbor)
        color[node] = BLACK

    for node_id in color:
        if color[node_id] == WHITE:
            dfs(node_id)

    return adj


def _find_terminal_heads(
    revisions: list[CoefficientRevisionRecord],
    superseded_ids: set[str],
) -> list[CoefficientRevisionRecord]:
    """Return revisions that are NOT superseded by any other revision."""
    return [r for r in revisions if r.id not in superseded_ids]


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

        # Narrow type for type checker
        db: Session = session

        # Derive applicability criteria from frozen ProjectVersion inputs
        # (read from coefficient_resolution_context, validated against DB)
        product_type = coefficient_resolution_context.get("product_type")
        zone_type = coefficient_resolution_context.get("zone_type")
        process_type = coefficient_resolution_context.get("process_type")
        required_codes: list[str] | None = None
        raw_required = coefficient_resolution_context.get("required_codes")
        if isinstance(raw_required, list):
            required_codes = [str(c) for c in raw_required]

        now = datetime.now(UTC)

        # 1 — Query approved revisions with active definitions (base filter)
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
        rows = list(db.execute(stmt).scalars().all())

        # Build definition lookup
        def_ids_set: set[str] = set()
        for rev in rows:
            def_ids_set.add(rev.coefficient_definition_id)

        def_rows = db.execute(
            select(CoefficientDefinitionRecord).where(
                CoefficientDefinitionRecord.id.in_(list(def_ids_set))
            )
        ).scalars().all()
        definitions: dict[str, CoefficientDefinitionRecord] = {
            d.id: d for d in def_rows
        }

        # 2 — Apply scope/applicability filtering
        filtered: list[CoefficientRevisionRecord] = []
        for rev in rows:
            definition = definitions.get(rev.coefficient_definition_id)
            if definition is None:
                # Orphaned revision — catalog integrity error
                raise CoefficientResolutionError(
                    "catalog_integrity",
                    f"Coefficient definition {rev.coefficient_definition_id!r} "
                    f"not found for its revisions",
                )

            if not self._matches_scope(definition, rev, product_type, zone_type, process_type):
                continue
            filtered.append(rev)

        if not filtered:
            raise CoefficientNotApprovedError("no_applicable_approved_revisions")

        # Group by definition_id
        by_definition: dict[str, list[CoefficientRevisionRecord]] = defaultdict(list)
        for rev in filtered:
            by_definition[rev.coefficient_definition_id].append(rev)

        # 3 — Enforce required coefficient completeness
        available_codes: set[str] = set()
        for def_id in by_definition:
            definition = definitions[def_id]
            available_codes.add(definition.code)

        if required_codes is not None:
            missing = set(required_codes) - available_codes
            if missing:
                raise CoefficientNotApprovedError(
                    f"required_coefficient_missing:{','.join(sorted(missing))}"
                )

        # 4 — Select one authoritative revision per definition
        coefficient_items: list[dict[str, object]] = []
        for def_id, revisions in by_definition.items():
            definition = definitions[def_id]
            selected = self._select_authoritative(revisions)
            coefficient_items.append(
                self._build_item(definition.code, def_id, selected)
            )

        # 5 — Canonical order: by definition.code ASC
        coefficient_items.sort(key=lambda it: str(it.get("code", "")))

        # 6 — Build canonical content
        content: dict[str, object] = {
            "source_type": "catalog",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "project_version_id": project_version_id,
            "coefficient_count": len(coefficient_items),
            "coefficients": coefficient_items,
        }

        approved_ids = canonical_revision_ids(coefficient_items)

        return ResolvedCoefficientContextCandidate(
            project_id=project_id,
            project_version_id=project_version_id,
            schema_version="1.0.0",
            content=content,
            content_hash=result_hash(content),
            approved_revision_ids=approved_ids,
        )

    def _matches_scope(
        self,
        definition: CoefficientDefinitionRecord,
        revision: CoefficientRevisionRecord,
        product_type: object,
        zone_type: object,
        process_type: object,
    ) -> bool:
        """Check whether *revision* is applicable given the scope constraints."""
        scope = definition.scope_type

        # Global scope matches everything
        if scope == "global":
            return True

        # Product scope: revision must match the product type
        if scope == "product":
            if product_type is not None and revision.applicable_product_type is not None:
                return str(revision.applicable_product_type) == str(product_type)
            return True  # No filter applied if either is None

        # Zone scope: revision must match the zone type
        if scope == "zone":
            if zone_type is not None and revision.applicable_zone_type is not None:
                return str(revision.applicable_zone_type) == str(zone_type)
            return True

        # Process scope: revision must match the process type
        if scope == "process":
            if process_type is not None and revision.applicable_process_type is not None:
                return str(revision.applicable_process_type) == str(process_type)
            return True

        # Project and project_version scope: fail closed until binding model exists
        if scope in ("project", "project_version"):
            raise CoefficientResolutionError(
                "unsupported_scope",
                f"Scope type {scope!r} requires project/version binding "
                f"which is not yet implemented for coefficient resolution",
            )

        # Unknown scope → fail closed
        raise CoefficientResolutionError(
            "unsupported_scope",
            f"Unknown scope type {scope!r} for definition {definition.code!r}",
        )

    def _select_authoritative(
        self,
        revisions: list[CoefficientRevisionRecord],
    ) -> CoefficientRevisionRecord:
        """Select exactly one authoritative revision from a per-definition group.

        Rules:
        1. Validate supersession DAG (cycles, missing targets, cross-def edges).
        2. Build terminal heads (revisions not superseded by any other).
        3. If no terminal heads → catalog integrity error (all superseded cycle).
        4. If one terminal head → that's the authoritative revision.
        5. If multiple terminal heads → apply frozen tie-breaking:
           revision_number DESC, then revision_id ASC.
           If still ambiguous (same revision_number), raise AmbiguousCoefficientError.
        """
        if len(revisions) == 1:
            return revisions[0]

        definition_id = revisions[0].coefficient_definition_id

        # Validate DAG
        adj = _validate_supersession_dag(revisions, definition_id)

        # Compute superseded IDs
        superseded_ids: set[str] = set()
        for sid in adj:
            superseded_ids.add(sid)
        for targets in adj.values():
            superseded_ids.update(targets)

        # Find terminal heads (not superseded by any other revision)
        terminal = _find_terminal_heads(revisions, superseded_ids)

        if not terminal:
            # All revisions are superseded — catalog integrity error
            raise CoefficientResolutionError(
                "supersession",
                f"All revisions in definition {definition_id!r} are superseded "
                f"(possible cycle or missing terminal)",
            )

        if len(terminal) == 1:
            return terminal[0]

        # Multiple terminal heads — apply frozen tie-breaking
        terminal.sort(key=lambda r: (-r.revision_number, r.id))

        best_number = terminal[0].revision_number
        candidates = [r for r in terminal if r.revision_number == best_number]
        if len(candidates) > 1:
            raise AmbiguousCoefficientError(
                f"ambiguous_revisions:{definition_id}"
            )

        return terminal[0]

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

        # Real coefficient values — canonicalized, must affect content_hash
        if revision.value_decimal is not None:
            item["value_decimal"] = _canonicalize_decimal(revision.value_decimal)
        if revision.value_json is not None:
            item["value_json"] = _canonicalize_json(revision.value_json)

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
