# R11 R15 · ten-door locker local rearrangement

TASK_ID=V2_2_2_R11_R15_TEN_DOOR_LOCKER_LOCAL_RELAYOUT_R1

Base: Draft PR #334, `784e87e1e1307b6379214903da6b2fcc393a244d`.
Independent branch: `codex/v222-r11-r15-ten-door-local-relayout`.

Scope: an additive photo-source supplement, independent analytic review of the
R14 15mm bound, and twelve finite waiting-home organizations in the unchanged
26331×3850mm counterfactual room. This is not a new layout search strategy,
Authority, approval mechanism, MAIN Runner or production integration.

The original selected 11 complete 850×390×1800mm units, 22 columns, 110 cells,
U06 mixed-shift columns, 53 people/shift, 55 exclusively allocated cells/shift
and four total spares are unchanged. No half cabinets or twelfth unit.

## Sources and unapproved conditions

R15's fixed Owner supplement is
`V2_2_2-r11-r15-owner-photo-supplement.txt`, SHA256
`6c4026e6c40a084ca1eff339cf199e7c46f662935b4bd8dc1f08a6b1959f59af`.
It references the original R14 selection source without overwriting it.
Owner-reported photo `IMG_0875.jpeg` has expected SHA256
`833c674259d29129d75703c37c6eb532b360d09647f3e221f6cce3951b41ccaa`.
Only matching raw bytes establish original-file evidence. If absent, actual
photo digest remains null/INPUT_REQUIRED. The photo is never copied, embedded
or published by the report generator; technical review remains unproved.

The strict sensitivity retains finish30mm, installation base40mm, margin
target100mm, 450×650mm transport body, 600×900mm front-changing envelope,
100mm base waiting gap plus100mm padding (200mm actual waiting gap), 1200mm
base aisle plus100mm padding (1300mm reserved), and both original1500mm
Portals. Body height1800mm, the original conditional reach and closed-door
movement assumptions remain unapproved. Whole cabinets and assignments do not
move; only waiting-home geometry and its roster ordering are enumerated.

## Finite candidates and separate gates

Three south-grid choices × two north-row choices × two row orders = twelve
combinations, strictly below36. Static failures do not start full motion.
Every static53-home combination receives the original two-shift movement and
per-door tests. Static PASS is not continuous-flow PASS. Collision-free
combined flow is not a100mm-margin PASS or actual functional approval.

Five combinations complete both shifts under ALL_LEFT and MIRRORED90°
hypotheses. R15-03 changes fewer roster-bound home records:14 north homes move
35mm north; a15th north home becomes available, for53 total. Actual generated
home53 bounds are `[12780,3225,13430,3675]`mm. These are output evidence, not
injected known coordinates. Cabinet, room, aisle and Portal geometry remain
unchanged. Three NORTH_FIRST candidates have53 static homes but fail entry
because the real rotated approach collides with a waiting person. Their
failures are retained.

The selected case completes53 entrants/initial occupants/served/exited users
for each shift and212 necessary person-opening events in each hinge profile.
Its65mm door bound remains below the unchanged100mm target. No candidate is
reported as satisfying every100mm margin.

## Distance proof

The existing analytic sweep is a quarter disk plus an axis-aligned thickness
square. Translate this Minkowski term to the target rectangle, then minimize
distance over the two radial segments and circular arc; combine vertical
separation by Pythagoras. Integer square-root intervals enclose distances to
0.001mm. Drawing samples are never used as proof.

R14's S1/E110/U01-L-T1-DOOR/S1-P001 yields an exact15.000mm distance **to this
conservative conditional model**, without collision. The15mm enclosure bound
is tight at that event and cannot become50mm through a tighter calculation.
Actual hardware/human distance remains INPUT_REQUIRED.50/100mm are unapproved
sensitivity targets, not introduced standards.

## Reproduction and local boundary

Use the Python3.12 locked dependency environment. From repository root:

```bash
PYTHONPATH=backend/src:backend/scripts python backend/scripts/validate_r11_r15_whitelist.py \
  --focused --evidence artifacts/r15-validation/focused-new
PYTHONPATH=backend/src:backend/scripts python backend/scripts/validate_r11_r15_whitelist.py \
  --evidence artifacts/r15-validation/all-new
PYTHONPATH=backend/src:backend/scripts python backend/scripts/build_r11_r15_local_relayout_review.py \
  --output artifacts/r15-review-new
```

All output directories must be new. The generator may accept an explicit
private `--photo /private/location/IMG_0875.jpeg`; it rejects mismatched bytes
and never exports the original photo. Do not fabricate a substitute image.
No image is supplied in the delivered record.

Both validation and generation reuse the existing guarded re-execution and
startup guard for both `CpSolver.solve` and `CpSolver.Solve`. Child Python
inherits the same protection. Negative probes intentionally request blocked
calls; those are not actual Native solves. Local tests use the explicit R15
and R11 functional/architecture whitelist, not the Stage B/Native directory.
The fast workflow appends only the new R15 test file; existing synthetic
Native tests remain and are distinguished from this task's local zero solves.

Historical R3–R14 source/results, R9 boundary exception, P1, Stage B,
comparators, MCP and production defaults remain byte-identical. No new20t
Native, MAIN, real Grant/Claim, formal fullCI, Ready, Merge or Deploy.

ACTUAL_CALIBRATION=INPUT_REQUIRED

ENGINEERING_APPROVAL=NOT_EVALUATED

FACTORY_APPLICABILITY=NOT_EVALUATED
