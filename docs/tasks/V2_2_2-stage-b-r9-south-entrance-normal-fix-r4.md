# R9 entrance normal correction and synthetic post-baseline verification

Task: V2_2_2_STAGE_B_R9_SOUTH_ENTRANCE_NORMAL_FIX_R4.
Base: ed0687313dc3d8c0368a87f65dcb8abf45542fcf (PR314, unchanged).

## Correction

`AccessModel.endpoint()` now selects the entrance axis before comparing its fixed
coordinate with the corresponding site bounds. West/east use sx/sr; south/north
use sy/st. An interior entrance raises `ENTRANCE_BOUNDARY_REFERENCE_INVALID`.
Previously a south entrance at y=0 on a site with sx=0 selected the west normal:
Q.y=0 made the first 2m corridor corner require both y=-1000mm and y>=0.
A square site's north edge could similarly be mistaken for east when sr==st.

No portal widths, offsets, corridor envelopes, room constraints, P1, Site, MUST,
Access validators, R7/R9 strategy, objective, comparator or production default is
changed. Existing source/dependency/HEAD admission remains mandatory for any
future real execution; this change does not authorize one.

## Constraint regressions

The actual `AccessModel` endpoint/portal/strip/corner constraints are solved in
small independent models (only unrelated base room construction is isolated).
Four directions cover a zero-origin square, nonzero equal-origin square and
nonzero unequal origins. Tests check the solved P-to-Q vector is cw/2 inward and
all actual envelopes remain inside Site; south's first corner starts at sy,
not sy-1000. Both internal entrance orientations must reject during construction.
Before the fix: 8 PASS / 6 FAIL. After: all 14 PASS. The new full-fixture
regression also runs both original engineering validation chains without mocks.

## Revalidated R3 engineering fixtures

The portable fixture in `backend/tests/r9_full_engineering_synthetic.py` preserves
R2/R3's deterministic 1t/day Plan, P1, Typed Site, obstacle, process Handoff and
legally rotated 14.96x7.6m Sorting room. Packaging remains 4x4m. Its horizontal
LONG edge and Sorting's horizontal SHORT edge share the original 2.4m direct
portal. A and B each pass 12 roles, 7 MUST, 11 non-Truck Access, independent
geometry/native validation, exact connected zero-hole union, Site/Footprint and
`_eligible()`. No frozen 20t Native solving or actual Grant/Claim is used.

A/B have the same Handoff, V2 organization and original area proxy 1225:

| Actual engineering metric | A | B |
| --- | ---: | ---: |
| Personnel route m / turns | 28 / 2 | 26 / 2 |
| Building area m2 | 585.5105 | 581.5105 |
| Perimeter m | 229.906 | 237.906 |
| Outline / reflex corners | 40 / 18 | 42 / 19 |

Both original nine- and twelve-metric comparators return `QUALITY_TRADEOFF`.
Truck and P2D are not validated.

## Bounded original R7/R9 search

[Actual Native geometries](../previews/v2.2.2/r9-south-entrance-normal-fix-r4/native-second-stage-comparison.svg)
and [machine-readable evidence](../previews/v2.2.2/r9-south-entrance-normal-fix-r4/validation.json).

Both arms use original first/second-stage control flow, independent validators,
valid physical Hint, exact cuts, Presolve, PARTIAL_FIXED_SEARCH, one worker and
final-model seed 3. Original warmups retain seed 0. Test-only factories restrict
the final model to this synthetic floor plan with Changing x in [40,42]m at
integer-mm resolution; neither A/B is injected as a Hint or forced first result.
The original warmup clone cuts remove tail fixture equalities in early phases;
both arms retain that same broader warmup scope. This is a restricted synthetic
mechanism check, not the unrestricted real factory search.

Each arm receives the same cumulative local test limits: 8s Native, 60s elapsed,
600000 Work, 512MiB RSS, 12 calls, 6 complete checks; original per-requirement Host
20000 protection remains. No actual Store, Lease, Grant or Claim is created.

Both final first stages return OPTIMAL and pass original engineering acceptance.
Only then the original stream installs a 130-variable current-valid physical
Hint and starts improvement; R9's own joint strategy receipt is present. Both
then produce the same sequence:

| Observation | Changing x m | Route m | Perimeter m | Result |
| --- | ---: | ---: | ---: | --- |
| First valid baseline | 40 | 26.750 | 227.906 | baseline V2: east portal |
| First second-stage return | 40 | 26.750 | 227.906 | repeated baseline |
| New geometry C03 | 40.001 | 32.749 | 251.904 | west portal; different V2 |
| New geometry C04 | 40.002 | 32.748 | 251.902 | west portal; different V2 |
| Terminal call | - | - | - | UNKNOWN, no infeasibility claim |

All four observations pass independent engineering checks. There are only three
unique geometries per arm: baseline plus **two new second-stage geometries**.
R9 does not find a shorter route than its baseline or more geometries than R7.
The known independently accepted 26m B alternative is shorter than the native
26.75m baseline, so the scene is not disqualified for lack of route headroom.

The original callback sees proxy 1225 throughout and never requests early stop.
A normal OPTIMAL return still allows enumeration: no UNKNOWN-to-INFEASIBLE
conversion, no fake acceptance and no baseline cut before initial improvement.
After the repeated baseline, room geometry cuts advance only 1mm at a time in
this trace. The old 130-variable valid Hint remains present; no strict proxy
frontier update occurs. These observations do not establish that removing Hint
or changing decision order would fix the remaining search limitation.

Baseline-to-C03/C04 comparisons are `NOT_COMPARABLE_STRUCTURE`, not Pareto wins.
C03-to-C04 within their west-portal V2 is an exact original strict Pareto change
of only 1mm route and 2mm perimeter; this is not baseline improvement or meaningful
whole-factory quality evidence. Comparators and tolerances are unchanged.

## Resources and limits

| Recorded resource | R7 | R9 |
| --- | ---: | ---: |
| Native solver wall s | 8.007802 | 8.011514 |
| Conservative cumulative wall s | 8.014003167 | 8.015419167 |
| Work | 175770 | 176027 |
| Native calls / complete checks | 9 / 4 | 9 / 4 |
| Peak RSS bytes | 239468544 | 261423104 |

**The local 8s Native quota is exceeded slightly: resource validation is FAIL,
not all PASS.** CP-SAT's cooperative deadline returns UNKNOWN slightly late;
the reused R3 memory-only test adapter did not enforce a post-Solve Native
counter guard. No counts are truncated, no quota is raised, no retry is run and
no production Lease is relaxed. Earlier valid candidates are preserved; the
overshoot cannot be used to claim full resource acceptance or MAIN readiness.

R9 adds 257 recorded Work for its actual strategy metadata/reference operations.
Test-domain construction and evidence IO are not represented as production Work.
This single paired run establishes no speedup or real factory efficiency gain.

## Validation and boundary

Local focused regression: 192 PASS, one Linux physical RSS case explicitly
excluded on macOS (NOT_RUN_ENVIRONMENT_SPECIFIC). Ruff/format/diff checks pass;
Mypy passes 452 source files. CI contracts: 64 PASS including 50 cleanup repeats.
The fast workflow adds this new regression file; formal ci.yml is unchanged.

Native raw models, candidate JSON, audits, quota records and before/after logs
are retained in the local `stage-b-r9-south-entrance-normal-fix-r4` artifact
folder. No real MAIN, Grant, Claim, formal CI, Ready, Merge or Deploy. PR313 and
PR314 and their historical resource records remain unchanged.
