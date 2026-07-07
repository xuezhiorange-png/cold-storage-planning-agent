"""Approved non-demo coefficient resolver.

Strict resolver used by the production path. Per design contract §3,
§5.3, §7 (no-fallback invariants) the resolver:

- Selects from ``status == approved`` revisions only.
- Filters out ``source_type == demo`` (no demo fallback).
- Filters out revisions whose ``valid_to`` is past (no stale fallback).
- Filters out revisions with a missing or malformed citation
  (per contract §5.5).
- Refuses to pick "the latest row" when multiple revisions tie on
  the deterministic priority order. Production callers must supply
  an explicit ``revision_id`` if ambiguity is acceptable.

Per Charles's Slice 1 boundary correction (2026-07-07):
- This module does not import from ``infrastructure.orm`` or
  ``infrastructure.repositories``. It depends only on ports (in this
  package) and on the existing domain models.
- ``CoefficientService.resolve_coefficient_set`` is not replaced;
  this resolver is the production-only counterparty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cold_storage.modules.coefficients.application.ports import (
    CoefficientClockPort,
    CoefficientRevisionReadPort,
)
from cold_storage.modules.coefficients.domain.approval import (
    is_stale,
    validate_citation,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    AmbiguousLatestRowError,
    DemoCoefficientInProductionError,
    InvalidCitationError,
    MissingApprovedCoefficientError,
    StaleApprovalError,
)
from cold_storage.modules.coefficients.domain.models import CoefficientRevision

#: Deterministic priority order for selecting among eligible revisions.
#: Per design contract §7 (no latest-row fallback): when multiple
#: revisions are eligible for the same (stage, calculation_type),
#: application code must request an explicit ``revision_id`` rather
#: than relying on this ordering. The ordering is documented for
#: diagnostic / tie-break purposes only.
_RESOLVER_PRIORITY_FIELDS = (
    # Lowest priority first so the ``max`` later picks the most
    # trustworthy candidate when ``revision_id`` is *not* supplied.
    "source_type",  # domain codes (alphabetical; demo is filtered)
    "revision_number",  # later revision numbers win on tie
    "approved_at",  # later approval wins on tie
)


@dataclass(frozen=True)
class ResolutionPlan:
    """Plan returned by :meth:`ApprovedCoefficientResolver.resolve`.

    The plan records the resolved ``revision_id`` (or absence) and
    the typed reason if no eligible candidate exists. Application
    startup code reads ``missing`` to fail closed.
    """

    stage_name: str
    calculation_type: str | None
    revision_id: str | None
    missing: MissingApprovedCoefficientError | None


class ApprovedCoefficientResolver:
    """Strict approved-coefficient resolver used by the production path.

    Used both at startup (per design contract §5.3) and at runtime
    for per-stage resolution (per design contract §3 / §7). The
    resolver is intentionally stateless; all state lives in
    ``read_port``.
    """

    def __init__(
        self,
        read_port: CoefficientRevisionReadPort,
        clock: CoefficientClockPort,
    ) -> None:
        self._read_port = read_port
        self._clock = clock

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_eligible(
        revision: CoefficientRevision,
        *,
        now: datetime,
    ) -> tuple[bool, str | None]:
        """Return ``(eligible, rejection_reason)`` for a single revision.

        A revision is eligible iff:
        1. ``status == approved``
        2. ``source_type != demo``
        3. ``valid_to`` is None OR ``now <= valid_to`` (not stale)
        4. ``source_reference`` is non-empty and matches a citation
           pattern.

        Each rejection carries a typed reason (string code); the
        caller is responsible for raising the matching typed error.
        """
        if revision.status != "approved":
            return False, "not-approved"
        if revision.source_type == "demo":
            return False, "demo"
        if is_stale(revision, now=now):
            return False, "stale"
        if not revision.source_reference:
            return False, "missing-citation"
        try:
            validate_citation(revision.source_reference)
        except InvalidCitationError:
            return False, "invalid-citation"
        return True, None

    @staticmethod
    def _priority_key(
        revision: CoefficientRevision,
    ) -> tuple[str, int, datetime]:
        """Deterministic ordering key for resolver diagnostics.

        Not used to pick without an explicit ``revision_id``. The
        order is documented for reproducibility only.
        """
        approved_at = revision.approved_at
        if approved_at is None:
            # Coerce ``None`` to the epoch so the comparison is well-
            # defined; ``status == approved`` should imply a non-null
            # ``approved_at`` at the infrastructure layer, but we
            # harden against drift.
            approved_at = datetime(1970, 1, 1, tzinfo=UTC)
        return (
            revision.source_type,
            revision.revision_number,
            approved_at,
        )

    # ------------------------------------------------------------------
    # Public resolution API
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        stage_name: str,
        calculation_type: str | None,
        explicit_revision_id: str | None = None,
    ) -> ResolutionPlan:
        """Resolve the approved revision for ``(stage_name, calculation_type)``.

        :param stage_name: Stage slot the caller needs to fill.
            Slice 1 commonly maps to ``CoefficientDefinition.category``
            (e.g. ``area``, ``pallet``, ``power``, ``investment``).
        :param calculation_type: Optional further binding; per design
            contract §5.1 the pool key is
            ``(stage_name, calculation_type, source_type)``.
        :param explicit_revision_id: When the caller already knows
            which revision to use (e.g. when the same coefficient
            is bound across multiple stages), the resolver pins to
            that revision. When ``None`` and more than one
            revision is eligible, the resolver raises
            :class:`AmbiguousLatestRowError`.

        :returns: A plan describing either the resolved revision or
            a typed :class:`MissingApprovedCoefficientError`.

        :raises DemoCoefficientInProductionError: When the only
            eligible revisions are demo rows.
        :raises StaleApprovalError: When the only candidate is past
            its ``valid_to``.
        :raises InvalidCitationError: When the only candidate has a
            missing/malformed citation.
        :raises AmbiguousLatestRowError: When the eligible set has
            more than one candidate and ``explicit_revision_id`` is
            ``None``.

        This method does not raise :class:`MissingApprovedCoefficientError`;
        the caller (``CoefficientApprovalService.validate_startup_readiness``
        and the composition-root wiring) inspects ``plan.missing``
        and raises it under the appropriate aggregation context.
        """
        candidates = self._read_port.list_approved_revisions(
            stage_name=stage_name,
            calculation_type=calculation_type,
        )
        now = self._clock.now()

        eligible: list[CoefficientRevision] = []
        rejection_reasons: dict[str, list[str]] = {
            "not-approved": [],
            "demo": [],
            "stale": [],
            "missing-citation": [],
            "invalid-citation": [],
        }
        for revision in candidates:
            ok, reason = self._is_eligible(revision, now=now)
            if ok:
                eligible.append(revision)
            elif reason is not None:
                rejection_reasons.setdefault(reason, []).append(revision.id)

        if explicit_revision_id is not None:
            for revision in eligible:
                if revision.id == explicit_revision_id:
                    return ResolutionPlan(
                        stage_name=stage_name,
                        calculation_type=calculation_type,
                        revision_id=revision.id,
                        missing=None,
                    )
            # Explicit id supplied but not in eligible set: propagate
            # the most specific typed error so callers can branch.
            self._raise_for_rejection(rejection_reasons)
            raise MissingApprovedCoefficientError(
                stage_name=stage_name,
                calculation_type=calculation_type,
            )

        if not eligible:
            return ResolutionPlan(
                stage_name=stage_name,
                calculation_type=calculation_type,
                revision_id=None,
                missing=MissingApprovedCoefficientError(
                    stage_name=stage_name,
                    calculation_type=calculation_type,
                ),
            )

        if len(eligible) > 1:
            ordered = sorted(eligible, key=self._priority_key)
            # Per design contract §7 (no latest-row fallback): tying
            # means ambiguous. The application caller must request an
            # explicit ``revision_id`` or pull the rows from the
            # audit trail. We raise with the full tie so callers can
            # make the routing decision explicitly.
            raise AmbiguousLatestRowError(
                definition_id=",".join(r.coefficient_definition_id for r in ordered),
                revision_ids=[r.id for r in ordered],
                tie_breaker="source_type,revision_number,approved_at",
            )

        # Exactly one eligible revision.
        return ResolutionPlan(
            stage_name=stage_name,
            calculation_type=calculation_type,
            revision_id=eligible[0].id,
            missing=None,
        )

    @staticmethod
    def _raise_for_rejection(reasons: dict[str, list[str]]) -> None:
        """Raise the most specific typed error from the rejection map.

        The priority is: a demo-only set first (``MissingApprovedCoefficientError``
        via :class:`DemoCoefficientInProductionError`), then stale,
        then invalid citation. Multiple citation issues collapse to
        :class:`InvalidCitationError`.
        """
        if reasons.get("demo"):
            raise DemoCoefficientInProductionError(
                reasons["demo"][0],
                source_type="demo",
            )
        if reasons.get("stale"):
            raise StaleApprovalError(reasons["stale"][0])
        if reasons.get("missing-citation") or reasons.get("invalid-citation"):
            # The first offending revision id surfaces the error.
            revision_id = (
                reasons.get("missing-citation", [None])[0]
                or reasons.get("invalid-citation", [None])[0]
                or "<unknown>"
            )
            raise InvalidCitationError(
                "<see log>",
                f"Approved revision {revision_id} has missing/invalid citation",
            )
        # Empty set — the caller will raise MissingApprovedCoefficientError.
