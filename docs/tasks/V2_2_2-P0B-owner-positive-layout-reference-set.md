# V2.2.2 P0B — Owner Positive Layout Reference Set

## Governance snapshot

```ini
TASK_ID=V2_2_2_P0B_OWNER_POSITIVE_LAYOUT_REFERENCE_SET_R1
TARGET_VERSION=v2.2.2
ACTIVE_GOVERNANCE_LANE=V2.2.2_P0B
PR_NUMBER=301
BASE_MAIN_SHA=3b90126fc4215460b93d6fd72b619dc507602669
PREVIOUS_P0A_HEAD_SHA=7dc2db96f01ae3d835c9a0540a3f226b4aa31aad
EVIDENCE_AND_RULE_DRAFT_ONLY=true
ORIGINAL_GOLDEN_SOURCE_AVAILABLE=true
GOLDEN_REFERENCE_COUNT=5
OWNER_POSITIVE_REFERENCE_COUNT=5
OWNER_NEGATIVE_REFERENCE_COUNT=1
PRIMARY_POSITIVE_REFERENCE=GD-005_PANLONG
GOLDEN_ENGINEERING_AUTHORITY=false
GOLDEN_RUNTIME_TRAINING_DATA=false
NUMERIC_THRESHOLD_CALIBRATION_READY=false
P1_ENTRY_CANONICAL_FIXTURE_READY=true
P1_ENTRY_OWNER_POSITIVE_REFERENCE_READY=true
P1_ENTRY_LAYOUT_RULES_READY=true
P1_ENTRY_CALIBRATION_MATRIX_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
RUNTIME_CHANGED=false
LAYOUT_RUNTIME_CHANGED=false
MCP_CONTRACT_CHANGED=false
PRODUCTION_CHANGED=false
P1_RUNTIME_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## Evidence handling

The five Owner-supplied original PDFs were readable and their raw bytes were
hashed on 2026-09-24. The files remain external attachments and are not copied
into the repository; this avoids adding multi-megabyte project drawings while
retaining source identity in the matrix. Full filenames and SHA-256 values are
recorded in [`owner-layout-reference-matrix.json`](evidence/v2_2_2_p0b/owner-layout-reference-matrix.json).

Review was qualitative and full-sheet visual. The drawings contain annotations,
dimensions, and project notes, but none of those values were transcribed into
this contract or treated as instructions. No OCR-derived dimension, coordinate,
area, aisle width, or project-specific parameter is used. The matrix explicitly
marks route facts and geometric metrics unavailable when a raster/vector sheet
cannot establish them. P0A's structured Xinzhao facts retain their existing
provenance and are quoted only as historical negative-sample evidence.

```ini
GD001_SOURCE_AVAILABLE=true
GD002_SOURCE_AVAILABLE=true
GD003_SOURCE_AVAILABLE=true
GD004_SOURCE_AVAILABLE=true
GD005_SOURCE_AVAILABLE=true
ORIGINAL_PDF_BYTES_COMMITTED=false
```

## Reference-by-reference findings

The detailed machine-readable rows include all required fields and 3–6
evidence-bounded reasons per accepted reference. The recurring visual pattern
is not one fixed footprint. It is a legible primary production organization,
grouped cold/storage blocks, repeated major axes where feasible, and support
functions that read as support rather than a competing main line.

### GD-001 — Zhu Yuan

The drawing's dominant elongated building organization is arranged in
continuous long bands. Repeated cold/storage modules form aligned runs, and
smaller peripheral/end functions remain visually subordinate. Its scale and
elongated outline are not a template for a smaller project. The image does not
provide an authoritative route trace, so backtrack and turn counts remain
unavailable.

### GD-002 — Xiaoxiang

This high-density plan remains legible through a distinct processing hub with
parallel production lines and grouped storage blocks around it. The organization
is branched rather than a single universal line, which is evidence that a
quality contract must preserve role order without forcing one compass direction
or one exact shape. Personnel/access separation and route turns are not
measurable from the sheet alone.

### GD-003 — Mouding

The site is visibly irregular, while the principal production core remains
predominantly orthogonal and organized. Site shape does not force every room to
follow the property edge. This is the key counterexample to a naive
rectangle-only compactness rule. Exact flow and depth metrics remain
unavailable from the drawing.

### GD-004 — Shuanglongying

The single-building plan shows a repeated grid family across long production
and storage bands. Cold/storage banks and processing lines are grouped within
one coherent envelope; support areas are secondary. The axes are a pattern,
not approved project coordinates or bay dimensions.

### GD-005 — Panlong, primary positive reference

The signed/fused reference presents a coherent building body with repeated
orthogonal room bands. Cold-stage and finished-storage groups are visually
organized around the main processing core; packaging and secondary-product
functions appear as side/support groups rather than new main-product stages.
The plan's grid rhythm and limited repeated band forms explain much of its
orderly appearance. The sheet does not prove portal-to-portal route direction,
personnel separation, or zero route turns; these require structured project
authority.

#### Panlong organization summary

1. The main processing composition is visually directional and continuous,
   moving between grouped process/cold-storage bands; exact receiving-to-shipping
   route direction is not claimed without route facts.
2. Sorting/packing reads as a connecting process core rather than an arbitrary
   room among peers.
3. Primary/secondary cold and finished-storage spaces form identifiable
   aligned groups around that core.
4. Packaging and secondary-product spaces read as related side groups, not as
   main product stages. Their actual path geometry is not inferred.
5. Major boundaries share a repeated orthogonal grid family; repeated band
   depths are visible, but no depth-alignment rate is calculated.
6. The principal building mass has a consistent envelope and wall rhythm,
   avoiding the appearance of unrelated blocks. Peripheral support remains
   subordinate.
7. Personnel/administrative rooms appear peripheral or subordinate where
   identifiable; the drawing alone cannot validate people-versus-logistics
   route separation.
8. Algorithm candidates: semantic bands, process-core ordering, cold-room
   grouping, shared axis families, and side-branch distinction. Owner judgment
   remains necessary for site exceptions, receiving-side mapping, and any
   ambiguous separation or branch conflict.

## Positive versus Xinzhao negative comparison

The 13-dimension comparison is in the evidence JSON. It distinguishes three
evidence types: visual organization patterns from the five accepted PDFs,
Owner's qualitative Xinzhao rejection, and exact metrics available from the
P0A structured replay. For example, P0A measured Xinzhao major-zone grid
alignment at `0.4`, footprint bounding-rectangle occupancy at
`0.5792454589543597230802131883`, and 16 reflex corners on one connected
footprint polygon. Those values describe that sample; they are not thresholds.
Backtrack, turn, depth, side-branch crossing, and personnel separation remain
unavailable for the Xinzhao v2.2.1 result.

The main contrast is organizational: positive references use a recognizable
production band or core, grouped cold/storage blocks, and repeated axes; the
Owner-described negative reads as independent tile-like blocks, has weak
process direction, has auxiliary functions attached around sorting in several
directions, and has a less legible receiving/shipping relationship. The
structured record is not sufficient to turn every qualitative difference into
a numeric score.

## Common rules supported across the five positive references

Five qualitative candidates are recorded in the matrix. None is promoted to a
hard geometric rule from PDFs alone:

| Rule | Type | Candidate |
| --- | --- | --- |
| P0B-ORG-001 | `QUALITY_PRIORITY` | Keep the production organization legible as a continuous band or central core, rather than treating every room as a peer rectangle. |
| P0B-ORG-002 | `QUALITY_PRIORITY` | Group repeated cold/storage rooms into coherent aligned banks or bands. |
| P0B-ORG-003 | `SOFT_PREFERENCE` | Prefer a limited orthogonal axis family for major boundaries where fixed geometry and site constraints permit. |
| P0B-ORG-004 | `QUALITY_PRIORITY` | Preserve a clear primary-core versus support/branch distinction; project-specific branch topology may differ. |
| P0B-ORG-005 | `SOFT_PREFERENCE` | Prefer one coherent principal building composition while allowing purposeful L-shaped and irregular-site solutions. |

There are no `HARD_CANDIDATE` rules in this evidence set: images cannot
establish authoritative flow direction, portal paths, or a universal hard
geometry condition. Those rules must come from the P0 role/process contract and
future validated route facts. `GOLDEN_ENGINEERING_AUTHORITY=false` and
`GOLDEN_RUNTIME_TRAINING_DATA=false` remain frozen.

## P1 layout implementation rules — draft only

The draft sequence is machine-readable in the matrix. At a high level, future
implementation should:

1. Generate candidate compositions by functional group and process band before
   resolving each zone.
2. Bind semantic process roles and receiving direction explicitly; never
   equate truck entrance with raw receiving.
3. Evaluate order/backtrack and turns from authoritative ordered routes, not
   centroids or image appearance.
4. Rank axis/depth alignment and grouped cold-room organization only after all
   engineering hard constraints and P2D full validation pass.
5. Preserve packaging straight-only authority and model secondary/frozen
   movements as side branches whose crossing facts come from routes.
6. Keep office/changing outside the product-process chain; evaluate
   personnel/logistics separation independently.
7. Use deterministic outline classes that distinguish a simple L and
   site-constrained shape from a narrow neck or unsupported appendage.
8. Rank with deterministic lexicographic atomic facts; explain the first
   decisive reason the selected candidate beats the next full-pass candidate.
9. Keep Owner review for irregular-site exceptions, omitted process stages,
   unresolved receiving-side authority, and ambiguous crossings.

This is a proposal for a later implementation task. It does not modify the
P0/P2 runtime or grant implementation authorization.

## Calibration and entry decision

The P0A canonical Xinzhao input remains verified and replayed against v2.2.1.
The five Owner-positive drawings now make the qualitative reference set ready.
However, the PDFs do not provide structured positive zone/route geometry, and
the Xinzhao result has no route-aggregated backtrack/turn or depth facts. Thus
the P1 calibration matrix is still incomplete for threshold selection.

```ini
OWNER_POSITIVE_COMMON_RULE_COUNT=5
NUMERIC_THRESHOLD_CALIBRATION_READY=false
DEPTH_ALIGNMENT_THRESHOLD_STATUS=NOT_READY
PROPOSED_DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_READY
COMPACTNESS_CLASSIFIER_STATUS=NOT_READY
PROPOSED_BOUNDING_RECTANGLE_OCCUPANCY_FLOOR=NOT_READY
PROPOSED_MAX_EXTERIOR_NOTCH_COUNT=NOT_READY
PROPOSED_MAX_ISOLATED_APPENDAGE_COUNT=NOT_READY
P1_ENTRY_CANONICAL_FIXTURE_READY=true
P1_ENTRY_OWNER_POSITIVE_REFERENCE_READY=true
P1_ENTRY_LAYOUT_RULES_READY=true
P1_ENTRY_CALIBRATION_MATRIX_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
```

Remaining blockers: structured Owner-positive layout fixtures suitable for
metric calculation; stable depth-pair eligibility; and versioned,
evidence-tested notch and isolated-appendage classifiers. This P0B task does
not set numerical thresholds or authorize runtime implementation.
