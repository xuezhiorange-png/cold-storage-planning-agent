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


def validate_weight_set(ws: SchemeWeightSet) -> None:
    """Validate a weight set's integrity. Raises on failure."""
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


def _normalize_higher(x: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    if min_val == max_val:
        return _D("100")
    return _D("100") * (x - min_val) / (max_val - min_val)


def _normalize_lower(x: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    if min_val == max_val:
        return _D("100")
    return _D("100") * (max_val - x) / (max_val - min_val)


def _normalize_binary(passed: bool) -> Decimal:
    return _D("100") if passed else _D("0")


def extract_criterion_value(candidate: SchemeCandidate, criterion_code: str) -> Decimal:
    """Extract the raw value for a criterion from a candidate."""
    mapping = {
        "total_area_m2": _D(str(candidate.total_area_m2)),
        "total_position_count": _D(str(candidate.total_position_count)),
        "room_module_count": _D(str(candidate.room_module_count)),
        "door_count": _D(str(candidate.door_count)),
        "partition_length_proxy_m": _D(str(candidate.partition_length_proxy_m)),
        "investment_cny": _D(str(candidate.investment_cny)),
        "installed_power_kw_e": _D(str(candidate.installed_power_kw_e)),
        "design_cooling_load_kw_r": _D(str(candidate.design_cooling_load_kw_r)),
        "compressor_installed_capacity_kw_r": _D(str(candidate.compressor_installed_capacity_kw_r)),
        "condenser_heat_rejection_kw": _D(str(candidate.condenser_heat_rejection_kw)),
        "daily_throughput_kg_day": _D(str(candidate.daily_throughput_kg_day)),
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


def score_candidates(
    candidates: list[SchemeCandidate],
    weight_set: SchemeWeightSet,
) -> list[SchemeScoreBreakdown]:
    """Score all candidates using the given weight set. Returns breakdowns."""
    validate_weight_set(weight_set)

    # Collect all raw values per criterion
    all_values: dict[str, list[Decimal]] = {}
    for c in weight_set.criteria:
        if not c.hard_constraint:
            vals = [extract_candidate_value(cand, c.criterion_code) for cand in candidates]
            all_values[c.criterion_code] = vals

    # Compute min/max per criterion
    ranges: dict[str, tuple[Decimal, Decimal]] = {}
    for code, vals in all_values.items():
        ranges[code] = (min(vals), max(vals))

    # Score each candidate
    breakdowns: list[SchemeScoreBreakdown] = []
    for cand in candidates:
        scores: list[SchemeCriterionScore] = []
        total = _D("0")

        for wc in weight_set.criteria:
            if wc.hard_constraint:
                continue

            raw = extract_candidate_value(cand, wc.criterion_code)
            min_val, max_val = ranges[wc.criterion_code]

            if wc.direction == "higher_is_better":
                norm = _normalize_higher(raw, min_val, max_val)
                formula = "100 * (x - min) / (max - min)"
            elif wc.direction == "lower_is_better":
                norm = _normalize_lower(raw, min_val, max_val)
                formula = "100 * (max - x) / (max - min)"
            elif wc.direction == "binary_pass":
                norm = _normalize_binary(raw > 0)
                formula = "pass=100, fail=0"
            else:
                raise WeightSetError(f"Unknown direction: {wc.direction}")

            weighted = (norm * wc.weight).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
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
                    normalized_score=norm.quantize(_D("0.001"), rounding=ROUND_HALF_UP),
                    weighted_contribution=weighted,
                    formula=formula,
                )
            )

        total_score = total.quantize(_D("0.001"), rounding=ROUND_HALF_UP)
        breakdowns.append(
            SchemeScoreBreakdown(
                scheme_code=cand.scheme_code,
                total_score=total_score,
                criterion_scores=scores,
            )
        )

    return breakdowns


def _infer_unit(code: str) -> str:
    units = {
        "total_area_m2": "m2",
        "total_position_count": "positions",
        "room_module_count": "modules",
        "door_count": "doors",
        "partition_length_proxy_m": "m",
        "investment_cny": "CNY",
        "installed_power_kw_e": "kW(e)",
        "design_cooling_load_kw_r": "kW(r)",
        "compressor_installed_capacity_kw_r": "kW(r)",
        "condenser_heat_rejection_kw": "kW(r)",
        "daily_throughput_kg_day": "kg/day",
        "area_efficiency_kg_day_per_m2": "kg/day/m2",
        "investment_per_ton_day_cny": "CNY/ton/day",
        "investment_per_m2_cny": "CNY/m2",
        "power_intensity_kw_e_per_ton_day": "kW(e)/ton/day",
    }
    return units.get(code, "")


def extract_candidate_value(candidate: SchemeCandidate, code: str) -> Decimal:
    return extract_criterion_value(candidate, code)


def stable_sort_key(
    breakdown: SchemeScoreBreakdown, candidates: list[SchemeCandidate]
) -> tuple[float, float, float, str]:
    """Sort key for stable recommendation ranking."""
    cand_map = {c.scheme_code: c for c in candidates}
    cand = cand_map[breakdown.scheme_code]
    return (
        -float(breakdown.total_score),  # highest first
        cand.investment_cny,  # lowest investment first
        cand.installed_power_kw_e,  # lowest power first
        breakdown.scheme_code,  # dict order
    )
