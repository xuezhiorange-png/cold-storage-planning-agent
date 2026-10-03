# V2.2.2 P1A R2 Access-Corridor-Aware Tail Completion Recovery

**Task:** `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`
**Mode:** `R2_ACCESS_CORRIDOR_AWARE_TAIL_COMPLETION_RECOVERY`
**Baseline:** `b680f8e35e399aae94cc212e4f11693fe8e854a8`
**Result:** `FAIL` — deterministic and fallback-valid, but no structured 12-zone candidate reached P2D.

## Scope and authority

The structured S2 tail phase now receives a thin application-layer validator backed by the existing `route_access_requirement()` authority. The placement domain does not import access routing. Structured personnel candidates are admitted only after both existing people routes pass; secondary-fruit and frozen-fruit placements are admitted only after their respective existing access route passes. Exact route corridor envelopes are reserved against later tail placements, and all active S2 routes are revalidated after each extension.

Final P2D remains an independent full validation. No access profile, route/portal/corridor rule, Truck authority, geometry authority, or node budget was changed. Configured budgets remain placement `120`, Truck `5000`, and route `20000`. The General Fallback / P1F compatibility path was not changed.

## Real Xinzhao Tool 7 replay

The canonical Xinzhao fixture was replayed twice without mocking Tool 7 or the access/P2D validators. Both runs agreed on access-slot counts, captured witnesses, P2D route rows, selected fallback layout, canonical result hash, SVG bytes, and SVG hash.

The structured path did not complete a 12-zone candidate:

| Measure | Result |
| --- | ---: |
| Structured placement context budget / visits | `36 / 36` (exhausted) |
| Global truncation flag / module sampling flags (personnel, secondary, frozen) | `false / 1, 1, 1` |
| Personnel geometry-slot occurrences / exact route probes / 2-of-2 pass | `55 / 12 / 0` |
| Secondary-fruit geometry-slot occurrences / exact route probes / pass | `129 / 1 / 1` |
| Frozen-fruit geometry-slot occurrences / exact route probes / pass | `64 / 12 / 0` |
| Exact construction route failures | `24`, all `ROUTE_SEARCH_EXHAUSTED` |
| Complete access-aware 12-zone candidates | `0` |
| Structured P2D attempts / full passes | `0 / 0` |
| Distinct structured full-pass skeletons | `0` |
| Visually acceptable full-pass candidates / families | `0 / 0` |

The run-level `tail_candidate_space_truncated` flag remained false, while the separate per-module sampling counters each recorded a truncated representative set (up to 12 representatives per route-probe set). Those raw-generation/probe counts and the zero-pass counts are observations from bounded construction coverage, **not** proof that no route-feasible placement exists. The configured global placement budget remains 120; this structured context received 36 nodes and exhausted that allocation. The replay does not justify changing any route authority or budget.

The independently selected General Fallback result remained hard-valid: project layout validated, P2 complete, 12/12 access, Truck route validated, and 12 zones. Its canonical result hash was `sha256:c8f4011cd0d565e6ecd0ce636ee50586d0d1d075e51eff0d845c156f31ca9d19`; SVG SHA-256 was `sha256:007f8066b55a3bdcf2583e0e4d9c2f325e1c2c6cee4bc9aa8fb9fd4a57c109d2`.

The reported construction-witness/P2D mismatch count is zero, but no complete construction witness existed; this count is therefore vacuous, not evidence of a structured full-pass.

## Evidence

- [Generated replay evidence](evidence/v2_2_2_p1a/xinzhao_p1a_r2_access_aware_tail_completion.json)
- [Access-aware tail candidate image](evidence/v2_2_2_p1a/xinzhao_access_aware_tail_candidates.png)
- [Access-aware tail candidate SVG](evidence/v2_2_2_p1a/xinzhao_access_aware_tail_candidates.svg)

The image shows the sampled partial structured tail witness only; it is not a complete 12-zone candidate or a P2D result. No P2D full-pass gallery was generated because the structured path produced no P2D candidate.

## Verification

- Focused R2 unit and architecture tests: `45 passed`.
- R9/R11/R13/R15 truck-construction, P1F, P2C/P2D, and related architecture regression selection: `130 passed`.
- Full architecture suite: `781 passed, 16 skipped`.
- P1F cross-fixture full-chain evaluation and exact-head CI are reported separately after their final runs; no historical assertion or evidence is weakened.
- Ruff, Ruff format check, production-source mypy, and `git diff --check`: passed.

## Closure

`DETERMINISM=PASS` is separate from task acceptance. Since the required structured access-aware 12-zone candidate and structured P2D full-pass were not produced, the recovery result remains `FAIL`. PR #302 remains Draft; no Ready, merge, tag, release, or deployment action is authorized.
