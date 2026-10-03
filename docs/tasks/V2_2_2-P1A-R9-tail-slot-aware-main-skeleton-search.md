# V2.2.2 P1A-R9: Tail-slot-aware main-skeleton search

TASK_ID=V2_2_2_P1A_R9_TAIL_SLOT_AWARE_MAIN_SKELETON_SEARCH_R1
BASE_HEAD_SHA=c66a68091981ed0329b4e1b694721bbb3b6e0cdb
RESULT=PARTIAL
PRODUCTION_PLACEMENT_NODE_BUDGET=120
PRODUCTION_BUDGET_CHANGED=false
OWNER_XINZHAO_P1A_R9_VISUAL_REVIEW=PENDING

## Decision and scope

R9 adds a necessary-feasibility preflight for only `packaging_material_storage`.
The preflight asks whether at least one rectangle with the complete current
authoritative dimension variants can fit inside the exact effective boundary,
clear of the existing no-build/obstacle polygons and the seven already-frozen
main-process rectangles. It does not require packaging storage to touch
sorting, does not add a process-flow relationship, and does not change P2C
placement predicates, access, truck, footprint, P2D, or Tool 7's public
contract.

The proof result is an internal, versioned
`tail-zone-slot-feasibility@1.0.0` fact. A proven no-slot result is a
tail-admission prune, not an engineering rule or quality score. If geometry is
not orthogonal or the complete dimension authority is unavailable, the result
is `UNAVAILABLE`; the skeleton is not rejected and proceeds to ordinary tail
search. The preflight does not consume a placement node.

## Exact finite-event completeness

The placement authority represents candidate origins on an integer-millimetre
lattice. For an axis-aligned candidate rectangle and orthogonal simple site,
obstacle, and fixed-zone polygons, each placement predicate can change only
when a candidate edge aligns with a polygon edge. On either axis, those events
are polygon vertex coordinates and those coordinates minus the candidate
rectangle extent. Between consecutive event coordinates the inside, closed
obstacle-intersection, and fixed-rectangle-overlap predicates are constant.
For every non-empty integer-lattice cell, the event itself or its immediately
adjacent integer-millimetre origin represents that cell. Enumerating the
Cartesian product of these finite event coordinates therefore finds a witness
whenever one exists in this geometry class.

Every representative is checked by the existing exact polygon predicates;
bounding boxes are not used as a substitute. The algorithm checks all
authoritative allowed orientations and records a witness or rejection counts.
It does not sweep the full millimetre grid. Before enumerating, it verifies
that every relevant polygon is orthogonal and the full fixed-rectangle
dimension variant set is supplied. Otherwise it returns
`EXACT_EVENT_COMPLETENESS_UNAVAILABLE`, which is never a hard prune.

This completeness argument is limited to the stated integer-mm, orthogonal,
axis-aligned case. It is not a global placement infeasibility proof and does
not prove that any entire site/layout is infeasible.

## Lifecycle and quota semantics

The lifecycle is now:

`SKELETON_CONSTRUCTED → CANONICALIZED → TAIL_SLOT_PREFLIGHT → TAIL_SEARCH → P2D`

An exact no-slot skeleton records
`FIRST_FAILURE_STAGE=TAIL_SLOT_PREFLIGHT` and
`FIRST_FAILURE_REASON=AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT`. It is
cached by exact main-skeleton geometry hash, is not tail-evaluated again if
rediscovered, and does not increment the tail-admissible skeleton completion
quota. The constructor continues its deterministic search after that geometry
is rejected. Only a preflight pass or an unavailable proof is yielded to tail
search.

## Canonical Xinzhao run

The unchanged fixture bytes were rechecked at SHA-256
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e` (9,552
bytes). Two real, unmocked Tool 7 calls produced identical selector evidence,
layout JSON, canonical result hash, SVG bytes, and SVG hash.

* `956e85ad…24dfcc` was discovered in the Hub lane and canonically classified
  as `STRAIGHT_LINEAR_BAND`. Its exact preflight checked both orientations,
  found no slot, recorded 3,672 no-build rejections and 4,098 fixed-main-zone
  overlaps, and started no tail search.
* `55589c20…ee9b953` passed preflight. The event search produced a geometric
  slot witness at `(60.960 m, 0 m)`, with the authoritative 17.3 m × 14.5 m
  room rotated 90 degrees. The full layout's own tail search then produced two
  complete P2C candidates; both reached P2D and passed.
* Across the three topology lanes, the run visited 98 of the unchanged 120
  placement nodes; 22 were unused. The run discovered two distinct main
  skeleton geometries, of which one was rejected by preflight, one was
  tail-admissible, and one distinct skeleton reached/full-passed P2D.
  The two passing P2D candidates are tail variants of the same skeleton, not
  two distinct main-process layouts. No distinct runner-up exists.
* The selected skeleton remains `55589…ee9b953`; the selected main-process
  geometry did not change. The SVG SHA-256 remains the R8 value
  `sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`.
  No new visual pack was generated because there is no new visual information.
* The selected Tool 7 result remains hard-valid: 12 zones, 12/12 access,
  validated truck route, and a non-empty derived building footprint.

The representative existing P4 Tool 7 full-chain fixture also remained
hard-valid and had a legal packaging slot. This is a positive regression
check, not a claim that every historical fixture was replayed.

Machine-readable replay and preflight details are in
`docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r9_slot_preflight_evidence.json`.

## Outcome and next boundary

The required early rejection is correct, but the bounded 120-node search still
found only one distinct tail-admissible/full-pass main skeleton. R9 therefore
remains `PARTIAL`; preflight correctness must not be presented as P1A
acceptance. The next decision should address why the current bounded
constructive search produces no additional admissible geometry, not increase
the global budget or weaken engineering authority.

P1B thresholds remain inactive. Weighted scores, fixture-specific runtime
branches, Golden coordinate templates, manual SVG edits, production changes,
and deployment remain unauthorized and unchanged. PR #302 must remain Draft.
