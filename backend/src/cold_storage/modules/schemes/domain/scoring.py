"""Scheme scoring — normalized, weighted, deterministic with Decimal precision."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from cold_storage.modules.schemes.domain.errors import (
    DuplicateCriterionError,
    MissingCriterionError,
    NegativeWeightError,
    WeightOutOfRangeError,
    WeightSetError,
    WeightSumError,
    WithdrawnWeightSetError,
)
from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeCriterionScore,
    SchemeScoreBreakdown,
    SchemeWeightSet,
)

_D = Decimal

# Required criterion codes that must exist in every weight set
REQUIRED_CRITERIA: frozenset[str] = frozenset(
    {
        "total_area_m2",
        "total_position_count",
        "room_module_count",
        "door_count",
        "partition_length_proxy_m",
        "investment_cny",
        "installed_power_kw_e",
    }
)


# ---------------------------------------------------------------------------
# Weight set validation
# ---------------------------------------------------------------------------


def validate_weight_set(ws: SchemeWeightSet) -> None:
    """Validate a weight set's integrity. Raises on failure.

    Checks performed:
    - Status must not be ``withdrawn``
    - No duplicate criterion codes
    - No negative weights
    - No weights exceeding 1
    - All required criteria present
    - Non-hard-constraint weights must sum to exactly 1.0
    """
    if ws.status == "withdrawn":
        raise WithdrawnWeightSetError(ws.id)

    codes_seen: set[str] = set()
    non_hard_sum = _D("0")

    for c in ws.criteria:
        if c.criterion_code in codes_seen:
            raise DuplicateCriterionError(c.criterion_code)
        codes_seen.add(c.criterion_code)

        if c.weight < 0:
            raise NegativeWeightError(c.criterion_code, float(c.weight))
        if c.weight > 1:
            raise WeightOutOfRangeError(c.criterion_code, float(c.weight))

        if not c.hard_constraint:
            non_hard_sum += c.weight

    for req in REQUIRED_CRITERIA:
        if req not in codes_seen:
            raise MissingCriterionError(req)

    if non_hard_sum != _D("1"):
        raise WeightSumError(float(non_hard_sum))


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_min_max(x: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """Min-max normalization scaled to [0, 100].

    When ``min_val == max_val`` (all candidates identical) the result is 100
    to avoid division by zero and treat the single value as "best".
    """
    if min_val == max_val:
        return _D("100")
    return _D("100") * (x - min_val) / (max_val - min_val)


# ---------------------------------------------------------------------------
# Criterion value extraction
# ---------------------------------------------------------------------------


def extract_criterion_value(candidate: SchemeCandidate, criterion_code: str) -> Decimal:
    """Extract the raw numeric value for *criterion_code* from *candidate*.

    Raises ``ValueError`` for unknown criterion codes.
    """
    mapping: dict[str, Decimal] = {
        # ---- Required criteria (hard-constraint + scoring) ----
        "total_area_m2": _D(str(candidate.total_area_m2)),
        "total_position_count": _D(str(candidate.total_position_count)),
        "room_module_count": _D(str(candidate.room_module_count)),
        "door_count": _D(str(candidate.door_count)),
        "partition_length_proxy_m": _D(str(candidate.partition_length_proxy_m)),
        "investment_cny": _D(str(candidate.investment_cny)),
        "installed_power_kw_e": _D(str(candidate.installed_power_kw_e)),
        # ---- Optional scoring criteria ----
        "design_cooling_load_kw_r": _D(str(candidate.design_cooling_load_kw_r)),
        "compressor_installed_capacity_kw_r": _D(str(candidate.compressor_installed_capacity_kw_r)),
        "condenser_heat_rejection_kw": _D(str(candidate.condenser_heat_rejection_kw)),
        "daily_throughput_kg_day": _D(str(candidate.daily_throughput_kg_day)),
        # ---- Derived criteria ----
        "area_efficiency_kg_day_per_m2": (
            _D(str(candidate.daily_throughput_kg_day / candidate.total_area_m2))
            if candidate.total_area_m2 > 0
            else _D("0")
        ),
        "investment_per_ton_day_cny": (
            _D(str(candidate.investment_cny / (candidate.daily_throughput_kg_day / 1000)))
            if candidate.daily_throughput_kg_day > 0
            else _D("0")
        ),
        "investment_per_m2_cny": (
            _D(str(candidate.investment_cny / candidate.total_area_m2))
            if candidate.total_area_m2 > 0
            else _D("0")
        ),
        "power_intensity_kw_e_per_ton_day": (
            _D(str(candidate.installed_power_kw_e / (candidate.daily_throughput_kg_day / 1000)))
            if candidate.daily_throughput_kg_day > 0
            else _D("0")
        ),
    }
    val = mapping.get(criterion_code)
    if val is None:
        raise ValueError(f"Unknown criterion code: {criterion_code}")
    return val


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_single_candidate(
    candidate: SchemeCandidate,
    weight_set: SchemeWeightSet,
    ranges: dict[str, tuple[Decimal, Decimal]],
) -> tuple[SchemeScoreBreakdown, Decimal]:
    """Score one candidate against pre-computed min/max ranges.

    Returns the ``SchemeScoreBreakdown`` and the un-quantised total (for
    intermediate use).
    """
    scores: list[SchemeCriterionScore] = []
    total = _D("0")

    for wc in weight_set.criteria:
        if wc.hard_constraint:
            continue

        raw = extract_criterion_value(candidate, wc.criterion_code)
        min_val, max_val = ranges[wc.criterion_code]

        if wc.direction == "higher_is_better":
            norm = normalize_min_max(raw, min_val, max_val)
            formula = "100 * (x - min) / (max - min)"
        elif wc.direction == "lower_is_better":
            # Inverted: lower raw value → higher score
            if min_val == max_val:
                norm = _D("100")
            else:
                norm = _D("100") * (max_val - raw) / (max_val - min_val)
            formula = "100 * (max - x) / (max - min)"
        elif wc.direction == "binary_pass":
            norm = _D("100") if raw > 0 else _D("0")
            formula = "pass=100, fail=0"
        else:
            raise WeightSetError(f"Unknown direction: {wc.direction}")

        norm_quantized = norm.quantize(_D("0.001"), rounding=ROUND_HALF_UP)
        weighted = (norm_quantized * wc.weight).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
        total += weighted

        scores.append(
            SchemeCriterionScore(
                criterion_code=wc.criterion_code,
                raw_value=raw,
                unit=_infer_unit(wc.criterion_code),
                direction=wc.direction,
                weight=wc.weight,
                min_value=min_val,
                max_value=max_val,
                normalized_score=norm_quantized,
                weighted_contribution=weighted,
                formula=formula,
            )
        )

    total_score = total.quantize(_D("0.001"), rounding=ROUND_HALF_UP)
    breakdown = SchemeScoreBreakdown(
        scheme_code=candidate.scheme_code,
        total_score=total_score,
        criterion_scores=scores,
    )
    return breakdown, total_score


def score_candidates(
    candidates: list[SchemeCandidate],
    weight_set: SchemeWeightSet,
) -> list[SchemeScoreBreakdown]:
    """Score all candidates using the given weight set.

    **Feasible** candidates participate in min/max normalization.
    **Infeasible** candidates are scored against the feasible ranges but marked
    ``diagnostic_only=True`` so they never influence the feasible min/max.

    Returns a list of ``SchemeScoreBreakdown`` for every candidate.
    """
    validate_weight_set(weight_set)

    feasible = [c for c in candidates if c.feasible]
    infeasible = [c for c in candidates if not c.feasible]

    # Compute min/max ranges from feasible candidates only
    ranges: dict[str, tuple[Decimal, Decimal]] = {}
    for wc in weight_set.criteria:
        if wc.hard_constraint:
            continue
        if feasible:
            vals = [extract_criterion_value(cand, wc.criterion_code) for cand in feasible]
            ranges[wc.criterion_code] = (min(vals), max(vals))
        else:
            # No feasible candidates: placeholder ranges (won't affect scoring
            # since every candidate is infeasible)
            ranges[wc.criterion_code] = (_D("0"), _D("0"))

    breakdowns: list[SchemeScoreBreakdown] = []

    # Score feasible candidates normally
    for cand in feasible:
        bd, _total = _score_single_candidate(cand, weight_set, ranges)
        breakdowns.append(bd)

    # Score infeasible candidates with diagnostic_only=True
    for cand in infeasible:
        bd, _total = _score_single_candidate(cand, weight_set, ranges)
        breakdowns.append(
            SchemeScoreBreakdown(
                scheme_code=bd.scheme_code,
                total_score=bd.total_score,
                criterion_scores=bd.criterion_scores,
                diagnostic_only=True,
            )
        )

    return breakdowns


# ---------------------------------------------------------------------------
# Unit inference
# ---------------------------------------------------------------------------


def _infer_unit(code: str) -> str:
    """Map a criterion code to its human-readable unit string."""
    units: dict[str, str] = {
        "total_area_m2": "m2",
        "total_position_count": "positions",
        "room_module_count": "modules",
        "door_count": "doors",
        "partition_length_proxy_m": "m",
        "investment_cny": "CNY",
        "installed_power_kw_e": "kW(e)",
        "design_cooling_load_kw_r": "kW(r)",
        "compressor_installed_capacity_kw_r": "kW(r)",
        "condenser_heat_rejection_kw": "kW(th)",
        "daily_throughput_kg_day": "kg/day",
        "area_efficiency_kg_day_per_m2": "kg/day/m2",
        "investment_per_ton_day_cny": "CNY/ton/day",
        "investment_per_m2_cny": "CNY/m2",
        "power_intensity_kw_e_per_ton_day": "kW(e)/ton/day",
    }
    return units.get(code, "")


# ---------------------------------------------------------------------------
# Sort key
# ---------------------------------------------------------------------------


def stable_sort_key(
    breakdown: SchemeScoreBreakdown,
    candidates: list[SchemeCandidate],
) -> tuple[Decimal, Decimal, Decimal, str]:
    """Deterministic sort key for ranking scheme candidates.

    Order of priority (all using ``Decimal`` for precision):
    1. ``-total_score`` — highest score first
    2. ``investment_cny`` — lower investment first
    3. ``installed_power_kw_e`` — lower power first
    4. ``scheme_code`` — lexicographic tiebreak
    """
    cand_map = {c.scheme_code: c for c in candidates}
    cand = cand_map[breakdown.scheme_code]
    return (
        -breakdown.total_score,
        cand.investment_cny,
        cand.installed_power_kw_e,
        breakdown.scheme_code,
    )
