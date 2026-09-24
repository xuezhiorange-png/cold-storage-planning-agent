# V2.2.2 P0C — Golden Layout Abstraction and Calibration

```ini
TASK_ID=V2_2_2_P0C_GOLDEN_LAYOUT_ABSTRACTION_AND_CALIBRATION_R1
PR_NUMBER=301
PR_STATE=OPEN_DRAFT
BASE_P0C_HEAD_SHA=9bc00b6157bb549f1fd3c7112cfc30f29452b8e0
EVIDENCE_AND_CALIBRATION_ONLY=true
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
OWNER_VISUAL_OVERLAY_REVIEW=PENDING
GOLDEN_ENGINEERING_AUTHORITY=false
REFERENCE_DERIVED=true
RUNTIME_PROJECT_INPUT=false
NUMERIC_THRESHOLD_CALIBRATION_READY=false
P1A_STRUCTURAL_IMPLEMENTATION_ENTRY_READY=true
P1B_NUMERIC_THRESHOLD_IMPLEMENTATION_ENTRY_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The Golden PDFs are reference evidence only; they are not engineering authority.

## Purpose and source handling

P0C turns the five Owner-labelled positive Golden drawings into normalized,
reviewable **visual organization abstractions**, alongside the existing
structured Xinzhao negative fixture. The positive files are the exact
Owner-provided PDF attachments whose hashes are recorded in the P0B matrix.
Their original bytes remain external; no original drawing PDF is copied into
the repository. PDF page/vector geometry was reviewed first. OCR was not used.
Some room labels are vector outlines rather than a text layer, so role mapping
is limited to roles supported by the accepted P0B visual observations.

Every abstraction and overlay has:

```ini
REFERENCE_DERIVED=true
ENGINEERING_AUTHORITY=false
RUNTIME_PROJECT_INPUT=false
REFERENCE_NORMALIZATION_VERSION=1.0.0
```

Normalized page-envelope coordinates use `[0,1]`, x right and y down, relative
to an approximate main-composition envelope. The stored `major_zone_rectangles`
are provisional **group envelopes**, not room-accurate geometry. They contain
no project metres, areas, capacities, or copied dimension annotations. This
level is sufficient to review grouping and organization, but it is not
interchangeable with exact P0 zone-boundary metrics.

Five original-page PNG overlays are stored under
[`evidence/v2_2_2_p0c/`](evidence/v2_2_2_p0c/). They fade the source page and
show the approximate principal envelope, major functional-group envelopes,
candidate axis families, and depth-family markers. The overlays are pending
Owner confirmation; they are not engineering drawings or runtime fixtures.
The source PDFs are not embedded in the repository.

## What the references support

The five positive drawings support a recurring qualitative organization
pattern:

1. A continuous production band or recognizable central process core is the
   plan's organizing center.
2. Repeated cold/storage areas read as grouped banks or coherent bands, rather
   than unrelated room tiles.
3. Packaging and other support functions read as side/edge/terminal branches,
   not as additional main product stages mixed through the core.
4. Major boundaries use a limited orthogonal family where the site permits.
5. One principal composition is preferred, while purposeful wings and
   irregular-site solutions remain valid. GD-003 Mouding is specifically kept
   as a positive case: its irregular site context does not make an orthogonal
   production core a failure.

These are layout-organization patterns, not copied project templates. The
Golden drawings do not establish authoritative process routes, portal paths,
backtrack counts, turn counts, equipment envelopes, or personnel/logistics
separation. Those values remain `UNAVAILABLE`.

Xinzhao differs in the Owner's labelled review: the accepted v2.2.1 geometry
was described as tile-like, with weak receiving-to-process-to-shipping
direction and auxiliary rooms attached around sorting in several directions.
P0A independently records an exact zone-level grid alignment of `0.4`, a
bounding-rectangle occupancy of `0.5792454589543597230802131883`, and 16
reflex corners on one connected footprint. These facts are consistent with
the Owner's concern, but none alone is a pass/fail rule. In particular, a low
occupancy or non-rectangular outline can be correct when site/no-build
authority or an intentional L-shaped organization requires it.

## Versioned geometry classifiers

`BUILDING_OUTLINE_CLASSIFIER_V1` is a deterministic classification vocabulary
for exact orthogonal building outlines:

| Class | Definition |
| --- | --- |
| `RECTANGLE` | One connected simple orthogonal polygon with four non-collinear vertices and no reflex corner. |
| `SIMPLE_L` | One connected simple orthogonal polygon with one re-entrant bay and one reflex corner. |
| `COMPLEX_L` | One connected outline with one principal re-entrant bay containing multiple orthogonal steps/reflex corners. |
| `STAIR_STEP` | Two or more distinct re-entrant bays in the exact outline; this is a topology label, not an automatic quality failure. |
| `NARROW_NECK` | Two larger lobes connected by a sole orthogonal separator whose exact cross-section is strictly narrower than each adjacent lobe. No numeric metre threshold is introduced. |
| `MULTI_COMPONENT` | More than one disconnected principal building component in the authoritative footprint. |
| `ISOLATED_APPENDAGE` | A geometrically protruding attachment is confirmed by Owner/project semantics to be unmotivated; geometry alone cannot establish that it is unnecessary. |
| `IRREGULAR_SITE_CONSTRAINED` | A non-regular outline is justified by the actual site/no-build constraints; it is not inferred from shape alone. |
| `AMBIGUOUS_REQUIRES_OWNER_REVIEW` | Evidence does not uniquely support a class, or an apparent wing/appendage lacks purpose authority. |

Classifier precedence is: disconnected components; Owner-confirmed unmotivated
appendage; exact narrow-neck topology; explicit site-constraint justification;
rectangle/simple-L/complex-L/stair-step topology; otherwise ambiguous. A
regular L is not called poor solely for being non-rectangular.

`EXTERIOR_REFLEX_CORNER_COUNT` remains the exact count of concave 90-degree
vertices. `EXTERIOR_NOTCH_COUNT` is different: for a single simple orthogonal
outer ring, it counts connected exterior pockets in the bounding-rectangle
complement using exact vertex-grid cell decomposition. A notch may have more
than one reflex corner. Rings with holes, uncertain outer/inner wall selection,
or unsegmented projections return `UNAVAILABLE`, not zero. The offline helper
tests a rectangle, L, and multi-reflex L-shaped example; it is not wired to
runtime.

Appendage classification requires both the exact component/neck topology and
purpose evidence. If only geometry is available, the output is
`AMBIGUOUS_REQUIRES_OWNER_REVIEW`; no protrusion is assumed unnecessary.

## Depth-pair policy `1.0.0`

Compare only a pair that satisfies all of the following:

1. Both members are individually identified room rectangles with a confident
   semantic role and the same functional group/bank.
2. Both occupy the same functional band and local orientation.
3. Their near/far depth limits have an unambiguous correspondence under that
   orientation. Aligned depth means exact equality in the normalized geometry
   for a reference or on the existing exact geometry grid for a project.
4. The explicit cross-role pair
   `SECONDARY_PRECOOL` / `FINISHED_STORAGE` is eligible only when the project
   authority places both in the same finished-side band.

Do not compare all room pairs, different storage banks, dissimilar roles,
unmapped labels, corridors, or whole-band envelopes as if they were rooms.
Zero eligible pairs is `NOT_APPLICABLE`; missing geometry/role/orientation is
`UNAVAILABLE`. The current five abstractions contain no room-level eligible
pairs, so their depth-alignment rates are unavailable.

## Functional grouping and process-core criteria

`FUNCTIONAL_GROUPING_CRITERIA_V1` is qualitatively PASS when the drawing
supports separate raw-side, processing-core, finished-side, support, and
personnel groups as applicable; repeated storage is grouped; support remains
an edge/terminal branch; and the principal product organization is not broken
into peer room tiles. A role can be omitted only when the project authority
states it is absent. An uncertain drawing role stays `UNAVAILABLE`.

`PROCESS_CORE_LEGIBILITY_CRITERIA_V1` is qualitatively PASS when
sorting/packing is readable as a coherent hub or a defined stage in the
dominant process band, distinct from attached side-support. This is a visual
organization observation, not proof that the ordered process routes pass.

Both criteria are supported by the five Owner-PASS references at the
qualitative level; they do not certify route direction, backtracking, or flow
efficiency.

## Calibration outcome

The calibration matrix includes five positive abstractions and the one
Owner-labelled negative Xinzhao fixture. Positive group-edge alignment values
range from `0.75` to `1.0`, but are provisional measurements of manually
traced group envelopes. Xinzhao's `0.4` is computed from exact room/zone
boundary incidences. Because these are different granularities, the apparent
gap is not a valid calibrated threshold. Positive complete-footprint
occupancy, exact notch/appendage counts, and eligible room-level depth pairs
are not available. Numeric thresholds remain `NOT_READY`.

| Metric | Positive sample evidence | Xinzhao evidence | Decision |
| --- | --- | --- | --- |
| Group-envelope axis alignment | 0.75–1.00, provisional | Exact zone rate 0.40 | `NOT_READY`; measurement granularity differs. |
| Depth alignment | 0 eligible room-level pairs | `UNAVAILABLE` | `NOT_READY`. |
| Bounding-box occupancy | `UNAVAILABLE`; no complete exact positive footprint trace | 0.5792454589543597230802131883 | `NOT_READY`; one negative cannot set a floor. |
| Reflex corners | `UNAVAILABLE` for coarse positive envelopes | 16 | Informational only; not a standalone gate. |
| Notches / appendages | `UNAVAILABLE` pending exact outline and purpose evidence | `UNAVAILABLE` | `NOT_READY`. |

Do not remove any Owner-PASS reference to improve a range. Do not reject an
irregular-site or intentional-L solution by a rectangle-only rule.

## P1 entry split proposal

The positive set and Owner-approved common patterns are sufficient to propose
a structural implementation entry for `group -> band -> zone`, process-core
versus support-branch separation, semantic grouping, deterministic outline
classes, and axis-family preference. Therefore:

```ini
P1A_STRUCTURAL_IMPLEMENTATION_ENTRY_READY=true
P1B_NUMERIC_THRESHOLD_IMPLEMENTATION_ENTRY_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
P1_RUNTIME_IMPLEMENTATION_AUTHORIZED=false
```

This is an entry-readiness proposal only. It does not authorize runtime work.
Numeric gates remain blocked on Owner review of these overlays, comparable
room-level positive geometry, exact positive outline traces, and Owner-labeled
appendage purpose evidence. P1 requires a separate explicit authorization.

## Scope and reproducibility

This P0C change adds only normalized reference evidence, its offline metric and
classifier helper, tests, the overlay generation utility, the review pack, and
P0/ADR/version-plan documentation. It does not change `backend/src`, P2/P2C/P2D,
Tool 7, MCP contracts, SVG runtime, database, frontend, production, or release
state. The overlay tool accepts source paths as invocation arguments so local
Owner file paths are not written into the repository.
