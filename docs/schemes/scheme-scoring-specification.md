# Scheme Scoring Specification

## Normalization

### higher_is_better
```
score = 100 × (x - min) / (max - min)
```

### lower_is_better
```
score = 100 × (max - x) / (max - min)
```

### All candidates identical
```
score = 100
```

### binary_pass
```
pass = 100, fail = 0
```

## Weighted Contribution
```
weighted_contribution = normalized_score × weight
total_score = Σ weighted_contribution
```

Final total_score rounded to 3 decimal places using ROUND_HALF_UP.

## Per-Criterion Output
Each criterion produces:
- raw_value
- unit
- direction
- weight
- min_value
- max_value
- normalized_score
- weighted_contribution
- formula

## Weight Rules
1. Non-hard-constraint weights sum to exactly 1.0
2. All weights in [0, 1]
3. No duplicate criterion codes
4. All required criteria present
5. Withdrawn weight sets rejected
6. No default weights in domain code

## Stable Sort
1. total_score descending
2. investment_cny ascending
3. installed_power_kw_e ascending
4. scheme_code lexicographic

## Infeasible Exclusion
Only feasible candidates (all hard constraints pass) are eligible for recommendation.
If no feasible candidate exists: recommended_scheme_code = null, NO_FEASIBLE_SCHEME.
