# V2.2.1 P1D — Drawing Lint Foundation

```ini
TASK_ID=V2_2_1_P1D_DRAWING_LINT_FOUNDATION_R1
BASE_MAIN_SHA=27400de6934fd6bf8a307ac1e4ce3786a959e331
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1D
P1D_AUTHORIZED=YES
P1E_AUTHORIZED=NO

DRAWING_LINT_IDENTITY=drawing-lint@1.0.0
DRAWING_LINT_IS_ENGINEERING_AUTHORITY=false
CANONICAL_ENGINEERING_AUTHORITY=STRUCTURED_LAYOUT_JSON
DRAWING_LINT_GATE=PASS|FAIL
THIRD_PARTY_RUNTIME_DEPENDENCY_ADDED=false
THIRD_PARTY_CODE_COPIED=false

SVG_VISUAL_OUTPUT_CHANGED=false
SVG_BYTES_CHANGED=false
SVG_HASH_CHANGED=false
P1A_COMPOSITION_PRESERVED=true
P1A2_FOCUS_PRESERVED=true
P1B_MONOCHROME_STYLE_PRESERVED=true
P1C_LABEL_POLICY_PRESERVED=true
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false

ZONE_DIMENSIONING_CHANGED=NO
ZONE_AREA_AUTHORITY_CHANGED=NO
PLACEMENT_ALGORITHM_CHANGED=NO
PLACEMENT_OBJECTIVE_CHANGED=NO
CANDIDATE_SELECTION_CHANGED=NO
ACCESS_ROUTING_CHANGED=NO
TRUCK_VALIDATION_CHANGED=NO
LOADING_FACE_SELECTION_CHANGED=NO
BUILDING_FOOTPRINT_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
FRONTEND_CHANGED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Scope

P1D adds an independent, immutable diagnostics model and application boundary
for already-resolved drawing facts. It does not render, repair, resize, move,
or recompose a drawing. Diagnostics are stable-sorted and the canonical lint
hash covers the profile, metrics, and issue payload.

The lint layer checks room labels, callouts, area schedule, page furniture,
business-view metadata leakage, and page containment. `ERROR` issues make the
Drawing Lint Gate fail. `WARNING` and `INFO` issues are exposed to the caller
without silently becoming visual acceptance.

The current renderer exposes review metadata on `ENGINEERING_SHEET` as part of
its historical projection behavior. P1D reports that condition as an explicit
warning so the SVG remains byte-identical; it does not silently claim the
engineering sheet is a clean business view. `ENGINEERING_REVIEW` retains its
debug visibility policy and is not treated as leakage.

## Evidence semantics correction

```ini
TASK_ID=V2_2_1_P1D_DRAWING_LINT_EVIDENCE_SEMANTICS_CORRECTION_R1
PREVIOUS_HEAD_SHA=c31ca60b5e140075c037866b101e5d725f78fb97
CORRECTION_SCOPE=EVIDENCE_AVAILABILITY_AND_FAIL_CLOSED_SEMANTICS
MISSING_FACT_IS_ZERO=false
MISSING_FACT_IS_FALSE=false
MISSING_REQUIRED_FACT_FAILS_CLOSED=true
EVIDENCE_STATUS_VALUES=MEASURED|DERIVED|NOT_APPLICABLE|UNAVAILABLE
EVIDENCE_STATUS_HASHED=true
EVIDENCE_SOURCE_HASHED=true
DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE=ERROR
SVG_VISUAL_OUTPUT_CHANGED=false
SVG_BYTES_CHANGED=false
SVG_HASH_CHANGED=false
ENGINEERING_SHEET_WARNING_POLICY_PRESERVED=true
P1E_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Required facts now carry explicit evidence status and stable source strings.
`UNAVAILABLE` is never converted to zero or false; a required unavailable fact
adds `DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE` and fails the lint gate.
`NOT_APPLICABLE` is reserved for an explicitly absent drawing feature, such as
callout checks when the resolved room-label plan has zero callouts. Resolved
label, dimension, and callout facts are exposed in a non-visual projection
sidecar. The sidecar is excluded from SVG metadata and does not alter SVG
bytes or hashes.

## Parity and governance

The representative four-profile SVG parity check is performed outside the
lint serializer. Lint does not mutate the projection object, and the SVG
`bytes`/`sha256` remain the renderer's existing authority. P1E remains
unauthorized; no sheet rearrangement, PDF/DXF export, UI, MCP, or automatic
geometry repair is part of this task.
