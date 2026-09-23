# V2.2.1 P1G — Release Closure

```ini
TASK_ID=V2_2_1_P1G_RELEASE_CLOSURE_R1
BASE_MAIN_SHA=a71347a7ca56c32b2facaa3b57e489427b9a7ea8
TARGET_VERSION=v2.2.1
PREVIOUS_RELEASE=v2.2.0
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1G
P1G_AUTHORIZED=true
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Closure scope and outcome

P1G audits release readiness and closes evidence for the merged V2.2.1 P0–P1F
work. This is a documentation/evidence and architecture-guard change only. It
does not add drawing behavior, alter a renderer, change any engineering
authority, or execute a release action.

The initial closure baseline was freshly fetched from the canonical repository
in an isolated clean clone. `main` resolved to the requested
`a71347a7ca56c32b2facaa3b57e489427b9a7ea8`; the existing workspace's damaged
Git reference was left untouched. Repository release metadata and tag history
were checked independently.

## Release lineage

```ini
CURRENT_MAIN_SHA=a71347a7ca56c32b2facaa3b57e489427b9a7ea8
PREVIOUS_RELEASE=v2.2.0
V2_2_0_TAG_TARGET_SHA=34cd6b56c1d79dde9730898c6bd46e295e423334
LATEST_GITHUB_RELEASE=v2.2.0
V2_2_1_TAG_EXISTS_AT_CLOSURE_START=false
V2_2_1_GITHUB_RELEASE_EXISTS_AT_CLOSURE_START=false
CLOSURE_START_COMMITS_SINCE_V2_2_0=31
CLOSURE_START_CHANGED_FILES_SINCE_V2_2_0=59
V2_2_0_IS_ANCESTOR_OF_V2_2_1_CANDIDATE=true
MAIN_LINEAGE=PASS
PREVIOUS_RELEASE_IMMUTABLE=true
```

The `v2.2.0` tag is annotated and still resolves to its original commit. No
existing tag or release was moved or rewritten. The current candidate is a
descendant of that tag. The `v2.2.1` tag/release checks above describe closure
start only; P1G does not create either one.

## Phase closure

| Phase | Result | Closure evidence |
| --- | --- | --- |
| P0 drawing-style contract | PASS | `LAYOUT_DRAWING_STYLE_V1`; structured layout JSON remains the engineering authority |
| P1A canvas/page composition | PASS | Separate engineering bounds and page-layout bounds |
| P1A2 presentation/mobile focus | PASS | Primary-plan bounds and context inset preserved |
| P1B monochrome CAD hierarchy | PASS | Monochrome-first style and W5–W0 hierarchy |
| P1C room labels/annotations | PASS | Deterministic label fallback, callouts, schedule and collision correction |
| P1D drawing lint | PASS | `drawing-lint@1.0.0`, required evidence fails closed |
| P1E Engineering Sheet composition | PASS | `engineering-sheet-composition@1.0.0`, true primary-plan metrics |
| P1F cross-fixture robustness | PASS | 3 full-chain fixtures, 2 composition-only scenarios, Owner visual review PASS |

P1F's former `OWNER_VISUAL_REVIEW=REQUIRED` was a stale current-state value.
It is now corrected to `PASS` in the current version-plan and P1F report
overlays. The R1 blocker and its failed measurements remain in explicitly
historical sections and are not presented as current state.

The P1E and P1F historical scope guards now compare each phase's original
base with its immutable merged PR tree. This prevents later P1G closure files
from being misattributed to the earlier phase change sets while preserving
their original allowlists.

## Drawing authority and frozen capability

```ini
CANONICAL_ENGINEERING_AUTHORITY=STRUCTURED_LAYOUT_JSON
SVG_ROLE=PRESENTATION_PROJECTION
ZONE_AREA_AUTHORITY_CHANGED=false
ZONE_DIMENSION_AUTHORITY_CHANGED=false
PLACEMENT_ALGORITHM_CHANGED=false
PLACEMENT_OBJECTIVE_CHANGED=false
P2_CANDIDATE_SELECTION_CHANGED=false
ACCESS_ROUTING_CHANGED=false
TRUCK_VALIDATION_CHANGED=false
LOADING_FACE_SELECTION_CHANGED=false
BUILDING_FOOTPRINT_AUTHORITY_CHANGED=false
P2_CHANGED=false
P2D_CHANGED=false
P4_ENGINEERING_AUTHORITY_CHANGED=false
```

The V2.2.1 drawing identity is `LAYOUT_DRAWING_STYLE_V1` / `CAD_FACTORY_LAYOUT`
with `MONOCHROME_PRIMARY` color mode. The frozen profiles remain
`PRESENTATION`, `MOBILE_PREVIEW`, `ENGINEERING_SHEET`, and `ENGINEERING_REVIEW`;
their roles and visibility behavior are unchanged. Drawing Lint and sheet
composition remain presentation/diagnostic capabilities, not a second
engineering authority.

## Representative drawing baselines

The representative 20 t/day full-pass fixture was reprojected during the P1F
acceptance-matrix replay. All four current outputs match the frozen SHA-256
values; repeat projection produces identical bytes and hashes.

```ini
PRESENTATION_SVG_SHA256=sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a
MOBILE_PREVIEW_SVG_SHA256=sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2
ENGINEERING_SHEET_SVG_SHA256=sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3
ENGINEERING_REVIEW_SVG_SHA256=sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d
REPRESENTATIVE_HASH_FREEZE=PASS
SAME_INPUT_SAME_SVG_BYTES=true
SAME_INPUT_SAME_SVG_HASH=true
```

P1E measurements use actual primary-plan bounds, not drawing bounds:

```ini
REPRESENTATIVE_PRIMARY_PLAN_WIDTH_M=71.9
REPRESENTATIVE_PRIMARY_PLAN_HEIGHT_M=60.2
REPRESENTATIVE_PRIMARY_PLAN_SCREEN_OCCUPANCY=0.7943176771550949
REPRESENTATIVE_PRIMARY_PLAN_WIDTH_RATIO=0.8998748435544431
REPRESENTATIVE_PRIMARY_PLAN_HEIGHT_RATIO=0.8826979472140762
REPRESENTATIVE_MAIN_DRAWING_OCCUPANCY=0.7008771929824561
```

The former erroneous `1.0 / 1.0 / 1.0` values are not used.

## Drawing Lint and cross-fixture acceptance

The P1F machine-readable matrix was checked against its five declared
scenarios and twelve authoritative profile rows. All twelve rows pass Drawing
Lint and deterministic replay; the three full-chain fixtures each cover all
four profiles. The two composition-only scenarios exercise candidate
composition selection without claiming a validated project or rendering an
SVG.

```ini
DRAWING_LINT_IDENTITY=drawing-lint@1.0.0
DRAWING_LINT_GATE=PASS
DRAWING_LINT_ERROR_COUNT=0
UNAVAILABLE_REQUIRED_FACT_COUNT=0
FULL_CHAIN_AUTHORITATIVE_FIXTURE_COUNT=3
COMPOSITION_ONLY_FIXTURE_COUNT=2
TOTAL_DRAWING_SCENARIO_COUNT=5
FULL_CHAIN_PROFILE_ROW_COUNT=12
DRAWING_LINT_FAILED_SCENARIO_COUNT=0
DETERMINISM_FAILED_SCENARIO_COUNT=0
VISUAL_BLOCKER_SCENARIO_COUNT=0
VISUAL_BLOCKER_PROFILE_COMBINATIONS=0
RIGHT_RAIL_PATH_VALIDATED=true
BOTTOM_RAIL_PATH_VALIDATED=true
P1D_FAIL_CLOSED_REGRESSION=PASS
PRESENTATION_CONTEXT_LOADING_FACE_COMPLETE=true
MOBILE_CONTEXT_LOADING_FACE_COMPLETE=true
ENGINEERING_SHEET_CONTEXT_LOADING_FACE_COMPLETE=true
CONTEXT_LOADING_FACE_ENDPOINTS_MATCH_AUTHORITATIVE_SEGMENT=true
PREVIOUS_FAILED_PROFILE_COMBINATIONS=6
FINAL_FAILED_PROFILE_COMBINATIONS=0
LOADING_FACE_SELECTION_CHANGED=false
```

## MCP and Tool 7 compatibility

Tool 7 remains the seventh and final tool. The original six tool names, order,
and input contracts are unchanged. V2.2.1 adds no MCP tool or transport/API
change. The unmocked Tool 7 full-chain regression continues to select through
the P2 validated-candidate selector; candidate ranking remains in P2, not P4.

```ini
MCP_TOOL_COUNT=7
MCP_TOOL_ORDER=preview_zone_plan|preview_cooling_load|preview_equipment|preview_installed_power|preview_investment|preview_factory_power|preview_site_layout
EXISTING_SIX_TOOL_ORDER_PRESERVED=true
EXISTING_SIX_TOOL_CONTRACT_PRESERVED=true
TOOL7_NAME=preview_site_layout
TOOL7_POSITION=7
TOOL7_INPUT_CONTRACT_CHANGED=false
MCP_TRANSPORT_CHANGED=false
NEW_MCP_TOOL_ADDED=false
EXISTING_SIX_TOOL_REGRESSION=PASS
REAL_TOOL7_FULL_CHAIN=PASS
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
ZONE_COUNT=12
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=true
FIRST_P2C_CANDIDATE_P2D_RESULT=REJECTED
LATER_FULL_PASS_CANDIDATE_FOUND=true
FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p2
FACTORY_POWER_RESULT_SCHEMA_VERSION=2.0.0-p1
```

No database migration or frontend change is part of this closure. Python and
frontend package versions remain `0.1.0`; the product release is represented by
Git tags and GitHub Releases, not package publication.

## Validation record

P1F exact-head run `35838403105` on `aea30a6e6d0e640574451fd5f58bcf5d291fe278`
completed successfully, including `backend-sqlite`, `backend-postgresql`, and
`ci-gate`. Its Git tree exactly matches the final P1F merge/main tree
`a71347a7ca56c32b2facaa3b57e489427b9a7ea8`, so those full backend-lane results
cover the same production/runtime source as the P1G base. A separate merge-main
run for that SHA was still in progress at closure start and is tracked
separately.

P1G's exact-head run is not known at document authoring time. It must be
verified on the pushed PR head, including the stable `ci-gate`; the exact head
SHA and run ID are recorded in the PR evidence after completion. Path-aware CI
may skip backend database jobs for this docs/architecture-only change. A skip
is not reported as a pass; the P1F full backend CI and local P1G validation
remain separately identified evidence.

```ini
PRODUCTION_RUNTIME_CHANGED=false
DATABASE_CHANGED=false
FRONTEND_CHANGED=false
MCP_CONTRACT_CHANGED=false
PACKAGE_METADATA_VERSION_BUMP_AUTHORIZED=false
P1G_EXACT_HEAD_CI_RUN_ID=PR_EXACT_HEAD_CHECK_REQUIRED
P1G_EXACT_HEAD_CI_RESULT=PENDING
CI_GATE_RESULT=PENDING
V2_2_1_RELEASE_READY=CONDITIONAL_ON_P1G_EXACT_HEAD_CI
RELEASE_BLOCKERS=EXACT_HEAD_CI_PENDING
```

## Release-note draft (not published)

### v2.2.1 — CAD Drawing Projection & Engineering Sheet Quality

#### New

- Added a monochrome-first CAD-style drawing hierarchy.
- Added `PRESENTATION`, `MOBILE_PREVIEW`, `ENGINEERING_SHEET`, and
  `ENGINEERING_REVIEW` projection profiles.
- Added Chinese room labels with deterministic label fallback, callout, and
  collision handling.
- Added fail-closed Drawing Lint diagnostics for labels, dimensions, callouts,
  schedules, page furniture, visibility, and page containment.
- Added Engineering Sheet primary-plan focus with a full-site context inset;
  the selected shipping loading face is retained in the supported context
  insets.
- Exercised three authoritative full-chain fixtures and two composition-only
  scenarios across the frozen profile matrix.

#### Compatibility and scope

- MCP Tool 7 and its input contract are unchanged; the original six tools and
  their contracts remain unchanged.
- Structured layout JSON remains the canonical engineering authority; SVG is a
  presentation projection only.
- No database migration or production deployment is included.
- This product does not claim construction-drawing readiness, replace formal
  engineering design, validate physical print scale, or provide PDF/DXF export.

## Release policy

```ini
RELEASE_TARGET_SHA=P1G_FINAL_MERGE_SHA_AFTER_EXACT_MAIN_CI
TAG_TARGET_EQUALS_FINAL_P1G_MAIN_SHA=true
TAGGING_P1G_BRANCH_HEAD=false
TAGGING_PRE_MERGE_MAIN=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The required sequence is Draft PR → exact-head CI PASS → Owner review →
separately authorized Ready/Merge → merge to `main` → exact-main CI PASS →
separate tag/Release authorization. No tag, GitHub Release, deployment, or
next-version work is authorized by P1G.
