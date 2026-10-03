# V2.2.2 P1A R2 P2D Footprint Regularity Recovery

## Result

`RESULT=FAIL` against the full R2 candidate-delivery target. The zones-only
outline admission gate is removed, and the canonical unmocked Xinzhao replay
now observes local 7-zone and complete 12-zone compositions in all three
structured families. No structured composition survived rigid site placement,
so none reached truck validation or P2D. The existing general-fallback
selection remains hard-valid, but its authoritative P2D footprint is classified
as `STAIR_STEP`; it is not counted as a regular visual candidate.

## Authority boundary

- `LOCAL_ZONE_UNION_OUTLINE_CLASS` is retained as diagnostic evidence only.
- The planned composition envelope is a non-authoritative generation frame;
  blank regions remain unassigned and are not zones or corridors.
- Final building footprint classification is derived from the real P2D result,
  whose source is `EXACT_ZONE_RECTANGLES_PLUS_ACCESS_CORRIDOR_ENVELOPES`.
- P2D routing, corridor generation, footprint derivation, truck authority,
  placement budget, and compatibility fallback were not changed.

## Canonical Xinzhao replay

| Measure | Result |
|---|---:|
| Raw local main compositions | 96 total; 32 per family |
| Distinct captured 7-zone compositions | 32 per family |
| Distinct captured 12-zone local compositions | 96 per family |
| Families with at least one full 12-zone local composition | 3 of 3 |
| Structured rigid site placements | 0 |
| Structured P2D full-pass candidates | 0 |
| General-fallback P2D full-pass candidates | 2 records |
| Selected validation | 12 zones; access 12/12; truck pass; P2 complete |
| Selected actual P2D footprint class | `STAIR_STEP` |
| Regular structured visual candidates | 0 |

All 12 structured attempts in the exercised structured phase failed at
`SITE_PLACEMENT` with `NO_EXACT_RIGID_TRANSLATION_FITS_SITE_AND_OBSTACLES`.
This is after local composition and before truck/P2D, not a footprint gate.
The 120-node production placement budget is unchanged.

## Local composition images

Dashed outline is the planned composition frame, not an asserted building
footprint. Empty space is intentionally blank.

- Linear: [PNG](evidence/v2_2_2_p1a/xinzhao_local_linear_composition.png) · [SVG](evidence/v2_2_2_p1a/xinzhao_local_linear_composition.svg)
- Central: [PNG](evidence/v2_2_2_p1a/xinzhao_local_central_composition.png) · [SVG](evidence/v2_2_2_p1a/xinzhao_local_central_composition.svg)
- Spine: [PNG](evidence/v2_2_2_p1a/xinzhao_local_spine_composition.png) · [SVG](evidence/v2_2_2_p1a/xinzhao_local_spine_composition.svg)

Machine-readable replay: [Xinzhao footprint regularity recovery evidence](evidence/v2_2_2_p1a/xinzhao_p1a_r2_footprint_regularity_recovery.json).

## Remaining acceptance gap

`STAGE_A_COMPLETE_12_ZONE_EXISTS=true` and
`STAGE_B_THREE_FAMILIES_COMPLETE=true`. `STAGE_C_STRUCTURED_P2D_FULL_PASS_EXISTS=false`
and `STAGE_D_FINAL_VISUAL_ACCEPTANCE=false`. The full acceptance target of at
least five visually distinct P2D-full-pass candidates in at least three layout
families is not met. No claim of visual acceptance is made.
