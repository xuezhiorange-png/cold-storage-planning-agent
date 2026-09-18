# V2.2 P5 — Release Closure and v2.2.0 Readiness

This document is the current V2.2 release-closure evidence record. It is a
readiness determination only: it does not create or move a tag, publish a
GitHub Release, deploy the system, or authorize the next feature lane.
Earlier P0–P4 task records remain historical records and are not rewritten.

## Closure status

```ini
TASK_ID=V2_2_P5_RELEASE_CLOSURE_R1
BASE_BRANCH=main
BASE_MAIN_SHA=31c888f446d2d4c5704221426d60685da91f43d8
TARGET_VERSION=v2.2.0
PREVIOUS_RELEASE=v2.1.2
P0_COMPLETE=YES
P1_COMPLETE=YES
P2_COMPLETE=YES
P3_COMPLETE=YES
P4_COMPLETE=YES
P5_AUTHORIZED=YES
P5_STATUS=RELEASE_CLOSURE_DRAFT_REVIEW
V21_IMPLEMENTATION_COMPLETE=YES
V2_2_0_RELEASE_READY=YES
RELEASE_TARGET_SHA=P5_FINAL_HEAD_AFTER_EVIDENCE_COMMIT
RELEASE_TARGET_SHA_POLICY=FINAL_P5_HEAD_PLUS_EXACT_MAIN_CI_AND_SEPARATE_RELEASE_AUTHORIZATION
RELEASE_BLOCKERS=NONE
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`RELEASE_TARGET_SHA` is deliberately a policy-bound value rather than the
current P4 merge SHA. The eventual release target is the P5 closure merge
commit after its exact-main CI succeeds and a separate release authorization
is granted. No future tag target is hard-coded here.

## V2.2 implementation closure

The merged stages are closed in the following order:

| Stage | Closed authority |
|---|---|
| P0 | Site-constrained layout contract, local Cartesian geometry, canonical JSON authority, and the future Tool 7 boundary |
| P1 | Hybrid zone dimensions, flexible-rectangle handoff, project truck input, and 2-D access profiles |
| P2A | Validated site geometry predicates |
| P2B1 | Owner-approved Option C maneuver-template contract |
| P2B2 | Deterministic lexicographic objective profile |
| P2C | Deterministic 12-zone placement candidate generation |
| P2D | Portal, corridor, access, truck, separation, footprint, and final-layout validation |
| P2 selector | P2C-ranked candidate enumeration followed by P2D full-pass selection |
| P3 | Deterministic static SVG projection of validated structured layout JSON |
| P4 | `preview_site_layout` Tool 7 application and Streamable HTTP integration |

The P2 selector remains the owner of candidate selection. P4 does not rank or
retry candidates. P2D's `PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED` rule remains
unchanged, and a candidate that fails it is rejected so that a later P2C-ranked
candidate can be validated.

## Release lineage

The previous release is immutable and is an ancestor of the current V2.2
candidate:

```ini
V20_RELEASE=v2.0.0
V21_RELEASE=v2.1.2
V21_RELEASE_TARGET_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
V21_RELEASE_IS_ANCESTOR_OF_V22_CANDIDATE=YES
V2_2_0_TAG_EXISTS_AT_CLOSURE_START=NO
V2_2_0_GITHUB_RELEASE_EXISTS_AT_CLOSURE_START=NO
```

The current main line contains the merged P0–P4 records, including the P4
merge commit `31c888f446d2d4c5704221426d60685da91f43d8`. The immutable lineage
check is `git merge-base --is-ancestor
0a68597a40aa460ed31441c537ca37c3d4cfd1a7 HEAD`; the closure architecture test
checks ancestry, not a moving `origin/main` diff endpoint.

The P0–P4 implementation evidence is anchored by these merged records:

```ini
V22_P0_MERGE_SHA=3ffb3790f85a990283ce972733c3f43b44d1e899
V22_P1F_MERGE_SHA=50210aa7cc876ed8a93a099c82ef4a4f287da82a
V22_P2A_MERGE_SHA=ccd6336de4810012deec64c1b0a5f3256ff13d85
V22_P2B1_MERGE_SHA=fa884b8ddf2b93f34beb2335d646fe6b157a8f5f
V22_P2B2_MERGE_SHA=776d6836975d5f27a0261820548425e798919f03
V22_P2C_MERGE_SHA=99116fb8f5999461f718ad6a4d5747f1ec865716
V22_P2D_MERGE_SHA=a1d035c4d42a2bc4895e6d3806d3f5fe77e7e0d2
V22_P2_SELECTOR_MERGE_SHA=efc1ce2e85b55e2e7fb907fee460ea4d2e84dc9d
V22_P3_MERGE_SHA=cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b
V22_P4_MERGE_SHA=31c888f446d2d4c5704221426d60685da91f43d8
```

## Authority and result invariants

The release candidate preserves the existing deterministic authority chain:

```text
cold_room_zone_plan@1.0.0
  -> p1-project-access-handoff@1.0.0
  -> hybrid_zone_dimension_handoff@1.0.0
  -> p1-dimension-access-handoff@1.0.0
  -> site-geometry-foundation@1.0.0
  -> site-constrained-deterministic-placement@1.0.0
  -> site-access-routing-and-validation@1.0.0
  -> p2-validated-candidate-selection-application@1.0.0
  -> site_validated_layout@1.0.0
  -> validated-layout-svg-projection@1.0.0
```

```ini
ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN
FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p2
FACTORY_POWER_RESULT_SCHEMA_VERSION=2.0.0-p1
P2_PLACEMENT_IDENTITY=site-constrained-deterministic-placement@1.0.0
P2_PLACEMENT_RESULT_IDENTITY=site_constrained_factory_layout@1.0.0
P2D_RESULT_IDENTITY=site_validated_layout@1.0.0
P2_SELECTOR_IDENTITY=p2-validated-candidate-selection-application@1.0.0
P2_SELECTOR_RESULT_IDENTITY=p2_validated_candidate_selection@1.0.0
P3_SVG_PROJECTION_IDENTITY=validated-layout-svg-projection@1.0.0
CANONICAL_LAYOUT_AUTHORITY=STRUCTURED_LAYOUT_JSON
SVG_IS_PROJECTION=YES
NO_ENGINEERING_RECALCULATION_IN_P4=YES
PERSISTED_RESULT=NO
CONCEPT_DESIGN=YES
REQUIRES_REVIEW=YES
CONSTRUCTION_DRAWING=NO
```

P0–P4 preserve the V2.1.2 engineering rules and the existing factory-power
authority. No formula, zone area, access profile, placement rule, route rule,
or SVG source geometry is changed by this closure.

## MCP, Doubao, and Feishu compatibility

The public surface is exactly seven tools, with Tool 7 appended after the
existing six:

```ini
MCP_TOOL_COUNT=7
MCP_TOOL_ORDER=preview_zone_plan,preview_cooling_load,preview_equipment,preview_installed_power,preview_investment,preview_factory_power,preview_site_layout
EXISTING_SIX_TOOL_ORDER_PRESERVED=YES
EXISTING_SIX_TOOL_CONTRACT_PRESERVED=YES
TOOL7_NAME=preview_site_layout
TOOL7_POSITION=7
TOOL7_INPUT=FIVE_BUSINESS_KEYS_PLUS_SITE_CONSTRAINTS_TRUCK_ACCESS_AND_TRUCK_MANEUVER
TOOL7_TRUCK_BINDING=SERVER_SIDE_P1F_BINDING
CALLER_BOUND_TRUCK_AUTHORITY_ALLOWED=NO
NO_CHAT_PARSING=YES
NO_NEW_REST_ROUTE=YES
STREAMABLE_HTTP_REUSED=YES
```

Tool 7 consumes raw project-level `truck_access` and raw approved
`truck_maneuver`; the server creates the bound maneuver input. It uses the P2
validated-candidate selector, the P2D full-pass result, and the P3 SVG
projection. It does not accept caller-supplied area, zone plan, placement,
hash, bound result, SVG, or theme authority, and it does not persist a result.

## Real-chain acceptance

The existing unmocked representative acceptance test is the release evidence
for the complete path:

```ini
REAL_TOOL7_FULL_CHAIN=PASS
FIRST_P2C_CANDIDATE_P2D_RESULT=REJECTED
LATER_FULL_PASS_CANDIDATE_FOUND=YES
SELECTED_LAYOUT_IDENTITY=site_validated_layout@1.0.0
SVG_IDENTITY=validated-layout-svg-projection@1.0.0
PROJECT_LAYOUT_VALIDATED=YES
P2_COMPLETE=YES
ZONE_COUNT=12
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=YES
P3_SVG_RENDERED=YES
SAME_INPUT_SAME_SELECTED_LAYOUT_HASH=YES
SAME_INPUT_SAME_SVG_BYTES=YES
SAME_INPUT_SAME_SVG_HASH=YES
```

This evidence comes from the production Tool 7 application path without
monkeypatching candidate generation, the selector, P2D routing, or P3. The
selector trace proves that the first P2C candidate can be rejected by P2D
while a later candidate is selected; P4 only consumes that selected result.

## Release blocker audit

```ini
P0_CONTRACT=PASS
P1_AUTHORITY=PASS
P2A_GEOMETRY=PASS
P2B1_TRUCK_TEMPLATE=PASS
P2B2_OBJECTIVE=PASS
P2C_PLACEMENT=PASS
P2D_ACCESS_AND_TRUCK=PASS
P2_VALIDATED_CANDIDATE_SELECTION=PASS
P3_SVG_PROJECTION=PASS
P4_TOOL7_INTEGRATION=PASS
MCP_REGRESSION=PASS
V21_FACTORY_POWER_REGRESSION=PASS
V21_2_ENGINEERING_RULES_REGRESSION=PASS
V18_COMPATIBILITY=PASS
EXISTING_SIX_TOOL_REGRESSION=PASS
ARCHITECTURE=PASS
MAIN_LINEAGE=PASS
NO_PRODUCTION_CODE_CHANGE=YES
NO_DATABASE_MIGRATION=YES
NO_FRONTEND_DEPENDENCY_CHANGE=YES
NO_DEPLOYMENT_CHANGE=YES
NO_NEW_RELEASE_BLOCKER=YES
RELEASE_BLOCKERS=NONE
```

Exact-head CI evidence is bound to the final closure PR head after the
evidence commit. The exact run id and `ci-gate` result are recorded in the PR
verification body; release execution must use the later closure merge commit,
another exact-main CI success, and a separate authorization.

## Release-note readiness

Future release-note content is prepared here but is not published:

* V2.2 adds canonical site-constrained factory-layout authority on top of the
  existing cold-room zone plan.
* P1 supplies hybrid fixed, deterministic-grid, and flexible rectangle
  handoff plus 2-D access authority.
* P2 validates deterministic 12-zone placement, access routes, truck maneuver
  templates, and the final structured layout.
* P3 projects validated layout JSON into deterministic static SVG.
* P4 exposes `preview_site_layout` as MCP Tool 7 with server-side project
  truck binding and no persistence.
* The existing six-tool workflow, factory-power calculator, and concept-design
  review boundary remain unchanged.

This is not a deployment statement and does not create a v2.2.0 tag or
GitHub Release.

## Non-goals and execution gate

The closure does not implement or authorize PDF/DXF/CAD/BIM export, a new
CalculationType, a new REST route, a new MCP tool, frontend integration,
database migration, deployment, or a V2.3/P6 feature lane. The following
remain false at this gate:

```ini
TAG_CREATED=NO
GITHUB_RELEASE_CREATED=NO
DEPLOYMENT_EXECUTED=NO
READY_EXECUTED=NO
MERGE_EXECUTED=NO
P5_RELEASE_EXECUTION=UNAUTHORIZED
```

## Post-P5 CI correction release closure (2026-09-18)

The original P5 readiness block above is retained as the historical review
snapshot. After the P5 merge, the only correction was the workflow prerequisite
in PR #288; it installed the already-required CJK font in the lightweight
architecture lane and changed no product behavior. PR #289 independently
validated that lane against the #288 head branch with a docs-only diff.

```ini
TASK_ID=V2_2_0_POST_P5_CI_CORRECTION_RELEASE_R1
P5_MERGE_SHA=853db6ecd2acc2a47196feb048a2f860d4b2f6e4
P5_MERGE_CI_RUN_ID=35241519009
P5_MERGE_CI_RESULT=FAILURE
P5_MERGE_CI_ROOT_CAUSE=LIGHTWEIGHT_ARCHITECTURE_LANE_MISSING_REQUIRED_CJK_FONT_INSTALL
CORRECTION_PR=288
CORRECTION_HEAD_SHA=b6b514a950ef3015c609d1d625f55827f21b86be
CORRECTION_MERGE_SHA=959c8d00911f7f3075f7bd23be9c1307f4d616c7
WORKFLOW_ONLY=true
PRODUCTION_CODE_CHANGED=false
TEST_SEMANTICS_CHANGED=false
V2_2_RUNTIME_CHANGED=false
MCP_CHANGED=false
DATABASE_CHANGED=false
VALIDATION_PR=289
VALIDATION_PR_DOCS_ONLY=true
LIGHTWEIGHT_SELECTED=true
CJK_INSTALL_STATUS=SUCCESS
ARCHITECTURE_VALIDATION_STATUS=685_PASSED_16_SKIPPED
LIGHTWEIGHT_STATUS=SUCCESS
CI_GATE_STATUS=SUCCESS
RELEASE_TARGET_EXACT_MAIN_CI_RUN=35336958482
RELEASE_TARGET_EXACT_MAIN_CI_STATUS=SUCCESS
V2_2_0_RELEASE_TARGET_SHA=959c8d00911f7f3075f7bd23be9c1307f4d616c7
V2_2_0_RELEASE_TARGET_REASON=POST_P5_WORKFLOW_ONLY_CI_PREREQUISITE_CORRECTION
P5_RUNTIME_AUTHORITY_CHANGED=false
RELEASE_BLOCKERS=NONE
TAG_AUTHORIZED=true
GITHUB_RELEASE_AUTHORIZED=true
DEPLOYMENT_AUTHORIZED=false
V2_2_0_RELEASED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The release target above is the corrected post-P5 main baseline. Release
execution must still tag the release-closure correction's final main commit
after its own exact-main CI succeeds; the failed P5 merge SHA is never a tag
target. No deployment, server change, production configuration change, or
next feature lane is authorized by this correction.
