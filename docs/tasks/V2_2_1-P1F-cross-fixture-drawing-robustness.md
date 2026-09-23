# V2.2.1 P1F — Cross-fixture drawing robustness

```ini
TASK_ID=V2_2_1_P1F_CROSS_FIXTURE_DRAWING_ROBUSTNESS_RERUN_R2
PR_NUMBER=297
PREVIOUS_PR_HEAD_SHA=0631d9f3410b54ff862406922f110505949ac85f
NEW_BASE_MAIN_SHA=0ba8334a8fd6c4dde5b887c12a6a271d0cad1fce
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1F
NEW_DRAWING_FEATURES_AUTHORIZED=false
ENGINEERING_ALGORITHM_CHANGED=false
VISUAL_STYLE_REDESIGN_AUTHORIZED=false
FULL_CHAIN_AUTHORITATIVE_FIXTURE_COUNT=3
COMPOSITION_ONLY_FIXTURE_COUNT=2
TOTAL_DRAWING_SCENARIO_COUNT=5
FULL_CHAIN_PROFILE_ROW_COUNT=12
PREVIOUS_FAILED_PROFILE_COMBINATIONS=6
AFTER_FAILED_PROFILE_COMBINATIONS=0
PRESENTATION_CONTEXT_LOADING_FACE_COMPLETE=true
MOBILE_CONTEXT_LOADING_FACE_COMPLETE=true
DRAWING_LINT_FAILED_SCENARIO_COUNT=0
DETERMINISM_FAILED_SCENARIO_COUNT=0
VISUAL_BLOCKER_SCENARIO_COUNT=0
VISUAL_BLOCKER_PROFILE_COMBINATIONS=0
RIGHT_RAIL_PATH_VALIDATED=true
BOTTOM_RAIL_PATH_VALIDATED=true
P1F_AUTOMATED_MATRIX_ACCEPTANCE=PASS
OWNER_VISUAL_REVIEW=PASS
P1F_ACCEPTANCE_COMPLETE=true
P1F_BLOCKERS=NONE
P1F_MERGED=true
P1F_FINAL_MERGE_SHA=a71347a7ca56c32b2facaa3b57e489427b9a7ea8
P1F_FINAL_EXACT_HEAD_SHA=aea30a6e6d0e640574451fd5f58bcf5d291fe278
P1F_FINAL_EXACT_CI_RUN_ID=35838403105
P1F_FINAL_EXACT_CI_RESULT=SUCCESS
PREVIOUS_BLOCKER=CONTEXT_INSET_MISSING_SHIPPING_LOADING_FACE
PREVIOUS_BLOCKER_RESOLVED_BY_PR=298
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
P1G_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## Current R2 rerun

The merged PR #298 correction was exercised across the unchanged three
authoritative full-chain fixtures and two bounds-only composition scenarios.
The 12 full-chain fixture/profile rows were produced by the P1F evaluator,
not hand-edited. For PRESENTATION, MOBILE_PREVIEW, and ENGINEERING_SHEET, the
context loading-face line is present and its SVG endpoints exactly match the
projection of that fixture's authoritative `shipping_loading_face_segment`.
The six combinations that failed in the original R1 evaluation now pass; no
new fixture, candidate mapping, renderer feature, or geometry rule was added.

The machine-readable [R2 acceptance matrix](evidence/v2_2_1_p1f/acceptance-matrix.json)
contains the full 12-row lint/evidence/hash matrix, both composition-only
candidate traces, all three authoritative layout hashes, deterministic replay
results, and regenerated visual-artifact hashes. All 12 rows have Drawing
Lint `PASS`, zero errors, zero unavailable required facts, and deterministic
SVG/lint replays. Both `RIGHT_RAIL` and `BOTTOM_RAIL` paths remain covered;
the latter remains bounds-only and does not claim a validated project or SVG.

Representative renderer baselines after the merged correction:

```ini
PRESENTATION_SVG_SHA256=sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a
MOBILE_PREVIEW_SVG_SHA256=sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2
ENGINEERING_SHEET_SVG_SHA256=sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3
ENGINEERING_REVIEW_SVG_SHA256=sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d
REPRESENTATIVE_DRAWING_BYTES_CHANGED_BY_P1F_RERUN=false
```

The P1E primary-plan metrics remain based on actual primary bounds:
screen occupancy `0.7943176771550949`, width ratio `0.8998748435544431`, and
height ratio `0.8826979472140762` (`71.9 × 60.2 m` primary bounds). They are
not forced to `1.0` by the inset-adjusted drawing bounds.

Visual evidence was regenerated from the R2 evaluation run: representative
PRESENTATION, MOBILE_PREVIEW, and ENGINEERING_SHEET; the no-build-site
ENGINEERING_SHEET; the concave-site ENGINEERING_REVIEW; and direct context-inset
renders for PRESENTATION and MOBILE_PREVIEW. These are raw SVG projections and
direct SVG renders/crops, with no editing of engineering or drawing geometry.
Owner visual review subsequently passed. P1F acceptance is complete; this
review approval does not authorize a new drawing phase or release execution.

### R2 regenerated visual evidence

The full SVG/PNG files below were regenerated from the existing authoritative
fixtures on the R2 branch. The context images are direct evidence views of the
SVG inset; the loading-face detail views are crops used only to inspect that
the transformed segment is present. The underlying SVG files are linked and
unchanged by those evidence crops.

| Sample | PNG SHA-256 | SVG SHA-256 | Files |
| --- | --- | --- | --- |
| P2D representative — PRESENTATION | `5a1df8aeee3ee6ec186d3c3ac329e342d60088b38416e0bdb53cc82097e852f9` | `sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a` | [PNG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.png) · [SVG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.svg) |
| P2D representative — MOBILE_PREVIEW | `08febada50be4c5bcf7682612102cd9d14c205611954136f08f309238ec9b264` | `sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2` | [PNG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.png) · [SVG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.svg) |
| P2D representative — ENGINEERING_SHEET | `8158376e015a1c3af3d2a18250c43d83e5d2478a3b3904dc50442d986638fc73` | `sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3` | [PNG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.png) · [SVG](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.svg) |
| Tool 7 no-build site — ENGINEERING_SHEET | `9e16953795abf62608d19d407b14d58b05433fc06bb4a8ad59589eb0cc6bcc57` | `sha256:6a222eb31572b812ed20cb76b796907a970807aff91f4ab9ae2b21beedc6c1bf` | [PNG](evidence/v2_2_1_p1f/p4_real_selector_site_with_no_build_zones-engineering_sheet.png) · [SVG](evidence/v2_2_1_p1f/p4_real_selector_site_with_no_build_zones-engineering_sheet.svg) |
| Existing concave site — ENGINEERING_REVIEW | `a89f79c72f8d9e33c522b2d8087d8bbb88b8f0c4fe5c8f7b97d4f82106542a30` | `sha256:5feff4442d0b11047bfd0eb74bb310876ebb9f58e11697107f0753b2e1d32fbc` | [PNG](evidence/v2_2_1_p1f/p3_existing_concave_site_validated_layout-engineering_review.png) · [SVG](evidence/v2_2_1_p1f/p3_existing_concave_site_validated_layout-engineering_review.svg) |

![R2 representative PRESENTATION](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.png)

![R2 representative MOBILE_PREVIEW](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.png)

![R2 representative ENGINEERING_SHEET](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.png)

Context-inset loading-face evidence:

| Profile | Full context inset PNG | Loading-face detail PNG |
| --- | --- | --- |
| PRESENTATION | [open](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-inset.png) (`b20b51c6cf0ae76eca86cbc8f41a1bbec9e1d9d8d9eb8d2be276f7c2edffe5f8`) | [open](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-loading-face-detail.png) (`ffa1eb4eed4f30d2bd1100d62017a72dc04242d60bb10a71321c9de8804ecb35`) |
| MOBILE_PREVIEW | [open](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-inset.png) (`5267005d1c62695af1bda86b66ebb21958765a07e070b87c8b48934974516349`) | [open](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-loading-face-detail.png) (`b0f3a25cdf00960fb53f315e54e8c1ae3005a49548ea32a02957e5fc11b0f228`) |

![PRESENTATION context inset](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-inset.png)

![MOBILE_PREVIEW context inset](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-inset.png)

![PRESENTATION loading-face detail](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-loading-face-detail.png)

![MOBILE_PREVIEW loading-face detail](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-loading-face-detail.png)

## Historical R1 snapshot (superseded by the R2 rerun below)

Everything from the following R1 scope/inventory through its final governance
snapshot is retained for traceability only. Its old blocker, visual hashes,
profile results, and `P1F_ACCEPTANCE_COMPLETE=false` are not the current result
or active baselines. The R2 result and evidence are above.

## Historical R1 — scope and fixture inventory

This is an evaluation-only change. It reuses existing P2D/P3 tests and the
unmocked P4 Tool 7 scenario. No renderer or engineering source was changed.
The full-chain count below means an existing P2D-validated result was rendered
and linted in all four profiles; only the Tool 7 case exercises the P2C
validated-candidate selector.

| fixture_id | source | site aspect ratio | primary aspect ratio | irregular site | no-build | truck geometry | P2D full pass | P2C selector | full SVG usable |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| `P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE` | Existing P2D representative fixture | 1.375 | 1.194352 | no | no | yes | yes | no | yes |
| `P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT` | Existing P3 concave-site test variation | 1.375 | 1.194352 | yes | no | yes | yes | no | yes |
| `P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES` | Existing unmocked Tool 7 full-chain fixture | 1.372 | 1.442830 | no | yes, 3 polygons | yes | yes | yes | yes |
| `COMPOSITION_ONLY_WIDE_SITE_RIGHT_RAIL` | Synthetic bounds only | 4.000000 | 3.428571 | n/a | n/a | n/a | no | no | no |
| `COMPOSITION_ONLY_WIDE_PLAN_BOTTOM_RAIL` | Synthetic bounds only | 2.888889 | 2.923077 | n/a | n/a | n/a | no | no | no |

The synthetic cases contain only `geometry_bounds` and `primary_bounds`. They
are not project inputs, do not claim `PROJECT_LAYOUT_VALIDATED`, and produce
no room, access, truck, or SVG geometry. They exercise the existing finite
candidate order and its composition/page-furniture gates only.

## Historical R1 — full-chain profile acceptance matrix

Every authoritative fixture was replayed at least twice. Each SVG and lint
report was also projected/evaluated twice from the same validated inputs.
Every profile passed `drawing-lint@1.0.0` with zero errors, warnings, and
unavailable required facts. Collision and page-furniture overlap counts are
zero throughout.

| SCENARIO | SOURCE_TYPE | SITE_ASPECT_RATIO | PRIMARY_ASPECT_RATIO | PROFILE | SELECTED_COMPOSITION | DRAWING_LINT_GATE | ERRORS | WARNINGS | UNAVAILABLE_FACTS | ROOM_LABEL_COLLISIONS | PAGE_FURNITURE_OVERLAPS | MAIN_DRAWING_OCCUPANCY | PRIMARY_PLAN_OCCUPANCY | SVG_HASH | DETERMINISM | PROFILE_RESULT |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| P2D representative | P2D validated fixture | 1.375 | 1.194352 | PRESENTATION | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 0.526630 | 0.754485 | `sha256:97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| P2D representative | P2D validated fixture | 1.375 | 1.194352 | MOBILE_PREVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 1.000000 | `sha256:db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| P2D representative | P2D validated fixture | 1.375 | 1.194352 | ENGINEERING_SHEET | RIGHT_RAIL | PASS | 0 | 0 | 0 | 0 | 0 | 0.700877 | 0.794318 | `sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3` | PASS | PASS |
| P2D representative | P2D validated fixture | 1.375 | 1.194352 | ENGINEERING_REVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 0.142261 | `sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d` | PASS | PASS |
| Existing concave site | P2D validated test variation | 1.375 | 1.194352 | PRESENTATION | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 0.526630 | 0.754485 | `sha256:4732742c0a27a8c5e808dc4de8b6b8d1594e4e8130d692bbb8f259f44a2756b3` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| Existing concave site | P2D validated test variation | 1.375 | 1.194352 | MOBILE_PREVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 1.000000 | `sha256:aadc14f5fcb47fdcfbfce2e3cdface491172cfad2efacdf48dd406db98558d93` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| Existing concave site | P2D validated test variation | 1.375 | 1.194352 | ENGINEERING_SHEET | RIGHT_RAIL | PASS | 0 | 0 | 0 | 0 | 0 | 0.700877 | 0.794318 | `sha256:52739bc7163a7522783574dbc516c7312727aa37b3bcd7558b1ed3533ca45344` | PASS | PASS |
| Existing concave site | P2D validated test variation | 1.375 | 1.194352 | ENGINEERING_REVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 0.142261 | `sha256:5feff4442d0b11047bfd0eb74bb310876ebb9f58e11697107f0753b2e1d32fbc` | PASS | PASS |
| Tool 7 no-build site | Unmocked Tool 7 full chain | 1.372 | 1.442830 | PRESENTATION | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 0.411693 | 0.762470 | `sha256:e731dbc092fb1758e4584c26d3c5d8caa11b18a567978555047ae035b7aff382` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| Tool 7 no-build site | Unmocked Tool 7 full chain | 1.372 | 1.442830 | MOBILE_PREVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 1.000000 | `sha256:1e29c2b517faba321139753ae01d475978c454d36fad0f9b5f2c32240d1a499f` | PASS | BLOCKED_CONTEXT_INSET_INCOMPLETE |
| Tool 7 no-build site | Unmocked Tool 7 full chain | 1.372 | 1.442830 | ENGINEERING_SHEET | RIGHT_RAIL | PASS | 0 | 0 | 0 | 0 | 0 | 0.709935 | 0.784193 | `sha256:6a222eb31572b812ed20cb76b796907a970807aff91f4ab9ae2b21beedc6c1bf` | PASS | PASS |
| Tool 7 no-build site | Unmocked Tool 7 full chain | 1.372 | 1.442830 | ENGINEERING_REVIEW | n/a | PASS | 0 | 0 | 0 | 0 | 0 | 1.000000 | 0.957143 | `sha256:3cad4c935733a653ce631cc2e1da0abf2147b02a4ffa9655d59e6ac58a3edd13` | PASS | PASS |

The Tool 7 test confirms the first P2C candidate fails P2D, a later candidate
passes, and the selected layout is projected without a mocked selector or
renderer. Both existing full-chain Engineering Sheet cases select `RIGHT_RAIL`.
The composition-only wide-plan case rejects `RIGHT_RAIL` on the frozen maximum
main-drawing occupancy and selects `BOTTOM_RAIL` on the next candidate. Its
main drawing occupancy is `0.7926479035`; all four occupancy floors, furniture
overlap, and furniture containment checks pass. This is not a validated SVG.

## Historical R1 — context-inset blocker (resolved by PR #298)

The full-chain projections were also checked for the authoritative context
layers required by P1F. All three fixtures preserve the site boundary,
effective buildable boundary, building footprint, 12 zone footprints, and both
entrances in their focused context inset. The three `ENGINEERING_SHEET`
projections also include the selected shipping loading face in that inset.
However, the current `PRESENTATION` and `MOBILE_PREVIEW` insets omit the
context-mapped shipping loading face in all three fixtures. The selected
loading face remains drawn on the primary plan, but that does not satisfy the
separate context-inset requirement.

```ini
CONTEXT_INSET_BLOCKED_FIXTURE_COUNT=3
CONTEXT_INSET_BLOCKED_PROFILE_COUNT=6
CONTEXT_INSET_BLOCKER=CONTEXT_SHIPPING_LOADING_FACE_MISSING
PRESENTATION_LOADING_FACE_IN_CONTEXT_INSET=false
MOBILE_PREVIEW_LOADING_FACE_IN_CONTEXT_INSET=false
ENGINEERING_SHEET_LOADING_FACE_IN_CONTEXT_INSET=true
DRAWING_LINT_GATE=PASS
REPRESENTATIVE_SVG_HASHES_UNCHANGED=true
P1F_ACCEPTANCE_COMPLETE=false
```

This is an existing projection limitation, not a P1F code change. The
PRESENTATION/MOBILE visibility policy also keeps truck maneuver review
overlays hidden; P1F did not override that policy or invent another
circulation symbol. No renderer fix is authorized in this evaluation-only
stage. The blocker is recorded for Owner direction.

## Historical R1 — bounds-only composition checks

| Scenario | Candidate attempts in frozen order | selected | main occupancy | primary occupancy | furniture overlaps | furniture out of page | lint/SVG |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `COMPOSITION_ONLY_WIDE_SITE_RIGHT_RAIL` | RIGHT_RAIL: pass | RIGHT_RAIL | 0.879121 | 0.868486 | 0 | 0 | not run; no drawing exists |
| `COMPOSITION_ONLY_WIDE_PLAN_BOTTOM_RAIL` | RIGHT_RAIL: reject (0.919213 > 0.88); BOTTOM_RAIL: pass | BOTTOM_RAIL | 0.792648 | 0.922606 | 0 | 0 | not run; no drawing exists |

## Historical R1 — representative exact-hash and P1D regression

The representative 20 t/day fixture retained the four hashes frozen by P1F:

```ini
PRESENTATION_SVG_HASH=sha256:97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e
MOBILE_PREVIEW_SVG_HASH=sha256:db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8
ENGINEERING_SHEET_SVG_HASH=sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3
ENGINEERING_REVIEW_SVG_HASH=sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d
REPRESENTATIVE_DRAWING_BYTES_CHANGED=false
P1D_REQUIRED_FACT_FAIL_CLOSED_REGRESSION=PASS
```

The P1E representative metrics are corrected in both the version plan and P1E
evidence document: primary-plan screen occupancy `0.7943176771550949`, width
ratio `0.8998748435544431`, and height ratio `0.8826979472140762`. The actual
primary bounds are `71.9 × 60.2 m`; these are not the drawing-bounds ratios.

## Historical R1 — visual evidence

The five selected PNGs are direct 1855×2400 MuPDF renders of the corresponding
unchanged SVG projection bytes. No crop, layout edit, post-processing, or
source-geometry change was applied. Evidence is rendered only from full-pass
authoritative scenarios; no picture is fabricated from bounds-only cases.

| Visual sample | PNG SHA-256 | SVG SHA-256 |
| --- | --- | --- |
| P2D representative — PRESENTATION | `d8b0f4c8042136a92fb65aefad490c2c84bfc7048894155c422dc9194199f958` | `sha256:97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e` |
| P2D representative — MOBILE_PREVIEW | `947de0a24a5e34b37f59ffe451339404cd534e626332572b24635184b2a3571d` | `sha256:db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8` |
| P2D representative — ENGINEERING_SHEET | `8158376e015a1c3af3d2a18250c43d83e5d2478a3b3904dc50442d986638fc73` | `sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3` |
| Tool 7 no-build site — ENGINEERING_SHEET | `9e16953795abf62608d19d407b14d58b05433fc06bb4a8ad59589eb0cc6bcc57` | `sha256:6a222eb31572b812ed20cb76b796907a970807aff91f4ab9ae2b21beedc6c1bf` |
| Existing concave site — ENGINEERING_REVIEW | `a89f79c72f8d9e33c522b2d8087d8bbb88b8f0c4fe5c8f7b97d4f82106542a30` | `sha256:5feff4442d0b11047bfd0eb74bb310876ebb9f58e11697107f0753b2e1d32fbc` |

### Representative PRESENTATION

![P2D representative PRESENTATION](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.png)

### Representative MOBILE_PREVIEW

![P2D representative MOBILE_PREVIEW](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.png)

### Representative ENGINEERING_SHEET — RIGHT_RAIL

![Representative Engineering Sheet](evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.png)

### No-build-site ENGINEERING_SHEET — RIGHT_RAIL

![Tool 7 no-build-site Engineering Sheet](evidence/v2_2_1_p1f/p4_real_selector_site_with_no_build_zones-engineering_sheet.png)

### Concave-site ENGINEERING_REVIEW

![Existing concave-site Engineering Review](evidence/v2_2_1_p1f/p3_existing_concave_site_validated_layout-engineering_review.png)

Visual evidence is supplied for Owner review. The bounds-only BOTTOM_RAIL
case intentionally has no SVG/PNG because it has no authoritative room or
vehicle geometry. Automated Drawing Lint and these images do not replace Owner
visual review.

## Historical R1 — change boundary and governance

Only the evaluation harness, this evidence document, generated drawing
artifacts, and the two P1E evidence documents are changed. No production source,
engineering geometry, calculation authority, P2/P2D/P4, MCP, database, or
frontend is changed. Existing presentation whitespace and engineering-review
debug overlays are observed as their current profile behavior; P1F did not
redesign them. Automated drawing lint and page-layout checks have zero
blockers; the separate context-inset completeness issue is recorded above.
Owner visual review remains an independent gate.

```ini
RIGHT_RAIL_PATH_VALIDATED=true
BOTTOM_RAIL_PATH_VALIDATED=true
DRAWING_LINT_FAILED_SCENARIO_COUNT=0
DETERMINISM_FAILED_SCENARIO_COUNT=0
VISUAL_BLOCKER_SCENARIO_COUNT=3
VISUAL_BLOCKER_PROFILE_COUNT=6
P1F_ACCEPTANCE_COMPLETE=false
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
P1G_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
